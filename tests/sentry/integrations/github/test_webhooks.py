from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import responses

from fixtures.github import (
    INSTALLATION_API_RESPONSE,
    INSTALLATION_DELETE_EVENT_EXAMPLE,
    INSTALLATION_EVENT_EXAMPLE,
    PULL_REQUEST_CLOSED_EVENT_EXAMPLE,
    PULL_REQUEST_EDITED_EVENT_EXAMPLE,
    PULL_REQUEST_OPENED_EVENT_EXAMPLE,
    PUSH_EVENT_EXAMPLE_INSTALLATION,
)
from sentry import options
from sentry.constants import ObjectStatus
from sentry.integrations.models.integration import Integration
from sentry.integrations.models.organization_integration import OrganizationIntegration
from sentry.middleware.integrations.parsers.github import GithubRequestParser
from sentry.models.commit import Commit
from sentry.models.commitauthor import CommitAuthor
from sentry.models.commitfilechange import CommitFileChange
from sentry.models.grouplink import GroupLink
from sentry.models.options.organization_option import OrganizationOption
from sentry.models.pullrequest import PullRequest
from sentry.models.repository import Repository
from sentry.silo.base import SiloMode
from sentry.testutils.asserts import assert_failure_metric, assert_success_metric
from sentry.testutils.cases import APITestCase
from sentry.testutils.silo import assume_test_silo_mode, control_silo_test


class WebhookTest(APITestCase):
    def setUp(self) -> None:
        self.url = "/extensions/github/webhook/"
        self.secret = "b3002c3e321d4b7880360d397db2ccfd"
        options.set("github-app.webhook-secret", self.secret)

    def test_get(self) -> None:
        response = self.client.get(self.url)

        assert response.status_code == 405

    def test_unregistered_event(self) -> None:
        response = self.client.post(
            path=self.url,
            data=PUSH_EVENT_EXAMPLE_INSTALLATION,
            content_type="application/json",
            HTTP_X_GITHUB_EVENT="UnregisteredEvent",
            HTTP_X_HUB_SIGNATURE="sha1=2b116e7c1f7510b62727673b0f9acc0db951263a",
            HTTP_X_GITHUB_DELIVERY=str(uuid4()),
        )

        assert response.status_code == 204

    def test_invalid_signature_event(self) -> None:
        response = self.client.post(
            path=self.url,
            data=PUSH_EVENT_EXAMPLE_INSTALLATION,
            content_type="application/json",
            HTTP_X_GITHUB_EVENT="push",
            HTTP_X_HUB_SIGNATURE="sha1=33521abeaaf9a57c2abf486e0ccd54d23cf36fec",
            HTTP_X_GITHUB_DELIVERY=str(uuid4()),
        )

        assert response.status_code == 401

    def test_missing_signature_event(self) -> None:
        response = self.client.post(
            path=self.url,
            data=PUSH_EVENT_EXAMPLE_INSTALLATION,
            content_type="application/json",
            HTTP_X_GITHUB_EVENT="push",
            HTTP_X_GITHUB_DELIVERY=str(uuid4()),
        )

        assert response.status_code == 400


