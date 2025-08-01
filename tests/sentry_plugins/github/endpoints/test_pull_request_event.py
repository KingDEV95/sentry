from uuid import uuid4

from sentry.models.options.organization_option import OrganizationOption
from sentry.models.pullrequest import PullRequest
from sentry.models.repository import Repository
from sentry.silo.base import SiloMode
from sentry.testutils.cases import APITestCase
from sentry.testutils.silo import assume_test_silo_mode
from sentry_plugins.github.testutils import (
    PULL_REQUEST_CLOSED_EVENT_EXAMPLE,
    PULL_REQUEST_EDITED_EVENT_EXAMPLE,
    PULL_REQUEST_OPENED_EVENT_EXAMPLE,
)
from social_auth.models import UserSocialAuth


class PullRequestEventWebhook(APITestCase):
    def test_opened(self) -> None:
        project = self.project  # force creation
        user = self.create_user(email="alberto@sentry.io")
        with assume_test_silo_mode(SiloMode.CONTROL):
            UserSocialAuth.objects.create(provider="github", user=user, uid=6752317)
        self.create_member(organization=project.organization, user=user, role="member")

        url = f"/plugins/github/organizations/{project.organization.id}/webhook/"

        secret = "b3002c3e321d4b7880360d397db2ccfd"

        OrganizationOption.objects.set_value(
            organization=project.organization, key="github:webhook_secret", value=secret
        )

        repo = Repository.objects.create(
            organization_id=project.organization.id,
            external_id="35129377",
            provider="github_apps",
            name="baxterthehacker/public-repo",
        )

        response = self.client.post(
            path=url,
            data=PULL_REQUEST_OPENED_EVENT_EXAMPLE,
            content_type="application/json",
            HTTP_X_GITHUB_EVENT="pull_request",
            HTTP_X_HUB_SIGNATURE="sha1=aa5b11bc52b9fac082cb59f9ee8667cb222c3aff",
            HTTP_X_GITHUB_DELIVERY=str(uuid4()),
        )

        assert response.status_code == 204

        prs = PullRequest.objects.filter(
            repository_id=repo.id, organization_id=project.organization.id
        )

        assert len(prs) == 1

        pr = prs[0]

        assert pr.key == "1"
        assert pr.message == "This is a pretty simple change that we need to pull into master."
        assert pr.title == "Update the README with new information"
        assert pr.author is not None
        assert pr.author.name == "baxterthehacker"
        assert pr.author.email == "alberto@sentry.io"

    def test_edited(self) -> None:
        project = self.project  # force creation

        url = f"/plugins/github/organizations/{project.organization.id}/webhook/"

        secret = "b3002c3e321d4b7880360d397db2ccfd"

        OrganizationOption.objects.set_value(
            organization=project.organization, key="github:webhook_secret", value=secret
        )

        repo = Repository.objects.create(
            organization_id=project.organization.id,
            external_id="35129377",
            provider="github_apps",
            name="baxterthehacker/public-repo",
        )

        pr = PullRequest.objects.create(
            key="1", repository_id=repo.id, organization_id=project.organization.id
        )

        response = self.client.post(
            path=url,
            data=PULL_REQUEST_EDITED_EVENT_EXAMPLE,
            content_type="application/json",
            HTTP_X_GITHUB_EVENT="pull_request",
            HTTP_X_HUB_SIGNATURE="sha1=b50a13afd33b514e8e62e603827ea62530f0690e",
            HTTP_X_GITHUB_DELIVERY=str(uuid4()),
        )

        assert response.status_code == 204

        pr = PullRequest.objects.get(id=pr.id)

        assert pr.key == "1"
        assert pr.message == "new edited body"
        assert pr.title == "new edited title"
        assert pr.author is not None
        assert pr.author.name == "baxterthehacker"
        assert pr.author.email == "baxterthehacker@localhost"

    def test_closed(self) -> None:
        project = self.project  # force creation

        url = f"/plugins/github/organizations/{project.organization.id}/webhook/"

        secret = "b3002c3e321d4b7880360d397db2ccfd"

        OrganizationOption.objects.set_value(
            organization=project.organization, key="github:webhook_secret", value=secret
        )

        repo = Repository.objects.create(
            organization_id=project.organization.id,
            external_id="35129377",
            provider="github_apps",
            name="baxterthehacker/public-repo",
        )

        response = self.client.post(
            path=url,
            data=PULL_REQUEST_CLOSED_EVENT_EXAMPLE,
            content_type="application/json",
            HTTP_X_GITHUB_EVENT="pull_request",
            HTTP_X_HUB_SIGNATURE="sha1=dff1c803cf1e48c1b9aefe4a17952ea132758806",
            HTTP_X_GITHUB_DELIVERY=str(uuid4()),
        )

        assert response.status_code == 204

        prs = PullRequest.objects.filter(
            repository_id=repo.id, organization_id=project.organization.id
        )

        assert len(prs) == 1

        pr = prs[0]

        assert pr.key == "1"
        assert pr.message == "new closed body"
        assert pr.title == "new closed title"
        assert pr.author is not None
        assert pr.author.name == "baxterthehacker"
        assert pr.author.email == "baxterthehacker@localhost"
        assert pr.merge_commit_sha == "0d1a26e67d8f5eaf1f6ba5c57fc3c7d91ac0fd1c"
