"""Tests for admin dashboard management commands (issue #1326)."""
from datetime import date
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError

from soroscan.ingest.models import (
    APIKey,
    Invoice,
    Organization,
    OrganizationCostSnapshot,
    OrganizationMembership,
)
from soroscan.ingest.tests.factories import UserFactory

User = get_user_model()


def _call(command, *args, **kwargs):
    out = StringIO()
    err = StringIO()
    call_command(command, *args, stdout=out, stderr=err, **kwargs)
    return out.getvalue(), err.getvalue()


def _help(command_name):
    from django.core.management import load_command_class

    cmd = load_command_class("soroscan.ingest", command_name)
    parser = cmd.create_parser("manage.py", command_name)
    return parser.format_help()


@pytest.mark.django_db
class TestCreateOrganizationCommand:
    def test_help_text_describes_required_options(self):
        help_text = _help("create_organization")
        assert "Create a new organization" in help_text
        assert "--name" in help_text
        assert "--owner" in help_text
        assert "--slug" in help_text
        assert "--quota" in help_text

    def test_creates_organization_and_owner_membership(self):
        owner = UserFactory(username="alice")
        out, _ = _call(
            "create_organization",
            "--name",
            "Acme Corp",
            "--owner",
            "alice",
            "--quota",
            "5000",
        )

        org = Organization.objects.get(name="Acme Corp")
        assert org.owner == owner
        assert org.slug == "acme-corp"
        assert org.quota == 5000
        assert OrganizationMembership.objects.filter(
            organization=org,
            user=owner,
            role=OrganizationMembership.Role.OWNER,
        ).exists()
        assert "Created organization" in out
        assert "acme-corp" in out

    def test_creates_organization_using_owner_email(self):
        owner = UserFactory(username="bob", email="bob@example.com")
        _call(
            "create_organization",
            name="Email Org",
            owner="bob@example.com",
            slug="email-org",
        )
        org = Organization.objects.get(slug="email-org")
        assert org.owner == owner

    def test_rejects_missing_owner(self):
        with pytest.raises(CommandError, match="not found"):
            call_command("create_organization", name="Ghost Org", owner="missing")

    def test_rejects_duplicate_slug(self):
        owner = UserFactory()
        Organization.objects.create(name="Taken", slug="taken", owner=owner)
        with pytest.raises(CommandError, match="already exists"):
            call_command(
                "create_organization",
                name="Other",
                owner=owner.username,
                slug="taken",
            )

    def test_rejects_empty_name(self):
        owner = UserFactory()
        with pytest.raises(CommandError, match="name is required"):
            call_command("create_organization", name="   ", owner=owner.username)

    def test_rejects_negative_quota(self):
        owner = UserFactory()
        with pytest.raises(CommandError, match="quota"):
            call_command(
                "create_organization",
                name="Bad Quota",
                owner=owner.username,
                quota=-1,
            )


@pytest.mark.django_db
class TestAddUserToOrgCommand:
    def test_help_text_describes_membership_options(self):
        help_text = _help("add_user_to_org")
        assert "Add a user to an organization" in help_text
        assert "--organization" in help_text
        assert "--user" in help_text
        assert "--role" in help_text
        assert "member" in help_text

    def test_adds_member_by_slug_and_username(self):
        owner = UserFactory(username="owner")
        member = UserFactory(username="member")
        org = Organization.objects.create(name="Acme", slug="acme", owner=owner)
        OrganizationMembership.objects.create(
            organization=org, user=owner, role=OrganizationMembership.Role.OWNER
        )

        out, _ = _call(
            "add_user_to_org",
            "--organization",
            "acme",
            "--user",
            "member",
            "--role",
            "admin",
        )

        membership = OrganizationMembership.objects.get(organization=org, user=member)
        assert membership.role == OrganizationMembership.Role.ADMIN
        assert "Added member to acme as admin" in out

    def test_adds_member_by_organization_id(self):
        owner = UserFactory()
        member = UserFactory(username="newbie")
        org = Organization.objects.create(name="Id Org", slug="id-org", owner=owner)

        _call(
            "add_user_to_org",
            organization=str(org.id),
            user="newbie",
        )
        assert OrganizationMembership.objects.filter(
            organization=org,
            user=member,
            role=OrganizationMembership.Role.MEMBER,
        ).exists()

    def test_updates_existing_membership_role(self):
        owner = UserFactory()
        member = UserFactory(username="member")
        org = Organization.objects.create(name="Acme", slug="acme", owner=owner)
        OrganizationMembership.objects.create(
            organization=org, user=member, role=OrganizationMembership.Role.MEMBER
        )

        out, _ = _call(
            "add_user_to_org",
            organization="acme",
            user="member",
            role="admin",
        )
        membership = OrganizationMembership.objects.get(organization=org, user=member)
        assert membership.role == OrganizationMembership.Role.ADMIN
        assert "Updated member" in out

    def test_already_member_same_role_is_warning(self):
        owner = UserFactory()
        member = UserFactory(username="member")
        org = Organization.objects.create(name="Acme", slug="acme", owner=owner)
        OrganizationMembership.objects.create(
            organization=org, user=member, role=OrganizationMembership.Role.MEMBER
        )

        out, _ = _call("add_user_to_org", organization="acme", user="member")
        assert "already a member" in out

    def test_rejects_unknown_organization(self):
        UserFactory(username="member")
        with pytest.raises(CommandError, match="not found"):
            call_command("add_user_to_org", organization="missing", user="member")

    def test_rejects_unknown_user(self):
        owner = UserFactory()
        Organization.objects.create(name="Acme", slug="acme", owner=owner)
        with pytest.raises(CommandError, match="not found"):
            call_command("add_user_to_org", organization="acme", user="ghost")


