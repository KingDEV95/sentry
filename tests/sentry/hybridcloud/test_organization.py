import itertools
from collections.abc import Callable
from typing import Any

import pytest
from django.core import mail
from django.db.models import F

from sentry.models.organization import Organization
from sentry.models.organizationmember import InviteStatus, OrganizationMember
from sentry.models.organizationmemberteam import OrganizationMemberTeam
from sentry.models.project import Project
from sentry.models.team import Team, TeamStatus
from sentry.organizations.services.organization import (
    RpcOrganization,
    RpcOrganizationMember,
    RpcTeam,
    RpcTeamMember,
    organization_service,
)
from sentry.organizations.services.organization.serial import serialize_member, unescape_flag_name
from sentry.projects.services.project import RpcProject
from sentry.silo.base import SiloMode
from sentry.testutils.cases import TestCase
from sentry.testutils.factories import Factories
from sentry.testutils.helpers.task_runner import TaskRunner
from sentry.testutils.pytest.fixtures import django_db_all
from sentry.testutils.silo import all_silo_test, assume_test_silo_mode, assume_test_silo_mode_of
from sentry.users.models.user import User


def basic_filled_out_org() -> tuple[Organization, list[User]]:
    owner = Factories.create_user()
    other_user = Factories.create_user()
    Factories.create_organization()  # unrelated org that shouldn't be in the result set
    org = Factories.create_organization(owner=owner)
    team_1 = Factories.create_team(org, members=[owner, other_user])
    team_2 = Factories.create_team(org, members=[other_user])
    team_3 = Factories.create_team(org)
    pending_delete_team = Factories.create_team(org, status=TeamStatus.PENDING_DELETION)
    deletion_in_progress_team = Factories.create_team(org, status=TeamStatus.DELETION_IN_PROGRESS)

    Factories.create_project(organization=org, teams=[team_1, pending_delete_team])
    Factories.create_project(
        organization=org, teams=[pending_delete_team, deletion_in_progress_team]
    )
    Factories.create_project(organization=org, teams=[team_2, deletion_in_progress_team])
    Factories.create_project(organization=org, teams=[team_1, team_2])
    Factories.create_project(organization=org, teams=[team_1])
    Factories.create_project(organization=org, teams=[team_2])

    # a distinct project and team that can only be reached by one user due to an is_active=False link.
    Factories.create_project(organization=org, teams=[team_3])
    Factories.create_team_membership(team=team_3, user=owner)
    inactive_team_membership = Factories.create_team_membership(team=team_3, user=other_user)
    inactive_team_membership.is_active = False
    with assume_test_silo_mode(SiloMode.REGION):
        inactive_team_membership.save()

    return org, [owner, other_user]


parameterize_with_orgs = pytest.mark.parametrize(
    "org_factory", [pytest.param(basic_filled_out_org)]
)


def find_ordering(list_of_things: list[Any], e: Any) -> int:
    try:
        return list_of_things.index(e)
    except ValueError:
        return -1


def order_things_by_id(a: list[Any], b: list[Any]) -> None:
    b_ids = [x.id for x in b]
    a.sort(key=lambda i: find_ordering(b_ids, i.id))


def assert_for_list(a: list[Any], b: list[Any], assertion: Callable[[Any, Any], None]) -> None:
    assert len(a) == len(b)
    order_things_by_id(a, b)
    for a_thing, b_thing in zip(a, b):
        assertion(a_thing, b_thing)


@assume_test_silo_mode(SiloMode.REGION)
def assert_team_equals(orm_team: Team, team: RpcTeam) -> None:
    assert team.id == orm_team.id
    assert team.slug == orm_team.slug
    assert team.status == orm_team.status
    assert team.organization_id == orm_team.organization_id


@assume_test_silo_mode(SiloMode.REGION)
def assert_project_equals(orm_project: Project, project: RpcProject) -> None:
    assert project.id == orm_project.id
    assert project.status == orm_project.status
    assert project.slug == orm_project.slug
    assert project.organization_id == orm_project.organization_id
    assert project.name == orm_project.name
    assert project.first_event == orm_project.first_event


@assume_test_silo_mode(SiloMode.REGION)
def assert_team_member_equals(
    orm_team_member: OrganizationMemberTeam, team_member: RpcTeamMember
) -> None:
    assert team_member.id == orm_team_member.id
    assert team_member.team_id == orm_team_member.team_id
    assert team_member.role == orm_team_member.get_team_role()
    assert team_member.is_active == orm_team_member.is_active
    assert frozenset(team_member.scopes) == orm_team_member.get_scopes()
    assert set(team_member.project_ids) == {
        p.id for p in Project.objects.get_for_team_ids([orm_team_member.team_id])
    }


