"""
Generate (issue) an organization invoice from a monthly cost snapshot.

Usage:
    python manage.py generate_invoice --organization acme --month 2026-08
    python manage.py generate_invoice --organization acme --month 2026-08 --force
    python manage.py generate_invoice --organization 12 --amount 19.99
"""
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from soroscan.ingest.services.admin_ops import (
    AdminOpsError,
    generate_invoice,
    parse_amount,
    parse_month,
    resolve_organization,
)


class Command(BaseCommand):
    help = (
        "Create an issued invoice for an organization billing period. "
        "Amount defaults to the OrganizationCostSnapshot actual cost for --month. "
        "Pass --amount to override, or when no snapshot exists. "
        "Use --force to replace an existing invoice for the same period."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--organization",
            required=True,
            help="Organization id, slug, or unique name.",
        )
        parser.add_argument(
            "--month",
            default=None,
            help="Billing month in YYYY-MM format (default: current UTC month).",
        )
        parser.add_argument(
            "--amount",
            default=None,
            help="Optional USD amount override (decimal). Required when no cost snapshot exists.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Replace an existing invoice for the same organization and month.",
        )

    def handle(self, *args, **options):
        try:
            organization = resolve_organization(options["organization"])
            month = (
                parse_month(options["month"])
                if options["month"]
                else timezone.now().date().replace(day=1)
            )
            amount = parse_amount(options["amount"]) if options["amount"] is not None else None
            invoice = generate_invoice(
                organization=organization,
                month=month,
                amount=amount,
                force=options["force"],
            )
        except AdminOpsError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            self.style.SUCCESS(
                f"Generated invoice {invoice.invoice_number} "
                f"org={organization.slug} period={invoice.billing_period:%Y-%m} "
                f"amount_usd={invoice.amount_usd} status={invoice.status}"
            )
        )
