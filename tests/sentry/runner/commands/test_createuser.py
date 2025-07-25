from sentry import roles
from sentry.models.organization import Organization
from sentry.models.organizationmember import OrganizationMember
from sentry.receivers import create_default_projects
from sentry.runner.commands.createuser import createuser
from sentry.silo.base import SiloMode
from sentry.testutils.cases import CliTestCase
from sentry.testutils.silo import assume_test_silo_mode, control_silo_test
from sentry.users.models.user import User
from sentry.users.models.userrole import manage_default_super_admin_role
from sentry.users.services.user.service import user_service


@control_silo_test
class CreateUserTest(CliTestCase):
    command = createuser
    default_args = ["--no-input"]

    def setUp(self) -> None:
        super().setUp()
        with assume_test_silo_mode(SiloMode.REGION):
            create_default_projects()
        manage_default_super_admin_role()

    def test_superuser(self) -> None:
        rv = self.invoke("--email=you@somewhereawesome.com", "--password=awesome", "--superuser")
        assert rv.exit_code == 0, rv.output
        assert "you@somewhereawesome.com" in rv.output
        assert User.objects.count() == 1
        user = User.objects.all()[0]
        assert user.email == "you@somewhereawesome.com"
        assert user.check_password("awesome")
        assert user.is_superuser
        assert user.is_staff
        assert user.is_active

    def test_no_superuser(self) -> None:
        rv = self.invoke("--email=you@somewhereawesome.com", "--password=awesome")
        assert rv.exit_code == 0, rv.output
        assert "you@somewhereawesome.com" in rv.output
        assert User.objects.count() == 1
        user = User.objects.all()[0]
        assert user.email == "you@somewhereawesome.com"
        assert user.check_password("awesome")
        assert not user.is_superuser
        assert not user.is_staff
        assert user.is_active

    def test_no_password(self) -> None:
        rv = self.invoke("--email=you@somewhereawesome.com", "--no-password")
        assert rv.exit_code == 0, rv.output
        assert "you@somewhereawesome.com" in rv.output
        assert User.objects.count() == 1
        user = User.objects.all()[0]
        assert user.email == "you@somewhereawesome.com"
        assert not user.password
        assert not user.is_superuser
        assert not user.is_staff
        assert user.is_active

    def test_single_org(self) -> None:
        with self.settings(SENTRY_SINGLE_ORGANIZATION=True):
            rv = self.invoke("--email=you@somewhereawesome.com", "--no-password")
            assert rv.exit_code == 0, rv.output
            assert "you@somewhereawesome.com" in rv.output
            with assume_test_silo_mode(SiloMode.REGION):
                assert OrganizationMember.objects.count() == 1
                member = OrganizationMember.objects.all()[0]
            assert member.user_id is not None
            u = user_service.get_user(user_id=member.user_id)
            assert u
            assert u.email == "you@somewhereawesome.com"
            assert member.organization.slug in rv.output
            assert member.role == member.organization.default_role

    def test_single_org_superuser(self) -> None:
        with self.settings(SENTRY_SINGLE_ORGANIZATION=True):
            rv = self.invoke("--email=you@somewhereawesome.com", "--no-password", "--superuser")
            assert rv.exit_code == 0, rv.output
            assert "you@somewhereawesome.com" in rv.output
            with assume_test_silo_mode(SiloMode.REGION):
                assert OrganizationMember.objects.count() == 1
                member = OrganizationMember.objects.all()[0]
            assert member.user_id is not None
            u = user_service.get_user(user_id=member.user_id)
            assert u
            assert u.email == "you@somewhereawesome.com"
            assert member.organization.slug in rv.output
            assert member.role == roles.get_top_dog().id

    def test_single_org_with_specified_id(self) -> None:
        with assume_test_silo_mode(SiloMode.REGION):
            sentry_org = Organization.objects.get(slug="sentry")
        with self.settings(SENTRY_SINGLE_ORGANIZATION=True):
            rv = self.invoke(
                "--email=you@somewhereawesome.com", "--no-password", f"--org-id={sentry_org.id}"
            )
            assert rv.exit_code == 0, rv.output

    def test_not_single_org(self) -> None:
        with self.settings(SENTRY_SINGLE_ORGANIZATION=False):
            rv = self.invoke("--email=you@somewhereawesome.com", "--no-password")
            assert rv.exit_code == 0, rv.output
            assert "you@somewhereawesome.com" in rv.output
            with assume_test_silo_mode(SiloMode.REGION):
                member_count = OrganizationMember.objects.count()
            assert member_count == 0

    def test_no_input(self) -> None:
        rv = self.invoke()
        assert rv.exit_code != 0, rv.output

    def test_missing_password(self) -> None:
        rv = self.invoke("--email=you@somewhereawesome.com")
        assert rv.exit_code != 0, rv.output
