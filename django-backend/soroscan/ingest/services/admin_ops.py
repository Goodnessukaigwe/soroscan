"""
Admin-operation helpers used by management commands.

These functions encapsulate organization, membership, API-key, and invoice
mutations so CLI commands stay thin and reuse the same validation rules as
the rest of the ingest app.
"""
from __future__ import annotations

import calendar
import secrets
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from soroscan.ingest.models import (
    APIKey,
    Invoice,
    Organization,
    OrganizationCostSnapshot,
    OrganizationMembership,
)

User = get_user_model()


class AdminOpsError(ValueError):
    """Domain error raised by admin CLI helpers (mapped to CommandError)."""


def parse_month(value: str) -> date:
    """Parse YYYY-MM into the first day of that month."""
    try:
        parsed = datetime.strptime(value, "%Y-%m").date()
    except (TypeError, ValueError) as exc:
        raise AdminOpsError("month must be in YYYY-MM format") from exc
    return parsed.replace(day=1)


def parse_amount(value: str) -> Decimal:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError) as exc:
        raise AdminOpsError("amount must be a valid decimal number") from exc
    if amount < 0:
        raise AdminOpsError("amount must be greater than or equal to 0")
    return amount.quantize(Decimal("0.0001"))


def resolve_user(identifier: str) -> User:
    """Resolve a user by username, then by unique email."""
    identifier = (identifier or "").strip()
    if not identifier:
        raise AdminOpsError("User identifier is required.")

    try:
        return User.objects.get(username=identifier)
    except User.DoesNotExist:
        pass

    matches = list(User.objects.filter(email__iexact=identifier))
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise AdminOpsError(
            f"Multiple users match email '{identifier}'. Use a username instead."
        )
    raise AdminOpsError(f"User '{identifier}' not found.")


def resolve_organization(identifier: str) -> Organization:
    """Resolve an organization by numeric id, slug, or exact name."""
    identifier = (identifier or "").strip()
    if not identifier:
        raise AdminOpsError("Organization identifier is required.")

    if identifier.isdigit():
        org = Organization.objects.filter(pk=int(identifier)).first()
        if org:
            return org

    org = Organization.objects.filter(slug=identifier).first()
    if org:
        return org

    matches = list(Organization.objects.filter(name__iexact=identifier))
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise AdminOpsError(
            f"Multiple organizations named '{identifier}'. Use a slug or id instead."
        )
    raise AdminOpsError(f"Organization '{identifier}' not found.")


def resolve_api_key(
    *,
    key_id: int | None = None,
    username: str | None = None,
    name: str | None = None,
) -> APIKey:
    if key_id is not None:
        try:
            return APIKey.objects.select_related("user").get(pk=key_id)
        except APIKey.DoesNotExist as exc:
            raise AdminOpsError(f"API key id={key_id} not found.") from exc

    if not username or not name:
        raise AdminOpsError(
            "Provide --id, or both --username and --name, to identify the API key."
        )

    user = resolve_user(username)
    matches = list(APIKey.objects.filter(user=user, name=name).order_by("-created_at"))
    if not matches:
        raise AdminOpsError(
            f"API key named '{name}' for user '{user.username}' not found."
        )
    if len(matches) > 1:
        raise AdminOpsError(
            f"Multiple API keys named '{name}' for user '{user.username}'. "
            "Use --id to select one."
        )
    return matches[0]


def create_organization(
    *,
    name: str,
    owner: User,
    slug: str | None = None,
    quota: int = 0,
) -> Organization:
    name = (name or "").strip()
    if not name:
        raise AdminOpsError("Organization name is required.")
    if quota < 0:
        raise AdminOpsError("quota must be greater than or equal to 0")

    slug = (slug or "").strip()
    if slug:
        slug = slugify(slug)
        if not slug:
            raise AdminOpsError("slug must contain at least one letter or number.")
        if Organization.objects.filter(slug=slug).exists():
            raise AdminOpsError(f"Organization slug '{slug}' already exists.")

    with transaction.atomic():
        org = Organization(name=name, owner=owner, quota=quota)
        if slug:
            org.slug = slug
        org.save()
        OrganizationMembership.objects.get_or_create(
            organization=org,
            user=owner,
            defaults={
                "role": OrganizationMembership.Role.OWNER,
                "invited_by": owner,
            },
        )
    return org


