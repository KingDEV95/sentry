from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from sentry.models.apiapplication import ApiApplication
from sentry.models.apitoken import ApiToken
from sentry.sentry_apps.token_exchange.util import GrantTypes
from sentry.silo.base import SiloMode
from sentry.testutils.cases import APITestCase
from sentry.testutils.silo import assume_test_silo_mode, control_silo_test
from sentry.testutils.skips import requires_snuba

pytestmark = [requires_snuba]


@control_silo_test
class TestSentryAppAuthorizations(APITestCase):
    endpoint = "sentry-api-0-sentry-app-installation-authorizations"
    method = "post"

    def setUp(self) -> None:
        self.sentry_app = self.create_sentry_app(
            name="nulldb",
            organization=self.create_organization(),
            scopes=["org:read"],
            webhook_url="http://example.com",
        )

        self.other_sentry_app = self.create_sentry_app(
            name="slowdb",
            organization=self.create_organization(),
            scopes=[],
            webhook_url="http://example.com",
        )

        self.install = self.create_sentry_app_installation(
            organization=self.organization,
            slug="nulldb",
            user=self.user,
            prevent_token_exchange=True,
        )

    def get_response(self, *args, **params):
        """Overriding `get_response` with some default data."""
        return super().get_response(
            self.install.uuid,
            **{
                "client_id": self.sentry_app.application.client_id,
                "client_secret": self.sentry_app.application.client_secret,
                "grant_type": GrantTypes.AUTHORIZATION,
                "code": self.install.api_grant.code,
                **params,
            },
        )

    def test_exchanges_for_token_successfully(self) -> None:
        expected_expires_at = (timezone.now() + timedelta(hours=8)).replace(second=0, microsecond=0)

        response = self.get_success_response()

        token = ApiToken.objects.get(application=self.sentry_app.application)

        assert response.data["scopes"] == self.sentry_app.scope_list
        assert response.data["token"] == token.token
        assert response.data["refreshToken"] == token.refresh_token

        expires_at = response.data["expiresAt"].replace(second=0, microsecond=0)

        assert expires_at == expected_expires_at

    def test_exchange_for_token_missing_data(self) -> None:
        response = self.get_error_response(code=None)

        assert response.status_code == 400

        # This is rejected by the base `SentryAppAuthorizationBaseEndpoint`
        # class's authentication, so expect an unauthorized error.
        response = self.get_error_response(client_id=None)
        assert response.status_code == 401

    def test_incorrect_grant_type(self) -> None:
        self.get_error_response(grant_type="notit", status_code=403)

    def test_invalid_installation(self) -> None:
        self.install = self.create_sentry_app_installation(
            organization=self.organization,
            slug="slowdb",
            user=self.user,
            prevent_token_exchange=True,
        )

        # URL with this new Install's uuid in it
        self.get_error_response(self.install.uuid, status_code=403)

    def test_non_sentry_app_user(self) -> None:
        app = ApiApplication.objects.create(owner=self.create_user())
        self.get_error_response(
            client_id=app.client_id, client_secret=app.client_secret, status_code=401
        )

    def test_invalid_grant(self) -> None:
        self.get_error_response(code="123", status_code=401)

    def test_expired_grant(self) -> None:
        self.install.api_grant.update(expires_at=timezone.now() - timedelta(minutes=2))
        response = self.get_error_response(status_code=401)
        assert response.data["detail"] == "Grant has already expired"

    def test_request_with_exchanged_access_token(self) -> None:
        response = self.get_response()
        token = response.data["token"]

        url = reverse("sentry-api-0-organization-details", args=[self.organization.slug])

        with assume_test_silo_mode(SiloMode.REGION):
            response = self.client.get(url, HTTP_AUTHORIZATION=f"Bearer {token}")

        assert response.status_code == 200
        assert response.data["id"] == str(self.organization.id)

    def test_state(self) -> None:
        response = self.get_success_response(state="abc123")
        assert response.data["state"] == "abc123"

    def test_refresh_token_exchange(self) -> None:
        response = self.get_success_response()

        token_id = response.data["id"]
        token = response.data["token"]
        refresh_token = response.data["refreshToken"]

        response = self.get_success_response(
            code=None, refresh_token=refresh_token, grant_type="refresh_token"
        )

        assert response.data["token"] != token
        assert response.data["refreshToken"] != refresh_token
        assert response.data["expiresAt"] > timezone.now()

        old_token = ApiToken.objects.filter(id=token_id)
        assert not old_token.exists()

        new_token = ApiToken.objects.filter(token=response.data["token"])
        assert new_token.exists()

        new_token = ApiToken.objects.filter(refresh_token=response.data["refreshToken"])
        assert new_token.exists()

    def test_refresh_token_exchange_with_missing_data(self) -> None:
        response = self.get_success_response()

        refresh_token = response.data["refreshToken"]

        assert response.data["refreshToken"] is not None

        response = self.get_error_response(
            code=None, refresh_token=None, grant_type="refresh_token"
        )

        assert response.status_code == 400

        # This is rejected by the base `SentryAppAuthorizationBaseEndpoint`
        # class's authentication, so expect an unauthorized error.
        response = self.get_error_response(
            code=None, refresh_token=refresh_token, grant_type="refresh_token", client_id=None
        )
        assert response.status_code == 401
