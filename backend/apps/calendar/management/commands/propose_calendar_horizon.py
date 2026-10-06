"""Job periodico (GAP-E06): propone run di bozza per le settimane dell'orizzonte.

Non pubblica: la pubblicazione resta un comando esplicito del centro."""

from django.conf import settings
from config import features
from django.core.management.base import BaseCommand, CommandError
from apps.identity.models import Account
from apps.identity.policies import is_center
from apps.calendar.lifecycle import propose_horizon, proposal_summary, horizon_weeks


class Command(BaseCommand):
    help = (
        "Propone l'estensione dell'orizzonte dopo la verifica dei conflitti irrisolti"
    )

    def add_arguments(self, parser):
        parser.add_argument("--actor", required=True, help="Username operatore centro")
        parser.add_argument("--policy", default=None)
        parser.add_argument("--weeks", type=int, default=None)

    def handle(self, *args, **options):
        if not features.calendar_enabled():
            raise CommandError("Calendario disattivato (FEATURE_CALENDAR)")
        actor = Account.objects.filter(username=options["actor"]).first()
        if not actor or not is_center(actor):
            raise CommandError("Operatore del centro necessario")
        rows = propose_horizon(
            actor, options["policy"], horizon_weeks(options["weeks"])
        )
        for row in rows:
            data = proposal_summary(row)
            self.stdout.write(
                f"{data['week_start']} r{data['revision']}: {data['state']}"
                + (f" run={data['run_id']}" if data["run_id"] else "")
            )
