import datetime
from datetime import timezone
from functools import cached_property
from time import time

import responses

from fixtures.vsts import COMMIT_DETAILS_EXAMPLE, COMPARE_COMMITS_EXAMPLE, FILE_CHANGES_EXAMPLE
from sentry.integrations.vsts.repository import VstsRepositoryProvider
from sentry.models.repository import Repository
from sentry.silo.base import SiloMode
from sentry.testutils.cases import IntegrationRepositoryTestCase, TestCase
from sentry.testutils.silo import assume_test_silo_mode, control_silo_test
from sentry.users.models.identity import Identity


@control_silo_test
class VisualStudioRepositoryProviderTest(TestCase):
    def setUp(self) -> None:
        self.base_url = "https://visualstudio.com/"
        self.vsts_external_id = "654321"

    @cached_property
    def provider(self):
        return VstsRepositoryProvider("integrations:vsts")

    @responses.activate
    def test_compare_commits(self) -> None:
        responses.add(
            responses.POST,
            "https://visualstudio.com/_apis/git/repositories/None/commitsBatch",
            body=COMPARE_COMMITS_EXAMPLE,
        )
        responses.add(
            responses.GET,
            "https://visualstudio.com/_apis/git/repositories/None/commits/6c36052c58bde5e57040ebe6bdb9f6a52c906fff/changes",
            body=FILE_CHANGES_EXAMPLE,
        )
        responses.add(
            responses.GET,
            "https://visualstudio.com/_apis/git/repositories/None/commits/6c36052c58bde5e57040ebe6bdb9f6a52c906fff",
            body=COMMIT_DETAILS_EXAMPLE,
        )

        integration = self.create_provider_integration(
            provider="vsts",
            external_id=self.vsts_external_id,
            name="Hello world",
            metadata={"domain_name": self.base_url},
        )
        default_auth = Identity.objects.create(
            idp=self.create_identity_provider(type="vsts"),
            user=self.user,
            external_id="123",
            data={
                "access_token": "123456789",
                "expires": int(time()) + 3600,
                "refresh_token": "rxxx-xxxx",
                "token_type": "jwt-bearer",
            },
        )
        integration.add_organization(self.organization, self.user, default_auth.id)
        with assume_test_silo_mode(SiloMode.REGION):
            repo = Repository.objects.create(
                provider="visualstudio",
                name="example",
                organization_id=self.organization.id,
                config={"instance": self.base_url, "project": "project-name", "name": "example"},
                integration_id=integration.id,
            )

        res = self.provider.compare_commits(repo, "a", "b")

        assert res == [
            {
                "patch_set": [{"path": "/README.md", "type": "M"}],
                "author_email": "max@sentry.io",
                "author_name": "max bittker",
                "message": "Updated README.md\n\nSecond line\n\nFixes SENTRY-1",
                "id": "6c36052c58bde5e57040ebe6bdb9f6a52c906fff",
                "repository": "example",
                "timestamp": datetime.datetime(2018, 4, 24, 0, 3, 18, tzinfo=timezone.utc),
            }
        ]

    @responses.activate
    def test_build_repository_config(self) -> None:
        organization = self.create_organization()
        integration = self.create_provider_integration(
            provider="vsts",
            external_id=self.vsts_external_id,
            name="Hello world",
            metadata={"domain_name": self.base_url},
        )
        data = {
            "name": "MyFirstProject",
            "external_id": "654321",
            "url": "https://mbittker.visualstudio.com/_git/MyFirstProject/",
            "instance": self.base_url,
            "project": "MyFirstProject",
            "installation": integration.id,
        }
        data = self.provider.build_repository_config(organization, data)

        assert data == {
            "name": "MyFirstProject",
            "external_id": self.vsts_external_id,
            "url": "https://mbittker.visualstudio.com/_git/MyFirstProject/",
            "config": {
                "project": "MyFirstProject",
                "name": "MyFirstProject",
                "instance": self.base_url,
            },
            "integration_id": integration.id,
        }

    def test_repository_external_slug(self) -> None:
        repo = Repository(
            name="MyFirstProject",
            url="https://mbittker.visualstudio.com/_git/MyFirstProject/",
            external_id=self.vsts_external_id,
        )
        result = self.provider.repository_external_slug(repo)
        assert result == repo.external_id


