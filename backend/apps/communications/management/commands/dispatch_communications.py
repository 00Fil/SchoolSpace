import json

from django.core.management.base import BaseCommand

from apps.communications.dispatch import reconcile


class Command(BaseCommand):
    help = "Riconcilia l'outbox: lease scaduti, esiti ambigui, consegne non accodate"

    def add_arguments(self, parser):
        parser.add_argument(
            "--inline",
            action="store_true",
            help="Consegna senza broker (es. Redis non disponibile)",
        )

    def handle(self, *args, **options):
        self.stdout.write(
            json.dumps(reconcile(inline=options["inline"]), sort_keys=True)
        )
