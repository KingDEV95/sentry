from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.core import mail
from django.db import router
from django.utils import timezone
from rest_framework.serializers import ValidationError

from sentry import roles
from sentry.auth import manager
from sentry.exceptions import UnableToAcceptMemberInvitationException
from sentry.models.authidentity import AuthIdentity
from sentry.models.authprovider import AuthProvider
from sentry.models.options.organization_option import OrganizationOption
from sentry.models.organizationmember import INVITE_DAYS_VALID, InviteStatus, OrganizationMember
from sentry.silo.base import SiloMode
from sentry.silo.safety import unguarded_write
from sentry.testutils.cases import TestCase
from sentry.testutils.helpers import with_feature
from sentry.testutils.hybrid_cloud import HybridCloudTestMixin
from sentry.testutils.outbox import outbox_runner
from sentry.testutils.silo import assume_test_silo_mode
from sentry.users.services.user.service import user_service


class MockOrganizationRoles:
    TEST_ORG_ROLES = [
        {
            "id": "alice",
            "name": "Alice",
            "desc": "In Wonderland",
            "scopes": ["project:read", "project:write"],
        },
        {"id": "bob", "name": "Bob", "desc": "The builder", "scopes": ["project:read"]},
        {"id": "carol", "name": "Carol", "desc": "A nanny?", "scopes": ["project:write"]},
    ]

    TEST_TEAM_ROLES = [
        {"id": "alice", "name": "Alice", "desc": "In Wonderland"},
        {"id": "bob", "name": "Bob", "desc": "The builder"},
        {"id": "carol", "name": "Carol", "desc": "A nanny?"},
    ]

    def __init__(self):
        from sentry.roles.manager import RoleManager

        self.default_manager = RoleManager(self.TEST_ORG_ROLES, self.TEST_TEAM_ROLES)
        self.organization_roles = self.default_manager.organization_roles

    def get_all(self):
        return self.organization_roles.get_all()

    def get(self, x):
        return self.organization_roles.get(x)


