import pytest

from sentry.exceptions import InvalidSearchQuery
from sentry.search.events.types import SnubaParams
from sentry.snuba import discover
from sentry.testutils.cases import SnubaTestCase, TestCase
from sentry.testutils.helpers.datetime import before_now


class GetFacetsTest(SnubaTestCase, TestCase):
    def setUp(self) -> None:
        super().setUp()

        self.project = self.create_project()
        self.min_ago = before_now(minutes=1)
        self.day_ago = before_now(days=1)

    def test_invalid_query(self) -> None:
        with pytest.raises(InvalidSearchQuery):
            discover.get_facets(
                "\n",
                SnubaParams(projects=[self.project], end=self.min_ago, start=self.day_ago),
                "testing.get-facets-test",
            )

    def test_no_results(self) -> None:
        results = discover.get_facets(
            "",
            SnubaParams(projects=[self.project], end=self.min_ago, start=self.day_ago),
            "testing.get-facets-test",
        )
        assert results == []

    def test_single_project(self) -> None:
        self.store_event(
            data={
                "message": "very bad",
                "type": "default",
                "timestamp": before_now(minutes=2).isoformat(),
                "tags": {"color": "red", "paying": "1"},
            },
            project_id=self.project.id,
        )
        self.store_event(
            data={
                "message": "very bad",
                "type": "default",
                "timestamp": before_now(minutes=2).isoformat(),
                "tags": {"color": "blue", "paying": "0"},
            },
            project_id=self.project.id,
        )
        result = discover.get_facets(
            "",
            SnubaParams(projects=[self.project], start=self.day_ago, end=self.min_ago),
            "testing.get-facets-test",
        )
        assert len(result) == 5
        assert {r.key for r in result} == {"color", "paying", "level"}
        assert {r.value for r in result} == {"red", "blue", "1", "0", "error"}
        assert {r.count for r in result} == {1, 2}

    def test_project_filter(self) -> None:
        self.store_event(
            data={
                "message": "very bad",
                "type": "default",
                "timestamp": before_now(minutes=2).isoformat(),
                "tags": {"color": "red"},
            },
            project_id=self.project.id,
        )
        other_project = self.create_project()
        self.store_event(
            data={
                "message": "very bad",
                "type": "default",
                "timestamp": before_now(minutes=2).isoformat(),
                "tags": {"toy": "train"},
            },
            project_id=other_project.id,
        )
        params = SnubaParams(projects=[self.project], start=self.day_ago, end=self.min_ago)
        result = discover.get_facets("", params, "testing.get-facets-test")
        keys = {r.key for r in result}
        assert keys == {"color", "level"}

        # Query more than one project.
        params = SnubaParams(
            projects=[self.project, other_project], start=self.day_ago, end=self.min_ago
        )
        result = discover.get_facets("", params, "testing.get-facets-test")
        keys = {r.key for r in result}
        assert keys == {"level", "toy", "color", "project"}

        projects = [f for f in result if f.key == "project"]
        assert [p.count for p in projects] == [1, 1]

    def test_environment_promoted_tag(self) -> None:
        for env in ("prod", "staging", None):
            self.store_event(
                data={
                    "message": "very bad",
                    "type": "default",
                    "environment": env,
                    "timestamp": before_now(minutes=2).isoformat(),
                },
                project_id=self.project.id,
            )
        result = discover.get_facets(
            "",
            SnubaParams(projects=[self.project], start=self.day_ago, end=self.min_ago),
            "testing.get-facets-test",
        )
        keys = {r.key for r in result}
        assert keys == {"environment", "level"}
        assert {None, "prod", "staging"} == {f.value for f in result if f.key == "environment"}
        assert {1} == {f.count for f in result if f.key == "environment"}

    def test_query_string(self) -> None:
        self.store_event(
            data={
                "message": "very bad",
                "type": "default",
                "timestamp": before_now(minutes=2).isoformat(),
                "tags": {"color": "red"},
            },
            project_id=self.project.id,
        )
        self.store_event(
            data={
                "message": "oh my",
                "type": "default",
                "timestamp": before_now(minutes=2).isoformat(),
                "tags": {"toy": "train"},
            },
            project_id=self.project.id,
        )
        params = SnubaParams(projects=[self.project], start=self.day_ago, end=self.min_ago)
        result = discover.get_facets("bad", params, "testing.get-facets-test")
        keys = {r.key for r in result}
        assert "color" in keys
        assert "toy" not in keys

        result = discover.get_facets("color:red", params, "testing.get-facets-test")
        keys = {r.key for r in result}
        assert "color" in keys
        assert "toy" not in keys

    def test_query_string_with_aggregate_condition(self) -> None:
        self.store_event(
            data={
                "message": "very bad",
                "type": "default",
                "timestamp": before_now(minutes=2).isoformat(),
                "tags": {"color": "red"},
            },
            project_id=self.project.id,
        )
        self.store_event(
            data={
                "message": "oh my",
                "type": "default",
                "timestamp": before_now(minutes=2).isoformat(),
                "tags": {"toy": "train"},
            },
            project_id=self.project.id,
        )
        params = SnubaParams(projects=[self.project], start=self.day_ago, end=self.min_ago)
        result = discover.get_facets("bad", params, "testing.get-facets-test")
        keys = {r.key for r in result}
        assert "color" in keys
        assert "toy" not in keys

        result = discover.get_facets("color:red p95():>1", params, "testing.get-facets-test")
        keys = {r.key for r in result}
        assert "color" in keys
        assert "toy" not in keys

    def test_date_params(self) -> None:
        self.store_event(
            data={
                "message": "very bad",
                "type": "default",
                "timestamp": before_now(minutes=2).isoformat(),
                "tags": {"color": "red"},
            },
            project_id=self.project.id,
        )
        self.store_event(
            data={
                "message": "oh my",
                "type": "default",
                "timestamp": before_now(days=2).isoformat(),
                "tags": {"toy": "train"},
            },
            project_id=self.project.id,
        )
        result = discover.get_facets(
            "",
            SnubaParams(projects=[self.project], start=self.day_ago, end=self.min_ago),
            "testing.get-facets-test",
        )
        keys = {r.key for r in result}
        assert "color" in keys
        assert "toy" not in keys

    def test_count_sorting(self) -> None:
        for _ in range(5):
            self.store_event(
                data={
                    "message": "very bad",
                    "type": "default",
                    "timestamp": before_now(minutes=2).isoformat(),
                    "tags": {"color": "zzz"},
                },
                project_id=self.project.id,
            )
        # aaa is before zzz, but there's more zzz so it should show up first
        self.store_event(
            data={
                "message": "oh my",
                "type": "default",
                "timestamp": before_now(minutes=2).isoformat(),
                "tags": {"color": "aaa"},
            },
            project_id=self.project.id,
        )
        result = discover.get_facets(
            "",
            SnubaParams(projects=[self.project], start=self.day_ago, end=self.min_ago),
            "testing.get-facets-test",
        )
        first = result[0]
        assert first.key == "color"
        assert first.value == "zzz"
        second = result[1]
        assert second.key == "color"
        assert second.value == "aaa"
