from django.core.management.base import BaseCommand

from apps.governance.pg_append_only import script


class Command(BaseCommand):
    help = "Stampa lo script SQL dei trigger append-only (infra/postgres/03_append_only_triggers.sql)."

    def handle(self, *args, **opts):
        self.stdout.write(script(), ending="")
