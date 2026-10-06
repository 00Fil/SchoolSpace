"""Integrazione calendario → outbox (GAP-F01, GAP-F05, FR20, T22) e API (GAP-F03, GAP-F04)."""

import json
from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from rest_framework.test import APIClient

from apps.availability.models import AvailabilityRule
from apps.calendar.models import CalendarEvent, LessonOccurrence
from apps.calendar.services import change_lesson
from apps.communications import dispatch
from apps.communications.dispatch import reconcile
from apps.communications.models import (
    CalendarFeedToken,
    Delivery,
    DeliveryStatus as S,
    MeetingLink,
    Notification,
    OutboxEvent,
)
from apps.communications.providers import SinkBackend
from apps.education.models import GuardianLink, Student, Tutor
from apps.identity.models import Account
from tests.test_calendar import center, plan_for, publish  # noqa: F401

from apps.identity.models import RoleGrant  # noqa: E402

pytestmark = pytest.mark.django_db(transaction=True)
FAMILY, LEARNER, TUTOR = (
    "portale-famiglia-demo",
    "portale-studente-demo",
    "tutor-planning-demo-1",
)
ALLOWED_KEYS = {
    "lesson_id",
    "version",
    "subject_name",
    "mode",
    "location",
    "start_at",
    "end_at",
    "state",
    "previous_start_at",
    "previous_end_at",
}
VIDEO_URL = "https://video.example.invalid/stanza-segreta-1"


@pytest.fixture(autouse=True)
def sink():
    SinkBackend.reset()
    yield SinkBackend
    SinkBackend.reset()


@pytest.fixture
def comms(center):  # noqa: F811
    call_command("seed_portal_demo", actor=center[0].username, stdout=StringIO())
    Account.objects.filter(username__in=[FAMILY, LEARNER, TUTOR]).update(
        email_verified=True
    )
    publish(center, plan_for(center))
    return center


def user(name):
    return Account.objects.get(username=name)


def own_students(account):
    return set(
        GuardianLink.objects.filter(account=account).values_list(
            "student_id", flat=True
        )
    )


def client_for(account=None):
    client = APIClient()
    if account:
        client.force_authenticate(account)
    return client


def family_lesson():
    return (
        LessonOccurrence.objects.filter(
            participants__student_id__in=own_students(user(FAMILY))
        )
        .order_by("start_at")
        .first()
    )


def everything_sent():
    """Testo di tutto ciò che esce: payload, contesti, notifiche, email."""
    parts = [json.dumps(e.payload) for e in OutboxEvent.objects.all()]
    parts += [json.dumps(d.context) for d in Delivery.objects.all()]
    parts += [n.title + n.body for n in Notification.objects.all()]
    parts += [m.subject + m.body for m in SinkBackend.messages]
    return "\n".join(parts)


# --- outbox dal calendario -----------------------------------------------------


def test_publish_writes_one_outbox_event_per_lesson(comms):
    lessons = list(LessonOccurrence.objects.all())
    events = OutboxEvent.objects.filter(event_type="lesson.published")
    assert events.count() == len(lessons) == CalendarEvent.objects.count() == 6
    assert {e.idempotency_key for e in events} == {
        f"calendar:lesson:{l.id}:v1" for l in lessons
    }
    for event in events:
        assert set(event.payload) <= ALLOWED_KEYS
    tutor_ids = set(
        Delivery.objects.filter(recipient=user(TUTOR), channel="IN_APP").values_list(
            "event__subject_ref", flat=True
        )
    )
    assert tutor_ids == {
        f"lesson:{l.id}" for l in lessons if l.tutor.account.username == TUTOR
    }


def test_publish_replay_creates_no_second_event_or_notification(comms):
    before = (OutboxEvent.objects.count(), Delivery.objects.count())
    plan = LessonOccurrence.objects.first().publication.plan
    publish(comms, plan)  # stessa chiave: risposta registrata
    assert (OutboxEvent.objects.count(), Delivery.objects.count()) == before
    reconcile(inline=True)
    reconcile(inline=True)
    notes = Notification.objects.count()
    assert notes == Delivery.objects.filter(channel="IN_APP", status=S.SENT).count()
    assert Notification.objects.values("event", "recipient").distinct().count() == notes


