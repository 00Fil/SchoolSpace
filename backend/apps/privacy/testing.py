"""Fixture condivise dai test s4-privacy (solo dati sintetici)."""

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.education.models import Family, Student
from apps.identity.models import Account, RoleGrant


@pytest.fixture(autouse=True)
def privacy_storage(settings, tmp_path):
    settings.PRIVACY_EXPORT_DIR = tmp_path / "exports"
    settings.PRIVACY_LEDGER_PATH = tmp_path / "ledger.jsonl"
    return tmp_path


def make_account(username, role=None, **extra):
    account = Account.objects.create_user(
        username=username,
        email=f"{username}@example.invalid",
        password="synthetic-Password-42!",
        **extra,
    )
    if role:
        RoleGrant.objects.create(
            account=account, role=role, valid_from=timezone.now() - timedelta(days=1)
        )
    return account


@pytest.fixture
def center():
    return make_account("s4-center", "CENTER")


@pytest.fixture
def outsider():
    return make_account("s4-outsider", "GUARDIAN")


@pytest.fixture
def family():
    return Family.objects.create(reference="FAM-S4-SYNTH")


@pytest.fixture
def student(family):
    from apps.privacy.models import StudentProfile

    s = Student.objects.create(family=family, display_name="Studente Sintetico")
    StudentProfile.objects.create(student=s)
    return s


def api(user=None):
    client = APIClient()
    if user is not None:
        client.force_authenticate(user=user)
    return client
