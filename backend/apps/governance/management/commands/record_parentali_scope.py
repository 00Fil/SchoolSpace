from django.core.management.base import BaseCommand
from apps.governance.models import Decision


class Command(BaseCommand):
    help = "Registra il chiarimento di perimetro D01 ricevuto in chat, non l'approvazione complessiva G1"

    def handle(self, *args, **kwargs):
        existing = Decision.objects.filter(code="D01").first()
        if existing and existing.status == "APPROVED":
            self.stdout.write(
                "D01 già approvata: nessuna modifica al registro esistente."
            )
            return
        Decision.objects.update_or_create(
            code="D01",
            defaults={
                "title": "Parentali: programma scolastico completo presso il centro",
                "proposed_default": "Gestione interna HOME_EDUCATION; genitori/tutori restano coperti",
                "status": "PROPOSED",
                "owner": "Committente — chiarimento in chat",
                "outcome": "Il committente conferma studenti che svolgono tutto il programma scolastico, tutte le materie, con il centro. Materie per anno/livello, monte ore, gruppi e responsabilità formali ancora da definire.",
                "approved_at": None,
            },
        )
        self.stdout.write(
            "D01: significato confermato; dettaglio e gate G1 non approvati automaticamente."
        )