def test_recipients_get_only_their_own_students(comms):
    family = user(FAMILY)
    mine = set(
        Student.objects.filter(id__in=own_students(family)).values_list(
            "display_name", flat=True
        )
    )
    for delivery in Delivery.objects.filter(recipient=family):
        assert set(delivery.context["student_names"]) <= mine
    for delivery in Delivery.objects.filter(recipient=user(TUTOR)):
        assert "student_names" not in delivery.context
    learner_name = Student.objects.get(account=user(LEARNER)).display_name
    for delivery in Delivery.objects.filter(recipient=user(LEARNER)):
        assert delivery.context["student_names"] == [learner_name]
        if delivery.channel == "EMAIL":  # D07: email agli studenti spenta di default
            assert delivery.last_error_code == "STUDENT_EMAIL_DISABLED"


def test_f05_no_member_list_no_video_link_in_any_copy(comms):
    family = user(FAMILY)
    lesson = family_lesson()
    MeetingLink.objects.create(lesson=lesson, join_url=VIDEO_URL)
    change_lesson(
        comms[0],
        lesson.id,
        "cancel",
        {"expected_version": lesson.version, "reason": "Sintetico"},
        "cancel-f05",
    )
    reconcile(inline=True)
    text = everything_sent()
    assert "video.example.invalid" not in text and "https://" not in text
    # Ogni email ha un solo destinatario e nessun nome di studenti altrui.
    mine = set(
        Student.objects.filter(id__in=own_students(family)).values_list(
            "display_name", flat=True
        )
    )
    others = set(Student.objects.values_list("display_name", flat=True)) - mine
    family_mail = [m for m in SinkBackend.messages if m.to == family.email]
    assert family_mail
    for message in family_mail:
        assert not any(name in message.body for name in others)
    assert all(m.to.count("@") == 1 for m in SinkBackend.messages)


def test_cancel_emits_once_and_replay_is_silent(comms):
    lesson = family_lesson()
    body = {"expected_version": lesson.version, "reason": "Sintetico"}
    change_lesson(comms[0], lesson.id, "cancel", body, "cancel-1")
    change_lesson(comms[0], lesson.id, "cancel", body, "cancel-1")
    events = OutboxEvent.objects.filter(event_type="lesson.cancelled")
    assert events.count() == 1
    assert events.get().idempotency_key == f"calendar:lesson:{lesson.id}:v2"
    reconcile(inline=True)
    family = user(FAMILY)
    assert (
        Notification.objects.filter(recipient=family, kind="lesson.cancelled").count()
        == 1
    )


def test_reschedule_emits_previous_and_new_time(comms):
    from apps.scheduling.models import ServiceWindow

    for rule in list(AvailabilityRule.objects.filter(weekday=0)):
        rule.pk, rule._state.adding, rule.weekday, rule.version = None, True, 1, 1
        rule.save()
    row = ServiceWindow.objects.get(weekday=0)
    row.pk, row._state.adding, row.weekday, row.version = None, True, 1, 1
    row.save()
    lesson = LessonOccurrence.objects.order_by("start_at").first()
    old = lesson.start_at
    change_lesson(
        comms[0],
        lesson.id,
        "reschedule",
        {
            "expected_version": 1,
            "reason": "Sintetico",
            "start_at": old + timedelta(days=1),
        },
        "move-1",
    )
    event = OutboxEvent.objects.get(event_type="lesson.rescheduled")
    assert event.payload["previous_start_at"] == old.isoformat()
    assert event.payload["start_at"] == (old + timedelta(days=1)).isoformat()
    assert event.payload["version"] == 2


def test_failed_publication_leaves_no_outbox(center, monkeypatch):  # noqa: F811
    from apps.calendar.services import save_bookings

    calls = []

    def fail(lesson):
        calls.append(lesson.id)
        if len(calls) == 3:
            raise RuntimeError("Guasto sintetico")
        return save_bookings(lesson)

    plan = plan_for(center)
    monkeypatch.setattr("apps.calendar.services.save_bookings", fail)
    with pytest.raises(RuntimeError):
        publish(center, plan)
    assert OutboxEvent.objects.count() == Delivery.objects.count() == 0


