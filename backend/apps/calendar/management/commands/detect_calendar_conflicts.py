"""Rileva lezioni future non più valide e apre ConflictCase (nessuna modifica)."""

from django.core.management.base import BaseCommand
from django.db import transaction
from apps.calendar.conflicts import detect_conflicts


class Command(BaseCommand):
    help = (
        "Apre pratiche di conflitto per lezioni pubblicate non più valide; idempotente"
    )

    def handle(self, *args, **options):
        with transaction.atomic():
            opened = detect_conflicts()
        self.stdout.write(f"Pratiche nuove: {len(opened)}. Calendario invariato.")
