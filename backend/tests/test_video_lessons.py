"""v0.10 · Aule creabili dal centro e videolezioni automatiche su Jitsi Meet."""

from datetime import timedelta

import pytest

from apps.calendar.models import LessonOccurrence
from apps.communications import video
from apps.communications.models import MeetingLink, MeetingPresence
from apps.education.models import Resource
from apps.identity.models import Account, RoleGrant
from tests.test_calendar import center, plan_for, publish  # noqa: F401
from tests.test_communications_calendar import (  # noqa: F401
    FAMILY,
    _force_online,
    client_for,
    comms,
    family_lesson,
    own_students,
    sink,
    user,
)

pytestmark = pytest.mark.django_db(transaction=True)
SECRET = "s" * 40
JITSI = "https://meet.example.invalid"


@pytest.fixture
def jitsi(settings):
    settings.VIDEO_PROVIDER = "jitsi"
    settings.VIDEO_JITSI_URL = JITSI
    settings.VIDEO_JITSI_APP_SECRET = SECRET
    settings.VIDEO_GRACE_MINUTES = 10
    return settings


# --- aule e canali (405 corretto) --------------------------------------------------


def test_center_creates_and_edits_resources():
    admin = Account.objects.create_superuser(
        username="centro-aule", email="aule@example.invalid", password=None
    )
    c = client_for(admin)
    made = c.post(
        "/api/v1/resources/",
        {"name": "Aula Blu", "kind": "SPACE", "student_capacity": 6, "active": True},
        format="json",
    )
    assert made.status_code == 201, made.data
    assert made.data["version"] == 1 and made.data["student_capacity"] == 6
    channel = c.post(
        "/api/v1/resources/",
        {"name": "Canale 1", "kind": "VIDEO_CHANNEL", "student_capacity": 9},
        format="json",
    )
    assert channel.status_code == 201 and channel.data["student_capacity"] is None
    bad = c.post(
        "/api/v1/resources/",
        {"name": "Aula senza posti", "kind": "SPACE", "student_capacity": None},
        format="json",
    )
    assert bad.status_code == 400
    dup = c.post(
        "/api/v1/resources/",
        {"name": "Aula Blu", "kind": "SPACE", "student_capacity": 2},
        format="json",
    )
    assert dup.status_code in (400, 409)
    rid = made.data["id"]
    edit = c.patch(
        f"/api/v1/resources/{rid}/",
        {"student_capacity": 8, "expected_version": 1},
        format="json",
    )
    assert edit.status_code == 200 and edit.data["version"] == 2
    stale = c.patch(
        f"/api/v1/resources/{rid}/",
        {"active": False, "expected_version": 1},
        format="json",
    )
    assert stale.status_code == 409
    off = c.patch(f"/api/v1/resources/{rid}/", {"active": False}, format="json")
    assert off.status_code == 200 and off.data["active"] is False
    assert c.delete(f"/api/v1/resources/{rid}/").status_code == 405
    assert Resource.objects.get(pk=rid).student_capacity == 8


def test_non_center_cannot_create_resources():
    someone = Account.objects.create_user(
        username="famiglia-x", email="x@example.invalid", password=None
    )
    r = client_for(someone).post(
        "/api/v1/resources/",
        {"name": "Aula X", "kind": "SPACE", "student_capacity": 2},
        format="json",
    )
    assert r.status_code == 403 and not Resource.objects.filter(name="Aula X").exists()


# --- stanza Jitsi automatica -----------------------------------------------------


def _tutor_account(lesson):
    account = lesson.tutor.account
    if not RoleGrant.objects.filter(account=account, role="TUTOR").exists():
        RoleGrant.objects.create(
            account=account,
            role="TUTOR",
            valid_from=lesson.start_at - timedelta(days=30),
        )
    return account


