from datetime import timedelta

import pytest

from sentry.exceptions import InvalidSearchQuery
from sentry.models.transaction_threshold import ProjectTransactionThreshold, TransactionMetric
from sentry.search.events.types import SnubaParams
from sentry.snuba import discover
from sentry.testutils.cases import SnubaTestCase, TestCase
from sentry.testutils.helpers.datetime import before_now
from sentry.utils.samples import load_data

ARRAY_COLUMNS = ["measurements", "span_op_breakdowns"]


class TimeseriesBase(SnubaTestCase, TestCase):
    def setUp(self) -> None:
        super().setUp()

        self.one_min_ago = before_now(minutes=1)
        self.day_ago = before_now(days=1).replace(hour=10, minute=0, second=0, microsecond=0)

        self.store_event(
            data={
                "event_id": "a" * 32,
                "message": "very bad",
                "timestamp": (self.day_ago + timedelta(hours=1)).isoformat(),
                "fingerprint": ["group1"],
                "tags": {"important": "yes"},
                "user": {"id": 1},
            },
            project_id=self.project.id,
        )
        self.store_event(
            data={
                "event_id": "b" * 32,
                "message": "oh my",
                "timestamp": (self.day_ago + timedelta(hours=1, minutes=1)).isoformat(),
                "fingerprint": ["group2"],
                "tags": {"important": "no"},
            },
            project_id=self.project.id,
        )
        self.store_event(
            data={
                "event_id": "c" * 32,
                "message": "very bad",
                "timestamp": (self.day_ago + timedelta(hours=2, minutes=1)).isoformat(),
                "fingerprint": ["group2"],
                "tags": {"important": "yes"},
            },
            project_id=self.project.id,
        )


