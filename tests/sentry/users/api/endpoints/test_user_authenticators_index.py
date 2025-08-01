from django.urls import reverse

from sentry.testutils.cases import APITestCase
from sentry.testutils.helpers.options import override_options
from sentry.testutils.silo import control_silo_test
from sentry.users.models.authenticator import Authenticator


@control_silo_test
class AuthenticatorIndex(APITestCase):
    def test_simple(self) -> None:
        user = self.create_user(email="a@example.com", is_superuser=True)
        Authenticator.objects.create(
            type=3,  # u2f
            user=user,
            config={
                "devices": [
                    {
                        "binding": {
                            "publicKey": "aowekroawker",
                            "keyHandle": "aowkeroakewrokaweokrwoer",
                            "appId": "https://dev.getsentry.net:8000/auth/2fa/u2fappid.json",
                        },
                        "name": "Amused Beetle",
                        "ts": 1512505334,
                    }
                ]
            },
        )

        self.login_as(user=user, superuser=True)

        url = reverse("sentry-api-0-authenticator-index")

        with override_options({"system.url-prefix": "https://testserver"}):
            resp = self.client.get(url, format="json")

            assert resp.status_code == 200, (resp.status_code, resp.content)
            assert resp.data
            assert resp.data[0]["challenge"]
            assert resp.data[0]["id"] == "u2f"
