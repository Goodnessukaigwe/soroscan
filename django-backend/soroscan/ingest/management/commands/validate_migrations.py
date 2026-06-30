from django.core.management import BaseCommand, CommandError, call_command
from django.core.management.base import SystemCheckError
from django.db import DEFAULT_DB_ALIAS, connections
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.loader import MigrationLoader


class Command(BaseCommand):
    help = (
        "Validate that all migrations can be applied cleanly on a fresh "
        "temporary database."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--database",
            default=DEFAULT_DB_ALIAS,
            help="Database alias to validate against.",
        )
        parser.add_argument(
            "--keepdb",
            action="store_true",
            help="Keep the temporary database after validation for debugging.",
        )

    def handle(self, *args, **options):
        database = options["database"]
        keepdb = options["keepdb"]
        connection = connections[database]

        test_db_name = None
        try:
            self.stdout.write("Creating temporary database for migration validation...")
            test_db_name = connection.creation.create_test_db(
                verbosity=options["verbosity"],
                autoclobber=True,
                serialize=False,
                keepdb=keepdb,
            )
            self.stdout.write(f"Temporary database created: {test_db_name}")

            loader = self._validate_migration_graph(connection)
            self._report_migration_plan(connection, loader, options["verbosity"])

            self.stdout.write("Applying all migrations to the temporary database...")
            call_command(
                "migrate",
                database=database,
                interactive=False,
                verbosity=options["verbosity"],
                run_syncdb=True,
            )
            self.stdout.write(
                self.style.SUCCESS(
                    "Migration validation succeeded: all migrations applied cleanly."
                )
            )
        except CommandError:
            raise
        except SystemCheckError as exc:
            raise CommandError(
                f"System checks failed during migration validation: {exc}"
            )
        except Exception as exc:
            raise CommandError(f"Migration validation failed: {exc}") from exc
        finally:
            if test_db_name and not keepdb:
                self.stdout.write("Destroying temporary database...")
                connection.creation.destroy_test_db(
                    test_db_name,
                    verbosity=options["verbosity"],
                    keepdb=False,
                )

    def _validate_migration_graph(self, connection) -> MigrationLoader:
        loader = MigrationLoader(connection)

        conflicts = loader.detect_conflicts()
        if conflicts:
            conflict_lines = []
            for app_label, names in sorted(conflicts.items()):
                conflict_lines.append(f"{app_label}: {', '.join(sorted(names))}")
            raise CommandError(
                "Migration conflicts detected (multiple leaf nodes):\n"
                + "\n".join(conflict_lines)
            )

        try:
            loader.check_consistent_history(connection)
        except Exception as exc:
            raise CommandError(f"Failed to validate migration history: {exc}") from exc

        return loader

    def _report_migration_plan(
        self,
        connection,
        loader: MigrationLoader,
        verbosity: int,
    ) -> None:
        targets = set(loader.graph.leaf_nodes())
        if not targets:
            self.stdout.write("No migrations to apply.")
            return

        executor = MigrationExecutor(connection)
        plan = executor.migration_plan(targets)
        forward_steps = [
            (migration.app_label, migration.name)
            for migration, backwards in plan
            if not backwards
        ]
        self.stdout.write(
            f"Migration plan: {len(forward_steps)} migration(s) to apply."
        )
        if verbosity >= 2:
            for app_label, migration_name in forward_steps:
                self.stdout.write(f"  - {app_label}.{migration_name}")