@pytest.mark.django_db
class TestResetApiKeyCommand:
    def test_help_text_mentions_confirmation(self):
        help_text = _help("reset_api_key")
        assert "Rotate an API key" in help_text
        assert "--no-input" in help_text
        assert "--id" in help_text
        assert "Confirmation is required" in help_text or "confirmation" in help_text.lower()

    def test_rotates_key_with_no_input(self):
        user = UserFactory(username="alice")
        api_key = APIKey(user=user, name="Production", tier="free")
        api_key.save()
        old_secret = api_key.key

        out, _ = _call("reset_api_key", "--id", str(api_key.id), "--no-input")

        api_key.refresh_from_db()
        assert api_key.key != old_secret
        assert len(api_key.key) >= 32
        assert api_key.key in out
        assert "Rotated API key" in out
        assert old_secret not in out or api_key.key != old_secret

    def test_rotates_key_by_username_and_name(self):
        user = UserFactory(username="alice")
        api_key = APIKey(user=user, name="CLI Key", tier="pro")
        api_key.save()
        old_secret = api_key.key

        _call(
            "reset_api_key",
            "--username",
            "alice",
            "--name",
            "CLI Key",
            "--no-input",
        )
        api_key.refresh_from_db()
        assert api_key.key != old_secret
        assert api_key.tier == "pro"

    def test_confirmation_abort_leaves_key_unchanged(self):
        user = UserFactory()
        api_key = APIKey(user=user, name="Keep", tier="free")
        api_key.save()
        old_secret = api_key.key

        with patch("sys.stdin.isatty", return_value=True):
            with patch("soroscan.ingest.management.cli.input", return_value="n"):
                with pytest.raises(CommandError, match="Aborted"):
                    call_command("reset_api_key", "--id", str(api_key.id))

        api_key.refresh_from_db()
        assert api_key.key == old_secret

    def test_confirmation_yes_rotates_key(self):
        user = UserFactory()
        api_key = APIKey(user=user, name="Rotate", tier="free")
        api_key.save()
        old_secret = api_key.key

        with patch("sys.stdin.isatty", return_value=True):
            with patch("soroscan.ingest.management.cli.input", return_value="yes"):
                call_command("reset_api_key", "--id", str(api_key.id))

        api_key.refresh_from_db()
        assert api_key.key != old_secret

    def test_non_interactive_without_no_input_fails(self):
        user = UserFactory()
        api_key = APIKey(user=user, name="Prod", tier="free")
        api_key.save()

        with patch("sys.stdin.isatty", return_value=False):
            with pytest.raises(CommandError, match="--no-input"):
                call_command("reset_api_key", "--id", str(api_key.id))

    def test_rejects_missing_key(self):
        with pytest.raises(CommandError, match="not found"):
            call_command("reset_api_key", "--id", "99999", "--no-input")

    def test_requires_id_or_username_and_name(self):
        with pytest.raises(CommandError, match="Provide --id"):
            call_command("reset_api_key", "--no-input")


