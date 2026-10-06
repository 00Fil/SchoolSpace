from django.core.management.base import BaseCommand

from apps.privacy.majority import run_majority_review

from ._base import dump


class Command(BaseCommand):
    help = "Segnala le deleghe da riconfermare con lo studente maggiorenne (nessuna revoca silenziosa)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opts):
        self.stdout.write(dump(run_majority_review(dry_run=opts["dry_run"])))
