from sentry.models.commit import Commit
from sentry.models.commitfilechange import CommitFileChange
from sentry.models.repository import Repository
from sentry.testutils.cases import TestCase


class CommitFileChangeTest(TestCase):
    def test_get_count_for_commits(self) -> None:
        group = self.create_group()
        organization_id = group.organization.id
        repo = Repository.objects.create(name="example", organization_id=organization_id)
        commit = Commit.objects.create(
            key="a" * 40,
            repository_id=repo.id,
            organization_id=organization_id,
            message=f"Foo Biz\n\nFixes {group.qualified_short_id}",
        )
        CommitFileChange.objects.create(
            organization_id=organization_id, commit=commit, filename=".gitignore", type="M"
        )

        count = CommitFileChange.objects.get_count_for_commits([commit])
        assert count == 1
