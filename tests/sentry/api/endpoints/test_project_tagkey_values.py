import urllib.parse

from django.urls import reverse

from sentry.testutils.cases import APITestCase, SnubaTestCase
from sentry.testutils.helpers.datetime import before_now


class ProjectTagKeyValuesTest(APITestCase, SnubaTestCase):
    def test_simple(self) -> None:
        project = self.create_project()
        self.store_event(
            data={"tags": {"foo": "bar"}, "timestamp": before_now(seconds=1).isoformat()},
            project_id=project.id,
        )

        self.login_as(user=self.user)

        url = reverse(
            "sentry-api-0-project-tagkey-values",
            kwargs={
                "organization_id_or_slug": project.organization.slug,
                "project_id_or_slug": project.slug,
                "key": "foo",
            },
        )

        response = self.client.get(url)

        assert response.status_code == 200
        assert len(response.data) == 1

        assert response.data[0]["value"] == "bar"

    def test_query(self) -> None:
        project = self.create_project()
        self.store_event(
            data={"tags": {"foo": "bar"}, "timestamp": before_now(seconds=1).isoformat()},
            project_id=project.id,
        )

        self.login_as(user=self.user)

        url = reverse(
            "sentry-api-0-project-tagkey-values",
            kwargs={
                "organization_id_or_slug": project.organization.slug,
                "project_id_or_slug": project.slug,
                "key": "foo",
            },
        )
        response = self.client.get(url + "?query=bar")

        assert response.status_code == 200
        assert len(response.data) == 1

        assert response.data[0]["value"] == "bar"

        response = self.client.get(url + "?query=foo")

        assert response.status_code == 200
        assert len(response.data) == 0

    def test_statperiod_query(self) -> None:
        project = self.create_project()
        self.store_event(
            data={"tags": {"foo": "bar"}, "timestamp": before_now(days=15).isoformat()},
            project_id=project.id,
        )

        self.login_as(user=self.user)

        url = reverse(
            "sentry-api-0-project-tagkey-values",
            kwargs={
                "organization_id_or_slug": project.organization.slug,
                "project_id_or_slug": project.slug,
                "key": "foo",
            },
        )
        response = self.client.get(url + "?query=bar&statsPeriod=14d")

        assert response.status_code == 200
        assert len(response.data) == 0

        response = self.client.get(url + "?query=bar&statsPeriod=30d")

        assert response.status_code == 200
        assert len(response.data) == 1
        assert response.data[0]["value"] == "bar"

    def test_start_end_query(self) -> None:
        project = self.create_project()
        self.store_event(
            data={"tags": {"foo": "bar"}, "timestamp": before_now(days=15).isoformat()},
            project_id=project.id,
        )

        self.login_as(user=self.user)

        url = reverse(
            "sentry-api-0-project-tagkey-values",
            kwargs={
                "organization_id_or_slug": project.organization.slug,
                "project_id_or_slug": project.slug,
                "key": "foo",
            },
        )

        response = self.client.get(
            url
            + "?"
            + urllib.parse.urlencode(
                {
                    "query": "bar",
                    "start": before_now(days=14).isoformat(),
                    "end": before_now(seconds=1).isoformat(),
                }
            )
        )

        assert response.status_code == 200
        assert len(response.data) == 0

        response = self.client.get(
            url
            + "?"
            + urllib.parse.urlencode(
                {
                    "query": "bar",
                    "start": before_now(days=16).isoformat(),
                    "end": before_now(days=14).isoformat(),
                }
            )
        )

        assert response.status_code == 200
        assert len(response.data) == 1
        assert response.data[0]["value"] == "bar"
