import json
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from config import features
from apps.scheduling.fixtures import demo_input
from apps.scheduling.contracts import InputError
from apps.scheduling.solver import simulate


class Command(BaseCommand):
    help = "Simulazione CP-SAT sintetica, nessuna pubblicazione o modifica al database"

    def add_arguments(self, parser):
        parser.add_argument(
            "--input", help="File DTO JSON opzionale; altrimenti demo sintetico"
        )
        parser.add_argument(
            "--output", required=True, help="File JSON del risultato non pubblicabile"
        )

    def handle(self, *args, **options):
        if not features.lab_enabled():
            raise CommandError("Laboratorio disattivato (FEATURE_PLANNING_LAB)")
        try:
            data = (
                json.loads(Path(options["input"]).read_text())
                if options["input"]
                else demo_input()
            )
            result = simulate(data)
        except (InputError, OSError, ValueError) as error:
            raise CommandError(str(error))
        Path(options["output"]).write_text(json.dumps(result, indent=2) + "\n")
        self.stdout.write(
            f"{result['solver_status']}: {len(result['assignments'])} assegnazioni, validazione {result['validation']['status']}; nessuna modifica al calendario."
        )