def test_t22_crash_before_enqueue_calendar_valid_and_outbox_recovers(
    center,
    monkeypatch,  # noqa: F811
):
    monkeypatch.setattr(dispatch, "enqueue", lambda ids: 0)  # processo morto
    publish(center, plan_for(center))
    assert LessonOccurrence.objects.count() == 6  # calendario già valido e persistente
    pending = Delivery.objects.filter(status=S.PENDING, enqueued_at__isnull=True)
    assert pending.count() > 0
    monkeypatch.undo()
    result = reconcile(inline=True)
    assert result["due"] == result["dispatched"] > 0
    assert not Delivery.objects.filter(status=S.PENDING).exists()
    assert reconcile(inline=True)["due"] == 0


# --- API notifiche e preferenze (GAP-F03) -----------------------------------------


def test_notifications_api_own_only_and_mark_read(comms):
    reconcile(inline=True)
    family, tutor = user(FAMILY), user(TUTOR)
    response = client_for(family).get("/api/v1/notifications")
    assert response.status_code == 200
    rows = response.data["results"]
    assert rows and response.data["unread_count"] == len(rows)
    assert Notification.objects.filter(recipient=family).count() == len(rows)
    target = rows[0]["id"]
    assert (
        client_for(tutor).post(f"/api/v1/notifications/{target}/read").status_code
        == 404
    )
    first = client_for(family).post(f"/api/v1/notifications/{target}/read")
    again = client_for(family).post(f"/api/v1/notifications/{target}/read")
    assert first.data["read_at"] and again.data["read_at"] == first.data["read_at"]
    unread = client_for(family).get("/api/v1/notifications?unread=1").data
    assert unread["unread_count"] == len(rows) - 1 == len(unread["results"])
    marked = client_for(family).post("/api/v1/notifications/read-all").data
    assert marked["marked_read"] == len(rows) - 1
    assert client_for().get("/api/v1/notifications").status_code in (401, 403)


def test_preferences_api_and_effect_on_new_events(comms):
    family = user(FAMILY)
    api = client_for(family)
    prefs = api.get("/api/v1/notifications/preferences").data["preferences"]
    service_in_app = [
        p for p in prefs if p["category"] == "SERVICE" and p["channel"] == "IN_APP"
    ]
    assert service_in_app[0]["mandatory"] and service_in_app[0]["enabled"]
    refused = api.put(
        "/api/v1/notifications/preferences",
        {
            "preferences": [
                {"category": "SERVICE", "channel": "IN_APP", "enabled": False}
            ]
        },
        format="json",
    )
    assert refused.status_code == 422
    bad = api.put(
        "/api/v1/notifications/preferences",
        {"preferences": [{"category": "SERVICE", "channel": "EMAIL", "enabled": "no"}]},
        format="json",
    )
    assert bad.status_code == 400
    ok = api.put(
        "/api/v1/notifications/preferences",
        {
            "preferences": [
                {"category": "SERVICE", "channel": "EMAIL", "enabled": False}
            ]
        },
        format="json",
    )
    assert ok.status_code == 200
    lesson = family_lesson()
    change_lesson(
        comms[0],
        lesson.id,
        "cancel",
        {"expected_version": 1, "reason": "Sintetico"},
        "c",
    )
    event = OutboxEvent.objects.get(event_type="lesson.cancelled")
    email = Delivery.objects.get(event=event, recipient=family, channel="EMAIL")
    assert email.status == S.SKIPPED and email.last_error_code == "PREFERENCE_DISABLED"
    assert (
        Delivery.objects.get(event=event, recipient=family, channel="IN_APP").status
        == S.PENDING
    )


# --- ICS personale (GAP-F04) ----------------------------------------------------


