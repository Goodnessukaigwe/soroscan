import pytest
from django.core.management import CommandError, call_command
from django.db import DEFAULT_DB_ALIAS, connections

from soroscan.ingest.management.commands import validate_migrations


def _patch_db_lifecycle(monkeypatch):
    monkeypatch.setattr(
        connections[DEFAULT_DB_ALIAS].creation,
        "create_test_db",
        lambda *args, **kwargs: "test_db_name",
    )
    monkeypatch.setattr(
        connections[DEFAULT_DB_ALIAS].creation,
        "destroy_test_db",
        lambda *args, **kwargs: None,
    )


@pytest.mark.django_db
def test_validate_migrations_runs_successfully(monkeypatch):
    _patch_db_lifecycle(monkeypatch)
    monkeypatch.setattr(
        validate_migrations,
        "call_command",
        lambda *args, **kwargs: None,
    )

    call_command("validate_migrations", verbosity=0)


@pytest.mark.django_db
def test_validate_migrations_reports_errors_when_migrate_fails(monkeypatch):
    _patch_db_lifecycle(monkeypatch)
    monkeypatch.setattr(
        validate_migrations,
        "call_command",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            CommandError("broken migration sequence")
        ),
    )

    with pytest.raises(CommandError, match="broken migration sequence"):
        call_command("validate_migrations", verbosity=0)


@pytest.mark.django_db
def test_validate_migrations_detects_conflicts(monkeypatch):
    _patch_db_lifecycle(monkeypatch)

    class FakeLoader:
        def detect_conflicts(self):
            return {"ingest": ["0045_a", "0045_b"]}

        def check_consistent_history(self, connection):
            return None

    monkeypatch.setattr(
        validate_migrations,
        "MigrationLoader",
        lambda connection: FakeLoader(),
    )

    with pytest.raises(CommandError, match="Migration conflicts detected"):
        call_command("validate_migrations", verbosity=0)


@pytest.mark.django_db
def test_validate_migrations_exits_nonzero_on_failure(monkeypatch):
    _patch_db_lifecycle(monkeypatch)
    monkeypatch.setattr(
        validate_migrations,
        "call_command",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    with pytest.raises(CommandError, match="Migration validation failed: boom"):
        call_command("validate_migrations", verbosity=0)


@pytest.mark.django_db
def test_validate_migrations_reports_plan(monkeypatch, capsys):
    _patch_db_lifecycle(monkeypatch)

    fake_migration = type(
        "Migration",
        (),
        {"app_label": "ingest", "name": "0001_initial"},
    )()

    class FakeExecutor:
        def migration_plan(self, targets):
            return [(fake_migration, False)]

    class FakeGraph:
        def leaf_nodes(self):
            return [("ingest", "0045_organization_cors_origins")]

    class FakeLoader:
        graph = FakeGraph()

        def detect_conflicts(self):
            return {}

        def check_consistent_history(self, connection):
            return None

    monkeypatch.setattr(
        validate_migrations,
        "MigrationLoader",
        lambda connection: FakeLoader(),
    )
    monkeypatch.setattr(
        validate_migrations,
        "MigrationExecutor",
        lambda connection: FakeExecutor(),
    )
    monkeypatch.setattr(
        validate_migrations,
        "call_command",
        lambda *args, **kwargs: None,
    )

    call_command("validate_migrations", verbosity=2)
    output = capsys.readouterr().out
    assert "Migration plan: 1 migration(s) to apply." in output
    assert "ingest.0001_initial" in output
