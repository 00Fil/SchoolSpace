"""Approvazione finale delle decisioni da parte del gestore del centro (superuser).

Uso: python manage.py approve_decisions --by <username-superuser> [--codes D01,D02]
Senza --codes approva G1 e D01–D09 con gli esiti decisi il 3/10/2026.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.governance.models import Decision
from apps.identity.models import Account

OUTCOMES = {
    "G1": "Contratto di dominio, fixture e policy approvati dal gestore del centro.",
    "D01": "Parentali come descritti (tutto il programma e tutte le materie con il centro); "
    "dettagli per anno/livello gestiti dal gestore nella configurazione dei percorsi.",
    "D02": "Gruppi approvati dal centro; massimo due in presenza; capienza online dichiarata.",
    "D03": "Priorità P0/P1/P2; modalità strict e coverage; calendario parziale solo con "
    "approvazione esplicita del gestore.",
    "D04": "Finestre online e in presenza distinte; nessuna disponibilità 24/7.",
    "D05": "Nessun tempo di transizione inventato; pause e carichi da configurazione.",
    "D06": "Ciclo mensile: il gestore genera con il motore il calendario del mese; i tutor "
    "approvano o chiedono rettifiche, decise dal gestore con il motore. Conflitti "
    "segnalati, non sospesi. Recuperi secondo recovery_policy.",
    "D07": "Account proprio per lo studente dai 14 anni; nessuna richiesta di cambio; "
    "nessuna email allo studente.",
    "D08": "Fornitore email: Resend.",
    "D09": "Matrice di conservazione proposta confermata; link calendario personale 365 giorni; "
    "sessioni: cookie 8 h, inattività staff 30 min.",
}
TITLES = {"G1": "Gate G1 – contratto di dominio e policy"}


class Command(BaseCommand):
    help = "Approva G1 e D01–D09 a nome del gestore del centro (superuser)"

    def add_arguments(self, parser):
        parser.add_argument("--by", required=True, help="username del superuser")
        parser.add_argument("--codes", default=",".join(OUTCOMES))

    @transaction.atomic
    def handle(self, *args, by, codes, **options):
        actor = Account.objects.filter(username=by, is_active=True).first()
        if not actor or not actor.is_superuser:
            raise CommandError("Solo il gestore del centro (superuser attivo) può approvare")
        wanted = [c.strip().upper() for c in codes.split(",") if c.strip()]
        unknown = [c for c in wanted if c not in OUTCOMES]
        if unknown:
            raise CommandError(f"Codici sconosciuti: {', '.join(unknown)}")
        stamp = timezone.now()
        owner = f"Gestore del centro ({actor.username})"
        for code in wanted:
            d, _ = Decision.objects.get_or_create(
                code=code, defaults={"title": TITLES.get(code, code)}
            )
            d.status = "APPROVED"
            d.outcome = OUTCOMES[code]
            d.owner = owner
            d.approved_at = stamp
            d.save()
        self.stdout.write(self.style.SUCCESS(f"Approvate: {', '.join(wanted)}"))
