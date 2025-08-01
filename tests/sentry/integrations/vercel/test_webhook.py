import hashlib
import hmac

import orjson
import responses
from rest_framework.response import Response

from fixtures.vercel import (
    DEPLOYMENT_WEBHOOK_NO_COMMITS,
    EXAMPLE_DEPLOYMENT_WEBHOOK_RESPONSE,
    MINIMAL_WEBHOOK,
    SECRET,
    SIGNATURE,
)
from sentry import VERSION
from sentry.sentry_apps.models.sentry_app_installation_token import SentryAppInstallationToken
from sentry.silo.base import SiloMode
from sentry.testutils.cases import APITestCase
from sentry.testutils.helpers import override_options
from sentry.testutils.silo import assume_test_silo_mode, control_silo_test
from sentry.utils.http import absolute_uri


@control_silo_test
class SignatureVercelTest(APITestCase):
    webhook_url = "/extensions/vercel/webhook/"

    def test_get(self) -> None:
        response = self.client.get(self.webhook_url)
        assert response.status_code == 405

    def test_invalid_signature(self) -> None:
        with override_options({"vercel.client-secret": SECRET}):
            response = self.client.post(
                path=self.webhook_url,
                data=EXAMPLE_DEPLOYMENT_WEBHOOK_RESPONSE,
                content_type="application/json",
                HTTP_X_ZEIT_SIGNATURE="xxxinvalidsignaturexxx",
            )

            assert response.status_code == 401


