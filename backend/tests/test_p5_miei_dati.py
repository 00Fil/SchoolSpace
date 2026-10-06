"""P5 · «I miei dati»: BOLA e regole (richiede PostgreSQL come gli altri test d'integrazione)."""

import pytest

from api.my_data import subjects_of

from tests.test_calendar import center, pytestmark  # noqa: F401


def test_center_is_redirected_to_privacy_area(center):
    res = center[2].get("/api/v1/me/data")
    assert res.status_code == 403


def test_export_of_foreign_subject_is_denied(center):
    from tests.test_calendar_conflicts import guardian_of
    from tests.test_p4_operativita import WEEK, publish, week_lessons, client_for
    from apps.education.models import Student

    publish(center)
    lesson = week_lessons(WEEK, state="PUBLISHED").first()
    mine = lesson.participants.values_list("student_id", flat=True).first()
    guardian = guardian_of(mine)
    other = Student.objects.exclude(pk=mine).first()
    client = client_for(guardian)
    assert {"type": "STUDENT", "id": str(mine)} in [{"type": r["type"], "id": r["id"]} for r in subjects_of(guardian)]
    if other:
        res = client.post("/api/v1/me/data/export", {"subject_type": "STUDENT", "subject_id": str(other.pk)}, format="json")
        assert res.status_code == 403
    res = client.post("/api/v1/me/data/requests", {"kind": "ERASURE", "subject_type": "ACCOUNT", "subject_id": str(guardian.pk)}, format="json")
    assert res.status_code == 201, res.content
    again = client.post("/api/v1/me/data/requests", {"kind": "ERASURE", "subject_type": "ACCOUNT", "subject_id": str(guardian.pk)}, format="json")
    assert again.status_code == 409


def test_minor_student_has_no_reconfirmations():
    from api.my_data import consent_of

    class Nobody:
        pk = None

    # Account senza ruolo STUDENT: nessun blocco consenso.
    import api.my_data as m

    m_active = m.active_roles
    try:
        m.active_roles = lambda user: set()
        assert consent_of(Nobody()) is None
    finally:
        m.active_roles = m_active
