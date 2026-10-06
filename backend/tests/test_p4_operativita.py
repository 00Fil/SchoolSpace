"""P4: regole dei recuperi (preavviso 24 ore, scadenza) e doppia conferma centro+tutor."""

from datetime import date, timedelta

from django.utils import timezone
from apps.calendar.models import ChangeRequest
from apps.communications.models import Delivery
from apps.education.models import Tutor
from apps.identity.models import Account, RoleGrant
from apps.scheduling.models import SchoolYear
from tests.test_calendar import center, publish, WEEK, pytestmark  # noqa: F401
from tests.test_calendar_conflicts import client_for, guardian_of
from tests.calendar_helpers import post, week_lessons


def tutor_client(lesson):
    tutor = Tutor.objects.get(pk=lesson.tutor_id)
    if tutor.account_id and not RoleGrant.objects.filter(account_id=tutor.account_id, role="TUTOR").exists():
        RoleGrant.objects.create(account_id=tutor.account_id, role="TUTOR", valid_from=timezone.now() - timedelta(days=1))
    if not tutor.account_id:
        account = Account.objects.create_user(
            username=f"tutor-{tutor.pk.hex[:8]}", email=f"t{tutor.pk.hex[:8]}@example.invalid"
        )
        RoleGrant.objects.create(account=account, role="TUTOR", valid_from=timezone.now() - timedelta(days=1))
        tutor.account = account
        tutor.save(update_fields=["account"])
    return client_for(tutor.account)


def cancelled_lesson(center, key):
    publish(center)
    lesson = week_lessons(WEEK, state="PUBLISHED").first()
    student = lesson.participants.values_list("student_id", flat=True).first()
    response = post(
        center[2],
        f"/api/v1/occurrences/{lesson.id}/cancel/",
        {"expected_version": lesson.version, "reason": "Assenza comunicata tardi"},
        key,
    )
    assert response.status_code == 200, response.data
    lesson.refresh_from_db()
    return lesson, student


def test_late_notice_needs_explicit_grant(center):
    lesson, student = cancelled_lesson(center, "c-late")
    # La lezione di prova cade a breve distanza: simuliamo un avviso arrivato tardi.
    ChangeRequest.objects.create(
        lesson=lesson, kind="ABSENCE", origin="GUARDIAN", reason="Febbre",
        student_id=student, proposal={}, requested_by=guardian_of(student),
    )
    ChangeRequest.objects.filter(lesson=lesson).update(created_at=lesson.start_at - timedelta(hours=3))
    body = {"expected_version": lesson.version, "cause": "STUDENT_ABSENCE", "participant_ids": [str(student)], "reason": "Recupero"}
    url = f"/api/v1/occurrences/{lesson.id}/recovery/"
    refused = post(center[2], url, body, "r1")
    assert refused.status_code == 422 and refused.data["code"] == "LATE_NOTICE"
    granted = post(center[2], url, {**body, "grant_late_notice": True}, "r2")
    assert granted.status_code == 200, granted.data
    assert granted.data["state"] == "OPEN"


def test_center_cancellation_needs_no_notice(center):
    lesson, student = cancelled_lesson(center, "c-ctr")
    body = {"expected_version": lesson.version, "cause": "CENTER_CANCELLATION", "participant_ids": [str(student)], "reason": "Chiusura"}
    done = post(center[2], f"/api/v1/occurrences/{lesson.id}/recovery/", body, "r3")
    assert done.status_code == 200, done.data


def test_makeup_after_school_year_is_refused(center):
    lesson, student = cancelled_lesson(center, "c-due")
    day = lesson.start_at.date()
    SchoolYear.objects.create(name="prova", start_date=day - timedelta(days=30), end_date=day + timedelta(days=10))
    body = {"expected_version": lesson.version, "cause": "CENTER_CANCELLATION", "participant_ids": [str(student)], "reason": "Chiusura"}
    obligation = post(center[2], f"/api/v1/occurrences/{lesson.id}/recovery/", body, "r4").data
    assert obligation["due_by"] == (day + timedelta(days=10)).isoformat()
    late = lesson.start_at + timedelta(days=60)
    response = post(center[2], f"/api/v1/recovery-obligations/{obligation['id']}/makeup/", {
        "expected_version": obligation["version"], "start_at": late.isoformat(), "tutor_id": str(lesson.tutor_id),
        "mode": lesson.mode, "location": lesson.location, "space_id": None, "video_id": None, "reason": "Recupero",
    }, "m1")
    assert response.status_code == 422 and response.data["code"] == "RECOVERY_PAST_DUE"