@control_silo_test
class VercelReleasesTest(APITestCase):
    webhook_url = "/extensions/vercel/webhook/"

    @staticmethod
    def get_signature(message: str) -> str:
        return hmac.new(
            key=b"vercel-client-secret",
            msg=message.encode("utf-8"),
            digestmod=hashlib.sha1,
        ).hexdigest()

    def _get_response(self, message: str, signature: str | None = None) -> Response:
        signature = signature or self.get_signature(message)
        return self.client.post(
            path=self.webhook_url,
            data=message,
            content_type="application/json",
            HTTP_X_VERCEL_SIGNATURE=signature,
        )

    def setUp(self) -> None:
        super().setUp()
        self.project = self.create_project(organization=self.organization)
        self.integration = self.create_provider_integration(
            provider="vercel",
            external_id="cstd1xKmLGVMed0z0f3SHlD2",
            metadata={"access_token": "my_token"},
        )

        self.org_integration = self.create_organization_integration(
            organization_id=self.organization.id,
            integration=self.integration,
            config={
                "project_mappings": [
                    [self.project.id, "QmQPfU4xn5APjEsSje4ccPcSJCmVAByA8CDKfZRhYyVPAg"]
                ]
            },
        )

        self.sentry_app = self.create_internal_integration(
            webhook_url=None,
            name="Vercel Internal Integration",
            organization=self.organization,
        )
        self.create_internal_integration_token(user=self.user, internal_integration=self.sentry_app)
        self.installation_for_provider = self.create_sentry_app_installation_for_provider(
            sentry_app_id=self.sentry_app.id,
            organization_id=self.organization.id,
            provider="vercel",
        )

    def tearDown(self):
        responses.reset()

    @responses.activate
    def test_create_release(self) -> None:
        responses.add(
            responses.POST,
            absolute_uri("/api/0/organizations/%s/releases/" % self.organization.slug),
            json={},
        )

        with override_options({"vercel.client-secret": SECRET}):
            response = self._get_response(EXAMPLE_DEPLOYMENT_WEBHOOK_RESPONSE, SIGNATURE)

            assert response.status_code == 201

            assert len(responses.calls) == 2
            release_request = responses.calls[0].request
            release_body = orjson.loads(release_request.body)
            set_refs_body = orjson.loads(responses.calls[1].request.body)
            assert release_body == {
                "projects": [self.project.slug],
                "version": "7488658dfcf24d9b735e015992b316e2a8340d93",
            }
            assert set_refs_body == {
                "projects": [self.project.slug],
                "version": "7488658dfcf24d9b735e015992b316e2a8340d93",
                "refs": [
                    {
                        "commit": "7488658dfcf24d9b735e015992b316e2a8340d93",
                        "repository": "MeredithAnya/nextjsblog-demo-new",
                    }
                ],
            }
            assert release_request.headers["User-Agent"] == f"sentry_vercel/{VERSION}"

    @responses.activate
    def test_no_match(self) -> None:
        responses.add(
            responses.POST,
            absolute_uri("/api/0/organizations/%s/releases/" % self.organization.slug),
            json={},
        )

        self.org_integration.config = {}
        self.org_integration.save()

        with override_options({"vercel.client-secret": SECRET}):
            response = self._get_response(EXAMPLE_DEPLOYMENT_WEBHOOK_RESPONSE, SIGNATURE)

            assert len(responses.calls) == 0
            assert response.status_code == 204

    @responses.activate
    def test_no_integration(self) -> None:
        responses.add(
            responses.POST,
            absolute_uri("/api/0/organizations/%s/releases/" % self.organization.slug),
            json={},
        )
        self.integration.delete()

        with override_options({"vercel.client-secret": SECRET}):
            response = self._get_response(EXAMPLE_DEPLOYMENT_WEBHOOK_RESPONSE, SIGNATURE)

            assert len(responses.calls) == 0
            assert response.status_code == 404
            assert response.data["detail"] == "Integration not found"

    @responses.activate
    def test_no_project(self) -> None:
        responses.add(
            responses.POST,
            absolute_uri("/api/0/organizations/%s/releases/" % self.organization.slug),
            json={},
        )
        with assume_test_silo_mode(SiloMode.MONOLITH):
            self.project.delete()

        with override_options({"vercel.client-secret": SECRET}):
            response = self._get_response(EXAMPLE_DEPLOYMENT_WEBHOOK_RESPONSE, SIGNATURE)

            assert len(responses.calls) == 0
            assert response.status_code == 404
            assert response.data["detail"] == "Project not found"

    @responses.activate
    def test_no_installation(self) -> None:
        responses.add(
            responses.POST,
            absolute_uri("/api/0/organizations/%s/releases/" % self.organization.slug),
            json={},
        )
        self.installation_for_provider.delete()

        with override_options({"vercel.client-secret": SECRET}):
            response = self._get_response(EXAMPLE_DEPLOYMENT_WEBHOOK_RESPONSE, SIGNATURE)

            assert len(responses.calls) == 0
            assert response.status_code == 404
            assert response.data["detail"] == "Installation not found"

    @responses.activate
    def test_no_token(self) -> None:
        responses.add(
            responses.POST,
            absolute_uri("/api/0/organizations/%s/releases/" % self.organization.slug),
            json={},
        )

        SentryAppInstallationToken.objects.filter().delete()

        with override_options({"vercel.client-secret": SECRET}):
            response = self._get_response(EXAMPLE_DEPLOYMENT_WEBHOOK_RESPONSE, SIGNATURE)

            assert len(responses.calls) == 0
            assert response.status_code == 404
            assert response.data["detail"] == "Token not found"

    @responses.activate
    def test_create_release_fails(self) -> None:
        responses.add(
            responses.POST,
            absolute_uri("/api/0/organizations/%s/releases/" % self.organization.slug),
            json={},
            status=400,
        )

        with override_options({"vercel.client-secret": SECRET}):
            response = self._get_response(EXAMPLE_DEPLOYMENT_WEBHOOK_RESPONSE, SIGNATURE)

            assert len(responses.calls) == 1
            assert response.status_code == 400
            assert "Error creating release" in response.data["detail"]

    @responses.activate
    def test_set_refs_failed(self) -> None:
        def request_callback(request):
            payload = orjson.loads(request.body)
            status_code = 400 if payload.get("refs") else 200
            return status_code, {}, orjson.dumps({}).decode()

        responses.add_callback(
            responses.POST,
            absolute_uri("/api/0/organizations/%s/releases/" % self.organization.slug),
            callback=request_callback,
        )

        with override_options({"vercel.client-secret": SECRET}):
            response = self._get_response(EXAMPLE_DEPLOYMENT_WEBHOOK_RESPONSE, SIGNATURE)

            assert len(responses.calls) == 2
            assert response.status_code == 400
            assert "Error setting refs" in response.data["detail"]

    @responses.activate
    def test_manual_vercel_deploy(self) -> None:
        response = self._get_response(DEPLOYMENT_WEBHOOK_NO_COMMITS)

        assert response.status_code == 404
        assert "No commit found" == response.data["detail"]
        assert len(responses.calls) == 0

    def test_empty_payload(self) -> None:
        response = self._get_response("{}")

        assert response.status_code == 400

    def test_missing_repository(self) -> None:
        response = self._get_response(MINIMAL_WEBHOOK)

        assert response.status_code == 400
        assert "Could not determine repository" == response.data["detail"]


@control_silo_test
class VercelReleasesNewTest(VercelReleasesTest):
    webhook_url = "/extensions/vercel/delete/"

    @responses.activate
    def test_release_already_created(self) -> None:
        responses.add(
            responses.POST,
            absolute_uri("/api/0/organizations/%s/releases/" % self.organization.slug),
            json={},
        )

        self.create_release(
            project=self.project, version="7488658dfcf24d9b735e015992b316e2a8340d9d"
        )

        with override_options({"vercel.client-secret": SECRET}):
            response = self._get_response(EXAMPLE_DEPLOYMENT_WEBHOOK_RESPONSE, SIGNATURE)

            assert response.status_code == 201