@control_silo_test
class InstallationEventWebhookTest(APITestCase):
    base_url = "https://api.github.com"

    def setUp(self) -> None:
        self.url = "/extensions/github/webhook/"
        self.secret = "b3002c3e321d4b7880360d397db2ccfd"
        options.set("github-app.webhook-secret", self.secret)

    @responses.activate
    @patch("sentry.integrations.github.client.get_jwt", return_value="jwt_token_1")
    @patch("sentry.integrations.utils.metrics.EventLifecycle.record_event")
    def test_installation_created(self, mock_record: MagicMock, get_jwt: MagicMock) -> None:
        responses.add(
            method=responses.GET,
            url="https://api.github.com/app/installations/2",
            body=INSTALLATION_API_RESPONSE,
            status=200,
            content_type="application/json",
        )

        response = self.client.post(
            path=self.url,
            data=INSTALLATION_EVENT_EXAMPLE,
            content_type="application/json",
            HTTP_X_GITHUB_EVENT="installation",
            HTTP_X_HUB_SIGNATURE="sha1=348e46312df2901e8cb945616ee84ce30d9987c9",
            HTTP_X_HUB_SIGNATURE_256="sha256=a9d5801982bcabdb4df5e1680cc37a00fe495cc0ab193668ba7bbbe345451c46",
            HTTP_X_GITHUB_DELIVERY=str(uuid4()),
        )
        assert response.status_code == 204

        integration = Integration.objects.get(external_id=2)
        assert integration.external_id == "2"
        assert integration.name == "octocat"
        assert integration.metadata["sender"]["id"] == 1
        assert integration.metadata["sender"]["login"] == "octocat"
        assert integration.status == ObjectStatus.ACTIVE

        assert_success_metric(mock_record)

    @responses.activate
    @patch("sentry.integrations.github.client.get_jwt", return_value="jwt_token_1")
    @patch("sentry.integrations.github.webhook.InstallationEventWebhook.__call__")
    @patch("sentry.integrations.utils.metrics.EventLifecycle.record_event")
    def test_installation_error_metric(
        self, mock_record: MagicMock, mock_event: MagicMock, get_jwt: MagicMock
    ) -> None:
        responses.add(
            method=responses.GET,
            url="https://api.github.com/app/installations/2",
            body=INSTALLATION_API_RESPONSE,
            status=200,
            content_type="application/json",
        )

        error = Exception("error")
        mock_event.side_effect = error

        response = self.client.post(
            path=self.url,
            data=INSTALLATION_EVENT_EXAMPLE,
            content_type="application/json",
            HTTP_X_GITHUB_EVENT="installation",
            HTTP_X_HUB_SIGNATURE="sha1=348e46312df2901e8cb945616ee84ce30d9987c9",
            HTTP_X_HUB_SIGNATURE_256="sha256=a9d5801982bcabdb4df5e1680cc37a00fe495cc0ab193668ba7bbbe345451c46",
            HTTP_X_GITHUB_DELIVERY=str(uuid4()),
        )
        assert response.status_code == 500

        assert_failure_metric(mock_record, error)


@control_silo_test
class InstallationDeleteEventWebhookTest(APITestCase):
    base_url = "https://api.github.com"

    def setUp(self) -> None:
        self.url = "/extensions/github/webhook/"
        self.secret = "b3002c3e321d4b7880360d397db2ccfd"
        options.set("github-app.webhook-secret", self.secret)

    @patch("sentry.integrations.github.client.get_jwt", return_value="jwt_token_1")
    def test_installation_deleted(self, get_jwt: MagicMock) -> None:
        future_expires = datetime.now().replace(microsecond=0) + timedelta(minutes=5)
        integration = self.create_integration(
            name="octocat",
            organization=self.organization,
            external_id="2",
            provider="github",
            metadata={"access_token": "1234", "expires_at": future_expires.isoformat()},
        )
        integration.add_organization(self.project.organization.id, self.user)
        assert integration.status == ObjectStatus.ACTIVE

        repo = self.create_repo(
            self.project,
            provider="integrations:github",
            integration_id=integration.id,
        )

        with patch.object(GithubRequestParser, "get_regions_from_organizations", return_value=[]):
            response = self.client.post(
                path=self.url,
                data=INSTALLATION_DELETE_EVENT_EXAMPLE,
                content_type="application/json",
                HTTP_X_GITHUB_EVENT="installation",
                HTTP_X_HUB_SIGNATURE="sha1=8f73a86cf0a0cfa6d05626ce425cef5d3c4062aa",
                HTTP_X_HUB_SIGNATURE_256="sha256=d06accfcb90d170d866ee0d7dfad84c8d759a2485b3aa64a787d689589435706",
                HTTP_X_GITHUB_DELIVERY=str(uuid4()),
            )
            assert response.status_code == 204

        integration = Integration.objects.get(external_id=2)
        assert integration.external_id == "2"
        assert integration.name == "octocat"
        assert integration.status == ObjectStatus.DISABLED

        with assume_test_silo_mode(SiloMode.REGION):
            repo.refresh_from_db()
            assert repo.status == ObjectStatus.DISABLED

    @patch("sentry.integrations.github.client.get_jwt", return_value="jwt_token_1")
    def test_installation_deleted_no_org_integration(self, get_jwt: MagicMock) -> None:
        future_expires = datetime.now().replace(microsecond=0) + timedelta(minutes=5)
        integration = self.create_integration(
            name="octocat",
            organization=self.organization,
            external_id="2",
            provider="github",
            metadata={"access_token": "1234", "expires_at": future_expires.isoformat()},
        )
        integration.add_organization(self.project.organization.id, self.user)
        assert integration.status == ObjectStatus.ACTIVE

        # Set up condition that the OrganizationIntegration is deleted prior to the webhook event
        OrganizationIntegration.objects.filter(
            integration_id=integration.id,
            organization_id=self.project.organization.id,
        ).delete()

        response = self.client.post(
            path=self.url,
            data=INSTALLATION_DELETE_EVENT_EXAMPLE,
            content_type="application/json",
            HTTP_X_GITHUB_EVENT="installation",
            HTTP_X_HUB_SIGNATURE="sha1=8f73a86cf0a0cfa6d05626ce425cef5d3c4062aa",
            HTTP_X_HUB_SIGNATURE_256="sha256=d06accfcb90d170d866ee0d7dfad84c8d759a2485b3aa64a787d689589435706",
            HTTP_X_GITHUB_DELIVERY=str(uuid4()),
        )
        assert response.status_code == 204

        integration = Integration.objects.get(external_id=2)
        assert integration.external_id == "2"
        assert integration.name == "octocat"
        assert integration.status == ObjectStatus.DISABLED


