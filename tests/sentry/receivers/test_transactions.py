from functools import cached_property
from unittest.mock import MagicMock, patch

from django.db import router

from sentry.analytics.events.first_transaction_sent import FirstTransactionSentEvent
from sentry.models.organizationmember import OrganizationMember
from sentry.models.project import Project
from sentry.signals import event_processed, transaction_processed
from sentry.silo.safety import unguarded_write
from sentry.testutils.cases import TestCase
from sentry.testutils.helpers.analytics import assert_any_analytics_event
from sentry.testutils.helpers.datetime import before_now
from sentry.testutils.skips import requires_snuba

pytestmark = [requires_snuba]


class RecordFirstTransactionTest(TestCase):
    @cached_property
    def min_ago(self):
        return before_now(minutes=1).isoformat()

    def test_transaction_processed(self) -> None:
        assert not self.project.flags.has_transactions
        event = self.store_event(
            data={
                "type": "transaction",
                "timestamp": self.min_ago,
                "start_timestamp": self.min_ago,
                "contexts": {"trace": {"trace_id": "b" * 32, "span_id": "c" * 16, "op": ""}},
            },
            project_id=self.project.id,
        )

        transaction_processed.send(project=self.project, event=event, sender=type(self.project))
        project = Project.objects.get(id=self.project.id)
        assert project.flags.has_transactions

    def test_transaction_processed_no_platform(self) -> None:
        self.project.update(platform=None)
        assert not self.project.platform
        assert not self.project.flags.has_transactions

        event = self.store_event(
            data={
                "type": "transaction",
                "timestamp": self.min_ago,
                "start_timestamp": self.min_ago,
                "contexts": {"trace": {"trace_id": "b" * 32, "span_id": "c" * 16, "op": ""}},
            },
            project_id=self.project.id,
        )

        transaction_processed.send(project=self.project, event=event, sender=type(self.project))
        project = Project.objects.get(id=self.project.id)
        assert project.flags.has_transactions

    def test_event_processed(self) -> None:
        assert not self.project.flags.has_transactions
        event = self.store_event(
            data={"type": "default", "timestamp": self.min_ago}, project_id=self.project.id
        )

        event_processed.send(project=self.project, event=event, sender=type(self.project))
        project = Project.objects.get(id=self.project.id)
        assert not project.flags.has_transactions

    @patch("sentry.analytics.record")
    def test_analytics_event(self, mock_record: MagicMock) -> None:
        assert not self.project.flags.has_transactions
        event = self.store_event(
            data={
                "type": "transaction",
                "timestamp": self.min_ago,
                "start_timestamp": self.min_ago,
                "contexts": {"trace": {"trace_id": "b" * 32, "span_id": "c" * 16, "op": ""}},
            },
            project_id=self.project.id,
        )

        transaction_processed.send(project=self.project, event=event, sender=type(self.project))
        project = Project.objects.get(id=self.project.id)
        assert project.flags.has_transactions

        assert_any_analytics_event(
            mock_record,
            FirstTransactionSentEvent(
                default_user_id=self.user.id,
                organization_id=self.organization.id,
                project_id=self.project.id,
                platform=self.project.platform,
            ),
        )

    def test_analytics_event_no_owner(self) -> None:
        with unguarded_write(using=router.db_for_write(OrganizationMember)):
            OrganizationMember.objects.filter(organization=self.organization, role="owner").delete()
        assert not self.project.flags.has_transactions
        event = self.store_event(
            data={
                "type": "transaction",
                "timestamp": self.min_ago,
                "start_timestamp": self.min_ago,
                "contexts": {"trace": {"trace_id": "b" * 32, "span_id": "c" * 16, "op": ""}},
            },
            project_id=self.project.id,
        )

        transaction_processed.send(project=self.project, event=event, sender=type(self.project))
        project = Project.objects.get(id=self.project.id)

        assert project.flags.has_transactions