@pytest.mark.django_db
class TestGenerateInvoiceCommand:
    def test_help_text_describes_billing_options(self):
        help_text = _help("generate_invoice")
        assert "invoice" in help_text.lower()
        assert "--organization" in help_text
        assert "--month" in help_text
        assert "--amount" in help_text
        assert "--force" in help_text

    def test_generates_invoice_from_cost_snapshot(self):
        owner = UserFactory()
        org = Organization.objects.create(name="Billed", slug="billed", owner=owner)
        snapshot = OrganizationCostSnapshot.objects.create(
            organization=org,
            month=date(2026, 8, 1),
            rpc_calls=100,
            storage_bytes=2048,
            compute_units=50,
            rpc_cost_usd=Decimal("1.2500"),
            storage_cost_usd=Decimal("0.5000"),
            compute_cost_usd=Decimal("0.2500"),
            actual_cost_usd=Decimal("2.0000"),
            projected_monthly_cost_usd=Decimal("2.5000"),
        )

        out, _ = _call(
            "generate_invoice",
            "--organization",
            "billed",
            "--month",
            "2026-08",
        )

        invoice = Invoice.objects.get(organization=org, billing_period=date(2026, 8, 1))
        assert invoice.amount_usd == Decimal("2.0000")
        assert invoice.status == Invoice.Status.ISSUED
        assert invoice.cost_snapshot_id == snapshot.id
        assert invoice.invoice_number.startswith("INV-")
        assert "Generated invoice" in out
        assert str(invoice.invoice_number) in out
        assert len(invoice.line_items) == 3

    def test_generates_invoice_with_amount_override_when_no_snapshot(self):
        owner = UserFactory()
        org = Organization.objects.create(name="Manual", slug="manual", owner=owner)

        _call(
            "generate_invoice",
            organization="manual",
            month="2026-07",
            amount="19.99",
        )
        invoice = Invoice.objects.get(organization=org)
        assert invoice.amount_usd == Decimal("19.9900")
        assert invoice.cost_snapshot is None

    def test_rejects_duplicate_invoice_without_force(self):
        owner = UserFactory()
        org = Organization.objects.create(name="Dup", slug="dup", owner=owner)
        OrganizationCostSnapshot.objects.create(
            organization=org,
            month=date(2026, 8, 1),
            actual_cost_usd=Decimal("1.0000"),
        )
        call_command("generate_invoice", organization="dup", month="2026-08")

        with pytest.raises(CommandError, match="already exists"):
            call_command("generate_invoice", organization="dup", month="2026-08")

    def test_force_replaces_existing_invoice(self):
        owner = UserFactory()
        org = Organization.objects.create(name="Dup", slug="dup", owner=owner)
        OrganizationCostSnapshot.objects.create(
            organization=org,
            month=date(2026, 8, 1),
            actual_cost_usd=Decimal("1.0000"),
        )
        call_command("generate_invoice", organization="dup", month="2026-08")
        original = Invoice.objects.get(organization=org)

        _call(
            "generate_invoice",
            organization="dup",
            month="2026-08",
            amount="9.50",
            force=True,
        )
        original.refresh_from_db()
        assert original.amount_usd == Decimal("9.5000")
        assert Invoice.objects.filter(organization=org).count() == 1

    def test_rejects_missing_snapshot_without_amount(self):
        owner = UserFactory()
        Organization.objects.create(name="Empty", slug="empty", owner=owner)
        with pytest.raises(CommandError, match="No cost snapshot"):
            call_command("generate_invoice", organization="empty", month="2026-08")

    def test_rejects_invalid_month(self):
        owner = UserFactory()
        Organization.objects.create(name="Bad", slug="bad", owner=owner)
        with pytest.raises(CommandError, match="YYYY-MM"):
            call_command("generate_invoice", organization="bad", month="08-2026")

    def test_rejects_unknown_organization(self):
        with pytest.raises(CommandError, match="not found"):
            call_command(
                "generate_invoice",
                organization="missing",
                month="2026-08",
                amount="1.00",
            )

    def test_invoice_str(self):
        owner = UserFactory()
        org = Organization.objects.create(name="StrOrg", slug="str-org", owner=owner)
        invoice = Invoice.objects.create(
            organization=org,
            invoice_number="INV-TEST-001",
            billing_period=date(2026, 1, 1),
            amount_usd=Decimal("1.0000"),
        )
        assert "INV-TEST-001" in str(invoice)
        assert "StrOrg" in str(invoice)
