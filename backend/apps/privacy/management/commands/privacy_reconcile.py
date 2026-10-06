from django.core.management.base import BaseCommand, CommandError

from apps.privacy import ledger
from apps.privacy.reconcile import apply, plan

from ._base import dump


class Command(BaseCommand):
    help = (
        "Dopo un restore: riapplica revoche e anonimizzazioni registrate nel ledger esterno. "
        "Default: solo piano; --apply per eseguire."
    )

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **opts):
        ok, index = ledger.verify_chain()
        if not ok:
            raise CommandError(
                f"Ledger alterato alla voce {index}: riconciliazione bloccata"
            )
        actions = plan()
        done = apply(actions) if opts["apply"] else []
        self.stdout.write(dump({"planned": actions, "applied": done}))
