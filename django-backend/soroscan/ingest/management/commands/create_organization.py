"""
Create a new organization and grant the owner membership.

Usage:
    python manage.py create_organization --name "Acme Corp" --owner alice
    python manage.py create_organization --name "Acme Corp" --owner alice@example.com --slug acme --quota 100000
"""
from django.core.management.base import BaseCommand, CommandError

from soroscan.ingest.services.admin_ops import (
    AdminOpsError,
    create_organization,
    resolve_user,
)


class Command(BaseCommand):
    help = (
        "Create a new organization and add the specified user as owner. "
        "Slug is auto-generated from the name unless --slug is provided. "
        "The owner is resolved by username or unique email."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--name",
            required=True,
            help="Display name for the new organization.",
        )
        parser.add_argument(
            "--owner",
            required=True,
            help="Username or email of the user who will own the organization.",
        )
        parser.add_argument(
            "--slug",
            default=None,
            help="Optional unique slug. Generated from --name when omitted.",
        )
        parser.add_argument(
            "--quota",
            type=int,
            default=0,
            help="Optional monthly event quota (default: 0, meaning unset/unlimited).",
        )

    def handle(self, *args, **options):
        try:
            owner = resolve_user(options["owner"])
            org = create_organization(
                name=options["name"],
                owner=owner,
                slug=options["slug"],
                quota=options["quota"],
            )
        except AdminOpsError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            self.style.SUCCESS(
                f"Created organization id={org.id} name={org.name!r} "
                f"slug={org.slug} owner={owner.username} quota={org.quota}"
            )
        )
