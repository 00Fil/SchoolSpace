from django.conf import settings
from django.contrib.auth.hashers import Argon2PasswordHasher


class ConfigurableArgon2PasswordHasher(Argon2PasswordHasher):
    """Argon2id con parametri da impostazioni (benchmark: ``manage.py benchmark_hashers``).

    Default identici a Django 5.2 (t=2, m=100 MiB, p=8). L'algoritmo resta ``argon2``: gli
    hash esistenti restano verificabili e si aggiornano al login se i parametri cambiano.
    """

    @property
    def time_cost(self):
        return int(getattr(settings, "ARGON2_TIME_COST", 2))

    @property
    def memory_cost(self):
        return int(getattr(settings, "ARGON2_MEMORY_COST_KIB", 102400))

    @property
    def parallelism(self):
        return int(getattr(settings, "ARGON2_PARALLELISM", 8))
