from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from jsonschema import ValidationError

from sentry.models.environment import Environment
from sentry.models.release import Release
from sentry.rules.age import AgeComparisonType
from sentry.rules.filters.latest_adopted_release_filter import (
    LatestAdoptedReleaseFilter,
    get_first_last_release_for_group_cache_key,
)
from sentry.search.utils import LatestReleaseOrders
from sentry.utils.cache import cache
from sentry.workflow_engine.models.data_condition import Condition
from sentry.workflow_engine.types import WorkflowEventData
from tests.sentry.workflow_engine.handlers.condition.test_base import ConditionTestCase


class TestLatestAdoptedReleaseCondition(ConditionTestCase):
    condition = Condition.LATEST_ADOPTED_RELEASE
    payload = {
        "id": LatestAdoptedReleaseFilter.id,
        "oldest_or_newest": "oldest",
        "older_or_newer": "newer",
        "environment": "prod",
    }

    def create_new_group_event(self, fingerprint):
        event = self.store_event(data={"fingerprint": [fingerprint]}, project_id=self.project.id)
        group = event.group
        group_event = self.event.for_group(group)
        return group, group_event

    def setUp(self) -> None:
        super().setUp()
        self.now = datetime.now(UTC)
        self.prod_env = self.create_environment(name="prod")
        self.test_env = self.create_environment(name="test")
        self.newest_release = self.create_release(
            project=self.event.group.project,
            version="test@2.0",
            date_added=self.now - timedelta(days=2),
            environments=[self.test_env],
            adopted=self.now - timedelta(days=2),
        )

        self.oldest_release = self.create_release(
            project=self.event.group.project,
            version="test@1.0",
            date_added=self.now - timedelta(days=1),
            environments=[self.prod_env],
            adopted=self.now - timedelta(days=1),
        )

        self.middle_release = self.create_release(
            project=self.event.group.project,
            version="test@1.5",
            date_added=self.now,
            environments=[self.prod_env],
            adopted=self.now,
        )

        self.event_data = WorkflowEventData(event=self.group_event, group=self.group_event.group)
        self.dc = self.create_data_condition(
            type=self.condition,
            comparison={
                "release_age_type": "oldest",
                "age_comparison": "newer",
                "environment": self.prod_env.name,
            },
            condition_result=True,
        )

    def test_dual_write(self) -> None:
        dcg = self.create_data_condition_group()
        dc = self.translate_to_data_condition(self.payload, dcg)

        assert dc.type == self.condition
        assert dc.comparison == {
            "release_age_type": "oldest",
            "age_comparison": "newer",
            "environment": "prod",
        }
        assert dc.condition_result is True
        assert dc.condition_group == dcg

    def test_json_schema(self) -> None:
        self.dc.comparison.update({"age_comparison": AgeComparisonType.OLDER})
        self.dc.save()

        self.dc.comparison.update({"age_comparison": "new"})
        with pytest.raises(ValidationError):
            self.dc.save()

        self.dc.comparison.update({"release_age_type": "new"})
        with pytest.raises(ValidationError):
            self.dc.save()

        self.dc.comparison.update({"environment": 123})
        with pytest.raises(ValidationError):
            self.dc.save()

    def test_semver(self) -> None:
        # Test no release
        self.assert_does_not_pass(self.dc, self.event_data)

        self.create_group_release(group=self.group, release=self.newest_release)
        self.assert_passes(
            self.dc, WorkflowEventData(event=self.group_event, group=self.group_event.group)
        )

        group_2, group_event_2 = self.create_new_group_event("group2")
        self.create_group_release(group=group_2, release=self.newest_release)
        self.create_group_release(group=group_2, release=self.oldest_release)
        self.assert_does_not_pass(self.dc, WorkflowEventData(event=group_event_2, group=group_2))

        group_3, group_event_3 = self.create_new_group_event("group3")
        self.create_group_release(group=group_3, release=self.middle_release)
        self.assert_does_not_pass(self.dc, WorkflowEventData(event=group_event_3, group=group_3))

        # Check that the group cache invalidation works by adding an older release to the first group
        self.create_group_release(group=self.group, release=self.oldest_release)
        self.assert_does_not_pass(
            self.dc, WorkflowEventData(event=self.group_event, group=self.group_event.group)
        )

        # Check that the project cache invalidation works by adding a newer release to the project
        group_4, group_event_4 = self.create_new_group_event("group4")
        self.create_group_release(group=group_4, release=self.newest_release)
        self.assert_passes(self.dc, WorkflowEventData(event=group_event_4, group=group_4))

        self.create_release(
            project=self.event.group.project,
            version="test@3.0",
            date_added=self.now - timedelta(days=5),
            environments=[self.prod_env],
            adopted=self.now - timedelta(days=2),
        )
        self.assert_does_not_pass(self.dc, WorkflowEventData(event=group_event_4, group=group_4))

    def test_date(self) -> None:
        self.create_group_release(group=self.group, release=self.newest_release)
        self.assert_passes(
            self.dc, WorkflowEventData(event=self.group_event, group=self.group_event.group)
        )

        group_2, group_event_2 = self.create_new_group_event("group2")
        self.create_group_release(group=group_2, release=self.newest_release)
        self.create_group_release(group=group_2, release=self.oldest_release)
        self.assert_does_not_pass(self.dc, WorkflowEventData(event=group_event_2, group=group_2))

        group_3, group_event_3 = self.create_new_group_event("group3")
        self.create_group_release(group=group_3, release=self.middle_release)
        self.assert_does_not_pass(self.dc, WorkflowEventData(event=group_event_3, group=group_3))

    def test_oldest_older(self) -> None:
        self.dc.update(
            comparison={
                "release_age_type": "oldest",
                "age_comparison": "older",
                "environment": self.prod_env.name,
            }
        )

        self.create_group_release(group=self.group, release=self.newest_release)
        self.assert_does_not_pass(
            self.dc, WorkflowEventData(event=self.group_event, group=self.group_event.group)
        )

        group_2, group_event_2 = self.create_new_group_event("group2")

        self.create_group_release(group=group_2, release=self.newest_release)
        self.create_group_release(group=group_2, release=self.oldest_release)
        self.assert_passes(self.dc, WorkflowEventData(event=group_event_2, group=group_2))

        group_3, group_event_3 = self.create_new_group_event("group3")

        self.create_group_release(group=group_3, release=self.middle_release)
        self.assert_does_not_pass(self.dc, WorkflowEventData(event=group_event_3, group=group_3))

    def test_newest_newer(self) -> None:
        self.dc.update(
            comparison={
                "release_age_type": "newest",
                "age_comparison": "newer",
                "environment": self.prod_env.name,
            }
        )

        self.create_group_release(group=self.group, release=self.newest_release)
        self.assert_passes(
            self.dc, WorkflowEventData(event=self.group_event, group=self.group_event.group)
        )

        group_2, group_event_2 = self.create_new_group_event("group2")

        self.create_group_release(group=group_2, release=self.newest_release)
        self.create_group_release(group=group_2, release=self.oldest_release)
        self.assert_passes(self.dc, WorkflowEventData(event=group_event_2, group=group_2))

        group_3, group_event_3 = self.create_new_group_event("group3")

        self.create_group_release(group=group_3, release=self.middle_release)
        self.assert_does_not_pass(self.dc, WorkflowEventData(event=group_event_3, group=group_3))

    def test_newest_older(self) -> None:
        self.dc.update(
            comparison={
                "release_age_type": "newest",
                "age_comparison": "older",
                "environment": self.prod_env.name,
            }
        )

        self.create_group_release(group=self.event.group, release=self.newest_release)
        self.assert_does_not_pass(
            self.dc, WorkflowEventData(event=self.event, group=self.group_event.group)
        )

        group_2, group_event_2 = self.create_new_group_event("group2")
        self.create_group_release(group=group_2, release=self.newest_release)
        self.create_group_release(group=group_2, release=self.oldest_release)
        self.assert_does_not_pass(self.dc, WorkflowEventData(event=group_event_2, group=group_2))

        group_3, group_event_3 = self.create_new_group_event("group3")
        self.create_group_release(group=group_3, release=self.middle_release)
        self.assert_does_not_pass(self.dc, WorkflowEventData(event=group_event_3, group=group_3))

    def test_caching(self) -> None:
        cache_key = get_first_last_release_for_group_cache_key(
            self.group.id, "oldest", LatestReleaseOrders.SEMVER
        )
        assert cache.get(cache_key) is None

        self.create_group_release(group=self.group, release=self.newest_release)
        self.assert_passes(self.dc, self.event_data)
        assert cache.get(cache_key) is not None

        # ensure we clear the cache after creating a new release
        oldest_group_release = self.create_group_release(
            group=self.group, release=self.oldest_release
        )
        assert cache.get(cache_key) is None

        self.assert_does_not_pass(self.dc, self.event_data)
        assert cache.get(cache_key) is not None

        # ensure we clear the cache when a release is deleted
        oldest_group_release.delete()
        assert cache.get(cache_key) is None

        self.assert_passes(self.dc, self.event_data)

    @patch("sentry.search.utils.get_first_last_release_for_group", side_effect=Release.DoesNotExist)
    def test_release_does_not_exist(self, mock_get_first_last_release: MagicMock) -> None:
        self.assert_does_not_pass(self.dc, self.event_data)

    @patch(
        "sentry.workflow_engine.handlers.condition.latest_adopted_release_handler.get_latest_adopted_release_for_env",
        return_value=None,
    )
    def test_latest_release_for_env_does_not_exist(
        self, mock_get_latest_adopted_release_for_env: MagicMock
    ) -> None:
        self.assert_does_not_pass(self.dc, self.event_data)
        mock_get_latest_adopted_release_for_env.assert_called()

    @patch(
        "sentry.workflow_engine.handlers.condition.latest_adopted_release_handler.get_first_last_release_for_event",
        return_value=None,
    )
    def test_first_last_release_for_event_does_not_exist(
        self, mock_get_first_last_release_for_event
    ):
        self.assert_does_not_pass(self.dc, self.event_data)

    @patch(
        "sentry.models.environment.Environment.get_for_organization_id",
        side_effect=Environment.DoesNotExist,
    )
    def test_environment_does_not_exist(self, mock_get_env: MagicMock) -> None:
        self.assert_does_not_pass(self.dc, self.event_data)

    def test_ignores_unadopted_releases(self) -> None:
        # Create unadopted release (newer) - should be ignored when finding newest adopted release
        self.create_release(
            project=self.project,
            version="test@3.0",
            date_added=self.now + timedelta(hours=1),
            environments=[self.prod_env],
            adopted=None,
        )

        # Condition: Is newest adopted release older than group's release?
        dc = self.create_data_condition(
            type=self.condition,
            comparison={
                "release_age_type": "newest",
                "age_comparison": "older",
                "environment": self.prod_env.name,
            },
            condition_result=True,
        )

        # Group has middle_release
        group, group_event = self.create_new_group_event("test")
        self.create_group_release(group=group, release=self.middle_release)

        # Should NOT pass: newest adopted (middle_release) is NOT older than group's (middle_release)
        # Would fail if test@3.0 (unadopted) was considered as newest, since 3.0 > 1.5
        self.assert_does_not_pass(dc, WorkflowEventData(event=group_event, group=group))