@assume_test_silo_mode(SiloMode.REGION)
def assert_organization_member_equals(
    orm_organization_member: OrganizationMember, organization_member: RpcOrganizationMember
) -> None:
    assert organization_member.organization_id == orm_organization_member.organization_id
    assert organization_member.id == orm_organization_member.id
    assert organization_member.user_id == orm_organization_member.user_id
    assert organization_member.role == orm_organization_member.role
    assert frozenset(organization_member.scopes) == orm_organization_member.get_scopes()
    assert_for_list(
        list(
            OrganizationMemberTeam.objects.filter(
                organizationmember_id=orm_organization_member.id,
                is_active=True,
                team__status=TeamStatus.ACTIVE,
            )
        ),
        organization_member.member_teams,
        assert_team_member_equals,
    )
    assert set(organization_member.project_ids) == {
        p.id
        for p in Project.objects.get_for_team_ids(
            [omt.team_id for omt in organization_member.member_teams]
        )
    }

    for field_name in organization_member.flags.get_field_names():
        assert getattr(organization_member.flags, field_name) == getattr(
            orm_organization_member.flags, unescape_flag_name(field_name)
        )


@assume_test_silo_mode(SiloMode.REGION)
def assert_orgs_equal(orm_org: Organization, org: RpcOrganization) -> None:
    assert org.id == orm_org.id
    assert org.name == orm_org.name
    assert org.slug == orm_org.slug

    for field_name in org.flags.get_field_names():
        orm_flag = getattr(orm_org.flags, field_name)
        org_flag = getattr(org.flags, field_name)
        assert orm_flag == org_flag

    with assume_test_silo_mode(SiloMode.REGION):
        assert_for_list(
            list(Team.objects.filter(organization_id=org.id)), org.teams, assert_team_equals
        )
        assert_for_list(
            list(Project.objects.filter(organization_id=org.id)),
            org.projects,
            assert_project_equals,
        )


@assume_test_silo_mode(SiloMode.REGION)
def assert_get_organization_by_id_works(user_context: User | None, orm_org: Organization) -> None:
    assert (
        organization_service.get_organization_by_id(
            id=-2, user_id=user_context.id if user_context else None
        )
        is None
    )
    org_context = organization_service.get_organization_by_id(
        id=orm_org.id, user_id=user_context.id if user_context else None
    )
    assert org_context is not None
    assert_orgs_equal(orm_org, org_context.organization)
    if user_context is None:
        assert org_context.user_id is None
        assert org_context.member is None
    else:
        assert org_context.user_id == user_context.id
        assert org_context.member is not None
        assert_organization_member_equals(
            OrganizationMember.objects.get(user_id=user_context.id, organization_id=orm_org.id),
            org_context.member,
        )


@django_db_all(transaction=True)
@all_silo_test
@parameterize_with_orgs
def test_get_organization_id(org_factory: Callable[[], tuple[Organization, list[User]]]) -> None:
    orm_org, orm_users = org_factory()

    for user_context in itertools.chain([None], orm_users):
        assert_get_organization_by_id_works(user_context, orm_org)


@assume_test_silo_mode(SiloMode.REGION)
def assert_get_org_by_id_works(user_context: User | None, orm_org: Organization) -> None:
    assert (
        organization_service.get_org_by_id(id=-2, user_id=user_context.id if user_context else None)
        is None
    )
    org_context = organization_service.get_org_by_id(
        id=orm_org.id, user_id=user_context.id if user_context else None
    )
    assert org_context is not None

    assert orm_org.id == org_context.id
    assert orm_org.name == org_context.name
    assert orm_org.slug == org_context.slug


@django_db_all(transaction=True)
@all_silo_test
@parameterize_with_orgs
def test_get_org_id(org_factory: Callable[[], tuple[Organization, list[User]]]) -> None:
    orm_org, orm_users = org_factory()

    for user_context in itertools.chain([None], orm_users):
        assert_get_org_by_id_works(user_context, orm_org)


@django_db_all(transaction=True)
@all_silo_test
@parameterize_with_orgs
def test_idempotency(org_factory: Callable[[], tuple[Organization, list[User]]]) -> None:
    orm_org, orm_users = org_factory()
    new_user = Factories.create_user()

    for i in range(2):
        member = organization_service.add_organization_member(
            organization_id=orm_org.id, default_org_role=orm_org.default_role, user_id=new_user.id
        )
        with assume_test_silo_mode(SiloMode.REGION):
            assert_organization_member_equals(OrganizationMember.objects.get(id=member.id), member)

        member = organization_service.add_organization_member(
            organization_id=orm_org.id,
            default_org_role=orm_org.default_role,
            email="me@thing.com",
        )
        with assume_test_silo_mode(SiloMode.REGION):
            assert_organization_member_equals(OrganizationMember.objects.get(id=member.id), member)