class PushEventWebhookTest(APITestCase):
    def setUp(self) -> None:
        self.url = "/extensions/github/webhook/"
        self.secret = "b3002c3e321d4b7880360d397db2ccfd"
        options.set("github-app.webhook-secret", self.secret)

    def _create_integration_and_send_push_event(self):
        future_expires = datetime.now().replace(microsecond=0) + timedelta(minutes=5)
        with assume_test_silo_mode(SiloMode.CONTROL):
            integration = self.create_integration(
                organization=self.organization,
                external_id="12345",
                provider="github",
                metadata={"access_token": "1234", "expires_at": future_expires.isoformat()},
            )
            integration.add_organization(self.project.organization.id, self.user)

        response = self.client.post(
            path=self.url,
            data=PUSH_EVENT_EXAMPLE_INSTALLATION,
            content_type="application/json",
            HTTP_X_GITHUB_EVENT="push",
            HTTP_X_HUB_SIGNATURE="sha1=2b116e7c1f7510b62727673b0f9acc0db951263a",
            HTTP_X_HUB_SIGNATURE_256="sha256=923b0fbedd24b106400c1dd23251972aee23dc797e0ab7cdd6d0c089db802402",
            HTTP_X_GITHUB_DELIVERY=str(uuid4()),
        )

        assert response.status_code == 204

    @responses.activate
    @patch("sentry.integrations.github.client.get_jwt", return_value="jwt_token_1")
    @patch("sentry.integrations.github.webhook.PushEventWebhook.__call__")
    @patch("sentry.integrations.utils.metrics.EventLifecycle.record_event")
    def test_webhook_error_metric(
        self, mock_record: MagicMock, mock_event: MagicMock, get_jwt: MagicMock
    ) -> None:
        future_expires = datetime.now().replace(microsecond=0) + timedelta(minutes=5)
        with assume_test_silo_mode(SiloMode.CONTROL):
            integration = self.create_integration(
                organization=self.organization,
                external_id="12345",
                provider="github",
                metadata={"access_token": "1234", "expires_at": future_expires.isoformat()},
            )
            integration.add_organization(self.project.organization.id, self.user)

        error = Exception("error")
        mock_event.side_effect = error

        response = self.client.post(
            path=self.url,
            data=PUSH_EVENT_EXAMPLE_INSTALLATION,
            content_type="application/json",
            HTTP_X_GITHUB_EVENT="push",
            HTTP_X_HUB_SIGNATURE="sha1=2b116e7c1f7510b62727673b0f9acc0db951263a",
            HTTP_X_HUB_SIGNATURE_256="sha256=923b0fbedd24b106400c1dd23251972aee23dc797e0ab7cdd6d0c089db802402",
            HTTP_X_GITHUB_DELIVERY=str(uuid4()),
        )

        assert response.status_code == 500

        assert_failure_metric(mock_record, error)

    @responses.activate
    @patch("sentry.integrations.utils.metrics.EventLifecycle.record_event")
    def test_simple(self, mock_record: MagicMock) -> None:
        repo = Repository.objects.create(
            organization_id=self.project.organization.id,
            external_id="35129377",
            provider="integrations:github",
            name="baxterthehacker/repo",
        )

        self._create_integration_and_send_push_event()

        commit_list = list(
            Commit.objects.filter(
                organization_id=self.project.organization.id,
            )
            .select_related("author")
            .order_by("-date_added")
        )

        assert len(commit_list) == 2

        commit = commit_list[0]

        assert commit.key == "133d60480286590a610a0eb7352ff6e02b9674c4"
        assert commit.message == "Update hello.py"
        assert commit.author is not None
        assert commit.author.name == "bàxterthehacker"
        assert commit.author.email == "baxterthehacker@users.noreply.github.com"
        assert commit.author.external_id is None
        assert commit.date_added == datetime(2015, 5, 5, 23, 45, 15, tzinfo=timezone.utc)

        commit = commit_list[1]

        assert commit.key == "0d1a26e67d8f5eaf1f6ba5c57fc3c7d91ac0fd1c"
        assert commit.message == "Update README.md"
        assert commit.author is not None
        assert commit.author.name == "bàxterthehacker"
        assert commit.author.email == "baxterthehacker@users.noreply.github.com"
        assert commit.author.external_id is None
        assert commit.date_added == datetime(2015, 5, 5, 23, 40, 15, tzinfo=timezone.utc)

        commit_filechanges = CommitFileChange.objects.all()
        assert len(commit_filechanges) == 4

        repo.refresh_from_db()
        assert set(repo.languages) == {"python", "javascript"}
        assert repo.name == "baxterthehacker/public-repo"

        assert_success_metric(mock_record)

    @responses.activate
    @patch("sentry.integrations.github.webhook.metrics")
    def test_creates_missing_repo(self, mock_metrics: MagicMock) -> None:
        self._create_integration_and_send_push_event()

        repos = Repository.objects.all()
        assert len(repos) == 1
        assert repos[0].organization_id == self.project.organization.id
        assert repos[0].external_id == "35129377"
        assert repos[0].provider == "integrations:github"
        assert repos[0].name == "baxterthehacker/public-repo"
        mock_metrics.incr.assert_called_with("github.webhook.repository_created")

    def test_ignores_hidden_repo(self) -> None:
        repo = self.create_repo(
            project=self.project,
            provider="integrations:github",
            name="baxterthehacker/public-repo",
        )
        repo.status = ObjectStatus.HIDDEN
        repo.external_id = "35129377"
        repo.save()

        self._create_integration_and_send_push_event()

        repos = Repository.objects.all()
        assert len(repos) == 1
        assert repos[0] == repo

    def test_anonymous_lookup(self) -> None:

        repo = Repository.objects.create(
            organization_id=self.project.organization.id,
            external_id="35129377",
            provider="integrations:github",
            name="baxterthehacker/public-repo",
        )

        CommitAuthor.objects.create(
            external_id="github:baxterthehacker",
            organization_id=self.project.organization.id,
            email="baxterthehacker@example.com",
            name="bàxterthehacker",
        )

        self._create_integration_and_send_push_event()

        commit_list = list(
            Commit.objects.filter(organization_id=self.project.organization.id)
            .select_related("author")
            .order_by("-date_added")
        )

        # should be skipping the #skipsentry commit
        assert len(commit_list) == 2

        commit = commit_list[0]

        assert commit.key == "133d60480286590a610a0eb7352ff6e02b9674c4"
        assert commit.message == "Update hello.py"
        assert commit.author is not None
        assert commit.author.name == "bàxterthehacker"
        assert commit.author.email == "baxterthehacker@example.com"
        assert commit.date_added == datetime(2015, 5, 5, 23, 45, 15, tzinfo=timezone.utc)

        commit = commit_list[1]

        assert commit.key == "0d1a26e67d8f5eaf1f6ba5c57fc3c7d91ac0fd1c"
        assert commit.message == "Update README.md"
        assert commit.author is not None
        assert commit.author.name == "bàxterthehacker"
        assert commit.author.email == "baxterthehacker@example.com"
        assert commit.date_added == datetime(2015, 5, 5, 23, 40, 15, tzinfo=timezone.utc)

        commit_filechanges = CommitFileChange.objects.all()
        assert len(commit_filechanges) == 4

        repo.refresh_from_db()
        assert set(repo.languages) == {"python", "javascript"}

    @responses.activate
    def test_multiple_orgs(self) -> None:
        Repository.objects.create(
            organization_id=self.project.organization.id,
            external_id="35129377",
            provider="integrations:github",
            name="baxterthehacker/public-repo",
        )

        future_expires = datetime.now().replace(microsecond=0) + timedelta(minutes=5)
        self.create_integration(
            organization=self.organization,
            external_id="12345",
            provider="github",
            metadata={"access_token": "1234", "expires_at": future_expires.isoformat()},
        )

        org2 = self.create_organization()
        project2 = self.create_project(organization=org2, name="bar")

        self.create_repo(
            project=project2,
            provider="integrations:github",
            name="another/repo",
        )

        integration = self.create_integration(
            organization=self.organization,
            external_id="99",
            provider="github",
            metadata={"access_token": "1234", "expires_at": future_expires.isoformat()},
        )
        with assume_test_silo_mode(SiloMode.CONTROL):
            integration.add_organization(org2.id, self.user)

        response = self.client.post(
            path=self.url,
            data=PUSH_EVENT_EXAMPLE_INSTALLATION,
            content_type="application/json",
            HTTP_X_GITHUB_EVENT="push",
            HTTP_X_HUB_SIGNATURE="sha1=2b116e7c1f7510b62727673b0f9acc0db951263a",
            HTTP_X_HUB_SIGNATURE_256="sha256=923b0fbedd24b106400c1dd23251972aee23dc797e0ab7cdd6d0c089db802402",
            HTTP_X_GITHUB_DELIVERY=str(uuid4()),
        )

        assert response.status_code == 204

        commit_list = list(
            Commit.objects.filter(organization_id=self.project.organization.id)
            .select_related("author")
            .order_by("-date_added")
        )

        assert len(commit_list) == 2

        commit_list = list(
            Commit.objects.filter(organization_id=org2.id)
            .select_related("author")
            .order_by("-date_added")
        )
        assert len(commit_list) == 0

    @responses.activate
    @patch("sentry.integrations.github.webhook.metrics")
    def test_multiple_orgs_creates_missing_repos(self, mock_metrics: MagicMock) -> None:
        org2 = self.create_organization()

        future_expires = datetime.now().replace(microsecond=0) + timedelta(minutes=5)
        integration = self.create_integration(
            organization=self.organization,
            external_id="12345",
            provider="github",
            metadata={"access_token": "1234", "expires_at": future_expires.isoformat()},
        )
        with assume_test_silo_mode(SiloMode.CONTROL):
            integration.add_organization(org2.id, self.user)

        response = self.client.post(
            path=self.url,
            data=PUSH_EVENT_EXAMPLE_INSTALLATION,
            content_type="application/json",
            HTTP_X_GITHUB_EVENT="push",
            HTTP_X_HUB_SIGNATURE="sha1=2b116e7c1f7510b62727673b0f9acc0db951263a",
            HTTP_X_HUB_SIGNATURE_256="sha256=923b0fbedd24b106400c1dd23251972aee23dc797e0ab7cdd6d0c089db802402",
            HTTP_X_GITHUB_DELIVERY=str(uuid4()),
        )

        assert response.status_code == 204

        repos = Repository.objects.all()
        assert len(repos) == 2

        assert {self.project.organization.id, org2.id} == {repo.organization_id for repo in repos}
        for repo in repos:
            assert repo.external_id == "35129377"
            assert repo.provider == "integrations:github"
            assert repo.name == "baxterthehacker/public-repo"
        mock_metrics.incr.assert_called_with("github.webhook.repository_created")

    def test_multiple_orgs_ignores_hidden_repo(self) -> None:
        org2 = self.create_organization()

        future_expires = datetime.now().replace(microsecond=0) + timedelta(minutes=5)
        with assume_test_silo_mode(SiloMode.CONTROL):
            integration = self.create_integration(
                organization=self.organization,
                external_id="12345",
                provider="github",
                metadata={"access_token": "1234", "expires_at": future_expires.isoformat()},
            )
            integration.add_organization(self.project.organization.id, self.user)
            integration.add_organization(org2.id, self.user)

        repo = self.create_repo(
            project=self.project,
            provider="integrations:github",
            name="baxterthehacker/public-repo",
        )
        repo.external_id = "35129377"
        repo.status = ObjectStatus.HIDDEN
        repo.save()

        response = self.client.post(
            path=self.url,
            data=PUSH_EVENT_EXAMPLE_INSTALLATION,
            content_type="application/json",
            HTTP_X_GITHUB_EVENT="push",
            HTTP_X_HUB_SIGNATURE="sha1=2b116e7c1f7510b62727673b0f9acc0db951263a",
            HTTP_X_HUB_SIGNATURE_256="sha256=923b0fbedd24b106400c1dd23251972aee23dc797e0ab7cdd6d0c089db802402",
            HTTP_X_GITHUB_DELIVERY=str(uuid4()),
        )

        assert response.status_code == 204

        repos = Repository.objects.all()
        assert len(repos) == 1

        assert repos[0] == repo


