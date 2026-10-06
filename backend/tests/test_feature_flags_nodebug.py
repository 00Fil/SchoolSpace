"""P0 (guida v3.1, T1): con DEBUG=0 calendario, pianificazione e portali restano attivi
se i flag di funzione sono accesi, e si spengono solo con i flag."""

import pytest
from config import features


@pytest.fixture
def nodebug(settings):
    settings.DEBUG = False
    settings.SECURE_SSL_REDIRECT = False
    settings.FEATURE_PLANNING = True
    settings.FEATURE_CALENDAR = True
    settings.FEATURE_PLANNING_LAB = False
    return settings


def test_flags_independent_from_debug(nodebug):
    assert features.planning_enabled() and features.calendar_enabled()
    assert not features.lab_enabled()


def test_calendar_requires_planning(nodebug):
    nodebug.FEATURE_PLANNING = False
    assert not features.calendar_enabled()


def test_each_flag_turns_off_its_area(nodebug):
    nodebug.FEATURE_CALENDAR = False
    assert features.planning_enabled() and not features.calendar_enabled()


@pytest.mark.django_db
def test_calendar_capabilities_with_debug_off(nodebug, django_user_model):
    from apps.identity.policies import is_center  # noqa: F401  (import di controllo)
    from django.test import Client

    # Utente non autenticato: la rotta esiste ma non espone dati (401/403), non 503.
    response = Client().get("/api/v1/calendar/capabilities")
    assert response.status_code in (401, 403)


@pytest.mark.django_db
def test_portal_calendar_enabled_with_debug_off(nodebug):
    from api.portals_v2 import calendar_enabled

    assert calendar_enabled() is True
    nodebug.FEATURE_CALENDAR = False
    assert calendar_enabled() is False