def test_ics_token_hash_only_minimal_feed_and_revocation(comms):
    family = user(FAMILY)
    api = client_for(family)
    created = api.post(
        "/api/v1/calendar-feed-tokens", {"label": "Telefono"}, format="json"
    )
    assert created.status_code == 201 and created["Cache-Control"] == "no-store"
    raw = created.data["token"]
    stored = CalendarFeedToken.objects.get(pk=created.data["id"])
    assert raw not in stored.token_hash and len(stored.token_hash) == 64
    assert "token" not in api.get("/api/v1/calendar-feed-tokens").data["results"][0]
    feed = client_for().get(f"/api/v1/calendar.ics?token={raw}")
    assert feed.status_code == 200 and feed["Content-Type"].startswith("text/calendar")
    text = feed.content.decode()
    expected = (
        LessonOccurrence.objects.filter(
            participants__student_id__in=own_students(family)
        )
        .distinct()
        .count()
    )
    assert text.count("BEGIN:VEVENT") == expected > 0
    names = list(Student.objects.values_list("display_name", flat=True))
    names += list(Tutor.objects.values_list("display_name", flat=True))
    assert not any(name in text for name in names)
    assert "https://" not in text and "\r\n" in text
    # Revoca della delega: il perimetro è ricalcolato a ogni richiesta.
    links = GuardianLink.objects.filter(account=family)
    links.update(revoked_at=links.first().valid_from)
    after = client_for().get(f"/api/v1/calendar.ics?token={raw}")
    assert after.status_code == 200 and "BEGIN:VEVENT" not in after.content.decode()
    # Revoca del token.
    other = client_for(user(TUTOR)).post(
        f"/api/v1/calendar-feed-tokens/{stored.id}/revoke"
    )
    assert other.status_code == 404
    assert api.post(f"/api/v1/calendar-feed-tokens/{stored.id}/revoke").data[
        "revoked_at"
    ]
    assert client_for().get(f"/api/v1/calendar.ics?token={raw}").status_code == 404
    assert client_for().get("/api/v1/calendar.ics?token=ics_falso").status_code == 404


def test_ics_inactive_account_and_token_limit(comms):
    tutor = user(TUTOR)
    api = client_for(tutor)
    tokens = [
        api.post("/api/v1/calendar-feed-tokens", {}, format="json") for _ in range(4)
    ]
    assert [t.status_code for t in tokens] == [201, 201, 201, 409]
    raw = tokens[0].data["token"]
    assert client_for().get(f"/api/v1/calendar.ics?token={raw}").status_code == 200
    Account.objects.filter(pk=tutor.pk).update(is_active=False)
    assert client_for().get(f"/api/v1/calendar.ics?token={raw}").status_code == 404


def _force_online(lesson):
    """Preparazione dati: rende ONLINE una lezione in presenza senza ripianificarla.

    Su PostgreSQL i trigger del calendario rifiuterebbero (giustamente) una lezione non
    coerente con l'unità canonica dello snapshot: per questo solo fixture si disattivano
    i trigger nella transazione (``session_replication_role``, consentito al superuser
    del DB di test). Il codice applicativo non usa mai questo percorso.
    """
    from django.db import connection, transaction

    with transaction.atomic():
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL session_replication_role = replica")
        LessonOccurrence.objects.filter(pk=lesson.pk).update(
            mode="ONLINE", location="REMOTE"
        )


# --- link video (GAP-F04) ---------------------------------------------------------


