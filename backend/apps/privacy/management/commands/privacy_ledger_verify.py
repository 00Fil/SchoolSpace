from django.core.management.base import BaseCommand, CommandError

from apps.privacy import ledger


class Command(BaseCommand):
    help = "Verifica la catena di hash del ledger esterno delle richieste privacy."

    def handle(self, *args, **opts):
        ok, index = ledger.verify_chain()
        if not ok:
            raise CommandError(f"Catena non valida alla voce {index}")
        self.stdout.write(f"Ledger integro: {len(ledger.read_entries())} voci")
