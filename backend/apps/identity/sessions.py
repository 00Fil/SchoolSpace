"""Registro server-side delle sessioni, timeout e revoca (GAP-B04)."""

from datetime import timedelta

from django.utils import timezone

from . import conf
from .models import UserSession
from .net import client_ip
from .policies import is_staff_account

SESSION_ID_KEY = "_identity_sid"
CONTEXT_KEY = "_identity_context"
PENDING_KEY = "_identity_mfa_pending"


def register(request, user):
    record = UserSession.objects.create(
        account=user,
        last_seen_at=timezone.now(),
        ip=client_ip(request),
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:200],
    )
    request.session[SESSION_ID_KEY] = str(record.id)
    return record


def current(request):
    sid = request.session.get(SESSION_ID_KEY) if hasattr(request, "session") else None
    if not sid:
        return None
    try:
        return UserSession.objects.filter(pk=sid, revoked_at__isnull=True).first()
    except Exception:  # id malformato nella sessione
        return None


def timeouts(user):
    if is_staff_account(user):
        return (
            conf.get("SESSION_IDLE_TIMEOUT_STAFF"),
            conf.get("SESSION_ABSOLUTE_TIMEOUT_STAFF"),
        )
    return (
        conf.get("SESSION_IDLE_TIMEOUT_DEFAULT"),
        conf.get("SESSION_ABSOLUTE_TIMEOUT_DEFAULT"),
    )


def expired(record, user, now=None):
    now = now or timezone.now()
    idle, absolute = timeouts(user)
    return (idle and now - record.last_seen_at > timedelta(seconds=idle)) or (
        absolute and now - record.created_at > timedelta(seconds=absolute)
    )


def touch(record, now=None):
    now = now or timezone.now()
    interval = timedelta(seconds=conf.get("SESSION_TOUCH_INTERVAL_SECONDS"))
    if now - record.last_seen_at >= interval:
        UserSession.objects.filter(pk=record.pk).update(last_seen_at=now)
        record.last_seen_at = now


def revoke(record, reason):
    return UserSession.objects.filter(pk=record.pk, revoked_at__isnull=True).update(
        revoked_at=timezone.now(), revoked_reason=reason[:40]
    )


def revoke_all(user, reason, except_id=None):
    query = UserSession.objects.filter(account=user, revoked_at__isnull=True)
    if except_id:
        query = query.exclude(pk=except_id)
    return query.update(revoked_at=timezone.now(), revoked_reason=reason[:40])


def mark_mfa(request):
    record = current(request)
    if record is not None:
        now = timezone.now()
        UserSession.objects.filter(pk=record.pk).update(mfa_verified_at=now)
        record.mfa_verified_at = now
    return record