def test_meeting_link_only_authorized_and_in_window(comms, monkeypatch):
    lesson = family_lesson()
    _force_online(lesson)
    url = f"/api/v1/occurrences/{lesson.id}/meeting"
    family = user(FAMILY)
    outsider = Account.objects.create_user(
        username="estraneo", email="estraneo@example.invalid", password=None
    )
    assert client_for(outsider).get(url).status_code == 404
    assert client_for().get(url).status_code in (401, 403)
    monkeypatch.setattr(
        "api.communications.now", lambda: lesson.start_at - timedelta(hours=2)
    )
    early = client_for(family).get(url)
    assert early.status_code == 403 and early.data["code"] == "MEETING_NOT_OPEN"
    assert "join_url" not in early.data
    monkeypatch.setattr(
        "api.communications.now", lambda: lesson.start_at - timedelta(minutes=5)
    )
    missing = client_for(family).get(url)
    assert (
        missing.status_code == 409 and missing.data["code"] == "MEETING_NOT_CONFIGURED"
    )
    MeetingLink.objects.create(lesson=lesson, join_url=VIDEO_URL)
    ok = client_for(family).get(url)
    assert ok.status_code == 200 and ok.data["join_url"] == VIDEO_URL
    assert ok.data["expires_at"] == lesson.end_at.isoformat()
    assert ok["Cache-Control"] == "no-store"
    # Il seed concede il ruolo TUTOR solo a un tutor demo; quale tutor tenga la lezione
    # dipende dalla soluzione del solver (diversa tra SQLite e PostgreSQL).
    tutor_account = lesson.tutor.account
    if not RoleGrant.objects.filter(account=tutor_account, role="TUTOR").exists():
        RoleGrant.objects.create(
            account=tutor_account,
            role="TUTOR",
            valid_from=lesson.start_at - timedelta(days=30),
        )
    assert client_for(tutor_account).get(url).status_code == 200
    monkeypatch.setattr("api.communications.now", lambda: lesson.end_at)
    assert client_for(family).get(url).status_code == 403  # scaduto
    # Mai nell'export generico.
    token = (
        client_for(family).post("/api/v1/calendar-feed-tokens", {}, format="json").data
    )
    feed = (
        client_for()
        .get(f"/api/v1/calendar.ics?token={token['token']}")
        .content.decode()
    )
    assert VIDEO_URL not in feed and "Online – link nel portale" in feed


def test_meeting_in_person_lesson_not_available(comms):
    lesson = LessonOccurrence.objects.filter(mode="IN_PERSON").first()
    response = client_for(comms[0]).get(f"/api/v1/occurrences/{lesson.id}/meeting")
    assert (
        response.status_code == 409 and response.data["code"] == "MEETING_NOT_AVAILABLE"
    )


# --- stato operativo e dead-letter --------------------------------------------------


def test_status_and_manual_resolution_center_only(comms):
    center_user = comms[0]
    assert (
        client_for(user(FAMILY)).get("/api/v1/communications/status").status_code == 403
    )
    status = client_for(center_user).get("/api/v1/communications/status").data
    assert (
        status["counts"]["IN_APP"]["PENDING"] > 0 and status["email_backend"] == "sink"
    )
    assert "recipient" not in json.dumps(status)
    delivery = Delivery.objects.filter(channel="EMAIL", status=S.PENDING).first()
    Delivery.objects.filter(pk=delivery.pk).update(status=S.DEAD, last_error_code="X")
    url = f"/api/v1/communications/deliveries/{delivery.id}/resolve"
    body = {"resolution": "MARK_SENT", "reason": "Verificato nel pannello del provider"}
    assert client_for(user(FAMILY)).post(url, body, format="json").status_code == 403
    done = client_for(center_user).post(url, body, format="json")
    assert done.status_code == 200 and done.data["status"] == S.SENT
    again = client_for(center_user).post(url, body, format="json")
    assert again.status_code == 409
    assert delivery.attempt_log.filter(outcome="MANUAL", actor=center_user).count() == 1


# --- ricontrollo dell'autorizzazione all'invio ------------------------------------


def test_revoked_delegation_after_emit_cancels_delivery(comms):
    family, tutor = user(FAMILY), user(TUTOR)
    assert Delivery.objects.filter(recipient=family, status=S.PENDING).exists()
    GuardianLink.objects.filter(account=family).update(
        revoked_at=GuardianLink.objects.filter(account=family).first().valid_from
    )
    reconcile(inline=True)
    family_rows = Delivery.objects.filter(recipient=family).exclude(status=S.SKIPPED)
    assert family_rows.exists()
    assert set(family_rows.values_list("status", flat=True)) == {S.REVOKED}
    assert set(family_rows.values_list("last_error_code", flat=True)) == {
        "RECIPIENT_NOT_AUTHORIZED"
    }
    assert not Notification.objects.filter(recipient=family).exists()
    assert not [m for m in SinkBackend.messages if m.to == family.email]
    assert Notification.objects.filter(recipient=tutor).exists()
