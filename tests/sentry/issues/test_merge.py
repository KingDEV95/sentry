from typing import Any
from unittest.mock import patch

import pytest
import rest_framework

from sentry.issues.grouptype import PerformanceNPlusOneGroupType
from sentry.issues.merge import handle_merge
from sentry.models.activity import Activity
from sentry.models.group import Group, GroupStatus
from sentry.models.groupinbox import GroupInboxReason, add_group_to_inbox
from sentry.testutils.cases import TestCase
from sentry.testutils.skips import requires_snuba
from sentry.types.activity import ActivityType
from sentry.types.group import GroupSubStatus

pytestmark = [requires_snuba]


class HandleIssueMergeTest(TestCase):
    def setUp(self) -> None:
        self.groups = []
        self.project_lookup = {self.project.id: self.project}
        for _ in range(5):
            group = self.create_group(
                status=GroupStatus.UNRESOLVED, substatus=GroupSubStatus.ONGOING
            )
            add_group_to_inbox(group, GroupInboxReason.NEW)
            self.groups.append(group)

    @patch("sentry.tasks.merge.merge_groups.delay")
    def test_handle_merge(self, merge_groups: Any) -> None:
        Activity.objects.all().delete()
        merge = handle_merge(self.groups, self.project_lookup, self.user)

        groups = Group.objects.filter(id__in=[g.id for g in self.groups])

        assert len(groups.filter(status=GroupStatus.PENDING_MERGE)) == 4
        assert len(groups.filter(substatus__isnull=True)) == 4
        assert merge_groups.called

        primary_group = self.groups[0]
        assert Activity.objects.filter(type=ActivityType.MERGE.value, group=primary_group)
        assert merge["parent"] == str(primary_group.id)
        assert len(merge["children"]) == 4
        assert primary_group.status == GroupStatus.UNRESOLVED
        assert primary_group.substatus == GroupSubStatus.ONGOING

    def test_handle_merge_performance_issues(self) -> None:
        group = Group.objects.create(
            project=self.project, type=PerformanceNPlusOneGroupType.type_id
        )
        add_group_to_inbox(group, GroupInboxReason.NEW)
        self.groups.append(group)

        with pytest.raises(rest_framework.exceptions.ValidationError) as e:
            handle_merge(self.groups, self.project_lookup, self.user)
        assert e.match("Only error issues can be merged.")