def test_family_request_needs_center_and_tutor(center):
    publish(center)
    lesson = week_lessons(WEEK, state="PUBLISHED").first()
    student = lesson.participants.values_list("student_id", flat=True).first()
    guardian = client_for(guardian_of(student))
    created = post(guardian, "/api/v1/change-requests/", {
        "lesson_id": str(lesson.id), "kind": "CANCEL", "reason": "Visita medica", "student_id": str(student),
    }, "g1").data
    base = f"/api/v1/change-requests/{created['id']}"
    tutor = tutor_client(lesson)
    early = post(tutor, base + "/tutor-confirm/", {"expected_version": 1, "decision": "CONFIRM", "reason": "Ok"}, "t0")
    assert early.status_code == 422 and early.data["code"] == "CHANGE_NOT_AWAITING_TUTOR"
    accepted = post(center[2], base + "/decide/", {"expected_version": 1, "decision": "ACCEPT", "apply": True, "reason": "Ok"}, "d1")
    assert accepted.data["awaiting"] == "TUTOR"
    assert post(guardian, base + "/tutor-confirm/", {"expected_version": 2, "decision": "CONFIRM", "reason": "x"}, "g2").status_code in (403, 404)
    other = Tutor.objects.exclude(pk=lesson.tutor_id).first()
    if other:
        fake = lesson.__class__(tutor_id=other.pk)
        assert post(tutor_client(fake), base + "/tutor-confirm/", {"expected_version": 2, "decision": "CONFIRM", "reason": "x"}, "o1").status_code == 404
    done = post(tutor, base + "/tutor-confirm/", {"expected_version": 2, "decision": "CONFIRM", "reason": "Ok"}, "t1")
    assert done.status_code == 200, done.data
    assert done.data["state"] == "ACCEPTED" and done.data["applied"]
    lesson.refresh_from_db()
    assert lesson.state == "CANCELLED"


def test_tutor_can_reject_family_request(center):
    publish(center)
    lesson = week_lessons(WEEK, state="PUBLISHED").first()
    student = lesson.participants.values_list("student_id", flat=True).first()
    guardian = client_for(guardian_of(student))
    created = post(guardian, "/api/v1/change-requests/", {
        "lesson_id": str(lesson.id), "kind": "CANCEL", "reason": "Visita", "student_id": str(student),
    }, "g1").data
    base = f"/api/v1/change-requests/{created['id']}"
    post(center[2], base + "/decide/", {"expected_version": 1, "decision": "ACCEPT", "apply": True, "reason": "Ok"}, "d1")
    done = post(tutor_client(lesson), base + "/tutor-confirm/", {"expected_version": 2, "decision": "REJECT", "reason": "Ho già spostato"}, "t1")
    assert done.data["state"] == "REJECTED"
    lesson.refresh_from_db()
    assert lesson.state == "PUBLISHED"


def test_no_email_when_center_uses_portal_only(center, settings):
    settings.COMMUNICATIONS_CHANNELS = ("IN_APP",)
    publish(center)
    lesson = week_lessons(WEEK, state="PUBLISHED").first()
    student = lesson.participants.values_list("student_id", flat=True).first()
    guardian = client_for(guardian_of(student))
    post(guardian, "/api/v1/change-requests/", {
        "lesson_id": str(lesson.id), "kind": "ABSENCE", "reason": "Febbre", "student_id": str(student),
    }, "g1")
    assert not Delivery.objects.filter(channel="EMAIL", event__event_type__startswith="change_request").exists()


def test_delivery_problems_center_only(center):
    from tests.test_calendar_conflicts import guardian_of

    assert center[2].get("/api/v1/communications/deliveries").status_code == 200
    publish(center)
    lesson = week_lessons(WEEK, state="PUBLISHED").first()
    student = lesson.participants.values_list("student_id", flat=True).first()
    assert client_for(guardian_of(student)).get("/api/v1/communications/deliveries").status_code == 403


def test_substitutes_read_only_and_center_only(center):
    from tests.test_calendar_conflicts import guardian_of

    publish(center)
    lesson = week_lessons(WEEK, state="PUBLISHED").first()
    before = (lesson.version, lesson.tutor_id)
    res = center[2].get(f"/api/v1/occurrences/{lesson.id}/substitutes/")
    assert res.status_code == 200, res.content
    body = res.json()
    assert all(r["tutor_id"] != str(lesson.tutor_id) for r in body["substitutes"])
    assert body["fallback"] in (None, "RECOVERY")
    lesson.refresh_from_db()
    assert (lesson.version, lesson.tutor_id) == before
    student = lesson.participants.values_list("student_id", flat=True).first()
    other = client_for(guardian_of(student)).get(f"/api/v1/occurrences/{lesson.id}/substitutes/")
    assert other.status_code == 403
