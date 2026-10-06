"""Testi in italiano per email e notifiche interne. Orari sempre in Europe/Rome."""

from datetime import datetime
from zoneinfo import ZoneInfo

from django.conf import settings
from django.template import TemplateDoesNotExist
from django.template.loader import render_to_string

ROME = ZoneInfo("Europe/Rome")
DAYS = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
MONTHS = [
    "gennaio",
    "febbraio",
    "marzo",
    "aprile",
    "maggio",
    "giugno",
    "luglio",
    "agosto",
    "settembre",
    "ottobre",
    "novembre",
    "dicembre",
]
MODES = {"IN_PERSON": "in presenza", "ONLINE": "online"}
LOCATIONS = {"ON_SITE": "in sede", "REMOTE": "da remoto"}


def italian_datetime(value):
    """``lunedì 5 ottobre 2026, ore 15:00`` nel fuso Europe/Rome."""
    if not value:
        return ""
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    local = value.astimezone(ROME)
    return (
        f"{DAYS[local.weekday()]} {local.day} {MONTHS[local.month - 1]} "
        f"{local.year}, ore {local:%H:%M}"
    )


def italian_time(value):
    if not value:
        return ""
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    return f"{value.astimezone(ROME):%H:%M}"


def build_context(event, delivery):
    payload = dict(event.payload)
    context = {
        **payload,
        "recipient_context": delivery.context,
        "student_names": ", ".join(delivery.context.get("student_names", [])),
        "start_text": italian_datetime(payload.get("start_at")),
        "end_time": italian_time(payload.get("end_at")),
        "previous_start_text": italian_datetime(payload.get("previous_start_at")),
        "mode_text": MODES.get(payload.get("mode"), ""),
        "location_text": LOCATIONS.get(payload.get("location"), ""),
        "portal_url": settings.COMMUNICATIONS_PORTAL_URL,
        "center_name": settings.COMMUNICATIONS_CENTER_NAME,
        "category": event.category,
        "essential": event.essential,
    }
    return context


def _render(event_type, part, context):
    name = event_type.replace(".", "_")
    try:
        return render_to_string(f"communications/email/{name}.{part}.txt", context)
    except TemplateDoesNotExist:
        return render_to_string(f"communications/email/generic.{part}.txt", context)


def _line(text):
    return " ".join(text.split())


def render_email(event, delivery, extra=None):
    """(oggetto, corpo) per un singolo destinatario; ``extra`` resta solo in memoria."""
    context = {**build_context(event, delivery), **(extra or {})}
    subject = _line(_render(event.event_type, "subject", context))[:150]
    body = _render(event.event_type, "body", context).strip() + "\n"
    footer = render_to_string("communications/email/footer.txt", context).strip()
    return subject, f"{body}\n{footer}\n"


def render_notification(event, delivery):
    """(titolo, testo breve) della notifica interna."""
    context = build_context(event, delivery)
    title = _line(_render(event.event_type, "subject", context))[:160]
    body = _line(_render(event.event_type, "notification", context))[:500]
    return title, body