@django_db_all(transaction=True)
@all_silo_test
def test_options() -> None:
    org = Factories.create_organization()
    organization_service.update_option(organization_id=org.id, key="test", value="a string")
    organization_service.update_option(organization_id=org.id, key="test2", value=False)
    organization_service.update_option(organization_id=org.id, key="test3", value=5)

    assert organization_service.get_option(organization_id=org.id, key="test") == "a string"
    assert organization_service.get_option(organization_id=org.id, key="test2") is False
    assert organization_service.get_option(organization_id=org.id, key="test3") == 5


class RpcOrganizationMemberTest(TestCase):
    def test_get_audit_log_metadata(self) -> None:
        org = self.create_organization(owner=self.user)
        user = self.create_user(email="foobar@sentry.io")
        member = self.create_member(user_id=user.id, role="owner", organization_id=org.id)
        self.create_team(organization=org, slug="baz", members=[user])
        rpc_member = serialize_member(member)
        assert member.get_audit_log_data() == rpc_member.get_audit_log_metadata()


@django_db_all(transaction=True)
def test_update_organization_member() -> None:
    org = Factories.create_organization()
    user = Factories.create_user(email="test@sentry.io")
    rpc_member = organization_service.add_organization_member(
        organization_id=org.id,
        default_org_role="member",
        user_id=user.id,
        invite_status=InviteStatus.APPROVED.value,
    )
    member_query = OrganizationMember.objects.all()
    assert member_query.count() == 1
    assert member_query[0].role == "member"
    assert rpc_member.id == member_query[0].id

    organization_service.update_organization_member(
        organization_id=org.id, member_id=rpc_member.id, attrs=dict(role="manager")
    )
    member_query = OrganizationMember.objects.all()
    assert member_query.count() == 1
    assert member_query[0].role == "manager"


@django_db_all(transaction=True)
@all_silo_test
def test_count_members_without_sso() -> None:
    org = Factories.create_organization()
    user = Factories.create_user(email="test@sentry.io")
    user_two = Factories.create_user(email="has.sso@sentry.io")
    Factories.create_member(organization=org, user=user)
    Factories.create_member(organization=org, email="invite@sentry.io")
    # has sso setup, not included in result
    Factories.create_member(
        organization=org,
        user=user_two,
        flags=OrganizationMember.flags["sso:linked"],
    )
    result = organization_service.count_members_without_sso(organization_id=org.id)
    assert result == 2


@django_db_all(transaction=True)
@all_silo_test
def test_send_sso_unlink_emails() -> None:
    org = Factories.create_organization()
    user = Factories.create_user(email="test@sentry.io")
    user_two = Factories.create_user(email="two@sentry.io")
    Factories.create_member(
        organization=org, user=user, flags=OrganizationMember.flags["sso:linked"]
    )
    Factories.create_member(
        organization=org, user=user_two, flags=OrganizationMember.flags["sso:linked"]
    )
    Factories.create_member(
        organization=org, email="invite@sentry.io", flags=OrganizationMember.flags["sso:invalid"]
    )
    with TaskRunner():
        result = organization_service.send_sso_unlink_emails(
            organization_id=org.id,
            sending_user_email="owner@sentry.io",
            provider_key="google",
        )
        assert result is None

    with assume_test_silo_mode(SiloMode.REGION):
        # No members should be linked or invalid now
        assert (
            OrganizationMember.objects.filter(
                flags=F("flags").bitor(OrganizationMember.flags["sso:linked"])
            ).count()
            == 0
        )
        assert (
            OrganizationMember.objects.filter(
                flags=F("flags").bitor(OrganizationMember.flags["sso:invalid"])
            ).count()
            == 0
        )

    # Only real members should get emails
    assert len(mail.outbox) == 2
    assert "Action Required" in mail.outbox[0].subject
    assert "Single Sign-On" in mail.outbox[0].body


@django_db_all(transaction=True)
@all_silo_test
def test_get_aggregate_project_flags() -> None:
    org = Factories.create_organization()
    project1 = Factories.create_project(organization_id=org.id, name="test-project-1")
    project2 = Factories.create_project(organization_id=org.id, name="test-project-2")
    flags = organization_service.get_aggregate_project_flags(organization_id=org.id)
    assert flags.has_insights_http is False
    assert flags.has_cron_checkins is False

    with assume_test_silo_mode_of(Project):
        project1.flags.has_insights_http = True
        project1.update(flags=F("flags").bitor(Project.flags.has_insights_http))
        project2.flags.has_insights_http = True
        project2.update(flags=F("flags").bitor(Project.flags.has_cron_checkins))

    flags = organization_service.get_aggregate_project_flags(organization_id=org.id)
    assert flags.has_insights_http is True
    assert flags.has_cron_checkins is True
