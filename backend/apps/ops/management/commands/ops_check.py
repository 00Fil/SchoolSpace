import json

from django.core.management.base import BaseCommand, CommandError

from apps.ops.readiness import CHECKS, run_checks


class Command(BaseCommand):
    help = (
        "Esegue i controlli di readiness (per healthcheck dei worker, smoke test e CD)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--checks",
            default="database,migrations,cache,broker",
            help=f"Tra: {','.join(CHECKS)}",
        )

    def handle(self, *args, **opts):
        names = [n.strip() for n in opts["checks"].split(",") if n.strip()]
        unknown = [n for n in names if n not in CHECKS]
        if unknown:
            raise CommandError(f"controlli sconosciuti: {unknown}")
        healthy, results = run_checks(names, required=names)
        self.stdout.write(
            json.dumps({"status": "ok" if healthy else "fail", "checks": results})
        )
        if not healthy:
            raise CommandError("readiness fallita")