@control_silo_test
class AzureDevOpsRepositoryProviderTest(IntegrationRepositoryTestCase):
    provider_name = "integrations:vsts"

    def setUp(self) -> None:
        super().setUp()
        self.base_url = "https://visualstudio.com/"
        self.vsts_external_id = "654321"
        self.integration = self.create_provider_integration(
            provider="vsts",
            external_id=self.vsts_external_id,
            name="Hello world",
            metadata={"domain_name": self.base_url},
        )
        default_auth = Identity.objects.create(
            idp=self.create_identity_provider(type="vsts"),
            user=self.user,
            external_id="123",
            data={
                "access_token": "123456789",
                "expires": int(time()) + 3600,
                "refresh_token": "rxxx-xxxx",
                "token_type": "jwt-bearer",
            },
        )
        self.integration.add_organization(self.organization, self.user, default_auth.id)
        with assume_test_silo_mode(SiloMode.REGION):
            self.repo = Repository.objects.create(
                provider="visualstudio",
                name="example",
                organization_id=self.organization.id,
                config={"instance": self.base_url, "project": "project-name", "name": "example"},
                integration_id=self.integration.id,
            )
        self.integration.get_provider().setup()

        self.default_repository_config = {
            "project": {"name": "getsentry"},
            "name": "example-repo",
            "id": "123",
            "_links": {
                "web": {"href": "https://example.gitlab.com/getsentry/projects/example-repo"}
            },
        }
        self.login_as(self.user)

    def tearDown(self):
        super().tearDown()
        responses.reset()

    def add_create_repository_responses(self, repository_config):
        responses.add(
            responses.GET,
            "https://visualstudio.com/_apis/git/repositories/123",
            json=repository_config,
        )

    @assume_test_silo_mode(SiloMode.REGION)
    def assert_repository(self, repository_config, organization_id=None):
        repo = Repository.objects.get(
            organization_id=organization_id or self.organization.id,
            provider=self.provider_name,
            external_id=repository_config["id"],
        )
        assert repo.name == repository_config["name"]
        assert repo.url == repository_config["_links"]["web"]["href"]
        assert repo.integration_id == self.integration.id
        assert repo.config == {
            "instance": self.base_url,
            "project": repository_config["project"]["name"],
            "name": repository_config["name"],
        }

    @responses.activate
    def test_create_repository(self) -> None:
        response = self.create_repository(self.default_repository_config, self.integration.id)
        assert response.status_code == 201
        self.assert_repository(self.default_repository_config)

    def test_data_has_no_installation_id(self) -> None:
        response = self.create_repository(self.default_repository_config, None)
        assert response.status_code == 400
        self.assert_error_message(response, "validation", "requires an integration id")

    def test_data_integration_does_not_exist(self) -> None:
        integration_id = self.integration.id
        self.integration.delete()

        response = self.create_repository(self.default_repository_config, integration_id)
        assert response.status_code == 404
        self.assert_error_message(
            response, "not found", "Integration matching query does not exist."
        )

    def test_org_given_has_no_installation(self) -> None:
        organization = self.create_organization(owner=self.user)
        response = self.create_repository(
            self.default_repository_config, self.integration.id, organization.slug
        )
        assert response.status_code == 404

    @responses.activate
    def test_get_repo_request_fails(self) -> None:
        responses.add(
            responses.GET,
            "https://visualstudio.com/_apis/git/repositories/123",
            json=self.default_repository_config,
            status=503,
        )
        response = self.create_repository(
            self.default_repository_config, self.integration.id, add_responses=False
        )
        assert response.status_code == 503
