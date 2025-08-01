from django.test import override_settings

from sentry.testutils.cases import APITestCase
from sentry.testutils.helpers.datetime import freeze_time
from sentry.testutils.silo import control_silo_test
from sentry.users.models.user import User


@control_silo_test
class UserPasswordTest(APITestCase):
    endpoint = "sentry-api-0-user-password"
    method = "put"

    def setUp(self) -> None:
        self.user = self.create_user(email="a@example.com", is_managed=False, name="example name")
        self.user.set_password("helloworld!")
        self.user.save()

        self.login_as(self.user)

    def test_change_password(self) -> None:
        old_password = self.user.password
        self.get_success_response(
            "me",
            status_code=204,
            **{
                "password": "helloworld!",
                "passwordNew": "testpassword",
                "passwordVerify": "testpassword",
            },
        )
        user = User.objects.get(id=self.user.id)
        assert old_password != user.password

    @override_settings(
        AUTH_PASSWORD_VALIDATORS=[
            {
                "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
                "OPTIONS": {"min_length": 8},
            },
        ]
    )
    def test_password_too_short(self) -> None:
        self.get_error_response(
            "me",
            status_code=400,
            **{
                "password": "helloworld!",
                "passwordNew": "hi",
                "passwordVerify": "hi",
            },
        )

    def test_no_password(self) -> None:
        self.get_error_response("me", status_code=400, **{"password": "helloworld!"})
        self.get_error_response("me", status_code=400)

    def test_require_current_password(self) -> None:
        self.get_error_response(
            "me",
            status_code=400,
            **{
                "password": "wrongpassword",
                "passwordNew": "testpassword",
                "passwordVerify": "testpassword",
            },
        )

    def test_verifies_mismatch_password(self) -> None:
        self.get_error_response(
            "me",
            status_code=400,
            **{
                "password": "helloworld!",
                "passwordNew": "testpassword",
                "passwordVerify": "passworddoesntmatch",
            },
        )

    def test_managed_unable_change_password(self) -> None:
        user = self.create_user(email="new@example.com", is_managed=True)
        self.login_as(user)

        self.get_error_response(
            user.id,
            status_code=400,
            **{"passwordNew": "newpassword", "passwordVerify": "newpassword"},
        )

    def test_unusable_password_unable_change_password(self) -> None:
        user = self.create_user(email="new@example.com")
        user.set_unusable_password()
        user.save()
        self.login_as(user)

        self.get_error_response(
            user.id,
            status_code=400,
            **{"passwordNew": "newpassword", "passwordVerify": "newpassword"},
        )

    def test_cannot_change_other_user_password(self) -> None:
        user = self.create_user(email="new@example.com", is_superuser=False)
        self.login_as(user)

        self.get_error_response(
            self.user.id,
            status_code=403,
            **{
                "password": "helloworld!",
                "passwordNew": "newpassword",
                "passwordVerify": "newpassword",
            },
        )

    def test_superuser_can_change_other_user_password(self) -> None:
        user = self.create_user(email="new@example.com", is_superuser=True)
        self.login_as(user, superuser=True)

        self.get_success_response(
            self.user.id,
            status_code=204,
            **{
                "password": "helloworld!",
                "passwordNew": "newpassword",
                "passwordVerify": "newpassword",
            },
        )

    @override_settings(SENTRY_SELF_HOSTED=False)
    def test_rate_limit(self) -> None:
        with freeze_time("2024-05-21"):
            for _ in range(5):
                self.test_require_current_password()
            self.get_error_response(
                "me",
                status_code=429,
                **{
                    "password": "wrongguess",
                    "passwordNew": "newpassword",
                    "passwordVerify": "newpassword",
                },
            )
