"""Shared helpers for ingest management commands."""
from __future__ import annotations

import sys

from django.core.management.base import CommandError


def confirm_action(prompt: str, *, no_input: bool) -> None:
    """
    Require an interactive yes confirmation unless ``--no-input`` is set.

    Destructive admin commands (API-key rotation, membership removal) must
    call this before mutating data.
    """
    if no_input:
        return
    if not sys.stdin.isatty():
        raise CommandError(
            "This operation requires confirmation. Re-run with --no-input to skip the prompt."
        )
    answer = input(f"{prompt} [y/N]: ").strip().lower()
    if answer not in {"y", "yes"}:
        raise CommandError("Aborted.")
