from __future__ import annotations

from unittest.mock import MagicMock, patch
from urllib.parse import urlencode

import responses
from django.db import router, transaction
from django.http import HttpRequest, HttpResponse
from django.test import RequestFactory
from django.urls import reverse
from rest_framework import status

from sentry.hybridcloud.models.outbox import outbox_context
from sentry.integrations.middleware.hybrid_cloud.parser import create_async_request_payload
from sentry.integrations.models.organization_integration import OrganizationIntegration
from sentry.integrations.slack.message_builder.routing import encode_action_id
from sentry.integrations.slack.message_builder.types import SlackAction
from sentry.integrations.slack.utils.auth import _encode_data
from sentry.integrations.slack.views import SALT
from sentry.middleware.integrations.parsers.slack import SlackRequestParser
from sentry.testutils.cases import TestCase
from sentry.testutils.helpers.options import override_options
from sentry.testutils.outbox import assert_no_webhook_payloads
from sentry.testutils.silo import assume_test_silo_mode_of, control_silo_test, create_test_regions
from sentry.utils import json
from sentry.utils.signing import sign


@control_silo_test(regions=create_test_regions("us"))
class SlackRequestParserTest(TestCase):
    factory = RequestFactory()
    timestamp = "123123123"

    def setUp(self) -> None:
        self.user = self.create_user()
        self.organization = self.create_organization(owner=self.user)
        self.integration = self.create_integration(
            organization=self.organization, external_id="TXXXXXXX1", provider="slack"
        )

    def get_response(self, request: HttpRequest) -> HttpResponse:
        return HttpResponse(status=200, content="passthrough")

    @responses.activate
    @patch(
        "slack_sdk.signature.SignatureVerifier.is_valid",
        return_value=True,
    )
    def test_webhook(self, mock_verify: MagicMock) -> None:
        # Retrieve the correct integration
        data = urlencode({"team_id": self.integration.external_id}).encode("utf-8")
        signature = _encode_data(secret="slack-signing-secret", data=data, timestamp=self.timestamp)
        request = self.factory.post(
            path=reverse("sentry-integration-slack-commands"),
            data=data,
            content_type="application/x-www-form-urlencoded",
            HTTP_X_SLACK_SIGNATURE=signature,
            HTTP_X_SLACK_REQUEST_TIMESTAMP=self.timestamp,
        )
        parser = SlackRequestParser(request, self.get_response)
        integration = parser.get_integration_from_request()
        assert integration == self.integration

        # Returns response from region
        responses.add(
            responses.POST,
            "http://us.testserver/extensions/slack/commands/",
            status=status.HTTP_201_CREATED,
            body=b"region_response",
        )
        response = parser.get_response()
        assert isinstance(response, HttpResponse)
        assert response.status_code == status.HTTP_201_CREATED
        assert response.content == b"region_response"
        assert len(responses.calls) == 1
        assert_no_webhook_payloads()

        # ...even if it returns an error
        responses.add(
            responses.POST,
            "http://us.testserver/extensions/slack/commands/",
            status=401,
            body=b"error_response",
        )
        response = parser.get_response()
        assert isinstance(response, HttpResponse)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.content == b"error_response"
        assert len(responses.calls) == 2
        assert_no_webhook_payloads()

    @responses.activate
    def test_django_view(self) -> None:
        # Retrieve the correct integration
        path = reverse(
            "sentry-integration-slack-link-identity",
            kwargs={"signed_params": sign(salt=SALT, integration_id=self.integration.id)},
        )
        request = self.factory.post(path)
        parser = SlackRequestParser(request, self.get_response)
        parser_integration = parser.get_integration_from_request()
        if not parser_integration:
            raise AssertionError("Parser could not identify an integration")
        assert parser_integration.id == self.integration.id

        # Passes through to control silo
        response = parser.get_response()
        assert isinstance(response, HttpResponse)
        assert response.status_code == status.HTTP_200_OK
        assert response.content == b"passthrough"
        assert len(responses.calls) == 0
        assert_no_webhook_payloads()

    @patch(
        "sentry.integrations.slack.requests.base.SlackRequest._check_signing_secret",
        return_value=True,
    )
    @patch("sentry.middleware.integrations.parsers.slack.convert_to_async_slack_response")
    def test_triggers_async_response(
        self, mock_slack_task: MagicMock, mock_signing_secret: MagicMock
    ) -> None:
        response_url = "https://hooks.slack.com/commands/TXXXXXXX1/1234567890123/something"
        data = {
            "payload": json.dumps(
                {"team_id": self.integration.external_id, "response_url": response_url}
            )
        }
        request = self.factory.post(reverse("sentry-integration-slack-action"), data=data)
        parser = SlackRequestParser(request, self.get_response)
        response = parser.get_response()
        mock_slack_task.apply_async.assert_called_once_with(
            kwargs={
                "region_names": ["us"],
                "payload": create_async_request_payload(request),
                "response_url": response_url,
            }
        )
        assert response.status_code == status.HTTP_200_OK

    @patch(
        "sentry.integrations.slack.requests.base.SlackRequest._check_signing_secret",
        return_value=True,
    )
    @patch("sentry.middleware.integrations.parsers.slack.convert_to_async_slack_response")
    def test_skips_async_response_if_org_integration_missing(
        self, mock_slack_task, mock_signing_secret
    ):
        response_url = "https://hooks.slack.com/commands/TXXXXXXX1/1234567890123/something"
        data = {
            "payload": json.dumps(
                {"team_id": self.integration.external_id, "response_url": response_url}
            )
        }
        with (
            assume_test_silo_mode_of(OrganizationIntegration),
            outbox_context(transaction.atomic(using=router.db_for_write(OrganizationIntegration))),
        ):
            OrganizationIntegration.objects.filter(organization_id=self.organization.id).delete()
        request = self.factory.post(reverse("sentry-integration-slack-action"), data=data)
        parser = SlackRequestParser(request, self.get_response)
        response = parser.get_response()
        assert response.status_code == status.HTTP_202_ACCEPTED
        assert mock_slack_task.apply_async.call_count == 0

    def test_async_request_payload(self) -> None:
        data = {
            "payload": json.dumps(
                {
                    "team_id": self.integration.external_id,
                    "response_url": "https://hooks.slack.com/commands/TXXXXX1/12345678/something",
                }
            )
        }
        request = self.factory.post(reverse("sentry-integration-slack-action"), data=data)
        result = create_async_request_payload(request)

        assert "method" in result
        assert result["method"] == request.method
        assert "path" in result
        assert result["path"] == request.get_full_path()
        assert "uri" in result
        assert result["uri"] == request.build_absolute_uri()
        assert "headers" in result
        assert isinstance(result["headers"], dict)
        assert "body" in result
        assert result["body"] == request.body.decode("utf8")

    @override_options({"hybrid_cloud.integration_region_targeting_rate": 1.0})
    def test_targeting_all_orgs(self) -> None:
        # Install the integration on two organizations
        other_organization = self.create_organization()
        self.integration.add_organization(other_organization)

        # Case 1: Without passing an organization, we expect to filter to both.
        for cmd in ["link team", "unlink team"]:
            data = urlencode(
                {
                    "text": cmd,
                    "team_id": self.integration.external_id,
                }
            ).encode("utf-8")
            request = self.factory.post(
                reverse("sentry-integration-slack-commands"),
                data=data,
                content_type="application/x-www-form-urlencoded",
            )
            parser = SlackRequestParser(request, self.get_response)
            organizations = parser.get_organizations_from_integration(self.integration)
            organization_ids = {org.id for org in organizations}
            assert len(organization_ids) == 2
            assert self.organization.id in organization_ids
            assert other_organization.id in organization_ids

    @override_options({"hybrid_cloud.integration_region_targeting_rate": 1.0})
    def test_targeting_specific_org(self) -> None:
        # Install the integration on two organizations
        other_organization = self.create_organization()
        self.integration.add_organization(other_organization)

        # When the organization slug is provided, filter to just that one.
        for cmd in ["link team", "unlink team"]:
            data = urlencode(
                {
                    "text": f"{cmd} {other_organization.slug}",
                    "team_id": self.integration.external_id,
                }
            ).encode("utf-8")
            request = self.factory.post(
                reverse("sentry-integration-slack-commands"),
                data=data,
                content_type="application/x-www-form-urlencoded",
            )
            parser = SlackRequestParser(request, self.get_response)
            organizations = parser.get_organizations_from_integration(self.integration)

            assert len(organizations) == 1
            assert organizations[0].id == other_organization.id

    @override_options({"hybrid_cloud.integration_region_targeting_rate": 1.0})
    def test_targeting_irrelevant_org(self) -> None:
        # Install the integration on two organizations
        other_organization = self.create_organization()
        self.integration.add_organization(other_organization)
        # And add another, maybe the user belongs to it, maybe not
        irrelevant_organization = self.create_organization()

        # Case 3: If the organization slug is irrelevant, ignore it and return all orgs
        for cmd in ["link team", "unlink team"]:
            data = urlencode(
                {
                    "text": f"{cmd} {irrelevant_organization.slug}",
                    "team_id": self.integration.external_id,
                }
            ).encode("utf-8")
            request = self.factory.post(
                reverse("sentry-integration-slack-commands"),
                data=data,
                content_type="application/x-www-form-urlencoded",
            )
            parser = SlackRequestParser(request, self.get_response)
            organizations = parser.get_organizations_from_integration(self.integration)
            organization_ids = {org.id for org in organizations}
            assert len(organization_ids) == 2
            assert irrelevant_organization.id not in organization_ids

    @override_options({"hybrid_cloud.integration_region_targeting_rate": 1.0})
    def test_targeting_issue_actions(self) -> None:
        # Install the integration on two organizations
        other_organization = self.create_organization()
        self.integration.add_organization(other_organization)

        # Case 1:With the default actions (non-encoded), we shouldn't filter the organization
        data = urlencode(
            {
                "payload": json.dumps(
                    {
                        "actions": [{"action_id": SlackAction.RESOLVE_DIALOG}],
                        "team_id": self.integration.external_id,
                    }
                ),
            }
        ).encode("utf-8")
        request = self.factory.post(
            reverse("sentry-integration-slack-action"),
            data=data,
            content_type="application/x-www-form-urlencoded",
        )
        parser = SlackRequestParser(request, self.get_response)
        organizations = parser.get_organizations_from_integration(self.integration)
        organization_ids = {org.id for org in organizations}
        assert len(organization_ids) == 2
        assert self.organization.id in organization_ids
        assert other_organization.id in organization_ids

        # Case 2: With the encoded action, we should filter to a single organization
        project = self.create_project(organization=other_organization)
        encoded_action = encode_action_id(
            action=SlackAction.RESOLVE_DIALOG,
            organization_id=other_organization.id,
            project_id=project.id,
        )
        data = urlencode(
            {
                "payload": json.dumps(
                    {
                        "actions": [{"action_id": encoded_action}],
                        "team_id": self.integration.external_id,
                    }
                ),
            }
        ).encode("utf-8")
        request = self.factory.post(
            reverse("sentry-integration-slack-action"),
            data=data,
            content_type="application/x-www-form-urlencoded",
        )
        parser = SlackRequestParser(request, self.get_response)
        organizations = parser.get_organizations_from_integration(self.integration)
        organization_ids = {org.id for org in organizations}
        assert len(organization_ids) == 1
        assert other_organization.id in organization_ids

        # Case 3: If we see an irrelevant organization, we should ignore it
        irrelevant_organization = self.create_organization()
        project = self.create_project(organization=irrelevant_organization)
        encoded_action = encode_action_id(
            action=SlackAction.RESOLVE_DIALOG,
            organization_id=irrelevant_organization.id,
            project_id=project.id,
        )
        data = urlencode(
            {
                "payload": json.dumps(
                    {
                        "actions": [{"action_id": encoded_action}],
                        "team_id": self.integration.external_id,
                    }
                ),
            }
        ).encode("utf-8")
        request = self.factory.post(
            reverse("sentry-integration-slack-action"),
            data=data,
            content_type="application/x-www-form-urlencoded",
        )
        parser = SlackRequestParser(request, self.get_response)
        organizations = parser.get_organizations_from_integration(self.integration)
        organization_ids = {org.id for org in organizations}
        assert len(organization_ids) == 2
        assert self.organization.id in organization_ids
        assert other_organization.id in organization_ids
