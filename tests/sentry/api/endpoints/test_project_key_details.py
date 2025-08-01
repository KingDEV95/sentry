from unittest.mock import MagicMock, patch

from django.urls import reverse

from sentry.loader.browsersdkversion import get_default_sdk_version_for_project
from sentry.models.projectkey import ProjectKey, ProjectKeyStatus, UseCase
from sentry.testutils.cases import APITestCase


class UpdateProjectKeyTest(APITestCase):
    def setUp(self) -> None:
        super().setUp()
        self.user = self.create_user(is_superuser=False)
        self.superuser = self.create_user(is_superuser=True)

    def test_simple(self) -> None:
        project = self.create_project()
        key = ProjectKey.objects.get_or_create(project=project)[0]
        self.login_as(user=self.user)
        url = reverse(
            "sentry-api-0-project-key-details",
            kwargs={
                "organization_id_or_slug": project.organization.slug,
                "project_id_or_slug": project.slug,
                "key_id": key.public_key,
            },
        )
        response = self.client.put(url, {"name": "hello world"})
        assert response.status_code == 200
        key = ProjectKey.objects.get(id=key.id)
        assert key.label == "hello world"

    def test_no_rate_limit(self) -> None:
        project = self.create_project()
        key = ProjectKey.objects.create(project=project, rate_limit_window=60, rate_limit_count=1)
        self.login_as(user=self.user)
        url = reverse(
            "sentry-api-0-project-key-details",
            kwargs={
                "organization_id_or_slug": project.organization.slug,
                "project_id_or_slug": project.slug,
                "key_id": key.public_key,
            },
        )
        response = self.client.put(url, {"rateLimit": None})
        assert response.status_code == 200, response.content
        key = ProjectKey.objects.get(id=key.id)
        assert key.rate_limit_count is None
        assert key.rate_limit_window is None

    def test_unset_rate_limit(self) -> None:
        project = self.create_project()
        key = ProjectKey.objects.create(project=project, rate_limit_window=60, rate_limit_count=1)
        self.login_as(user=self.user)
        url = reverse(
            "sentry-api-0-project-key-details",
            kwargs={
                "organization_id_or_slug": project.organization.slug,
                "project_id_or_slug": project.slug,
                "key_id": key.public_key,
            },
        )
        response = self.client.put(url)
        assert response.status_code == 200
        key = ProjectKey.objects.get(id=key.id)
        assert key.rate_limit_count == 1
        assert key.rate_limit_window == 60

    def test_remove_rate_limit(self) -> None:
        project = self.create_project()
        key = ProjectKey.objects.create(project=project, rate_limit_window=60, rate_limit_count=1)
        self.login_as(user=self.user)
        url = reverse(
            "sentry-api-0-project-key-details",
            kwargs={
                "organization_id_or_slug": project.organization.slug,
                "project_id_or_slug": project.slug,
                "key_id": key.public_key,
            },
        )
        response = self.client.put(url, {"rateLimit": {"count": "", "window": 300}})
        assert response.status_code == 200
        key = ProjectKey.objects.get(id=key.id)
        assert key.rate_limit_count is None
        assert key.rate_limit_window is None

    def test_simple_rate_limit(self) -> None:
        project = self.create_project()
        key = ProjectKey.objects.create(
            project=project, rate_limit_window=None, rate_limit_count=None
        )
        self.login_as(user=self.user)
        url = reverse(
            "sentry-api-0-project-key-details",
            kwargs={
                "organization_id_or_slug": project.organization.slug,
                "project_id_or_slug": project.slug,
                "key_id": key.public_key,
            },
        )
        response = self.client.put(url, {"rateLimit": {"count": 1, "window": 60}})
        assert response.status_code == 200
        key = ProjectKey.objects.get(id=key.id)
        assert key.rate_limit_count == 1
        assert key.rate_limit_window == 60

    @patch("sentry.api.base.create_audit_entry")
    def test_rate_limit_change_data(self, mock_create_audit_entry: MagicMock) -> None:
        project = self.create_project()
        key = ProjectKey.objects.create(
            project=project, rate_limit_window=None, rate_limit_count=None
        )
        self.login_as(user=self.user)
        url = reverse(
            "sentry-api-0-project-key-details",
            kwargs={
                "organization_id_or_slug": project.organization.slug,
                "project_id_or_slug": project.slug,
                "key_id": key.public_key,
            },
        )
        response = self.client.put(url, {"rateLimit": {"count": 1, "window": 60}})
        assert response.status_code == 200
        key = ProjectKey.objects.get(id=key.id)
        assert key.rate_limit_count == 1
        assert key.rate_limit_window == 60

        assert mock_create_audit_entry.call_args[-1]["data"]["prev_rate_limit_count"] is None
        assert mock_create_audit_entry.call_args[-1]["data"]["prev_rate_limit_window"] is None
        assert mock_create_audit_entry.call_args[-1]["data"]["rate_limit_count"] == 1
        assert mock_create_audit_entry.call_args[-1]["data"]["rate_limit_window"] == 60

    def test_deactivate(self) -> None:
        project = self.create_project()
        key = ProjectKey.objects.get_or_create(project=project)[0]
        self.login_as(user=self.user)
        url = reverse(
            "sentry-api-0-project-key-details",
            kwargs={
                "organization_id_or_slug": project.organization.slug,
                "project_id_or_slug": project.slug,
                "key_id": key.public_key,
            },
        )
        response = self.client.put(url, {"isActive": False, "name": "hello world"})
        assert response.status_code == 200
        key = ProjectKey.objects.get(id=key.id)
        assert key.label == "hello world"
        assert key.status == ProjectKeyStatus.INACTIVE

    def test_default_browser_sdk_version(self) -> None:
        project = self.create_project()
        key = ProjectKey.objects.get_or_create(project=project)[0]
        self.login_as(user=self.user)
        url = reverse(
            "sentry-api-0-project-key-details",
            kwargs={
                "organization_id_or_slug": project.organization.slug,
                "project_id_or_slug": project.slug,
                "key_id": key.public_key,
            },
        )
        response = self.client.put(url, {})
        assert response.status_code == 200
        key = ProjectKey.objects.get(id=key.id)
        assert key.data["browserSdkVersion"] == get_default_sdk_version_for_project(project)

    def test_set_browser_sdk_version(self) -> None:
        project = self.create_project()
        key = ProjectKey.objects.get_or_create(project=project)[0]
        self.login_as(user=self.user)
        url = reverse(
            "sentry-api-0-project-key-details",
            kwargs={
                "organization_id_or_slug": project.organization.slug,
                "project_id_or_slug": project.slug,
                "key_id": key.public_key,
            },
        )
        response = self.client.put(url, {"browserSdkVersion": "5.x"})
        assert response.status_code == 200
        key = ProjectKey.objects.get(id=key.id)
        assert key.data["browserSdkVersion"] == "5.x"

    def test_default_dynamic_sdk_loader_options(self) -> None:
        project = self.create_project()
        key = ProjectKey.objects.get_or_create(project=project)[0]
        self.login_as(user=self.user)
        url = reverse(
            "sentry-api-0-project-key-details",
            kwargs={
                "organization_id_or_slug": project.organization.slug,
                "project_id_or_slug": project.slug,
                "key_id": key.public_key,
            },
        )
        response = self.client.put(url, {})
        assert response.status_code == 200
        key = ProjectKey.objects.get(id=key.id)
        assert "dynamicSdkLoaderOptions" in key.data
        assert key.data["dynamicSdkLoaderOptions"] == {
            "hasPerformance": True,
            "hasReplay": True,
        }

    def test_dynamic_sdk_loader_options(self) -> None:
        project = self.create_project()
        key = ProjectKey.objects.get_or_create(project=project)[0]
        self.login_as(user=self.user)
        url = reverse(
            "sentry-api-0-project-key-details",
            kwargs={
                "organization_id_or_slug": project.organization.slug,
                "project_id_or_slug": project.slug,
                "key_id": key.public_key,
            },
        )
        response = self.client.put(
            url,
            {"dynamicSdkLoaderOptions": {}},
        )
        assert response.status_code == 200
        key = ProjectKey.objects.get(id=key.id)
        assert "dynamicSdkLoaderOptions" in key.data
        assert key.data["dynamicSdkLoaderOptions"] == {
            "hasPerformance": True,
            "hasReplay": True,
        }

        response = self.client.put(
            url,
            {"dynamicSdkLoaderOptions": {"hasReplay": False, "hasDebug": True}},
        )
        assert response.status_code == 200
        key = ProjectKey.objects.get(id=key.id)
        assert key.data.get("dynamicSdkLoaderOptions") == {
            "hasReplay": False,
            "hasPerformance": True,
            "hasDebug": True,
        }

        response = self.client.put(
            url,
            {
                "dynamicSdkLoaderOptions": {
                    "hasReplay": False,
                    "hasPerformance": True,
                }
            },
        )
        assert response.status_code == 200
        key = ProjectKey.objects.get(id=key.id)
        assert key.data.get("dynamicSdkLoaderOptions") == {
            "hasReplay": False,
            "hasPerformance": True,
            "hasDebug": True,
        }

        response = self.client.put(
            url,
            {"dynamicSdkLoaderOptions": {"hasDebug": False, "invalid-key": "blah"}},
        )
        assert response.status_code == 200
        key = ProjectKey.objects.get(id=key.id)
        assert key.data.get("dynamicSdkLoaderOptions") == {
            "hasReplay": False,
            "hasPerformance": True,
            "hasDebug": False,
        }

        response = self.client.put(
            url,
            {
                "dynamicSdkLoaderOptions": {
                    "hasReplay": "invalid",
                }
            },
        )
        assert response.status_code == 400
        key = ProjectKey.objects.get(id=key.id)
        assert key.data.get("dynamicSdkLoaderOptions") == {
            "hasReplay": False,
            "hasPerformance": True,
            "hasDebug": False,
        }

        response = self.client.put(
            url,
            {
                "dynamicSdkLoaderOptions": {
                    "invalid-key": "blah",
                }
            },
        )
        assert response.status_code == 200
        key = ProjectKey.objects.get(id=key.id)
        assert key.data.get("dynamicSdkLoaderOptions") == {
            "hasReplay": False,
            "hasPerformance": True,
            "hasDebug": False,
        }

    def test_use_case(self) -> None:
        """Regular user cannot update an internal DSN"""
        project = self.create_project()
        key = ProjectKey.objects.get_or_create(use_case=UseCase.PROFILING.value, project=project)[0]
        self.login_as(user=self.user)
        url = reverse(
            "sentry-api-0-project-key-details",
            kwargs={
                "organization_id_or_slug": project.organization.slug,
                "project_id_or_slug": project.slug,
                "key_id": key.public_key,
            },
        )
        response = self.client.put(url, {"name": "hello world"})
        assert response.status_code == 404

        # Superuser can update
        self.login_as(user=self.superuser, superuser=True)
        response = self.client.put(url, {"name": "hello world"})
        assert response.status_code == 200

    def test_cannot_upgrade_to_internal(self) -> None:
        """PUT request ignores use case field"""
        project = self.create_project()
        key = ProjectKey.objects.get_or_create(use_case=UseCase.USER.value, project=project)[0]
        self.login_as(user=self.user)
        url = reverse(
            "sentry-api-0-project-key-details",
            kwargs={
                "organization_id_or_slug": project.organization.slug,
                "project_id_or_slug": project.slug,
                "key_id": key.public_key,
            },
        )
        self.client.put(url, {"useCase": "profiling", "name": "updated"})
        updated = ProjectKey.objects.get(pk=key.id)
        assert updated.label == "updated"
        assert updated.use_case == UseCase.USER.value


