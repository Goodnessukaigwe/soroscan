"""
Rotate (reset) an API key secret. The previous key is invalidated immediately.

Usage:
    python manage.py reset_api_key --id 42 --no-input
    python manage.py reset_api_key --username alice --name "Production"
"""
from django.core.management.base import BaseCommand, CommandError

from soroscan.ingest.management.cli import confirm_action
from soroscan.ingest.services.admin_ops import (
    AdminOpsError,
    resolve_api_key,
    rotate_api_key,
)


class Command(BaseCommand):
    help = (
        "Rotate an API key and print the new secret once. The previous key stops "
        "working immediately. Identify the key with --id, or with --username and "
        "--name together. Confirmation is required unless --no-input is passed."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--id",
            dest="key_id",
            type=int,
            default=None,
            help="Primary key of the APIKey to rotate.",
        )
        parser.add_argument(
            "--username",
            default=None,
            help="Username or email of the API key owner (used with --name).",
        )
        parser.add_argument(
            "--name",
            default=None,
            help="API key display name (used with --username).",
        )
        parser.add_argument(
            "--no-input",
            "--noinput",
            action="store_true",
            dest="no_input",
            help="Do not prompt for confirmation (required in non-interactive runs).",
        )

    def handle(self, *args, **options):
        try:
            api_key = resolve_api_key(
                key_id=options["key_id"],
                username=options["username"],
                name=options["name"],
            )
        except AdminOpsError as exc:
            raise CommandError(str(exc)) from exc

        confirm_action(
            (
                f"This will invalidate the current API key {api_key.id} "
                f"({api_key.name!r} for user {api_key.user.username}). Continue?"
            ),
            no_input=options["no_input"],
        )

        new_secret = rotate_api_key(api_key)
        self.stdout.write(
            self.style.WARNING(
                "Store this secret now; it will not be shown again."
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Rotated API key id={api_key.id} name={api_key.name!r} "
                f"user={api_key.user.username} key={new_secret}"
            )
        )
