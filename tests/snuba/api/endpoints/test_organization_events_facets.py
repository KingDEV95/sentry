from datetime import timedelta
from unittest import mock
from uuid import uuid4

import requests
from django.urls import reverse
from django.utils import timezone
from rest_framework.exceptions import ParseError

from sentry.testutils.cases import APITestCase, SnubaTestCase
from sentry.testutils.helpers.datetime import before_now


class OrganizationEventsFacetsEndpointTest(SnubaTestCase, APITestCase):
    def setUp(self):
        super().setUp()
        self.min_ago = before_now(minutes=1).replace(microsecond=0)
        self.day_ago = before_now(days=1).replace(microsecond=0)
        self.login_as(user=self.user)
        self.project = self.create_project()
        self.project2 = self.create_project()
        self.url = reverse(
            "sentry-api-0-organization-events-facets",
            kwargs={"organization_id_or_slug": self.project.organization.slug},
        )
        self.min_ago_iso = self.min_ago.isoformat()
        self.features = {"organizations:discover-basic": True, "organizations:global-views": True}

    def assert_facet(self, response, key, expected):
        actual = None
        for facet in response.data:
            if facet["key"] == key:
                actual = facet
                break
        assert actual is not None, f"Could not find {key} facet in {response.data}"
        assert "topValues" in actual
        key = lambda row: row["name"] if row["name"] is not None else ""
        assert sorted(expected, key=key) == sorted(actual["topValues"], key=key)

    def test_performance_view_feature(self) -> None:
        self.features.update(
            {
                "organizations:discover-basic": False,
                "organizations:performance-view": True,
            }
        )
        with self.feature(self.features):
            response = self.client.get(self.url, data={"project": self.project.id}, format="json")

        assert response.status_code == 200, response.content

    def test_simple(self) -> None:
        self.store_event(
            data={
                "event_id": uuid4().hex,
                "timestamp": self.min_ago_iso,
                "tags": {"number": "one"},
            },
            project_id=self.project2.id,
        )
        self.store_event(
            data={
                "event_id": uuid4().hex,
                "timestamp": self.min_ago_iso,
                "tags": {"number": "one"},
            },
            project_id=self.project.id,
        )
        self.store_event(
            data={
                "event_id": uuid4().hex,
                "timestamp": self.min_ago_iso,
                "tags": {"number": "two"},
            },
            project_id=self.project.id,
        )

        with self.feature(self.features):
            response = self.client.get(self.url, format="json")

        assert response.status_code == 200, response.content
        expected = [
            {"count": 2, "name": "one", "value": "one"},
            {"count": 1, "name": "two", "value": "two"},
        ]
        self.assert_facet(response, "number", expected)

    def test_order_by(self) -> None:
        self.store_event(
            data={
                "event_id": uuid4().hex,
                "timestamp": self.min_ago_iso,
                "tags": {"alpha": "one"},
                "environment": "aaaa",
            },
            project_id=self.project2.id,
        )
        self.store_event(
            data={
                "event_id": uuid4().hex,
                "timestamp": self.min_ago_iso,
                "tags": {"beta": "one"},
                "environment": "bbbb",
            },
            project_id=self.project.id,
        )
        self.store_event(
            data={
                "event_id": uuid4().hex,
                "timestamp": self.min_ago_iso,
                "tags": {"charlie": "two"},
                "environment": "cccc",
            },
            project_id=self.project.id,
        )

        with self.feature(self.features):
            response = self.client.get(self.url, format="json")

        assert response.status_code == 200, response.content
        keys = [facet["key"] for facet in response.data]
        assert ["alpha", "beta", "charlie", "environment", "level", "project"] == keys

    def test_with_message_query(self) -> None:
        self.store_event(
            data={
                "event_id": uuid4().hex,
                "timestamp": self.min_ago_iso,
                "message": "how to make fast",
                "tags": {"color": "green"},
            },
            project_id=self.project.id,
        )
        self.store_event(
            data={
                "event_id": uuid4().hex,
                "timestamp": self.min_ago_iso,
                "message": "Delet the Data",
                "tags": {"color": "red"},
            },
            project_id=self.project.id,
        )
        self.store_event(
            data={
                "event_id": uuid4().hex,
                "timestamp": self.min_ago_iso,
                "message": "Data the Delet ",
                "tags": {"color": "yellow"},
            },
            project_id=self.project2.id,
        )

        with self.feature(self.features):
            response = self.client.get(self.url, {"query": "delet"}, format="json")

        assert response.status_code == 200, response.content
        expected = [
            {"count": 1, "name": "yellow", "value": "yellow"},
            {"count": 1, "name": "red", "value": "red"},
        ]
        self.assert_facet(response, "color", expected)

    def test_with_condition(self) -> None:
        self.store_event(
            data={
                "event_id": uuid4().hex,
                "timestamp": self.min_ago_iso,
                "message": "how to make fast",
                "tags": {"color": "green"},
            },
            project_id=self.project.id,
        )
        self.store_event(
            data={
                "event_id": uuid4().hex,
                "timestamp": self.min_ago_iso,
                "message": "Delet the Data",
                "tags": {"color": "red"},
            },
            project_id=self.project.id,
        )
        self.store_event(
            data={
                "event_id": uuid4().hex,
                "timestamp": self.min_ago_iso,
                "message": "Data the Delet ",
                "tags": {"color": "yellow"},
            },
            project_id=self.project2.id,
        )

        with self.feature(self.features):
            response = self.client.get(self.url, {"query": "color:yellow"}, format="json")

        assert response.status_code == 200, response.content
        expected = [{"count": 1, "name": "yellow", "value": "yellow"}]
        self.assert_facet(response, "color", expected)

    def test_with_conditional_filter(self) -> None:
        self.store_event(
            data={
                "event_id": uuid4().hex,
                "timestamp": self.min_ago_iso,
                "message": "how to make fast",
                "tags": {"color": "green"},
            },
            project_id=self.project.id,
        )
        self.store_event(
            data={
                "event_id": uuid4().hex,
                "timestamp": self.min_ago_iso,
                "message": "Delet the Data",
                "tags": {"color": "red"},
            },
            project_id=self.project.id,
        )
        self.store_event(
            data={
                "event_id": uuid4().hex,
                "timestamp": self.min_ago_iso,
                "message": "Data the Delet ",
                "tags": {"color": "yellow"},
            },
            project_id=self.project2.id,
        )

        with self.feature(self.features):
            response = self.client.get(
                self.url, {"query": "color:yellow OR color:red"}, format="json"
            )

        assert response.status_code == 200, response.content
        expected = [
            {"count": 1, "name": "yellow", "value": "yellow"},
            {"count": 1, "name": "red", "value": "red"},
        ]
        self.assert_facet(response, "color", expected)

    def test_start_end(self) -> None:
        two_days_ago = self.day_ago - timedelta(days=1)
        hour_ago = self.min_ago - timedelta(hours=1)
        two_hours_ago = hour_ago - timedelta(hours=1)

        self.store_event(
            data={
                "event_id": uuid4().hex,
                "timestamp": two_days_ago.isoformat(),
                "tags": {"color": "red"},
            },
            project_id=self.project.id,
        )
        self.store_event(
            data={
                "event_id": uuid4().hex,
                "timestamp": hour_ago.isoformat(),
                "tags": {"color": "red"},
            },
            project_id=self.project.id,
        )
        self.store_event(
            data={
                "event_id": uuid4().hex,
                "timestamp": two_hours_ago.isoformat(),
                "tags": {"color": "red"},
            },
            project_id=self.project.id,
        )
        self.store_event(
            data={
                "event_id": uuid4().hex,
                "timestamp": timezone.now().isoformat(),
                "tags": {"color": "red"},
            },
            project_id=self.project2.id,
        )

        with self.feature(self.features):
            response = self.client.get(
                self.url,
                {"start": self.day_ago.isoformat(), "end": self.min_ago.isoformat()},
                format="json",
            )

        assert response.status_code == 200, response.content
        expected = [{"count": 2, "name": "red", "value": "red"}]
        self.assert_facet(response, "color", expected)

    def test_excluded_tag(self) -> None:
        self.user = self.create_user()
        self.user2 = self.create_user()
        self.store_event(
            data={
                "event_id": uuid4().hex,
                "timestamp": self.day_ago.isoformat(),
                "message": "very bad",
                "tags": {"sentry:user": self.user.email},
            },
            project_id=self.project.id,
        )
        self.store_event(
            data={
                "event_id": uuid4().hex,
                "timestamp": self.day_ago.isoformat(),
                "message": "very bad",
                "tags": {"sentry:user": self.user2.email},
            },
            project_id=self.project.id,
        )
        self.store_event(
            data={
                "event_id": uuid4().hex,
                "timestamp": self.day_ago.isoformat(),
                "message": "very bad",
                "tags": {"sentry:user": self.user2.email},
            },
            project_id=self.project.id,
        )

        with self.feature(self.features):
            response = self.client.get(self.url, format="json", data={"project": [self.project.id]})

        assert response.status_code == 200, response.content
        expected = [
            {"count": 2, "name": self.user2.email, "value": self.user2.email},
            {"count": 1, "name": self.user.email, "value": self.user.email},
        ]
        self.assert_facet(response, "user", expected)

    def test_no_projects(self) -> None:
        org = self.create_organization(owner=self.user)
        url = reverse(
            "sentry-api-0-organization-events-facets", kwargs={"organization_id_or_slug": org.slug}
        )
        with self.feature("organizations:discover-basic"):
            response = self.client.get(url, format="json")
        assert response.status_code == 200, response.content
        assert response.data == []

    def test_multiple_projects_without_global_view(self) -> None:
        self.store_event(data={"event_id": uuid4().hex}, project_id=self.project.id)
        self.store_event(data={"event_id": uuid4().hex}, project_id=self.project2.id)

        with self.feature("organizations:discover-basic"):
            response = self.client.get(self.url, format="json")
        assert response.status_code == 400, response.content
        assert response.data == {"detail": "You cannot view events from multiple projects."}

    def test_project_selected(self) -> None:
        self.store_event(
            data={
                "event_id": uuid4().hex,
                "timestamp": self.min_ago_iso,
                "tags": {"number": "two"},
            },
            project_id=self.project.id,
        )
        self.store_event(
            data={
                "event_id": uuid4().hex,
                "timestamp": self.min_ago_iso,
                "tags": {"number": "one"},
            },
            project_id=self.project2.id,
        )

        with self.feature(self.features):
            response = self.client.get(self.url, {"project": [self.project.id]}, format="json")

        assert response.status_code == 200, response.content
        expected = [{"name": "two", "value": "two", "count": 1}]
        self.assert_facet(response, "number", expected)

    def test_project_filtered(self) -> None:
        self.store_event(
            data={
                "event_id": uuid4().hex,
                "timestamp": self.min_ago_iso,
                "tags": {"number": "two"},
            },
            project_id=self.project.id,
        )
        self.store_event(
            data={
                "event_id": uuid4().hex,
                "timestamp": self.min_ago_iso,
                "tags": {"number": "one"},
            },
            project_id=self.project2.id,
        )

        with self.feature(self.features):
            response = self.client.get(
                self.url, {"query": f"project:{self.project.slug}"}, format="json"
            )

        assert response.status_code == 200, response.content
        expected = [{"name": "two", "value": "two", "count": 1}]
        self.assert_facet(response, "number", expected)

    def test_project_key(self) -> None:
        self.store_event(
            data={
                "event_id": uuid4().hex,
                "timestamp": self.min_ago_iso,
                "tags": {"color": "green"},
            },
            project_id=self.project.id,
        )
        self.store_event(
            data={
                "event_id": uuid4().hex,
                "timestamp": self.min_ago_iso,
                "tags": {"number": "one"},
            },
            project_id=self.project2.id,
        )
        self.store_event(
            data={
                "event_id": uuid4().hex,
                "timestamp": self.min_ago_iso,
                "tags": {"color": "green"},
            },
            project_id=self.project.id,
        )
        self.store_event(
            data={"event_id": uuid4().hex, "timestamp": self.min_ago_iso, "tags": {"color": "red"}},
            project_id=self.project.id,
        )

        with self.feature(self.features):
            response = self.client.get(self.url, format="json")

        assert response.status_code == 200, response.content
        expected = [
            {"count": 3, "name": self.project.slug, "value": self.project.id},
            {"count": 1, "name": self.project2.slug, "value": self.project2.id},
        ]
        self.assert_facet(response, "project", expected)

    def test_project_key_with_project_tag(self) -> None:
        self.organization.flags.allow_joinleave = False
        self.organization.save()

        member_user = self.create_user()
        team = self.create_team(members=[member_user])
        private_project1 = self.create_project(organization=self.organization, teams=[team])
        private_project2 = self.create_project(organization=self.organization, teams=[team])
        self.login_as(member_user)

        self.store_event(
            data={
                "event_id": uuid4().hex,
                "timestamp": self.min_ago_iso,
                "tags": {"color": "green", "project": "%d" % private_project1.id},
            },
            project_id=self.project.id,
        )
        self.store_event(
            data={
                "event_id": uuid4().hex,
                "timestamp": self.min_ago_iso,
                "tags": {"number": "one", "project": "%d" % private_project1.id},
            },
            project_id=private_project1.id,
        )
        self.store_event(
            data={
                "event_id": uuid4().hex,
                "timestamp": self.min_ago_iso,
                "tags": {"color": "green"},
            },
            project_id=private_project1.id,
        )
        self.store_event(
            data={"event_id": uuid4().hex, "timestamp": self.min_ago_iso, "tags": {"color": "red"}},
            project_id=private_project2.id,
        )
        self.store_event(
            data={"event_id": uuid4().hex, "timestamp": self.min_ago_iso, "tags": {"color": "red"}},
            project_id=private_project2.id,
        )

        with self.feature(self.features):
            response = self.client.get(self.url, format="json")

        assert response.status_code == 200, response.content
        expected = [
            {"count": 2, "name": private_project1.slug, "value": private_project1.id},
            {"count": 2, "name": private_project2.slug, "value": private_project2.id},
        ]

        self.assert_facet(response, "project", expected)

    def test_malformed_query(self) -> None:
        self.store_event(data={"event_id": uuid4().hex}, project_id=self.project.id)
        self.store_event(data={"event_id": uuid4().hex}, project_id=self.project2.id)

        with self.feature(self.features):
            response = self.client.get(self.url, format="json", data={"query": "\n\n\n\n"})
        assert response.status_code == 400, response.content
        assert response.data["detail"].endswith(
            "(column 1). This is commonly caused by unmatched parentheses. Enclose any text in double quotes."
        )

    @mock.patch("sentry.search.events.builder.base.raw_snql_query")
    def test_handling_snuba_errors(self, mock_query: mock.MagicMock) -> None:
        mock_query.side_effect = ParseError("test")
        with self.feature(self.features):
            response = self.client.get(self.url, format="json")

        assert response.status_code == 400, response.content

    def test_environment(self) -> None:
        self.store_event(
            data={
                "event_id": uuid4().hex,
                "timestamp": self.min_ago_iso,
                "tags": {"number": "one"},
                "environment": "staging",
            },
            project_id=self.project2.id,
        )
        self.store_event(
            data={
                "event_id": uuid4().hex,
                "timestamp": self.min_ago_iso,
                "tags": {"number": "one"},
                "environment": "production",
            },
            project_id=self.project.id,
        )
        self.store_event(
            data={
                "event_id": uuid4().hex,
                "timestamp": self.min_ago_iso,
                "tags": {"number": "two"},
            },
            project_id=self.project.id,
        )

        with self.feature(self.features):
            response = self.client.get(self.url, format="json")

            assert response.status_code == 200, response.content
            expected = [
                {"count": 1, "name": "production", "value": "production"},
                {"count": 1, "name": "staging", "value": "staging"},
                {"count": 1, "name": None, "value": None},
            ]
            self.assert_facet(response, "environment", expected)

        with self.feature(self.features):
            # query by an environment
            response = self.client.get(self.url, {"environment": "staging"}, format="json")

            assert response.status_code == 200, response.content
            expected = [{"count": 1, "name": "staging", "value": "staging"}]
            self.assert_facet(response, "environment", expected)

        with self.feature(self.features):
            # query by multiple environments
            response = self.client.get(
                self.url, {"environment": ["staging", "production"]}, format="json"
            )

            assert response.status_code == 200, response.content

            expected = [
                {"count": 1, "name": "production", "value": "production"},
                {"count": 1, "name": "staging", "value": "staging"},
            ]
            self.assert_facet(response, "environment", expected)

        with self.feature(self.features):
            # query by multiple environments, including the "no environment" environment
            response = self.client.get(
                self.url, {"environment": ["staging", "production", ""]}, format="json"
            )
            assert response.status_code == 200, response.content
            expected = [
                {"count": 1, "name": "production", "value": "production"},
                {"count": 1, "name": "staging", "value": "staging"},
                {"count": 1, "name": None, "value": None},
            ]
            self.assert_facet(response, "environment", expected)

    def test_out_of_retention(self) -> None:
        with self.options({"system.event-retention-days": 10}):
            with self.feature(self.features):
                response = self.client.get(
                    self.url,
                    format="json",
                    data={
                        "start": before_now(days=20).isoformat(),
                        "end": before_now(days=15).isoformat(),
                    },
                )
        assert response.status_code == 400

    @mock.patch("sentry.utils.snuba.quantize_time")
    def test_quantize_dates(self, mock_quantize: mock.MagicMock) -> None:
        mock_quantize.return_value = before_now(days=1)
        with self.feature("organizations:discover-basic"):
            # Don't quantize short time periods
            self.client.get(
                self.url,
                format="json",
                data={"statsPeriod": "1h", "query": "", "field": ["id", "timestamp"]},
            )
            # Don't quantize absolute date periods
            self.client.get(
                self.url,
                format="json",
                data={
                    "start": before_now(days=20).isoformat(),
                    "end": before_now(days=15).isoformat(),
                    "query": "",
                    "field": ["id", "timestamp"],
                },
            )

            assert len(mock_quantize.mock_calls) == 0

            # Quantize long date periods
            self.client.get(
                self.url,
                format="json",
                data={"field": ["id", "timestamp"], "statsPeriod": "90d", "query": ""},
            )

            assert len(mock_quantize.mock_calls) == 2

    def test_device_class(self) -> None:
        self.store_event(
            data={
                "event_id": uuid4().hex,
                "timestamp": self.min_ago_iso,
                "tags": {"device.class": "1"},
            },
            project_id=self.project2.id,
        )
        self.store_event(
            data={
                "event_id": uuid4().hex,
                "timestamp": self.min_ago_iso,
                "tags": {"device.class": "2"},
            },
            project_id=self.project.id,
        )
        self.store_event(
            data={
                "event_id": uuid4().hex,
                "timestamp": self.min_ago_iso,
                "tags": {"device.class": "3"},
            },
            project_id=self.project.id,
        )

        with self.feature(self.features):
            response = self.client.get(self.url, format="json")

        assert response.status_code == 200, response.content
        expected = [
            {"count": 1, "name": "high", "value": "high"},
            {"count": 1, "name": "medium", "value": "medium"},
            {"count": 1, "name": "low", "value": "low"},
        ]
        self.assert_facet(response, "device.class", expected)

    def test_with_cursor_parameter(self) -> None:
        test_project = self.create_project()
        test_tags = {
            "a": "one",
            "b": "two",
            "c": "three",
            "d": "four",
            "e": "five",
            "f": "six",
            "g": "seven",
            "h": "eight",
            "i": "nine",
            "j": "ten",
            "k": "eleven",
        }

        self.store_event(
            data={"event_id": uuid4().hex, "timestamp": self.min_ago_iso, "tags": test_tags},
            project_id=test_project.id,
        )

        # Test the default query fetches the first 10 results
        with self.feature(self.features):
            response = self.client.get(self.url, format="json", data={"project": test_project.id})
            links = requests.utils.parse_header_links(
                response.get("link", "").rstrip(">").replace(">,<", ",<")
            )

        assert response.status_code == 200, response.content
        assert links[1]["results"] == "true"  # There are more results to be fetched
        assert links[1]["cursor"] == "0:10:0"
        assert len(response.data) == 10

        # Loop over the first 10 tags to ensure they're in the results
        for tag_key in list(test_tags.keys())[:10]:
            expected = [
                {"count": 1, "name": test_tags[tag_key], "value": test_tags[tag_key]},
            ]
            self.assert_facet(response, tag_key, expected)

        # Get the next page
        with self.feature(self.features):
            response = self.client.get(
                self.url, format="json", data={"project": str(test_project.id), "cursor": "0:10:0"}
            )
            links = requests.utils.parse_header_links(
                response.get("link", "").rstrip(">").replace(">,<", ",<")
            )

        assert response.status_code == 200, response.content
        assert links[1]["results"] == "false"  # There should be no more tags to fetch
        assert len(response.data) == 2
        expected = [
            {"count": 1, "name": "eleven", "value": "eleven"},
        ]
        self.assert_facet(response, "k", expected)
        expected = [
            {"count": 1, "name": "error", "value": "error"},
        ]
        self.assert_facet(response, "level", expected)

    def test_projects_data_are_injected_on_first_page_with_multiple_projects_selected(self) -> None:
        test_project = self.create_project()
        test_project2 = self.create_project()
        test_tags = {
            "a": "one",
            "b": "two",
            "c": "three",
            "d": "four",
            "e": "five",
            "f": "six",
            "g": "seven",
            "h": "eight",
            "i": "nine",
            "j": "ten",
            "k": "eleven",
        }

        self.store_event(
            data={"event_id": uuid4().hex, "timestamp": self.min_ago_iso, "tags": test_tags},
            project_id=test_project.id,
        )

        # Test the default query fetches the first 10 results
        with self.feature(self.features):
            response = self.client.get(
                self.url, format="json", data={"project": [test_project.id, test_project2.id]}
            )
            links = requests.utils.parse_header_links(
                response.get("link", "").rstrip(">").replace(">,<", ",<")
            )

        assert response.status_code == 200, response.content
        assert links[1]["results"] == "true"  # There are more results to be fetched
        assert links[1]["cursor"] == "0:10:0"
        assert len(response.data) == 10

        # Project is injected into the first page
        expected = [
            {"count": 1, "name": test_project.slug, "value": test_project.id},
        ]
        self.assert_facet(response, "project", expected)

        # Loop over the first 9 tags to ensure they're in the results
        # in this case, the 10th key is "projects" since it was injected
        for tag_key in list(test_tags.keys())[:9]:
            expected = [
                {"count": 1, "name": test_tags[tag_key], "value": test_tags[tag_key]},
            ]
            self.assert_facet(response, tag_key, expected)

        # Get the next page
        with self.feature(self.features):
            response = self.client.get(
                self.url,
                format="json",
                data={"project": [str(test_project.id), str(test_project2.id)], "cursor": "0:10:0"},
            )
            links = requests.utils.parse_header_links(
                response.get("link", "").rstrip(">").replace(">,<", ",<")
            )

        assert response.status_code == 200, response.content
        assert links[1]["results"] == "false"  # There should be no more tags to fetch
        assert len(response.data) == 3
        expected = [
            {"count": 1, "name": "ten", "value": "ten"},
        ]
        self.assert_facet(response, "j", expected)
        expected = [
            {"count": 1, "name": "eleven", "value": "eleven"},
        ]
        self.assert_facet(response, "k", expected)
        expected = [
            {"count": 1, "name": "error", "value": "error"},
        ]
        self.assert_facet(response, "level", expected)

    def test_multiple_pages_with_single_project(self) -> None:
        test_project = self.create_project()
        test_tags = {str(i): str(i) for i in range(22)}

        self.store_event(
            data={"event_id": uuid4().hex, "timestamp": self.min_ago_iso, "tags": test_tags},
            project_id=test_project.id,
        )

        # Test the default query fetches the first 10 results
        with self.feature(self.features):
            response = self.client.get(self.url, format="json", data={"project": test_project.id})
            links = requests.utils.parse_header_links(
                response.get("link", "").rstrip(">").replace(">,<", ",<")
            )

        assert response.status_code == 200, response.content
        assert links[1]["results"] == "true"  # There are more results to be fetched
        assert links[1]["cursor"] == "0:10:0"
        assert len(response.data) == 10

        # Get the next page
        with self.feature(self.features):
            response = self.client.get(
                self.url,
                format="json",
                data={"project": str(test_project.id), "cursor": links[1]["cursor"]},
            )
            links = requests.utils.parse_header_links(
                response.get("link", "").rstrip(">").replace(">,<", ",<")
            )

        assert response.status_code == 200, response.content
        assert links[1]["results"] == "true"  # There are more tags to fetch
        assert len(response.data) == 10

        # Get the next page
        with self.feature(self.features):
            response = self.client.get(
                self.url,
                format="json",
                data={"project": str(test_project.id), "cursor": links[1]["cursor"]},
            )
            links = requests.utils.parse_header_links(
                response.get("link", "").rstrip(">").replace(">,<", ",<")
            )

        assert response.status_code == 200, response.content
        assert links[1]["results"] == "false"  # There should be no more tags to fetch
        assert len(response.data) == 3

    def test_multiple_pages_with_multiple_projects(self) -> None:
        test_project = self.create_project()
        test_project2 = self.create_project()
        test_tags = {str(i): str(i) for i in range(22)}  # At least 3 pages worth of information

        self.store_event(
            data={"event_id": uuid4().hex, "timestamp": self.min_ago_iso, "tags": test_tags},
            project_id=test_project.id,
        )

        # Test the default query fetches the first 10 results
        with self.feature(self.features):
            response = self.client.get(
                self.url, format="json", data={"project": [test_project.id, test_project2.id]}
            )
            links = requests.utils.parse_header_links(
                response.get("link", "").rstrip(">").replace(">,<", ",<")
            )

        assert response.status_code == 200, response.content
        assert links[1]["results"] == "true"  # There are more results to be fetched
        assert links[1]["cursor"] == "0:10:0"
        assert len(response.data) == 10

        # Get the next page
        with self.feature(self.features):
            response = self.client.get(
                self.url,
                format="json",
                data={
                    "project": [str(test_project.id), str(test_project2.id)],
                    "cursor": links[1]["cursor"],
                },
            )
            links = requests.utils.parse_header_links(
                response.get("link", "").rstrip(">").replace(">,<", ",<")
            )

        assert response.status_code == 200, response.content
        assert links[1]["results"] == "true"  # There are more tags to fetch
        assert len(response.data) == 10

        # Get the next page
        with self.feature(self.features):
            response = self.client.get(
                self.url,
                format="json",
                data={
                    "project": [str(test_project.id), str(test_project2.id)],
                    "cursor": links[1]["cursor"],
                },
            )
            links = requests.utils.parse_header_links(
                response.get("link", "").rstrip(">").replace(">,<", ",<")
            )

        assert response.status_code == 200, response.content
        assert links[1]["results"] == "false"  # There should be no more tags to fetch
        assert len(response.data) == 4  # 4 because projects and levels were added to the base 22

    def test_get_all_tags(self) -> None:
        test_project = self.create_project()
        test_tags = {str(i): str(i) for i in range(22)}

        self.store_event(
            data={"event_id": uuid4().hex, "timestamp": self.min_ago_iso, "tags": test_tags},
            project_id=test_project.id,
        )

        # Test the default query fetches the first 10 results
        with self.feature(self.features):
            response = self.client.get(
                self.url, format="json", data={"project": test_project.id, "includeAll": True}
            )

        assert response.status_code == 200, response.content
        assert len(response.data) == 23

    @mock.patch("sentry.search.events.builder.base.raw_snql_query")
    def test_dont_turbo_trace_queries(self, mock_run: mock.MagicMock) -> None:
        # Need to create more projects so we'll even want to turbo in the first place
        for _ in range(3):
            self.create_project()
        with self.feature(self.features):
            self.client.get(self.url, {"query": f"trace:{'a' * 32}"}, format="json")

        mock_run.assert_called_once
        assert not mock_run.mock_calls[0].args[0].flags.turbo

    @mock.patch("sentry.search.events.builder.base.raw_snql_query")
    def test_use_turbo_without_trace(self, mock_run: mock.MagicMock) -> None:
        # Need to create more projects so we'll even want to turbo in the first place
        for _ in range(3):
            self.create_project()
        with self.feature(self.features):
            self.client.get(self.url, format="json")

        mock_run.assert_called_once
        assert mock_run.mock_calls[0].args[0].flags.turbo
