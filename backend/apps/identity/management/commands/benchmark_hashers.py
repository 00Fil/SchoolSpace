import statistics
import time

from django.contrib.auth.hashers import get_hasher
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        "Misura il tempo di hash delle password con gli hasher configurati "
        "(obiettivo indicativo: 200-500 ms per Argon2id sull'hardware di produzione)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--rounds", type=int, default=5)

    def handle(self, *args, rounds, **options):
        for algorithm in ("argon2", "pbkdf2_sha256"):
            try:
                hasher = get_hasher(algorithm)
            except ValueError:
                self.stdout.write(f"{algorithm}: non configurato")
                continue
            samples = []
            for _ in range(max(1, rounds)):
                start = time.perf_counter()
                hasher.encode("benchmark-password-not-real", hasher.salt())
                samples.append((time.perf_counter() - start) * 1000)
            params = ""
            if algorithm == "argon2":
                params = (
                    f" (t={hasher.time_cost}, m={hasher.memory_cost} KiB, "
                    f"p={hasher.parallelism})"
                )
            self.stdout.write(
                f"{algorithm}{params}: mediana {statistics.median(samples):.0f} ms"
            )
