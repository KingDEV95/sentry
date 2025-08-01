from uuid import uuid4

from sentry.api.serializers import serialize
from sentry.models.commit import Commit
from sentry.models.commitauthor import CommitAuthor
from sentry.models.pullrequest import PullRequest
from sentry.models.release import Release
from sentry.models.releasecommit import ReleaseCommit
from sentry.models.repository import Repository
from sentry.testutils.cases import TestCase


class CommitSerializerTest(TestCase):
    def test_simple(self) -> None:
        user = self.create_user()
        project = self.create_project()
        release = Release.objects.create(
            organization_id=project.organization_id, version=uuid4().hex
        )
        release.add_project(project)
        repository = Repository.objects.create(
            organization_id=project.organization_id, name="test/test"
        )
        commit_author = CommitAuthor.objects.create(
            name="stebe", email="stebe@sentry.io", organization_id=project.organization_id
        )
        commit = Commit.objects.create(
            organization_id=project.organization_id,
            repository_id=repository.id,
            key="abc",
            author=commit_author,
            message="waddap",
        )
        ReleaseCommit.objects.create(
            organization_id=project.organization_id,
            project_id=project.id,
            release=release,
            commit=commit,
            order=1,
        )
        result = serialize(commit, user)

        assert result["message"] == "waddap"
        assert result["repository"]["name"] == "test/test"
        assert result["author"] == {"name": "stebe", "email": "stebe@sentry.io"}

    def test_no_author(self) -> None:
        user = self.create_user()
        project = self.create_project()
        release = Release.objects.create(
            organization_id=project.organization_id, version=uuid4().hex
        )
        release.add_project(project)
        repository = Repository.objects.create(
            organization_id=project.organization_id, name="test/test"
        )
        commit = Commit.objects.create(
            organization_id=project.organization_id,
            repository_id=repository.id,
            key="abc",
            message="waddap",
        )
        ReleaseCommit.objects.create(
            organization_id=project.organization_id,
            project_id=project.id,
            release=release,
            commit=commit,
            order=1,
        )

        result = serialize(commit, user)

        assert result["author"] == {}

    def test_pull_requests(self) -> None:
        """Test we can correctly match pull requests to commits."""
        user = self.create_user()
        project = self.create_project()
        release = Release.objects.create(
            organization_id=project.organization_id, version=uuid4().hex
        )
        release.add_project(project)
        repository = Repository.objects.create(
            organization_id=project.organization_id, name="test/test"
        )
        commit1 = Commit.objects.create(
            organization_id=project.organization_id,
            repository_id=repository.id,
            key="abc",
            message="waddap",
        )
        ReleaseCommit.objects.create(
            organization_id=project.organization_id,
            project_id=project.id,
            release=release,
            commit=commit1,
            order=1,
        )

        commit2 = Commit.objects.create(
            organization_id=project.organization_id,
            repository_id=repository.id,
            key="def",
            message="waddap2",
        )
        ReleaseCommit.objects.create(
            organization_id=project.organization_id,
            project_id=project.id,
            release=release,
            commit=commit2,
            order=2,
        )

        PullRequest.objects.create(
            organization_id=project.organization_id,
            repository_id=repository.id,
            key="pr1",
            merge_commit_sha=commit1.key,
        )
        PullRequest.objects.create(
            organization_id=project.organization_id,
            repository_id=repository.id,
            key="pr2",
            merge_commit_sha=commit2.key,
        )
        PullRequest.objects.create(
            organization_id=project.organization_id,
            repository_id=repository.id,
            key="pr3",
            merge_commit_sha=commit1.key,
        )

        results = serialize([commit1, commit2], user)

        # In the case of multiple pull requests, one is chosen arbitrarily.
        assert results[0]["pullRequest"]["id"] == "pr1" or results[0]["pullRequest"]["id"] == "pr3"
        assert results[1]["pullRequest"]["id"] == "pr2"