def add_user_to_organization(
    *,
    organization: Organization,
    user: User,
    role: str = OrganizationMembership.Role.MEMBER,
    invited_by: User | None = None,
) -> tuple[OrganizationMembership, bool, bool]:
    """
    Add or update organization membership.

    Returns (membership, created, role_updated).
    """
    valid_roles = {choice[0] for choice in OrganizationMembership.Role.choices}
    if role not in valid_roles:
        raise AdminOpsError(
            f"Invalid role '{role}'. Choose one of: {', '.join(sorted(valid_roles))}."
        )

    membership, created = OrganizationMembership.objects.get_or_create(
        organization=organization,
        user=user,
        defaults={"role": role, "invited_by": invited_by},
    )
    role_updated = False
    if not created and membership.role != role:
        membership.role = role
        membership.save(update_fields=["role"])
        role_updated = True
    return membership, created, role_updated


def rotate_api_key(api_key: APIKey) -> str:
    """Rotate an API key secret and return the new plaintext value."""
    return api_key.rotate()


def _line_items_from_snapshot(snapshot: OrganizationCostSnapshot) -> list[dict]:
    items = [
        {
            "description": "RPC usage",
            "quantity": snapshot.rpc_calls,
            "amount_usd": str(snapshot.rpc_cost_usd),
        },
        {
            "description": "Storage",
            "quantity": snapshot.storage_bytes,
            "amount_usd": str(snapshot.storage_cost_usd),
        },
        {
            "description": "Compute",
            "quantity": snapshot.compute_units,
            "amount_usd": str(snapshot.compute_cost_usd),
        },
    ]
    return items


def _build_invoice_number(organization: Organization, billing_period: date) -> str:
    suffix = secrets.token_hex(3)
    slug = (organization.slug or slugify(organization.name) or "org")[:24]
    return f"INV-{slug}-{billing_period:%Y%m}-{suffix}"


def generate_invoice(
    *,
    organization: Organization,
    month: date,
    amount: Decimal | None = None,
    force: bool = False,
) -> Invoice:
    """
    Create (or replace) an issued invoice for an organization month.

    Amounts default to OrganizationCostSnapshot.actual_cost_usd when a
    snapshot exists. Pass ``amount`` to override, or when no snapshot exists.
    """
    billing_period = month.replace(day=1)
    snapshot = OrganizationCostSnapshot.objects.filter(
        organization=organization,
        month=billing_period,
    ).first()

    if amount is None:
        if snapshot is None:
            raise AdminOpsError(
                f"No cost snapshot for organization '{organization.slug}' "
                f"in {billing_period:%Y-%m}. Run cost aggregation first, or pass --amount."
            )
        amount = Decimal(snapshot.actual_cost_usd)

    if amount < 0:
        raise AdminOpsError("amount must be greater than or equal to 0")
    amount = Decimal(amount).quantize(Decimal("0.0001"))

    last_day = calendar.monthrange(billing_period.year, billing_period.month)[1]
    notes = (
        f"Billing period {billing_period:%Y-%m-01} through "
        f"{billing_period.replace(day=last_day):%Y-%m-%d}."
    )
    line_items = _line_items_from_snapshot(snapshot) if snapshot else [
        {"description": "Manual amount", "quantity": 1, "amount_usd": str(amount)}
    ]

    existing = Invoice.objects.filter(
        organization=organization,
        billing_period=billing_period,
    ).first()
    if existing and not force:
        raise AdminOpsError(
            f"Invoice {existing.invoice_number} already exists for "
            f"{organization.slug} {billing_period:%Y-%m}. Use --force to replace it."
        )

    now = timezone.now()
    with transaction.atomic():
        if existing and force:
            existing.amount_usd = amount
            existing.status = Invoice.Status.ISSUED
            existing.line_items = line_items
            existing.cost_snapshot = snapshot
            existing.notes = notes
            existing.issued_at = now
            existing.save(
                update_fields=[
                    "amount_usd",
                    "status",
                    "line_items",
                    "cost_snapshot",
                    "notes",
                    "issued_at",
                    "updated_at",
                ]
            )
            return existing

        invoice = Invoice.objects.create(
            organization=organization,
            invoice_number=_build_invoice_number(organization, billing_period),
            billing_period=billing_period,
            amount_usd=amount,
            status=Invoice.Status.ISSUED,
            line_items=line_items,
            cost_snapshot=snapshot,
            notes=notes,
            issued_at=now,
        )
    return invoice
