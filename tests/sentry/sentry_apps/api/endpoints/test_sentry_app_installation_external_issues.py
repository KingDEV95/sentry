from unittest.mock import MagicMock, patch

from django.urls import reverse

from sentry.sentry_apps.models.platformexternalissue import PlatformExternalIssue
from sentry.testutils.cases import APITestCase


class SentryAppInstallationExternalIssuesEndpointTest(APITestCase):
    def setUp(self) -> None:
        self.superuser = self.create_user(email="a@example.com", is_superuser=True)
        self.user = self.create_user(email="boop@example.com")
        self.org = self.create_organization(owner=self.user)
        self.project = self.create_project(organization=self.org)
        self.group = self.create_group(project=self.project)

    def _set_up_sentry_app(self, name, scopes):
        self.sentry_app = self.create_sentry_app(
            name=name,
            organization=self.org,
            webhook_url="https://example.com",
            scopes=scopes,
        )

        self.install = self.create_sentry_app_installation(
            organization=self.org, slug=self.sentry_app.slug, user=self.user
        )
        self.api_token = self.create_internal_integration_token(
            install=self.install, user=self.user
        )

        self.url = reverse(
            "sentry-api-0-sentry-app-installation-external-issues", args=[self.install.uuid]
        )

    def _post_data(self):
        return {
            "issueId": self.group.id,
            "webUrl": "https://somerandom.io/project/issue-id",
            "project": "ExternalProj",
            "identifier": "issue-1",
        }

    def test_creates_external_issue(self) -> None:
        self._set_up_sentry_app("Testin", ["event:write"])
        data = self._post_data()

        response = self.client.post(
            self.url, data=data, HTTP_AUTHORIZATION=f"Bearer {self.api_token.token}"
        )

        external_issue = PlatformExternalIssue.objects.get()

        assert response.status_code == 200
        assert response.data == {
            "id": str(external_issue.id),
            "issueId": str(self.group.id),
            "serviceType": self.sentry_app.slug,
            "displayName": "ExternalProj#issue-1",
            "webUrl": "https://somerandom.io/project/issue-id",
        }

    def test_invalid_group_id(self) -> None:
        self._set_up_sentry_app("Testin", ["event:write"])
        data = self._post_data()
        data["issueId"] = self.create_group(project=self.create_project()).id

        response = self.client.post(
            self.url, data=data, HTTP_AUTHORIZATION=f"Bearer {self.api_token.token}"
        )

        assert response.status_code == 404

    def test_invalid_scopes(self) -> None:
        self._set_up_sentry_app("Testin", ["project:read"])
        data = self._post_data()

        response = self.client.post(
            self.url, data=data, HTTP_AUTHORIZATION=f"Bearer {self.api_token.token}"
        )
        assert response.status_code == 403

    def test_invalid_token(self) -> None:
        """
        You can only create external issues for the integration
        whose token you are using to hit this endpoint.
        """
        self._set_up_sentry_app("Testin", ["event:write"])

        new_install = self.create_sentry_app_installation(
            organization=self.org,
            slug=self.create_sentry_app(
                name="NewApp", organization=self.org, scopes=["event:write"]
            ).slug,
            user=self.user,
        )
        new_api_token = self.create_internal_integration_token(install=new_install, user=self.user)

        data = self._post_data()
        response = self.client.post(
            self.url,
            data=data,
            HTTP_AUTHORIZATION=f"Bearer {new_api_token.token}",
        )
        assert response.status_code == 403

    @patch(
        "sentry.sentry_apps.external_issues.external_issue_creator.PlatformExternalIssue.objects.update_or_create"
    )
    def test_external_issue_creation_fails_with_db_error(
        self, mock_update_or_create: MagicMock
    ) -> None:
        self._set_up_sentry_app("Testin", ["event:write"])
        mock_update_or_create.side_effect = Exception("bruh")
        data = self._post_data()

        response = self.client.post(
            self.url, data=data, HTTP_AUTHORIZATION=f"Bearer {self.api_token.token}"
        )

        assert response.status_code == 500
        assert response.data == {
            "detail": f"An issue occured during the integration platform process. Sentry error ID: {None}"
        }
        mock_update_or_create.assert_called_once()
