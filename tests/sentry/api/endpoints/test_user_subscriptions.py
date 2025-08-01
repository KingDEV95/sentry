import pytest
from django.conf import settings

from sentry import newsletter
from sentry.newsletter.dummy import DummyNewsletter
from sentry.testutils.cases import APITestCase
from sentry.testutils.silo import control_silo_test
from sentry.users.models.useremail import UserEmail


@pytest.mark.skipif(
    settings.SENTRY_NEWSLETTER != "sentry.newsletter.dummy.DummyNewsletter",
    reason="Requires DummyNewsletter.",
)
@control_silo_test
class UserSubscriptionsNewsletterTest(APITestCase):
    endpoint = "sentry-api-0-user-subscriptions"
    method = "put"

    @pytest.fixture(autouse=True)
    def enable_newsletter(self):
        with newsletter.backend.test_only__downcast_to(DummyNewsletter).enable():
            yield

    def setUp(self) -> None:
        self.user = self.create_user(email="foo@example.com")
        self.login_as(self.user)

    def test_get_subscriptions(self) -> None:
        self.get_success_response(self.user.id, method="get")

    def test_subscribe(self) -> None:
        self.get_success_response(self.user.id, listId="123", subscribed=True, status_code=204)
        results = newsletter.backend.get_subscriptions(self.user)["subscriptions"]
        assert len(results) == 1
        assert results[0].list_id == 123
        assert results[0].subscribed
        assert results[0].verified

    def test_requires_subscribed(self) -> None:
        self.get_error_response(self.user.id, listId="123", status_code=400)

    def test_unverified_emails(self) -> None:
        UserEmail.objects.get(email=self.user.email).update(is_verified=False)
        self.get_success_response(self.user.id, listId="123", subscribed=True, status_code=204)

    def test_unsubscribe(self) -> None:
        self.get_success_response(self.user.id, listId="123", subscribed=False, status_code=204)
        results = newsletter.backend.get_subscriptions(self.user)["subscriptions"]
        assert len(results) == 1
        assert results[0].list_id == 123
        assert not results[0].subscribed
        assert results[0].verified

    def test_default_subscription(self) -> None:
        self.get_success_response(self.user.id, method="post", subscribed=True, status_code=204)
        results = newsletter.backend.get_subscriptions(self.user)["subscriptions"]
        assert len(results) == 1
        assert results[0].list_id == newsletter.backend.get_default_list_id()
        assert results[0].subscribed
        assert results[0].verified
