from django.conf import settings
from config import features
from django.core.management.base import BaseCommand, CommandError
from apps.scheduling.runs import reconcile_runs


class Command(BaseCommand):
    help = "Recupera lease scadute e invii pendenti dalla coda persistente DB"

    def handle(self, *args, **kwargs):
        if not features.planning_enabled():
            raise CommandError("Pianificazione disattivata (FEATURE_PLANNING)")
        self.stdout.write(f"Invii accettati dal broker: {reconcile_runs()}")