class OrganizationMemberTest(TestCase, HybridCloudTestMixin):
    def test_legacy_token_generation(self) -> None:
        member = OrganizationMember(id=1, organization_id=1, email="foo@example.com")
        with self.settings(SECRET_KEY="a"):
            assert member.legacy_token == "f3f2aa3e57f4b936dfd4f42c38db003e"

    def test_legacy_token_generation_no_email(self) -> None:
        """
        We include membership tokens in RPC memberships so it needs to not error
        for accepted invites.
        """
        member = OrganizationMember(organization_id=1, user_id=self.user.id)
        assert member.legacy_token

    def test_legacy_token_generation_unicode_key(self) -> None:
        member = OrganizationMember(id=1, organization_id=1, email="foo@example.com")
        with self.settings(
            SECRET_KEY=(
                b"\xfc]C\x8a\xd2\x93\x04\x00\x81\xeak\x94\x02H"
                b"\x1d\xcc&P'q\x12\xa2\xc0\xf2v\x7f\xbb*lX"
            )
        ):
            assert member.legacy_token == "df41d9dfd4ba25d745321e654e15b5d0"

    def test_get_invite_link_with_referrer(self) -> None:
        member = OrganizationMember(id=1, organization=self.organization, email="foo@example.com")

        link = member.get_invite_link(referrer="test_referrer")
        assert "?referrer=test_referrer" in link

    def test_send_invite_email(self) -> None:
        member = OrganizationMember(id=1, organization=self.organization, email="foo@example.com")
        with self.options({"system.url-prefix": "http://example.com"}), self.tasks():
            member.send_invite_email()

        assert len(mail.outbox) == 1

        msg = mail.outbox[0]
        assert msg.to == ["foo@example.com"]

    @with_feature("system:multi-region")
    def test_send_invite_email_customer_domains(self) -> None:
        member = OrganizationMember(id=1, organization=self.organization, email="admin@example.com")
        with self.tasks():
            member.send_invite_email()
        assert len(mail.outbox) == 1
        assert self.organization.absolute_url("/accept/") in mail.outbox[0].body

    def test_send_sso_link_email(self) -> None:
        organization = self.create_organization()
        member = OrganizationMember(id=1, organization=organization, email="foo@example.com")
        provider = manager.get("dummy")
        with self.options({"system.url-prefix": "http://example.com"}), self.tasks():
            member.send_sso_link_email("sender@example.com", provider)

        assert len(mail.outbox) == 1

        msg = mail.outbox[0]
        assert msg.to == ["foo@example.com"]
        assert msg.subject == f"Action Required for {organization.name}"

    @patch("sentry.utils.email.MessageBuilder")
    def test_send_sso_unlink_email(self, builder: MagicMock) -> None:
        with assume_test_silo_mode(SiloMode.CONTROL):
            user = self.create_user(email="foo@example.com")
            user.password = ""
            user.save()

        member = self.create_member(user=user, organization=self.organization)
        provider = manager.get("dummy")

        with self.options({"system.url-prefix": "http://example.com"}), self.tasks():
            rpc_user = user_service.get_user(user_id=user.id)
            member.send_sso_unlink_email(rpc_user, provider)

        context = builder.call_args[1]["context"]

        assert context["organization"] == self.organization
        assert context["provider"] == provider
        assert context["actor_email"] == user.email

        assert not context["has_password"]
        assert "set_password_url" in context

    @patch("sentry.utils.email.MessageBuilder")
    def test_send_sso_unlink_email_str_sender(self, builder: MagicMock) -> None:
        with assume_test_silo_mode(SiloMode.CONTROL):
            user = self.create_user(email="foo@example.com")
            user.password = ""
            user.save()

        member = self.create_member(user=user, organization=self.organization)
        provider = manager.get("dummy")

        with self.options({"system.url-prefix": "http://example.com"}), self.tasks():
            member.send_sso_unlink_email(user.email, provider)

        context = builder.call_args[1]["context"]

        assert context["organization"] == self.organization
        assert context["provider"] == provider
        assert context["actor_email"] == user.email

        assert not context["has_password"]
        assert "set_password_url" in context

    def test_token_expires_at_set_on_save(self) -> None:
        with outbox_runner():
            member = OrganizationMember(organization=self.organization, email="foo@example.com")
            member.token = member.generate_token()
            member.save()
        self.assert_org_member_mapping(org_member=member)

        expires_at = timezone.now() + timedelta(days=INVITE_DAYS_VALID)
        assert member.token_expires_at
        assert member.token_expires_at.date() == expires_at.date()

    def test_token_expiration(self) -> None:
        with outbox_runner():
            member = OrganizationMember(organization=self.organization, email="foo@example.com")
            member.token = member.generate_token()
            member.save()
        self.assert_org_member_mapping(org_member=member)

        assert member.is_pending
        assert member.token_expired is False

        member.token_expires_at = timezone.now() - timedelta(minutes=1)
        assert member.token_expired

    def test_set_user(self) -> None:
        with outbox_runner():
            member = OrganizationMember(organization=self.organization, email="foo@example.com")
            member.token = member.generate_token()
            member.save()

        self.assert_org_member_mapping(org_member=member)

        with outbox_runner():
            user = self.create_user(email="foo@example.com")
            member.set_user(user.id)
            member.save()

        assert member.is_pending is False
        assert member.token_expires_at is None
        assert member.token is None
        assert member.email is None
        member.refresh_from_db()
        self.assert_org_member_mapping(org_member=member)

    def test_regenerate_token(self) -> None:
        member = OrganizationMember(organization=self.organization, email="foo@example.com")
        assert (member.token, member.token_expires_at) == (None, None)

        member.regenerate_token()
        assert member.token
        assert member.token_expires_at
        expires_at = timezone.now() + timedelta(days=INVITE_DAYS_VALID)
        assert member.token_expires_at.date() == expires_at.date()

    def test_delete_expired_clear(self) -> None:
        ninety_one_days = timezone.now() - timedelta(days=1)
        member = self.create_member(
            organization=self.organization,
            role="member",
            email="test@example.com",
            token="abc-def",
            token_expires_at=ninety_one_days,
        )
        with outbox_runner():
            OrganizationMember.objects.delete_expired(timezone.now())
        assert OrganizationMember.objects.filter(id=member.id).first() is None
        self.assert_org_member_mapping_not_exists(org_member=member)

    def test_delete_identities(self) -> None:
        org = self.create_organization()
        user = self.create_user()
        member = self.create_member(user_id=user.id, organization_id=org.id)
        self.assert_org_member_mapping(org_member=member)
        with assume_test_silo_mode(SiloMode.CONTROL):
            ap = AuthProvider.objects.create(
                organization_id=org.id, provider="sentry_auth_provider", config={}
            )
            AuthIdentity.objects.create(user=user, auth_provider=ap)
            qs = AuthIdentity.objects.filter(auth_provider__organization_id=org.id, user_id=user.id)
            assert qs.exists()

        with outbox_runner():
            member.outbox_for_update().save()

        # ensure that even if the outbox sends a general, non delete update, it doesn't cascade
        # the delete to auth identity objects.
        with assume_test_silo_mode(SiloMode.CONTROL):
            assert qs.exists()

        with outbox_runner():
            member.delete()

        with assume_test_silo_mode(SiloMode.CONTROL):
            assert not qs.exists()
            self.assert_org_member_mapping_not_exists(org_member=member)

    def test_delete_expired_SCIM_enabled(self) -> None:
        organization = self.create_organization()
        org3 = self.create_organization()
        with assume_test_silo_mode(SiloMode.CONTROL):
            AuthProvider.objects.create(
                provider="saml2",
                organization_id=organization.id,
                flags=AuthProvider.flags.scim_enabled,
            )
            AuthProvider.objects.create(
                provider="saml2",
                organization_id=org3.id,
                flags=AuthProvider.flags.allow_unlinked,
            )
        ninety_one_days = timezone.now() - timedelta(days=91)
        member = self.create_member(
            organization=organization,
            role="member",
            email="test@example.com",
            token="abc-def",
            token_expires_at=ninety_one_days,
        )
        member2 = self.create_member(
            organization=org3,
            role="member",
            email="test2@example.com",
            token="abc-defg",
            token_expires_at=ninety_one_days,
        )
        with outbox_runner():
            OrganizationMember.objects.delete_expired(timezone.now())
        assert OrganizationMember.objects.filter(id=member.id).exists()
        assert not OrganizationMember.objects.filter(id=member2.id).exists()
        self.assert_org_member_mapping_not_exists(org_member=member2)

    def test_delete_expired_miss(self) -> None:
        tomorrow = timezone.now() + timedelta(days=1)
        member = self.create_member(
            organization=self.organization,
            role="member",
            email="test@example.com",
            token="abc-def",
            token_expires_at=tomorrow,
        )
        with outbox_runner():
            OrganizationMember.objects.delete_expired(timezone.now())
        assert OrganizationMember.objects.filter(id=member.id).exists()
        self.assert_org_member_mapping(org_member=member)

    def test_delete_expired_leave_claimed(self) -> None:
        user = self.create_user()
        member = self.create_member(
            organization=self.organization,
            role="member",
            user=user,
            token="abc-def",
            token_expires_at="2018-01-01 10:00:00+00:00",
        )
        with outbox_runner():
            OrganizationMember.objects.delete_expired(timezone.now())
        assert OrganizationMember.objects.filter(id=member.id).exists()
        self.assert_org_member_mapping(org_member=member)

    def test_delete_expired_leave_null_expires(self) -> None:
        member = self.create_member(
            organization=self.organization,
            role="member",
            email="test@example.com",
            token="abc-def",
            token_expires_at=None,
        )
        with outbox_runner():
            OrganizationMember.objects.delete_expired(timezone.now())
        assert OrganizationMember.objects.get(id=member.id)
        self.assert_org_member_mapping(org_member=member)

    def test_approve_invite(self) -> None:
        member = self.create_member(
            organization=self.organization,
            role="member",
            email="test@example.com",
            invite_status=InviteStatus.REQUESTED_TO_BE_INVITED.value,
        )
        assert not member.invite_approved

        member.approve_invite()
        member.save()

        member = OrganizationMember.objects.get(id=member.id)
        assert member.invite_approved
        assert member.invite_status == InviteStatus.APPROVED.value
        self.assert_org_member_mapping(org_member=member)

    def test_scopes_with_member_admin_config(self) -> None:
        member = OrganizationMember.objects.create(
            organization=self.organization,
            role="member",
            email="test@example.com",
        )

        assert "event:admin" in member.get_scopes()

        self.organization.update_option("sentry:events_member_admin", True)

        assert "event:admin" in member.get_scopes()

        self.organization.update_option("sentry:events_member_admin", False)

        assert "event:admin" not in member.get_scopes()

    def test_scopes_with_member_alert_write(self) -> None:
        member = OrganizationMember.objects.create(
            organization=self.organization,
            role="member",
            email="test@example.com",
        )
        admin = OrganizationMember.objects.create(
            organization=self.organization,
            role="admin",
            email="admin@example.com",
        )

        assert "alerts:write" in member.get_scopes()
        assert "alerts:write" in admin.get_scopes()

        self.organization.update_option("sentry:alerts_member_write", True)

        assert "alerts:write" in member.get_scopes()
        assert "alerts:write" in admin.get_scopes()

        self.organization.update_option("sentry:alerts_member_write", False)

        assert "alerts:write" not in member.get_scopes()
        assert "alerts:write" in admin.get_scopes()

    def test_get_contactable_members_for_org(self) -> None:
        organization = self.create_organization()
        user1 = self.create_user()
        user2 = self.create_user()

        member = self.create_member(organization=organization, user=user1)
        self.create_member(
            organization=organization,
            user=user2,
            invite_status=InviteStatus.REQUESTED_TO_BE_INVITED.value,
        )
        self.create_member(organization=organization, email="hi@example.com")

        assert OrganizationMember.objects.filter(organization=organization).count() == 3
        results = OrganizationMember.objects.get_contactable_members_for_org(organization.id)
        assert results.count() == 1
        assert results[0].user_id == member.user_id

    def test_validate_invitation_success(self) -> None:
        member = self.create_member(
            organization=self.organization,
            invite_status=InviteStatus.REQUESTED_TO_BE_INVITED.value,
            email="hello@sentry.io",
            role="member",
        )
        user = self.create_user()
        assert member.validate_invitation(user, [roles.get("member")])

    @with_feature({"organizations:invite-members": False})
    def test_validate_invitation_lack_feature(self) -> None:
        member = self.create_member(
            organization=self.organization,
            invite_status=InviteStatus.REQUESTED_TO_BE_INVITED.value,
            email="hello@sentry.io",
            role="member",
        )
        user = self.create_user()
        with pytest.raises(
            UnableToAcceptMemberInvitationException,
            match="Your organization is not allowed to invite members.",
        ):
            member.validate_invitation(user, [roles.get("member")])

    def test_validate_invitation_no_join_requests(self) -> None:
        OrganizationOption.objects.create(
            organization_id=self.organization.id, key="sentry:join_requests", value=False
        )

        member = self.create_member(
            organization=self.organization,
            invite_status=InviteStatus.REQUESTED_TO_JOIN.value,
            email="hello@sentry.io",
            role="member",
        )
        user = self.create_user()
        with pytest.raises(
            UnableToAcceptMemberInvitationException,
            match="Your organization does not allow requests to join.",
        ):
            member.validate_invitation(user, [roles.get("member")])

    def test_validate_invitation_outside_allowed_role(self) -> None:
        member = self.create_member(
            organization=self.organization,
            invite_status=InviteStatus.REQUESTED_TO_BE_INVITED.value,
            email="hello@sentry.io",
            role="admin",
        )
        user = self.create_user()
        with pytest.raises(
            UnableToAcceptMemberInvitationException,
            match="You do not have permission to approve a member invitation with the role admin.",
        ):
            member.validate_invitation(user, [roles.get("member")])

    def test_approve_member_invitation(self) -> None:
        member = self.create_member(
            organization=self.organization,
            invite_status=InviteStatus.REQUESTED_TO_BE_INVITED.value,
            email="hello@sentry.io",
            role="member",
        )
        user = self.create_user()
        member.approve_member_invitation(user)
        self.assert_org_member_mapping(org_member=member)
        assert member.invite_status == InviteStatus.APPROVED.value

    def test_reject_member_invitation(self) -> None:
        member = self.create_member(
            organization=self.organization,
            invite_status=InviteStatus.REQUESTED_TO_BE_INVITED.value,
            email="hello@sentry.io",
            role="member",
        )
        user = self.create_user()
        member.reject_member_invitation(user)
        assert not OrganizationMember.objects.filter(id=member.id).exists()
        self.assert_org_member_mapping_not_exists(org_member=member)

    def test_invalid_reject_member_invitation(self) -> None:
        user = self.create_user(email="hello@sentry.io")
        member = self.create_member(
            organization=self.organization,
            invite_status=InviteStatus.APPROVED.value,
            user=user,
            role="member",
        )
        user = self.create_user()
        member.reject_member_invitation(user)
        self.assert_org_member_mapping(org_member=member)
        assert OrganizationMember.objects.filter(id=member.id).exists()

    def test_get_allowed_org_roles_to_invite(self) -> None:
        member = OrganizationMember.objects.get(
            user_id=self.user.id, organization=self.organization
        )
        with unguarded_write(using=router.db_for_write(OrganizationMember)):
            member.update(role="manager")
        assert member.get_allowed_org_roles_to_invite() == [
            roles.get("member"),
            roles.get("admin"),
            roles.get("manager"),
        ]

    def test_get_allowed_org_roles_to_invite_subset_logic(self) -> None:
        mock_org_roles = MockOrganizationRoles()
        with (
            patch("sentry.roles.organization_roles.get", mock_org_roles.get),
            patch("sentry.roles.organization_roles.get_all", mock_org_roles.get_all),
        ):
            alice = self.create_member(
                user=self.create_user(), organization=self.organization, role="alice"
            )
            assert alice.get_allowed_org_roles_to_invite() == [
                roles.get("alice"),
                roles.get("bob"),
                roles.get("carol"),
            ]

            bob = self.create_member(
                user=self.create_user(), organization=self.organization, role="bob"
            )
            assert bob.get_allowed_org_roles_to_invite() == [
                roles.get("bob"),
            ]

            carol = self.create_member(
                user=self.create_user(), organization=self.organization, role="carol"
            )
            assert carol.get_allowed_org_roles_to_invite() == [
                roles.get("carol"),
            ]

    def test_cannot_demote_last_owner(self) -> None:
        org = self.create_organization()

        with pytest.raises(ValidationError):
            member = self.create_member(organization=org, role="owner", user=self.create_user())

            member.role = "manager"
            member.save()

    def test_cannot_edit_placeholder_org_member(self) -> None:
        omi = self.create_member_invite()
        placeholder_om = omi.organization_member

        placeholder_om.role = "manager"
        with pytest.raises(
            AssertionError, match="Cannot save placeholder organization member for an invited user"
        ):
            placeholder_om.save()
