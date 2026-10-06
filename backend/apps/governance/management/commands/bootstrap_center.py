from django.core.management.base import BaseCommand
from django.db import transaction
from apps.education.models import Resource
from apps.governance.models import Decision

DECISIONS = [
    (
        "D01",
        "Significato e perimetro dei parentali",
        "Confermato in chat: studenti che svolgono tutto il programma scolastico e tutte le materie con il centro. Dettagli per anno/livello e approvazione G1 da completare",
    ),
    (
        "D02",
        "Formazione dei gruppi e capienza online",
        "Gruppi approvati dal centro; massimo due in presenza; online da dichiarare",
    ),
    (
        "D03",
        "Priorità, domanda obbligatoria e calendario parziale",
        "P0/P1/P2; strict e coverage; approvazione esplicita del parziale",
    ),
    (
        "D04",
        "Aperture online e presenza del tutor",
        "Finestre distinte; nessuna disponibilità 24/7",
    ),
    ("D05", "Spostamenti, pause e carichi", "Nessun tempo di transizione inventato"),
    (
        "D06",
        "Anno didattico, orizzonte e recuperi",
        "Orizzonte proposto sei settimane; politiche da approvare",
    ),
    (
        "D07",
        "Account studenti e finalità dei dati",
        "Invito verificato e policy privacy da approvare",
    ),
    (
        "D08",
        "Fornitori, budget e servizio",
        "Provider UE preferito; target da verificare",
    ),
    ("D09", "Conservazione ed esportazione", "Matrice retention da approvare"),
]


class Command(BaseCommand):
    help = "Seed idempotente di tre spazi e decisioni aperte; nessun account né dato personale"

    @transaction.atomic
    def handle(self, *args, **options):
        for i in range(1, 4):
            Resource.objects.get_or_create(
                name=f"Spazio {i}", defaults={"kind": "SPACE", "student_capacity": 2}
            )
        for code, title, default in DECISIONS:
            Decision.objects.get_or_create(
                code=code, defaults={"title": title, "proposed_default": default}
            )
        self.stdout.write(
            self.style.SUCCESS(
                "Tre spazi e registro D01–D09 inizializzati senza sovrascrivere dati esistenti."
            )
        )