class DeleteProjectKeyTest(APITestCase):
    def setUp(self) -> None:
        super().setUp()
        self.user = self.create_user(is_superuser=False)
        self.superuser = self.create_user(is_superuser=True)

    def test_simple(self) -> None:
        project = self.create_project()
        self.login_as(user=self.user)
        key = ProjectKey.objects.get_or_create(project=project)[0]
        url = reverse(
            "sentry-api-0-project-key-details",
            kwargs={
                "organization_id_or_slug": project.organization.slug,
                "project_id_or_slug": project.slug,
                "key_id": key.public_key,
            },
        )
        resp = self.client.delete(url)
        assert resp.status_code == 204, resp.content
        assert not ProjectKey.objects.filter(id=key.id).exists()

    def test_use_case(self) -> None:
        """Regular user cannot delete an internal DSN"""
        project = self.create_project()
        self.login_as(user=self.user)
        key = ProjectKey.objects.get_or_create(use_case=UseCase.PROFILING.value, project=project)[0]
        url = reverse(
            "sentry-api-0-project-key-details",
            kwargs={
                "organization_id_or_slug": project.organization.slug,
                "project_id_or_slug": project.slug,
                "key_id": key.public_key,
            },
        )
        resp = self.client.delete(url)
        assert resp.status_code == 404, resp.content

        # Superuser can delete
        self.login_as(user=self.superuser, superuser=True)
        resp = self.client.delete(url)
        assert resp.status_code == 204, resp.content
