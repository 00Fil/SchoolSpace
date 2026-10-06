from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.privacy.errors import PrivacyError
from apps.privacy.importer import run_import

from ._base import dump, resolve_actor


class Command(BaseCommand):
    help = (
        "Import iniziale famiglie/studenti/deleghe da template CSV versionato. "
        "Default: dry-run senza scritture né inviti (T17). --execute per applicare."
    )

    def add_arguments(self, parser):
        parser.add_argument("csv_path")
        parser.add_argument("--actor", required=True)
        parser.add_argument("--template-version", default="1")
        parser.add_argument("--execute", action="store_true")
        parser.add_argument(
            "--verify-links",
            action="store_true",
            help="le relazioni sono già state verificate su documenti prima dell'import",
        )
        parser.add_argument("--create-invites", action="store_true")

    def handle(self, *args, **opts):
        actor = resolve_actor(opts["actor"], required=True)
        content = Path(opts["csv_path"]).read_bytes()
        try:
            batch = run_import(
                actor,
                content,
                template_version=opts["template_version"],
                dry_run=not opts["execute"],
                verify_links=opts["verify_links"],
                create_invites=opts["create_invites"],
            )
        except PrivacyError as exc:
            raise CommandError(f"{exc.code}: {exc.message}") from exc
        self.stdout.write(
            dump(
                {
                    "batch": str(batch.id),
                    "status": batch.status,
                    "rows": batch.rows,
                    "summary": batch.summary,
                    "errors": batch.errors,
                }
            )
        )
        if batch.status in ("INVALID", "CONFLICT"):
            raise CommandError("Import non applicato: correggere gli errori")
