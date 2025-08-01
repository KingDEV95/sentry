from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.utils import timezone

from sentry.models.group import GroupStatus
from sentry.models.grouphistory import GroupHistory, GroupHistoryStatus
from sentry.models.groupsnooze import GroupSnooze
from sentry.tasks.clear_expired_snoozes import clear_expired_snoozes
from sentry.testutils.cases import TestCase
from sentry.types.group import GroupSubStatus


class ClearExpiredSnoozesTest(TestCase):
    def test_task_persistent_name(self) -> None:
        assert clear_expired_snoozes.name == "sentry.tasks.clear_expired_snoozes"

    @patch("sentry.signals.issue_unignored.send_robust")
    def test_simple(self, send_robust: MagicMock) -> None:
        group1 = self.create_group(status=GroupStatus.IGNORED)
        snooze1 = GroupSnooze.objects.create(
            group=group1, until=timezone.now() - timedelta(minutes=1)
        )

        group2 = self.create_group(status=GroupStatus.IGNORED)
        snooze2 = GroupSnooze.objects.create(
            group=group2, until=timezone.now() + timedelta(minutes=1)
        )

        clear_expired_snoozes()

        group1.refresh_from_db()
        group2.refresh_from_db()

        assert group1.status == GroupStatus.UNRESOLVED
        assert group1.substatus == GroupSubStatus.ONGOING

        # Check if unexpired snooze got cleared
        assert group2.status == GroupStatus.IGNORED

        assert not GroupSnooze.objects.filter(id=snooze1.id).exists()
        assert GroupSnooze.objects.filter(id=snooze2.id).exists()
        assert GroupHistory.objects.filter(group=group1, status=GroupHistoryStatus.ONGOING).exists()
        assert not GroupHistory.objects.filter(
            group=group2, status=GroupHistoryStatus.ONGOING
        ).exists()

        assert send_robust.called

    @patch("sentry.signals.issue_unignored.send_robust")
    def test_simple_with_escalating_issues(self, send_robust: MagicMock) -> None:
        group1 = self.create_group(status=GroupStatus.IGNORED)
        snooze1 = GroupSnooze.objects.create(
            group=group1, until=timezone.now() - timedelta(minutes=1)
        )

        group2 = self.create_group(status=GroupStatus.IGNORED)
        snooze2 = GroupSnooze.objects.create(
            group=group2, until=timezone.now() + timedelta(minutes=1)
        )

        clear_expired_snoozes()

        group1.refresh_from_db()
        group2.refresh_from_db()

        assert group1.status == GroupStatus.UNRESOLVED
        assert group1.substatus == GroupSubStatus.ONGOING

        # Check if unexpired snooze got cleared
        assert group2.status == GroupStatus.IGNORED

        assert not GroupSnooze.objects.filter(id=snooze1.id).exists()
        assert GroupSnooze.objects.filter(id=snooze2.id).exists()
        assert GroupHistory.objects.filter(group=group1, status=GroupHistoryStatus.ONGOING).exists()
        assert not GroupHistory.objects.filter(
            group=group2, status=GroupHistoryStatus.UNIGNORED
        ).exists()

        assert send_robust.called

    def test_resolved_group(self) -> None:
        group1 = self.create_group(status=GroupStatus.RESOLVED)
        snooze1 = GroupSnooze.objects.create(
            group=group1, until=timezone.now() - timedelta(minutes=1)
        )

        clear_expired_snoozes()

        group1.refresh_from_db()

        assert group1.status == GroupStatus.RESOLVED
        # Validate that even though the group wasn't modified, we still remove the snooze
        assert not GroupSnooze.objects.filter(id=snooze1.id).exists()
