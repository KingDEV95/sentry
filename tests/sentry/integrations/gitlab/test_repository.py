from functools import cached_property

import orjson
import pytest
import responses

from fixtures.gitlab import COMMIT_DIFF_RESPONSE, COMMIT_LIST_RESPONSE, COMPARE_RESPONSE
from sentry.integrations.gitlab.repository import GitlabRepositoryProvider
from sentry.models.pullrequest import PullRequest
from sentry.models.repository import Repository
from sentry.shared_integrations.exceptions import IntegrationError
from sentry.silo.base import SiloMode
from sentry.testutils.asserts import assert_commit_shape
from sentry.testutils.cases import IntegrationRepositoryTestCase
from sentry.testutils.silo import assume_test_silo_mode
from sentry.users.models.identity import Identity


class GitLabRepositoryProviderTest(IntegrationRepositoryTestCase):
    provider_name = "integrations:gitlab"

    def setUp(self) -> None:
        super().setUp()
        with assume_test_silo_mode(SiloMode.CONTROL):
            self.integration = self.create_provider_integration(
                provider="gitlab",
                name="Example GitLab",
                external_id="example.gitlab.com:getsentry",
                metadata={
                    "instance": "example.gitlab.com",
                    "domain_name": "example.gitlab.com/getsentry",
                    "verify_ssl": False,
                    "base_url": "https://example.gitlab.com",
                    "webhook_secret": "secret-token-value",
                },
            )
            identity = Identity.objects.create(
                idp=self.create_identity_provider(
                    type="gitlab", config={}, external_id="1234567890"
                ),
                user=self.user,
                external_id="example.gitlab.com:4",
                data={"access_token": "1234567890"},
            )
            self.integration.add_organization(self.organization, self.user, identity.id)
            self.integration.get_provider().setup()

            self.default_repository_config = {
                "path_with_namespace": "getsentry/example-repo",
                "name_with_namespace": "Get Sentry / Example Repo",
                "path": "example-repo",
                "id": "123",
                "web_url": "https://example.gitlab.com/getsentry/projects/example-repo",
            }
            self.gitlab_id = 123

    @cached_property
    def provider(self):
        return GitlabRepositoryProvider("gitlab")

    def tearDown(self):
        super().tearDown()
        responses.reset()

    def add_create_repository_responses(self, repository_config):
        responses.add(
            responses.GET,
            "https://example.gitlab.com/api/v4/projects/%s" % self.gitlab_id,
            json=repository_config,
        )
        responses.add(
            responses.POST,
            "https://example.gitlab.com/api/v4/projects/%s/hooks" % self.gitlab_id,
            json={"id": 99},
        )

    @assume_test_silo_mode(SiloMode.REGION)
    def get_repository(self, **kwargs) -> Repository:
        return Repository.objects.get(**kwargs)

    def assert_repository(self, repository_config, organization_id=None):
        instance = self.integration.metadata["instance"]

        external_id = "{}:{}".format(instance, repository_config["id"])
        repo = self.get_repository(
            organization_id=organization_id or self.organization.id,
            provider=self.provider_name,
            external_id=external_id,
        )
        assert repo.name == repository_config["name_with_namespace"]
        assert repo.url == repository_config["web_url"]
        assert repo.integration_id == self.integration.id
        assert repo.config == {
            "instance": instance,
            "path": repository_config["path_with_namespace"],
            "project_id": repository_config["id"],
            "webhook_id": 99,
        }

    @responses.activate
    def test_create_repository(self) -> None:
        response = self.create_repository(self.default_repository_config, self.integration.id)
        assert response.status_code == 201
        self.assert_repository(self.default_repository_config)

    @responses.activate
    def test_create_repository_verify_payload(self) -> None:
        def request_callback(request):
            payload = orjson.loads(request.body)
            assert "url" in payload
            assert payload["push_events"]
            assert payload["merge_requests_events"]
            expected_token = "{}:{}".format(
                self.integration.external_id, self.integration.metadata["webhook_secret"]
            )
            assert payload["token"] == expected_token

            return 201, {}, orjson.dumps({"id": 99}).decode()

        responses.add_callback(
            responses.POST,
            "https://example.gitlab.com/api/v4/projects/%s/hooks" % self.gitlab_id,
            callback=request_callback,
        )
        response = self.create_repository(self.default_repository_config, self.integration.id)
        assert response.status_code == 201
        self.assert_repository(self.default_repository_config)

    @responses.activate
    def test_create_repository_request_invalid_url(self) -> None:
        responses.add(
            responses.GET,
            "https://example.gitlab.com/api/v4/projects/%s" % self.gitlab_id,
            status=200,
            json=self.default_repository_config,
        )
        responses.add(
            responses.POST,
            "https://example.gitlab.com/api/v4/projects/%s/hooks" % self.gitlab_id,
            status=422,
            json={"error": "Invalid url given"},
        )
        response = self.create_repository(
            self.default_repository_config, self.integration.id, add_responses=False
        )
        assert response.status_code == 400
        self.assert_error_message(
            response, "validation", "Error Communicating with GitLab (HTTP 422): Invalid url given"
        )

    def test_create_repository_data_no_installation_id(self) -> None:
        response = self.create_repository(self.default_repository_config, None)
        assert response.status_code == 400
        self.assert_error_message(response, "validation", "requires an integration id")

    def test_create_repository_data_integration_does_not_exist(self) -> None:
        integration_id = self.integration.id
        with assume_test_silo_mode(SiloMode.CONTROL):
            self.integration.delete()

        response = self.create_repository(self.default_repository_config, integration_id)
        assert response.status_code == 404
        self.assert_error_message(
            response, "not found", "Integration matching query does not exist."
        )

    def test_create_repository_org_given_has_no_installation(self) -> None:
        organization = self.create_organization(owner=self.user)
        response = self.create_repository(
            self.default_repository_config, self.integration.id, organization.slug
        )
        assert response.status_code == 404

    @responses.activate
    def test_create_repository_get_project_request_fails(self) -> None:
        responses.add(
            responses.GET,
            "https://example.gitlab.com/api/v4/projects/%s" % self.gitlab_id,
            status=503,
        )
        response = self.create_repository(
            self.default_repository_config, self.integration.id, add_responses=False
        )
        assert response.status_code == 503

    @responses.activate
    def test_create_repository_integration_create_webhook_failure(self) -> None:
        responses.add(
            responses.GET,
            "https://example.gitlab.com/api/v4/projects/%s" % self.gitlab_id,
            json=self.default_repository_config,
        )
        responses.add(
            responses.POST,
            "https://example.gitlab.com/api/v4/projects/%s/hooks" % self.gitlab_id,
            status=503,
        )
        response = self.create_repository(
            self.default_repository_config, self.integration.id, add_responses=False
        )
        assert response.status_code == 503

    @responses.activate
    def test_on_delete_repository_remove_webhook(self) -> None:
        response = self.create_repository(self.default_repository_config, self.integration.id)
        responses.reset()

        responses.add(
            responses.DELETE,
            "https://example.gitlab.com/api/v4/projects/%s/hooks/99" % self.gitlab_id,
            status=204,
        )
        repo = self.get_repository(pk=response.data["id"])
        self.provider.on_delete_repository(repo)
        assert len(responses.calls) == 1

    @responses.activate
    def test_on_delete_repository_remove_webhook_missing_hook(self) -> None:
        response = self.create_repository(self.default_repository_config, self.integration.id)
        responses.reset()

        responses.add(
            responses.DELETE,
            "https://example.gitlab.com/api/v4/projects/%s/hooks/99" % self.gitlab_id,
            status=404,
        )
        repo = self.get_repository(pk=response.data["id"])
        self.provider.on_delete_repository(repo)
        assert len(responses.calls) == 1

    @responses.activate
    def test_compare_commits_start_and_end(self) -> None:
        responses.add(
            responses.GET,
            "https://example.gitlab.com/api/v4/projects/%s/repository/compare?from=abc&to=xyz"
            % self.gitlab_id,
            json=orjson.loads(COMPARE_RESPONSE),
        )
        responses.add(
            responses.GET,
            "https://example.gitlab.com/api/v4/projects/%s/repository/commits/12d65c8dd2b2676fa3ac47d955accc085a37a9c1/diff"
            % self.gitlab_id,
            json=orjson.loads(COMMIT_DIFF_RESPONSE),
        )
        responses.add(
            responses.GET,
            "https://example.gitlab.com/api/v4/projects/%s/repository/commits/8b090c1b79a14f2bd9e8a738f717824ff53aebad/diff"
            % self.gitlab_id,
            json=orjson.loads(COMMIT_DIFF_RESPONSE),
        )
        response = self.create_repository(self.default_repository_config, self.integration.id)
        repo = self.get_repository(pk=response.data["id"])
        commits = self.provider.compare_commits(repo, "abc", "xyz")
        assert 2 == len(commits)
        for commit in commits:
            assert_commit_shape(commit)

    @responses.activate
    def test_compare_commits_start_and_end_gitlab_failure(self) -> None:
        responses.add(
            responses.GET,
            "https://example.gitlab.com/api/v4/projects/%s/repository/compare?from=abc&to=xyz"
            % self.gitlab_id,
            status=502,
        )
        response = self.create_repository(self.default_repository_config, self.integration.id)
        repo = self.get_repository(pk=response.data["id"])
        with pytest.raises(IntegrationError):
            self.provider.compare_commits(repo, "abc", "xyz")

    @responses.activate
    def test_compare_commits_no_start(self) -> None:
        responses.add(
            responses.GET,
            "https://example.gitlab.com/api/v4/projects/%s/repository/commits/xyz" % self.gitlab_id,
            json={"created_at": "2018-09-19T13:14:15Z"},
        )
        responses.add(
            responses.GET,
            "https://example.gitlab.com/api/v4/projects/%s/repository/commits?until=2018-09-19T13:14:15Z"
            % self.gitlab_id,
            json=orjson.loads(COMMIT_LIST_RESPONSE),
        )
        responses.add(
            responses.GET,
            "https://example.gitlab.com/api/v4/projects/%s/repository/commits/ed899a2f4b50b4370feeea94676502b42383c746/diff"
            % self.gitlab_id,
            json=orjson.loads(COMMIT_DIFF_RESPONSE),
        )
        responses.add(
            responses.GET,
            "https://example.gitlab.com/api/v4/projects/%s/repository/commits/6104942438c14ec7bd21c6cd5bd995272b3faff6/diff"
            % self.gitlab_id,
            json=orjson.loads(COMMIT_DIFF_RESPONSE),
        )

        response = self.create_repository(self.default_repository_config, self.integration.id)
        repo = self.get_repository(pk=response.data["id"])
        commits = self.provider.compare_commits(repo, None, "xyz")
        for commit in commits:
            assert_commit_shape(commit)

    @responses.activate
    def test_compare_commits_no_start_gitlab_failure(self) -> None:
        responses.add(
            responses.GET,
            "https://example.gitlab.com/api/v4/projects/%s/repository/commits/abc" % self.gitlab_id,
            status=502,
        )
        response = self.create_repository(self.default_repository_config, self.integration.id)
        repo = self.get_repository(pk=response.data["id"])
        with pytest.raises(IntegrationError):
            self.provider.compare_commits(repo, None, "abc")

    @responses.activate
    def test_pull_request_url(self) -> None:
        response = self.create_repository(self.default_repository_config, self.integration.id)
        repo = self.get_repository(pk=response.data["id"])
        pull = PullRequest(key=99)
        result = self.provider.pull_request_url(repo, pull)
        assert (
            result == "https://example.gitlab.com/getsentry/projects/example-repo/merge_requests/99"
        )

    @responses.activate
    def test_repository_external_slug(self) -> None:
        response = self.create_repository(self.default_repository_config, self.integration.id)
        repo = self.get_repository(pk=response.data["id"])
        result = self.provider.repository_external_slug(repo)
        assert result == repo.config["project_id"]
