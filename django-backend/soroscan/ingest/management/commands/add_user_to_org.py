"""
Add a user to an organization or update their membership role.

Usage:
    python manage.py add_user_to_org --organization acme --user bob
    python manage.py add_user_to_org --organization acme --user bob --role admin
    python manage.py add_user_to_org --organization 12 --user bob@example.com --role member
"""
from django.core.management.base import BaseCommand, CommandError

from soroscan.ingest.models import OrganizationMembership
from soroscan.ingest.services.admin_ops import (
    AdminOpsError,
    add_user_to_organization,
    resolve_organization,
    resolve_user,
)


class Command(BaseCommand):
    help = (
        "Add a user to an organization or update an existing membership role. "
        "Organization may be an id, slug, or unique name. User may be a username "
        "or unique email. Roles: owner, admin, member (default: member)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--organization",
            required=True,
            help="Organization id, slug, or unique name.",
        )
        parser.add_argument(
            "--user",
            required=True,
            help="Username or email of the user to add.",
        )
        parser.add_argument(
            "--role",
            choices=[choice[0] for choice in OrganizationMembership.Role.choices],
            default=OrganizationMembership.Role.MEMBER,
            help="Membership role to assign (default: member).",
        )

    def handle(self, *args, **options):
        try:
            organization = resolve_organization(options["organization"])
            user = resolve_user(options["user"])
            membership, created, role_updated = add_user_to_organization(
                organization=organization,
                user=user,
                role=options["role"],
            )
        except AdminOpsError as exc:
            raise CommandError(str(exc)) from exc

        if created:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Added {user.username} to {organization.slug} as {membership.role}"
                )
            )
            return

        if role_updated:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Updated {user.username} on {organization.slug} to role={membership.role}"
                )
            )
            return

        self.stdout.write(
            self.style.WARNING(
                f"{user.username} is already a {membership.role} of {organization.slug}"
            )
        )