class PullRequestEventWebhook(APITestCase):
    def setUp(self) -> None:
        self.url = "/extensions/github/webhook/"
        self.secret = "b3002c3e321d4b7880360d397db2ccfd"
        options.set("github-app.webhook-secret", self.secret)

    def _create_integration_and_send_pull_request_opened_event(self):
        future_expires = datetime.now().replace(microsecond=0) + timedelta(minutes=5)
        with assume_test_silo_mode(SiloMode.CONTROL):
            integration = self.create_integration(
                organization=self.organization,
                external_id="12345",
                provider="github",
                metadata={"access_token": "1234", "expires_at": future_expires.isoformat()},
            )
            integration.add_organization(self.project.organization.id, self.user)

        response = self.client.post(
            path=self.url,
            data=PULL_REQUEST_OPENED_EVENT_EXAMPLE,
            content_type="application/json",
            HTTP_X_GITHUB_EVENT="pull_request",
            HTTP_X_HUB_SIGNATURE="sha1=bc7ce12fc1058a35bf99355e6fc0e6da72c35de3",
            HTTP_X_HUB_SIGNATURE_256="sha256=ed9e5aed0617ad10312986257e22448b019569200c5fdbd005a2b68a80049317",
            HTTP_X_GITHUB_DELIVERY=str(uuid4()),
        )

        assert response.status_code == 204

    @responses.activate
    @patch("sentry.integrations.github.client.get_jwt", return_value="jwt_token_1")
    @patch("sentry.integrations.github.webhook.PullRequestEventWebhook.__call__")
    @patch("sentry.integrations.utils.metrics.EventLifecycle.record_event")
    def test_webhook_error_metric(
        self, mock_record: MagicMock, mock_event: MagicMock, get_jwt: MagicMock
    ) -> None:
        future_expires = datetime.now().replace(microsecond=0) + timedelta(minutes=5)
        with assume_test_silo_mode(SiloMode.CONTROL):
            integration = self.create_integration(
                organization=self.organization,
                external_id="12345",
                provider="github",
                metadata={"access_token": "1234", "expires_at": future_expires.isoformat()},
            )
            integration.add_organization(self.project.organization.id, self.user)

        error = Exception("error")
        mock_event.side_effect = error

        response = self.client.post(
            path=self.url,
            data=PULL_REQUEST_OPENED_EVENT_EXAMPLE,
            content_type="application/json",
            HTTP_X_GITHUB_EVENT="pull_request",
            HTTP_X_HUB_SIGNATURE="sha1=bc7ce12fc1058a35bf99355e6fc0e6da72c35de3",
            HTTP_X_HUB_SIGNATURE_256="sha256=ed9e5aed0617ad10312986257e22448b019569200c5fdbd005a2b68a80049317",
            HTTP_X_GITHUB_DELIVERY=str(uuid4()),
        )

        assert response.status_code == 500

        assert_failure_metric(mock_record, error)

    @patch("sentry.integrations.source_code_management.tasks.open_pr_comment_workflow.delay")
    @patch("sentry.integrations.source_code_management.commit_context.metrics")
    @patch("sentry.integrations.utils.metrics.EventLifecycle.record_event")
    def test_opened(
        self,
        mock_record: MagicMock,
        mock_metrics: MagicMock,
        mock_open_pr_comment_workflow_delay: MagicMock,
    ) -> None:
        group = self.create_group(project=self.project, short_id=7)
        repo = Repository.objects.create(
            organization_id=self.project.organization.id,
            external_id="35129377",
            provider="integrations:github",
            name="baxterthehacker/public-repo",
        )

        self._create_integration_and_send_pull_request_opened_event()

        prs = PullRequest.objects.filter(
            repository_id=repo.id, organization_id=self.project.organization.id
        )

        assert len(prs) == 1

        pr = prs[0]

        assert pr.key == "1"
        assert (
            pr.message
            == "This is a pretty simple change that we need to pull into master. Fixes BAR-7"
        )
        assert pr.title == "Update the README with new information"
        assert pr.author is not None
        assert pr.author.name == "baxterthehacker"

        self.assert_group_link(group, pr)

        mock_metrics.incr.assert_called_with("github.open_pr_comment.queue_task")

        assert_success_metric(mock_record)

        mock_open_pr_comment_workflow_delay.assert_called_with(
            pr_id=pr.id,
        )

    @patch("sentry.integrations.github.webhook.metrics")
    def test_opened_missing_option(self, mock_metrics: MagicMock) -> None:
        Repository.objects.create(
            organization_id=self.project.organization.id,
            external_id="35129377",
            provider="integrations:github",
            name="baxterthehacker/public-repo",
        )

        OrganizationOption.objects.set_value(
            organization=self.organization, key="sentry:github_open_pr_bot", value=False
        )

        self._create_integration_and_send_pull_request_opened_event()

        assert mock_metrics.incr.call_count == 0

    @patch("sentry.integrations.github.webhook.metrics")
    def test_creates_missing_repo(self, mock_metrics: MagicMock) -> None:

        self._create_integration_and_send_pull_request_opened_event()

        repos = Repository.objects.all()
        assert len(repos) == 1
        assert repos[0].organization_id == self.project.organization.id
        assert repos[0].external_id == "35129377"
        assert repos[0].provider == "integrations:github"
        assert repos[0].name == "baxterthehacker/public-repo"
        mock_metrics.incr.assert_any_call("github.webhook.repository_created")

    def test_ignores_hidden_repo(self) -> None:

        repo = self.create_repo(
            project=self.project,
            provider="integrations:github",
            name="baxterthehacker/public-repo",
        )
        repo.status = ObjectStatus.HIDDEN
        repo.external_id = "35129377"
        repo.save()

        self._create_integration_and_send_pull_request_opened_event()

        repos = Repository.objects.all()
        assert len(repos) == 1
        assert repos[0] == repo

    @patch("sentry.integrations.github.webhook.metrics")
    def test_multiple_orgs_creates_missing_repo(self, mock_metrics: MagicMock) -> None:
        project = self.project  # force creation

        org2 = self.create_organization()

        future_expires = datetime.now().replace(microsecond=0) + timedelta(minutes=5)
        with assume_test_silo_mode(SiloMode.CONTROL):
            integration = self.create_integration(
                organization=project.organization.id,
                external_id="12345",
                provider="github",
                metadata={"access_token": "1234", "expires_at": future_expires.isoformat()},
            )
            integration.add_organization(org2.id, self.user)
            integration.add_organization(org2.id, self.user)

        response = self.client.post(
            path=self.url,
            data=PULL_REQUEST_OPENED_EVENT_EXAMPLE,
            content_type="application/json",
            HTTP_X_GITHUB_EVENT="pull_request",
            HTTP_X_HUB_SIGNATURE="sha1=bc7ce12fc1058a35bf99355e6fc0e6da72c35de3",
            HTTP_X_HUB_SIGNATURE_256="sha256=ed9e5aed0617ad10312986257e22448b019569200c5fdbd005a2b68a80049317",
            HTTP_X_GITHUB_DELIVERY=str(uuid4()),
        )

        assert response.status_code == 204

        repos = Repository.objects.all()
        assert len(repos) == 2

        assert repos[0].organization_id == project.organization.id
        assert repos[1].organization_id == org2.id
        for repo in repos:
            assert repo.external_id == "35129377"
            assert repo.provider == "integrations:github"
            assert repo.name == "baxterthehacker/public-repo"
        mock_metrics.incr.assert_any_call("github.webhook.repository_created")

    def test_multiple_orgs_ignores_hidden_repo(self) -> None:

        org2 = self.create_organization()

        future_expires = datetime.now().replace(microsecond=0) + timedelta(minutes=5)
        with assume_test_silo_mode(SiloMode.CONTROL):
            integration = self.create_integration(
                organization=self.organization,
                external_id="12345",
                provider="github",
                metadata={"access_token": "1234", "expires_at": future_expires.isoformat()},
            )
            integration.add_organization(self.project.organization.id, self.user)
            integration.add_organization(org2.id, self.user)

        repo = self.create_repo(
            project=self.project,
            provider="integrations:github",
            name="baxterthehacker/public-repo",
        )
        repo.external_id = "35129377"
        repo.status = ObjectStatus.HIDDEN
        repo.save()

        response = self.client.post(
            path=self.url,
            data=PULL_REQUEST_OPENED_EVENT_EXAMPLE,
            content_type="application/json",
            HTTP_X_GITHUB_EVENT="pull_request",
            HTTP_X_HUB_SIGNATURE="sha1=bc7ce12fc1058a35bf99355e6fc0e6da72c35de3",
            HTTP_X_HUB_SIGNATURE_256="sha256=ed9e5aed0617ad10312986257e22448b019569200c5fdbd005a2b68a80049317",
            HTTP_X_GITHUB_DELIVERY=str(uuid4()),
        )

        assert response.status_code == 204

        repos = Repository.objects.all()
        assert len(repos) == 1

        assert repos[0] == repo

    def test_edited_pr_description_with_group_link(self) -> None:
        group = self.create_group(project=self.project, short_id=7)
        url = "/extensions/github/webhook/"
        secret = "b3002c3e321d4b7880360d397db2ccfd"
        options.set("github-app.webhook-secret", secret)

        future_expires = datetime.now().replace(microsecond=0) + timedelta(minutes=5)
        with assume_test_silo_mode(SiloMode.CONTROL):
            integration = self.create_integration(
                organization=self.organization,
                external_id="12345",
                provider="github",
                metadata={"access_token": "1234", "expires_at": future_expires.isoformat()},
            )
            integration.add_organization(self.project.organization.id, self.user)

        repo = Repository.objects.create(
            organization_id=self.project.organization.id,
            external_id="35129377",
            provider="integrations:github",
            name="baxterthehacker/public-repo",
        )

        pr = PullRequest.objects.create(
            key="1", repository_id=repo.id, organization_id=self.project.organization.id
        )

        response = self.client.post(
            path=url,
            data=PULL_REQUEST_EDITED_EVENT_EXAMPLE,
            content_type="application/json",
            HTTP_X_GITHUB_EVENT="pull_request",
            HTTP_X_HUB_SIGNATURE="sha1=83100642f0cf5d7f6145cf8d04da5d00a09f890f",
            HTTP_X_HUB_SIGNATURE_256="sha256=3e45e315ec12367c10ae7aa9de22372868440ece2ea719251a4dc6cc6531ca20",
            HTTP_X_GITHUB_DELIVERY=str(uuid4()),
        )

        assert response.status_code == 204

        pr = PullRequest.objects.get(id=pr.id)

        assert pr.key == "1"
        assert pr.message == "new edited body. Fixes BAR-7"
        assert pr.title == "new edited title"
        assert pr.author is not None
        assert pr.author.name == "baxterthehacker"

        self.assert_group_link(group, pr)

    @patch("sentry.integrations.github.webhook.metrics")
    def test_closed(self, mock_metrics: MagicMock) -> None:
        future_expires = datetime.now().replace(microsecond=0) + timedelta(minutes=5)
        with assume_test_silo_mode(SiloMode.CONTROL):
            integration = self.create_integration(
                organization=self.organization,
                external_id="12345",
                provider="github",
                metadata={"access_token": "1234", "expires_at": future_expires.isoformat()},
            )
            integration.add_organization(self.project.organization.id, self.user)

        repo = Repository.objects.create(
            organization_id=self.project.organization.id,
            external_id="35129377",
            provider="integrations:github",
            name="baxterthehacker/public-repo",
        )

        response = self.client.post(
            path=self.url,
            data=PULL_REQUEST_CLOSED_EVENT_EXAMPLE,
            content_type="application/json",
            HTTP_X_GITHUB_EVENT="pull_request",
            HTTP_X_HUB_SIGNATURE="sha1=49db856f5658b365b73a2fa73a7cffa543f4d3af",
            HTTP_X_HUB_SIGNATURE_256="sha256=c99f2b44a5915b1430d1a1b095a44e3297c70ffd24d06c156a4efc449ec53c47",
            HTTP_X_GITHUB_DELIVERY=str(uuid4()),
        )

        assert response.status_code == 204

        prs = PullRequest.objects.filter(
            repository_id=repo.id, organization_id=self.project.organization.id
        )

        assert len(prs) == 1

        pr = prs[0]

        assert pr.key == "1"
        assert pr.message == "new closed body"
        assert pr.title == "new closed title"
        assert pr.author is not None
        assert pr.author.name == "baxterthehacker"
        assert pr.merge_commit_sha == "0d1a26e67d8f5eaf1f6ba5c57fc3c7d91ac0fd1c"

        assert mock_metrics.incr.call_count == 0

    def assert_group_link(self, group, pr):
        link = GroupLink.objects.get()
        assert link.group_id == group.id
        assert link.linked_id == pr.id
        assert link.linked_type == GroupLink.LinkedType.pull_request
