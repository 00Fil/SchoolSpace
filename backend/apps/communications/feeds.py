"""Export ICS personale con token revocabile e link video autorizzati (GAP-F04)."""

import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from .models import CalendarFeedToken, MeetingLink

TOKEN_PREFIX = "ics_"


def hash_token(raw):
    return hashlib.sha256(raw.encode()).hexdigest()


def create_feed_token(account, label=""):
    """Restituisce (record, token in chiaro). Il chiaro non viene mai salvato."""
    active = CalendarFeedToken.objects.filter(account=account, revoked_at__isnull=True)
    if active.count() >= settings.COMMUNICATIONS_ICS_MAX_TOKENS:
        raise ValueError("Numero massimo di link calendario attivi raggiunto")
    raw = TOKEN_PREFIX + secrets.token_urlsafe(32)
    days = settings.COMMUNICATIONS_ICS_TOKEN_DAYS
    record = CalendarFeedToken.objects.create(
        account=account,
        token_hash=hash_token(raw),
        label=label[:60],
        expires_at=timezone.now() + timedelta(days=days) if days else None,
    )
    return record, raw


def resolve_feed_token(raw):
    if not raw or not raw.startswith(TOKEN_PREFIX) or len(raw) > 100:
        return None
    now = timezone.now()
    record = (
        CalendarFeedToken.objects.select_related("account")
        .filter(token_hash=hash_token(raw), revoked_at__isnull=True)
        .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
        .first()
    )
    if not record or not record.account.is_active:
        return None
    if not record.last_used_at or record.last_used_at < now - timedelta(minutes=5):
        CalendarFeedToken.objects.filter(pk=record.pk).update(last_used_at=now)
    return record


def _escape(text):
    return (
        str(text)
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def _fold(line):
    raw = line.encode()
    if len(raw) <= 75:
        return line
    parts, current = [], b""
    for char in line:
        encoded = char.encode()
        if len(current) + len(encoded) > (75 if not parts else 74):
            parts.append(current.decode())
            current = b""
        current += encoded
    parts.append(current.decode())
    return "\r\n ".join(parts)


def build_ics(lessons, now=None):
    """VCALENDAR minimizzato: materia, orari, stato, modalità. Nessun nome o link."""
    from datetime import timezone as dt_timezone

    now = now or timezone.now()
    stamp = now.astimezone(dt_timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    domain = settings.COMMUNICATIONS_EMAIL["MESSAGE_ID_DOMAIN"]
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Gestionale ripetizioni//Calendario personale//IT",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:" + _escape("Lezioni – " + settings.COMMUNICATIONS_CENTER_NAME),
        "X-WR-TIMEZONE:Europe/Rome",
    ]
    for lesson in lessons:
        where = "Online – link nel portale" if lesson.mode == "ONLINE" else "In sede"
        lines += [
            "BEGIN:VEVENT",
            f"UID:lesson-{lesson.id}@{domain}",
            f"DTSTAMP:{stamp}",
            "DTSTART:"
            + lesson.start_at.astimezone(dt_timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
            "DTEND:"
            + lesson.end_at.astimezone(dt_timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
            f"SEQUENCE:{lesson.version}",
            "SUMMARY:" + _escape(f"Lezione di {lesson.subject.name}"),
            "LOCATION:" + _escape(where),
            "DESCRIPTION:" + _escape("Dettagli aggiornati nel portale del centro."),
            "STATUS:" + ("CANCELLED" if lesson.state == "CANCELLED" else "CONFIRMED"),
            "CLASS:PRIVATE",
            "TRANSP:OPAQUE",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(l) for l in lines) + "\r\n"


def meeting_window(lesson):
    opens = lesson.start_at - timedelta(
        minutes=settings.COMMUNICATIONS_MEETING_OPEN_MINUTES_BEFORE
    )
    return opens, lesson.end_at


def meeting_link_for(lesson):
    link = MeetingLink.objects.filter(lesson=lesson).first()
    if not link and lesson.video_id:
        link = MeetingLink.objects.filter(resource_id=lesson.video_id).first()
    return link
