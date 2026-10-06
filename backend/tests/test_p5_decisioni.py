"""P5 · decisioni D07 e DC-CONFERMA-GENITORI (logica pura, senza database)."""

from types import SimpleNamespace

from django.conf import settings

from apps.calendar.conflicts import awaiting


def row(**proposal):
    return SimpleNamespace(state="SUBMITTED", proposal=proposal)


def test_settings_reflect_decisions():
    assert settings.STUDENT_ACCOUNT_MIN_AGE == 14
    assert settings.PORTAL_STUDENT_CAN_REQUEST_CHANGES is False
    assert settings.TUTOR_CHANGES_REQUIRE_GUARDIANS is True


def test_tutor_change_waits_for_guardians_then_center():
    r = row(center_accepted=True, tutor_confirmed=True, guardians_confirmation_required=True)
    assert awaiting(r) == "GUARDIANS"
    r.proposal["guardians_confirmed"] = True
    assert awaiting(r) == "CENTER"


def test_family_request_still_waits_for_tutor():
    assert awaiting(row(center_accepted=True)) == "TUTOR"
    assert awaiting(SimpleNamespace(state="ACCEPTED", proposal={})) is None