class DiscoverTimeseriesQueryTest(TimeseriesBase):
    def test_invalid_field_in_function(self) -> None:
        with pytest.raises(InvalidSearchQuery):
            discover.timeseries_query(
                selected_columns=["min(transaction)"],
                query="transaction:api.issue.delete",
                referrer="test_discover_query",
                snuba_params=SnubaParams(
                    start=self.day_ago,
                    end=self.day_ago + timedelta(hours=2),
                    projects=[self.project],
                ),
                rollup=1800,
            )

    def test_missing_start_and_end(self) -> None:
        with pytest.raises(InvalidSearchQuery):
            discover.timeseries_query(
                selected_columns=["count()"],
                query="transaction:api.issue.delete",
                referrer="test_discover_query",
                snuba_params=SnubaParams(projects=[self.project]),
                rollup=1800,
            )

    def test_no_aggregations(self) -> None:
        with pytest.raises(InvalidSearchQuery):
            discover.timeseries_query(
                selected_columns=["transaction", "title"],
                query="transaction:api.issue.delete",
                referrer="test_discover_query",
                snuba_params=SnubaParams(
                    start=self.day_ago,
                    end=self.day_ago + timedelta(hours=2),
                    projects=[self.project],
                ),
                rollup=1800,
            )

    def test_field_alias(self) -> None:
        result = discover.timeseries_query(
            selected_columns=["p95()"],
            query="event.type:transaction transaction:api.issue.delete",
            referrer="test_discover_query",
            snuba_params=SnubaParams(
                start=self.day_ago, end=self.day_ago + timedelta(hours=2), projects=[self.project]
            ),
            rollup=3600,
        )
        assert len(result.data["data"]) == 3

    def test_failure_rate_field_alias(self) -> None:
        result = discover.timeseries_query(
            selected_columns=["failure_rate()"],
            query="event.type:transaction transaction:api.issue.delete",
            referrer="test_discover_query",
            snuba_params=SnubaParams(
                start=self.day_ago, end=self.day_ago + timedelta(hours=2), projects=[self.project]
            ),
            rollup=3600,
        )
        assert len(result.data["data"]) == 3

    def test_aggregate_function(self) -> None:
        result = discover.timeseries_query(
            selected_columns=["count()"],
            query="",
            referrer="test_discover_query",
            snuba_params=SnubaParams(
                start=self.day_ago, end=self.day_ago + timedelta(hours=2), projects=[self.project]
            ),
            rollup=3600,
        )
        assert len(result.data["data"]) == 3
        assert [2] == [val["count"] for val in result.data["data"] if "count" in val]

        result = discover.timeseries_query(
            selected_columns=["count_unique(user)"],
            query="",
            referrer="test_discover_query",
            snuba_params=SnubaParams(
                start=self.day_ago, end=self.day_ago + timedelta(hours=2), projects=[self.project]
            ),
            rollup=3600,
        )
        assert len(result.data["data"]) == 3
        keys = set()
        for row in result.data["data"]:
            keys.update(list(row.keys()))
        assert "count_unique_user" in keys
        assert "time" in keys

    def test_comparison_aggregate_function_invalid(self) -> None:
        with pytest.raises(
            InvalidSearchQuery, match="Only one column can be selected for comparison queries"
        ):
            discover.timeseries_query(
                selected_columns=["count()", "count_unique(user)"],
                query="",
                referrer="test_discover_query",
                snuba_params=SnubaParams(
                    start=self.day_ago,
                    end=self.day_ago + timedelta(hours=2),
                    projects=[self.project],
                ),
                rollup=3600,
                comparison_delta=timedelta(days=1),
            )

    def test_comparison_aggregate_function(self) -> None:
        self.store_event(
            data={
                "timestamp": (self.day_ago + timedelta(hours=1)).isoformat(),
                "user": {"id": 1},
            },
            project_id=self.project.id,
        )

        result = discover.timeseries_query(
            selected_columns=["count()"],
            query="",
            referrer="test_discover_query",
            snuba_params=SnubaParams(
                start=self.day_ago, end=self.day_ago + timedelta(hours=2), projects=[self.project]
            ),
            rollup=3600,
            comparison_delta=timedelta(days=1),
        )
        assert len(result.data["data"]) == 3
        # Values should all be 0, since there is no comparison period data at all.
        assert [(0, 0), (3, 0), (0, 0)] == [
            (val.get("count", 0), val.get("comparisonCount", 0)) for val in result.data["data"]
        ]

        self.store_event(
            data={
                "timestamp": (self.day_ago + timedelta(days=-1, hours=1)).isoformat(),
                "user": {"id": 1},
            },
            project_id=self.project.id,
        )
        self.store_event(
            data={
                "timestamp": (self.day_ago + timedelta(days=-1, hours=1, minutes=2)).isoformat(),
                "user": {"id": 2},
            },
            project_id=self.project.id,
        )
        self.store_event(
            data={
                "timestamp": (self.day_ago + timedelta(days=-1, hours=2, minutes=1)).isoformat(),
            },
            project_id=self.project.id,
        )

        result = discover.timeseries_query(
            selected_columns=["count()"],
            query="",
            referrer="test_discover_query",
            snuba_params=SnubaParams(
                start=self.day_ago,
                end=self.day_ago + timedelta(hours=2, minutes=1),
                projects=[self.project],
            ),
            rollup=3600,
            comparison_delta=timedelta(days=1),
        )
        assert len(result.data["data"]) == 3
        # In the second bucket we have 3 events in the current period and 2 in the comparison, so
        # we get a result of 50% increase
        assert [(0, 0), (3, 2), (0, 0)] == [
            (val.get("count", 0), val.get("comparisonCount", 0)) for val in result.data["data"]
        ]

        result = discover.timeseries_query(
            selected_columns=["count_unique(user)"],
            query="",
            snuba_params=SnubaParams(
                start=self.day_ago,
                end=self.day_ago + timedelta(hours=2, minutes=2),
                projects=[self.project],
            ),
            rollup=3600,
            referrer="test_discover_query",
            comparison_delta=timedelta(days=1),
        )
        assert len(result.data["data"]) == 3
        # In the second bucket we have 1 unique user in the current period and 2 in the comparison, so
        # we get a result of -50%
        assert [(0, 0), (1, 2), (0, 0)] == [
            (val.get("count_unique_user", 0), val.get("comparisonCount", 0))
            for val in result.data["data"]
        ]

    def test_count_miserable(self) -> None:
        event_data = load_data("transaction")
        # Half of duration so we don't get weird rounding differences when comparing the results
        event_data["breakdowns"]["span_ops"]["ops.http"]["value"] = 300
        event_data["start_timestamp"] = (self.day_ago + timedelta(minutes=30)).isoformat()
        event_data["timestamp"] = (self.day_ago + timedelta(minutes=30, seconds=3)).isoformat()
        self.store_event(data=event_data, project_id=self.project.id)
        ProjectTransactionThreshold.objects.create(
            project=self.project,
            organization=self.project.organization,
            threshold=100,
            metric=TransactionMetric.DURATION.value,
        )

        project2 = self.create_project()
        ProjectTransactionThreshold.objects.create(
            project=project2,
            organization=project2.organization,
            threshold=100,
            metric=TransactionMetric.DURATION.value,
        )

        result = discover.timeseries_query(
            selected_columns=["count_miserable(user)"],
            referrer="test_discover_query",
            query="",
            snuba_params=SnubaParams(
                start=self.day_ago,
                end=self.day_ago + timedelta(hours=2),
                projects=[self.project],
                organization=self.organization,
            ),
            rollup=3600,
        )
        assert len(result.data["data"]) == 3
        assert [1] == [
            val["count_miserable_user"]
            for val in result.data["data"]
            if "count_miserable_user" in val
        ]

    def test_count_miserable_with_arithmetic(self) -> None:
        event_data = load_data("transaction")
        # Half of duration so we don't get weird rounding differences when comparing the results
        event_data["breakdowns"]["span_ops"]["ops.http"]["value"] = 300
        event_data["start_timestamp"] = (self.day_ago + timedelta(minutes=30)).isoformat()
        event_data["timestamp"] = (self.day_ago + timedelta(minutes=30, seconds=3)).isoformat()
        self.store_event(data=event_data, project_id=self.project.id)
        ProjectTransactionThreshold.objects.create(
            project=self.project,
            organization=self.project.organization,
            threshold=100,
            metric=TransactionMetric.DURATION.value,
        )

        project2 = self.create_project()
        ProjectTransactionThreshold.objects.create(
            project=project2,
            organization=project2.organization,
            threshold=100,
            metric=TransactionMetric.DURATION.value,
        )

        result = discover.timeseries_query(
            selected_columns=["equation|count_miserable(user) - 100"],
            referrer="test_discover_query",
            query="",
            snuba_params=SnubaParams(
                start=self.day_ago,
                end=self.day_ago + timedelta(hours=2),
                projects=[self.project, project2],
                organization=self.organization,
            ),
            rollup=3600,
        )
        assert len(result.data["data"]) == 3
        assert [1 - 100] == [
            val["equation[0]"] for val in result.data["data"] if "equation[0]" in val
        ]

    def test_equation_function(self) -> None:
        result = discover.timeseries_query(
            selected_columns=["equation|count() / 100"],
            query="",
            referrer="test_discover_query",
            snuba_params=SnubaParams(
                start=self.day_ago, end=self.day_ago + timedelta(hours=2), projects=[self.project]
            ),
            rollup=3600,
        )
        assert len(result.data["data"]) == 3
        assert [0.02] == [val["equation[0]"] for val in result.data["data"] if "equation[0]" in val]

        result = discover.timeseries_query(
            selected_columns=["equation|count_unique(user) / 100"],
            query="",
            snuba_params=SnubaParams(
                start=self.day_ago, end=self.day_ago + timedelta(hours=2), projects=[self.project]
            ),
            rollup=3600,
            referrer="test_discover_query",
        )
        assert len(result.data["data"]) == 3
        keys = set()
        for row in result.data["data"]:
            keys.update(list(row.keys()))
        assert "equation[0]" in keys
        assert "time" in keys

    def test_zerofilling(self) -> None:
        result = discover.timeseries_query(
            selected_columns=["count()"],
            query="",
            referrer="test_discover_query",
            snuba_params=SnubaParams(
                start=self.day_ago, end=self.day_ago + timedelta(hours=3), projects=[self.project]
            ),
            rollup=3600,
        )
        assert len(result.data["data"]) == 4, "Should have empty results"
        assert [2, 1] == [
            val["count"] for val in result.data["data"] if "count" in val
        ], result.data["data"]

    def test_conditional_filter(self) -> None:
        project2 = self.create_project(organization=self.organization)
        project3 = self.create_project(organization=self.organization)

        self.store_event(
            data={"message": "hello", "timestamp": self.one_min_ago.isoformat()},
            project_id=project2.id,
        )
        self.store_event(
            data={"message": "hello", "timestamp": self.one_min_ago.isoformat()},
            project_id=project3.id,
        )

        result = discover.timeseries_query(
            selected_columns=["count()"],
            query=f"project:{self.project.slug} OR project:{project2.slug}",
            snuba_params=SnubaParams(
                start=before_now(minutes=5),
                end=before_now(seconds=1),
                projects=[self.project, project2, project3],
            ),
            rollup=3600,
            referrer="test_discover_query",
        )

        data = result.data["data"]
        assert len([d for d in data if "count" in d]) == 1
        for d in data:
            if "count" in d:
                assert d["count"] == 1

    def test_nested_conditional_filter(self) -> None:
        project2 = self.create_project(organization=self.organization)
        self.store_event(
            data={"release": "a" * 32, "timestamp": self.one_min_ago.isoformat()},
            project_id=self.project.id,
        )
        self.event = self.store_event(
            data={"release": "b" * 32, "timestamp": self.one_min_ago.isoformat()},
            project_id=self.project.id,
        )
        self.event = self.store_event(
            data={"release": "c" * 32, "timestamp": self.one_min_ago.isoformat()},
            project_id=self.project.id,
        )
        self.event = self.store_event(
            data={"release": "a" * 32, "timestamp": self.one_min_ago.isoformat()},
            project_id=project2.id,
        )

        result = discover.timeseries_query(
            selected_columns=["release", "count()"],
            query="(release:{} OR release:{}) AND project:{}".format(
                "a" * 32, "b" * 32, self.project.slug
            ),
            snuba_params=SnubaParams(
                start=before_now(minutes=5),
                end=before_now(seconds=1),
                projects=[self.project, project2],
            ),
            rollup=3600,
            referrer="test_discover_query",
        )

        data = result.data["data"]
        data = result.data["data"]
        assert len([d for d in data if "count" in d]) == 1
        for d in data:
            if "count" in d:
                assert d["count"] == 2
