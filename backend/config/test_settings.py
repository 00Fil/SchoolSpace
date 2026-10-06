import os

os.environ.setdefault("DJANGO_SECRET_KEY", "test-only-not-for-production")
os.environ.setdefault("DJANGO_DEBUG", "1")
os.environ.setdefault("DJANGO_ALLOWED_HOSTS", "testserver,localhost,127.0.0.1")
# SQLite only for the explicitly limited core smoke suite, never for booking guarantees.
os.environ.setdefault("USE_SQLITE_FOR_TESTS", "1")
from .settings import *

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

FEATURE_PLANNING = EXPERIMENTAL_DB_PLANNING = True
FEATURE_PLANNING_LAB = True
CELERY_BROKER_URL = "memory://"

FEATURE_CALENDAR = EXPERIMENTAL_CALENDAR = True
CALENDAR_ALLOW_SQLITE_TESTS = True
