"""v0.10: email HTML nello stile del centro (Lumen), con struttura fissa."""

import json
from email import message_from_bytes
from types import SimpleNamespace as N

import pytest

from apps.communications import email_layout, providers
from apps.communications.providers import OutgoingEmail, build_mime
from apps.communications.rendering import render_email, render_email_html

BASE = {
    "subject_name": "Fisica",
    "start_at": "2026-10-26T14:00:00+00:00",
    "end_at": "2026-10-26T15:00:00+00:00",
    "previous_start_at": "2026-10-23T13:00:00+00:00",
    "previous_end_at": "2026-10-23T14:00:00+00:00",
    "mode": "ONLINE",
    "overflow_minutes": 15,
    "outcome": "REJECTED",
    "resolution": "Il tutor non è disponibile",
}
TYPES = [*email_layout.BUILDERS, "other.event"]


def render(event_type, payload=None, context=None, extra=None):
    event = N(
        event_type=event_type,
        payload=payload if payload is not None else BASE,
        category="calendar",
        essential=event_type.startswith("identity."),
    )
    delivery = N(context=context if context is not None else {"student_names": ["Sara"]})
    subject, text = render_email(event, delivery, extra)
    return subject, text, render_email_html(event, delivery, extra, subject)


@pytest.fixture(autouse=True)
def portal(settings):
    settings.COMMUNICATIONS_PORTAL_URL = "https://portale.example.invalid"
    settings.COMMUNICATIONS_CENTER_NAME = "Centro Lumen"


@pytest.mark.parametrize("event_type", TYPES)
def test_every_type_has_structured_lumen_html(event_type):
    extra = {"link": "https://portale.example.invalid/#/invito/t0k3n", "hours": 72, "minutes": 30}
    subject, _text, html = render(event_type, extra=extra)
    assert html.startswith("<!DOCTYPE html>") and 'lang="it"' in html
    assert "{{" not in html and "{%" not in html
    assert "Centro Lumen" in html and "#4F7CF7" in html  # logo e palette Lumen
    assert "prefers-color-scheme:dark" in html
    # nessuna risorsa remota: niente immagini, pixel o font esterni
    assert "<img" not in html and "src=" not in html and "@import" not in html
    assert subject in html  # <title>


def test_lesson_html_has_calendar_tile_details_and_cta():
    _, _, html = render("lesson.rescheduled")
    assert "OTT" in html and ">26<" in html and "Lunedì 26 ottobre 2026" in html
    assert "15:00 – 16:00" in html and "60 min" in html and "ora italiana" in html
    assert "line-through" in html and "Venerdì 23 ottobre 2026" in html  # orario precedente
    assert "Materia" in html and "Sara" in html and "Online" in html
    assert 'href="https://portale.example.invalid"' in html
    assert "Lezione spostata" in html


def test_confirmation_requests_list_steps():
    _, _, html = render("autoplan.confirmation_requested")
    assert "Cosa fare" in html and "Da confermare" in html and "15 minuti" in html


def test_user_text_is_escaped_and_bad_links_dropped(settings):
    settings.COMMUNICATIONS_PORTAL_URL = "javascript:alert(1)"
    payload = {**BASE, "subject_name": "<script>x</script>", "resolution": '"><b>no</b>'}
    _, _, html = render("lesson.change_answered", payload)
    assert "<script>x" not in html and "&lt;script&gt;" in html
    assert "<b>no</b>" not in html
    assert "javascript:" not in html


def test_identity_html_carries_link_only_in_memory_render():
    link = "https://portale.example.invalid/#/reset/abc"
    _, text, html = render("identity.password_reset", {}, {}, {"link": link, "minutes": 30})
    assert html.count(link) >= 2  # pulsante + indirizzo in chiaro
    assert "Scegli una nuova password" in html and "30 minuti" in html
    assert link in text
    assert "Preferenze di notifica" not in html  # messaggio di sicurezza


def test_mime_is_multipart_alternative_with_text_first():
    msg = OutgoingEmail(to="a@example.invalid", subject="S", body="Testo", idempotency_key="k", html="<p>Ciao</p>")
    mime = message_from_bytes(build_mime(msg, "c@example.invalid", "example.invalid").as_bytes())
    assert mime.get_content_type() == "multipart/alternative"
    parts = [p.get_content_type() for p in mime.walk() if not p.is_multipart()]
    assert parts == ["text/plain", "text/html"]


def test_resend_payload_includes_html(settings, monkeypatch):
    settings.COMMUNICATIONS_ENV = "production"
    settings.COMMUNICATIONS_EMAIL = {
        **settings.COMMUNICATIONS_EMAIL,
        "BACKEND": "resend",
        "RESEND_API_KEY": "re_test",
        "FROM": "Centro <c@example.invalid>",
    }
    seen = {}

    class Resp:
        status = 200

        def read(self):
            return b'{"id": "r-1"}'

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def urlopen(req, timeout):
        seen.update(json.loads(req.data))
        return Resp()

    monkeypatch.setattr(providers.urlrequest, "urlopen", urlopen)
    msg = OutgoingEmail(to="a@example.invalid", subject="S", body="Testo", idempotency_key="k", html="<p>Ciao</p>")
    providers.get_backend().send(msg)
    assert seen["text"] == "Testo" and seen["html"] == "<p>Ciao</p>"