def test_automatic_jitsi_room_with_signed_token(comms, jitsi, monkeypatch):  # noqa: F811
    lesson = family_lesson()
    _force_online(lesson)
    lesson.refresh_from_db()
    url = f"/api/v1/occurrences/{lesson.id}/meeting"
    family = user(FAMILY)
    monkeypatch.setattr(
        "api.communications.now", lambda: lesson.start_at - timedelta(hours=2)
    )
    assert client_for(family).get(url).data["code"] == "MEETING_NOT_OPEN"
    monkeypatch.setattr(
        "api.communications.now", lambda: lesson.start_at - timedelta(minutes=5)
    )
    ok = client_for(family).get(url)
    assert ok.status_code == 200, ok.data
    assert ok.data["provider"] == "jitsi" and ok.data["moderator"] is False
    room = video.room_name(lesson)
    assert ok.data["room"] == room and ok.data["join_url"].startswith(
        f"{JITSI}/{room}?jwt="
    )
    token = ok.data["join_url"].split("jwt=")[1].split("#")[0]
    claims = video.decode(token)
    assert claims["room"] == room and claims["aud"] == "jitsi"
    assert claims["exp"] == int((lesson.end_at + timedelta(minutes=10)).timestamp())
    assert claims["context"]["user"]["moderator"] is False
    # Integrata: una sola intestazione, Jitsi non ripete materia e timer.
    assert "hideConferenceSubject" in ok.data["embed_url"]
    assert "hideConferenceSubject" not in ok.data["join_url"]
    assert ok.data["starts_at"] == lesson.start_at.isoformat()
    assert family.email not in ok.data["join_url"] and str(family.id) not in token
    # Il nome visualizzato è quello dello studente, non dell'account del genitore.
    names = {
        p.student.display_name for p in lesson.participants.select_related("student")
    }
    assert set(ok.data["display_name"].split(", ")) <= names
    # Il tutor della lezione entra come moderatore, nella stessa stanza.
    tutor = client_for(_tutor_account(lesson)).get(url)
    assert tutor.status_code == 200 and tutor.data["moderator"] is True
    assert tutor.data["room"] == room
    with pytest.raises(ValueError):
        video.decode(token[:-2] + "xx")
    # Un link manuale ha sempre la precedenza.
    MeetingLink.objects.create(
        lesson=lesson, join_url="https://altro.example.invalid/x"
    )
    manual = client_for(family).get(url)
    assert manual.data["join_url"] == "https://altro.example.invalid/x"
    assert "provider" not in manual.data


def test_rooms_are_distinct_and_stable(comms, jitsi):  # noqa: F811
    a, b = LessonOccurrence.objects.order_by("start_at")[:2]
    assert video.room_name(a) != video.room_name(b)
    assert video.room_name(a) == video.room_name(a)
    assert video.room_name(a) == video.room_name(a).lower()


def test_presence_tracking_prefills_attendance(comms, jitsi, monkeypatch):  # noqa: F811
    lesson = family_lesson()
    _force_online(lesson)
    lesson.refresh_from_db()
    family = user(FAMILY)
    url = f"/api/v1/occurrences/{lesson.id}/meeting/presence"
    clock = {"t": lesson.start_at - timedelta(hours=1)}
    monkeypatch.setattr("api.communications.now", lambda: clock["t"])
    early = client_for(family).post(url, {"event": "join"}, format="json")
    assert early.status_code == 403
    clock["t"] = lesson.start_at - timedelta(minutes=2)
    assert (
        client_for(family).post(url, {"event": "join"}, format="json").status_code
        == 200
    )
    for minute in range(1, 21):  # 20 minuti dentro la lezione
        clock["t"] = lesson.start_at + timedelta(minutes=minute)
        client_for(family).post(url, {"event": "heartbeat"}, format="json")
    clock["t"] = lesson.start_at + timedelta(minutes=40)  # buco: scheda chiusa
    client_for(family).post(url, {"event": "heartbeat"}, format="json")
    row = MeetingPresence.objects.get(lesson=lesson, account=family)
    assert row.seconds == 20 * 60
    assert set(row.student_ids) <= {str(s) for s in own_students(family)}
    # Solo tutor o centro leggono il riepilogo.
    assert client_for(family).get(url).status_code == 403
    summary = client_for(comms[0]).get(url)
    assert summary.status_code == 200
    joined = [s for s in summary.data["students"] if s["joined"]]
    assert joined and all(s["minutes"] == 20 for s in joined)
    outsider = Account.objects.create_user(
        username="estraneo-v", email="ev@example.invalid", password=None
    )
    assert (
        client_for(outsider).post(url, {"event": "join"}, format="json").status_code
        == 404
    )
