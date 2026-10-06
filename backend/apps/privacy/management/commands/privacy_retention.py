from django.core.management.base import BaseCommand

from apps.privacy.errors import PrivacyError
from apps.privacy.retention import run_retention, seed_default_matrix

from ._base import dump, resolve_actor


class Command(BaseCommand):
    help = (
        "Job di cancellazione/minimizzazione della matrice D09. Default: dry-run. "
        "Con --execute agisce solo sulle categorie APPROVED e stampa la ricevuta."
    )

    def add_arguments(self, parser):
        parser.add_argument("--execute", action="store_true")
        parser.add_argument("--category", action="append", dest="categories")
        parser.add_argument("--actor")
        parser.add_argument(
            "--seed", action="store_true", help="crea i default mancanti"
        )

    def handle(self, *args, **opts):
        if opts["seed"]:
            created = seed_default_matrix()
            self.stdout.write(f"Categorie create: {created}")
        try:
            run = run_retention(
                actor=resolve_actor(opts["actor"]),
                dry_run=not opts["execute"],
                categories=opts["categories"],
            )
        except PrivacyError as exc:
            from django.core.management.base import CommandError

            raise CommandError(exc.message) from exc
        self.stdout.write(
            dump(
                {
                    "receipt": str(run.id),
                    "receipt_hash": run.receipt_hash,
                    "dry_run": run.dry_run,
                    "results": run.results,
                }
            )
        )
