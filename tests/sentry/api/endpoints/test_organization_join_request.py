from functools import cached_property
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

import orjson
from django.core import mail

from sentry.analytics.events.join_request_created import JoinRequestCreatedEvent
from sentry.models.authprovider import AuthProvider
from sentry.models.options.organization_option import OrganizationOption
from sentry.models.organizationmember import InviteStatus, OrganizationMember
from sentry.silo.base import SiloMode
from sentry.testutils.cases import APITestCase, SlackActivityNotificationTest
from sentry.testutils.helpers.analytics import assert_last_analytics_event
from sentry.testutils.helpers.features import with_feature
from sentry.testutils.hybrid_cloud import HybridCloudTestMixin
from sentry.testutils.outbox import outbox_runner
from sentry.testutils.silo import assume_test_silo_mode


class OrganizationJoinRequestTest(APITestCase, SlackActivityNotificationTest, HybridCloudTestMixin):
    endpoint = "sentry-api-0-organization-join-request"
    method = "post"

    def setUp(self) -> None:
        super(APITestCase, self).setUp()
        super(SlackActivityNotificationTest, self).setUp()
        self.email = "test@example.com"

    @cached_property
    def owner(self):
        return OrganizationMember.objects.get(user_id=self.user.id, organization=self.organization)

    def test_invalid_org_slug(self) -> None:
        self.get_error_response("invalid-slug", email=self.email, status_code=404)

    def test_email_required(self) -> None:
        response = self.get_error_response(self.organization.slug, status_code=400)
        assert response.data["email"][0] == "This field is required."

    def test_invalid_email(self) -> None:
        response = self.get_error_response(
            self.organization.slug, email="invalid-email", status_code=400
        )
        assert response.data["email"][0] == "Enter a valid email address."

    def test_organization_setting_disabled(self) -> None:
        OrganizationOption.objects.create(
            organization_id=self.organization.id, key="sentry:join_requests", value=False
        )

        self.get_error_response(self.organization.slug, status_code=403)

    @patch(
        "sentry.api.endpoints.organization_member.requests.join.ratelimiter.backend.is_limited",
        return_value=True,
    )
    def test_ratelimit(self, is_limited: MagicMock) -> None:
        response = self.get_error_response(
            self.organization.slug, email=self.email, status_code=429
        )
        assert response.data["detail"] == "Rate limit exceeded."

    @patch("sentry.api.endpoints.organization_member.requests.join.logger")
    def test_org_sso_enabled(self, mock_log: MagicMock) -> None:
        with assume_test_silo_mode(SiloMode.CONTROL):
            AuthProvider.objects.create(organization_id=self.organization.id, provider="google")

        self.get_error_response(self.organization.slug, email=self.email, status_code=403)

        member = OrganizationMember.objects.get(organization=self.organization)
        assert member == self.owner
        assert not mock_log.info.called

    @patch("sentry.api.endpoints.organization_member.requests.join.logger")
    def test_user_already_exists(self, mock_log: MagicMock) -> None:
        assert OrganizationMember.objects.filter(organization=self.organization).count() == 1
        self.get_success_response(self.organization.slug, email=self.user.email, status_code=204)

        member = OrganizationMember.objects.get(organization=self.organization)
        assert member == self.owner
        assert not mock_log.info.called

    @patch("sentry.api.endpoints.organization_member.requests.join.logger")
    def test_pending_member_already_exists(self, mock_log: MagicMock) -> None:
        pending_email = "pending@example.com"
        original_pending = self.create_member(
            email=pending_email, organization=self.organization, role="admin"
        )

        self.get_success_response(self.organization.slug, email=pending_email, status_code=204)

        members = OrganizationMember.objects.filter(organization=self.organization)
        assert members.count() == 2
        pending = members.get(email=pending_email)
        assert pending == original_pending
        assert not mock_log.info.called

    @patch("sentry.analytics.record")
    @patch("sentry.api.endpoints.organization_member.requests.join.logger")
    def test_already_requested_to_join(self, mock_log: MagicMock, mock_record: MagicMock) -> None:
        join_request_email = "join-request@example.com"
        original_join_request = self.create_member(
            email=join_request_email,
            organization=self.organization,
            role="member",
            invite_status=InviteStatus.REQUESTED_TO_JOIN.value,
        )

        self.get_success_response(self.organization.slug, email=join_request_email, status_code=204)

        members = OrganizationMember.objects.filter(organization=self.organization)
        assert members.count() == 2
        join_request = members.get(email=join_request_email)
        assert join_request == original_join_request
        assert not mock_log.info.called

        assert not any(c[0][0] == "join_request.created" for c in mock_record.call_args_list)

    @patch("sentry.analytics.record")
    def test_request_to_join_email(self, mock_record: MagicMock) -> None:
        self.organization = self.create_organization()

        user1 = self.create_user(email="manager@localhost")
        user2 = self.create_user(email="owner@localhost")
        user3 = self.create_user(email="member@localhost")

        self.create_member(organization=self.organization, user=user1, role="manager")
        self.create_member(organization=self.organization, user=user2, role="owner")
        self.create_member(organization=self.organization, user=user3, role="member")

        with self.tasks(), outbox_runner():
            self.get_success_response(self.organization.slug, email=self.email, status_code=204)

        members = OrganizationMember.objects.filter(organization=self.organization)
        join_request = members.get(email=self.email)
        assert join_request.user_id is None
        assert join_request.role == "member"
        assert not join_request.invite_approved

        assert_last_analytics_event(
            mock_record,
            JoinRequestCreatedEvent(
                member_id=join_request.id,
                organization_id=self.organization.id,
                referrer=None,
            ),
        )

        self.assert_org_member_mapping(org_member=join_request)

        users_able_to_approve_requests = {user1, user2}
        expected_subject = f"Access request to {self.organization.name}"
        assert len(mail.outbox) == len(users_able_to_approve_requests)
        for i in range(len(mail.outbox)):
            assert mail.outbox[i].to in ([user.email] for user in users_able_to_approve_requests)
            assert mail.outbox[i].subject == expected_subject

    @with_feature("system:multi-region")
    def test_request_to_join_email_customer_domains(self) -> None:
        manager = self.create_user(email="manager@localhost")
        self.create_member(organization=self.organization, user=manager, role="manager")

        with self.tasks():
            self.get_success_response(self.organization.slug, email=self.email, status_code=204)

        with outbox_runner():
            members = OrganizationMember.objects.filter(organization=self.organization)
        join_request = members.get(email=self.email)
        assert join_request.user_id is None
        assert join_request.role == "member"
        assert not join_request.invite_approved

        self.assert_org_member_mapping(org_member=join_request)

        assert mail.outbox[0].subject == f"Access request to {self.organization.name}"
        assert self.organization.absolute_url("/settings/members/") in mail.outbox[0].body

    def test_request_to_join_slack(self) -> None:
        with self.tasks():
            self.get_success_response(self.organization.slug, email=self.email, status_code=204)

        blocks = orjson.loads(self.mock_post.call_args.kwargs["blocks"])
        fallback_text = self.mock_post.call_args.kwargs["text"]

        assert fallback_text == f"{self.email} is requesting to join {self.organization.name}"
        query_params = parse_qs(urlparse(blocks[1]["elements"][0]["text"]).query)
        notification_uuid = query_params["notification_uuid"][0]
        notification_uuid = notification_uuid.split("|")[
            0
        ]  # remove method of hyperlinking in slack
        assert blocks[2]["type"] == "actions"
        assert blocks[2]["elements"] == [
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "Approve"},
                "action_id": "approve_request",
                "value": "approve_member",
            },
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "Reject"},
                "action_id": "reject_request",
                "value": "reject_member",
            },
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "See Members & Requests"},
                "url": f"http://testserver/settings/{self.organization.slug}/members/?referrer=join_request-slack-user&notification_uuid={notification_uuid}",
                "value": "link_clicked",
            },
        ]
        context_params = orjson.loads(
            orjson.loads(self.mock_post.call_args.kwargs["blocks"])[0]["block_id"]
        )

        with outbox_runner():
            member = OrganizationMember.objects.get(email=self.email)
        assert context_params == {
            "member_id": member.id,
            "member_email": self.email,
        }

        self.assert_org_member_mapping(org_member=member)
