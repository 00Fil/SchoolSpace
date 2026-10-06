"""Portali v2 (s6-frontend): endpoint di sola lettura per famiglie, studenti e tutor.

Nessuna scrittura: le azioni usano gli endpoint esistenti (``/availability-rules/``,
``/change-requests/``, ``/occurrences/{id}/attendance/``). Lo scope riusa le policy di
``apps.identity.policies`` (deleghe verificate, contesto attivo, maggiore età) e quindi
cambia subito quando il centro revoca una delega. Fuori scope → 404 senza enumerazione.

Decisioni aperte (da approvare, D07): ``PORTAL_STUDENT_CAN_REQUEST_CHANGES`` (default
``False``) stabilisce se uno studente può chiedere cambi o segnalare assenze dal portale.
"""

from datetime import datetime, time, timedelta

from django.conf import settings
from config import features
from django.db.models import Count, F, Q
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import api_view
from rest_framework.pagination import CursorPagination
from rest_framework.response import Response

from apps.availability.models import AvailabilityException, AvailabilityRule
from apps.education.models import Tutor
from apps.identity.policies import (
    active_guardian_links,
    active_roles,
    can_manage_student_availability,
    can_request_student_changes,
    is_center,
    selected_context,
    visible_students,
)
from domain.intervals import local_to_utc

ZONE_NAME = "Europe/Rome"
ATTENDANCE_LOOKBACK_DAYS = 14
RULE_KEYS = {"APPROVED": "approved", "DRAFT": "draft", "REVOKED": "revoked"}


def current_time():
    """Punto unico per l'orologio (sostituibile nei test)."""
    return timezone.now()


def calendar_enabled():
    return features.calendar_enabled()


def student_can_request_changes():
    """D07 da approvare: default prudenziale = lo studente non invia richieste."""
    return bool(getattr(settings, "PORTAL_STUDENT_CAN_REQUEST_CHANGES", False))


def _week(request):
    raw = request.query_params.get("week")
    if raw:
        try:
            day = datetime.strptime(raw, "%Y-%m-%d").date()
        except ValueError:
            raise serializers.ValidationError({"week": "Data AAAA-MM-GG"})
    else:
        day = timezone.localtime(current_time()).date()
    monday = day - timedelta(days=day.weekday())
    return monday, monday + timedelta(days=7)


def _bounds(first, last):
    return (
        local_to_utc(datetime.combine(first, time.min)),
        local_to_utc(datetime.combine(last, time.min)),
    )


def _minutes(lesson):
    return int((lesson.end_at - lesson.start_at).total_seconds() // 60)


def _availability_counts(lookup, now):
    counts = {"approved": 0, "draft": 0, "revoked": 0}
    for status in AvailabilityRule.objects.filter(**lookup).values_list(
        "status", flat=True
    ):
        counts[RULE_KEYS[status]] += 1
    counts["exceptions_upcoming"] = AvailabilityException.objects.filter(
        **lookup, end_at__gt=now
    ).count()
    return counts


def _link_detail(link):
    detail = getattr(link, "detail", None) if link is not None else None
    return {
        "can_receive_notifications": bool(
            getattr(detail, "can_receive_notifications", True)
        ),
        "reconfirmation": getattr(detail, "reconfirmation", None) or None,
    }


def _student_week(student, first, last, now):
    from apps.calendar.models import LessonOccurrence

    start, end = _bounds(first, last)
    rows = list(
        LessonOccurrence.objects.filter(
            participants__student=student,
            start_at__lt=end,
            end_at__gt=start,
            state__in=("PUBLISHED", "CANCELLED", "COMPLETED"),
        ).distinct()
    )
    active = [r for r in rows if r.state != "CANCELLED"]
    upcoming = sorted(r.start_at for r in active if r.end_at > now)
    return {
        "lessons": len(active),
        "cancelled": len(rows) - len(active),
        "minutes": sum(_minutes(r) for r in active),
        "next_lesson_at": upcoming[0].isoformat() if upcoming else None,
    }


def _open_requests(user, student=None):
    if not calendar_enabled():
        return 0
    from apps.calendar.models import ChangeRequest

    rows = ChangeRequest.objects.filter(requested_by=user, state="SUBMITTED")
    if student is not None:
        rows = rows.filter(student=student)
    return rows.count()


def _children(user, first, last, now):
    roles = active_roles(user)
    links = {}
    if "GUARDIAN" in roles:
        for link in (
            active_guardian_links(now, can_view=True)
            .filter(account=user)
            .select_related("detail")
        ):
            links.setdefault(link.student_id, link)
    out = []
    for student in visible_students(user).order_by("display_name", "id"):
        own = student.account_id == user.id and "STUDENT" in roles
        detail = _link_detail(links.get(student.id))
        if own:
            can_request, can_manage = student_can_request_changes(), False
        else:
            can_request = can_request_student_changes(user, student)
            can_manage = can_manage_student_availability(user, student)
        out.append(
            {
                "student_id": str(student.id),
                "display_name": student.display_name,
                "level": student.level,
                "relation": "SELF" if own else "GUARDIAN",
                "permissions": {
                    "can_view": True,
                    "can_manage_availability": can_manage,
                    "can_request_changes": can_request,
                    "can_receive_notifications": detail["can_receive_notifications"],
                },
                "read_only": not (can_manage or can_request),
                "reconfirmation": detail["reconfirmation"],
                "availability": _availability_counts({"student": student}, now),
                "week": _student_week(student, first, last, now)
                if calendar_enabled()
                else None,
                "open_change_requests": _open_requests(user, student),
            }
        )
    return out


def _pending_attendance(tutor, now):
    """Lezioni concluse del tutor, ancora attive, con almeno un partecipante senza presenza."""
    from apps.calendar.models import LessonOccurrence

    return (
        LessonOccurrence.objects.filter(
            tutor=tutor,
            state="PUBLISHED",
            end_at__lte=now,
            end_at__gt=now - timedelta(days=ATTENDANCE_LOOKBACK_DAYS),
        )
        .annotate(
            people=Count("participants", distinct=True),
            recorded=Count(
                "attendances",
                filter=~Q(attendances__status="NOT_RECORDED"),
                distinct=True,
            ),
        )
        .filter(recorded__lt=F("people"))
        .order_by("start_at", "id")
    )


def _tutor_week(tutor, first, last, now):
    from apps.calendar.models import LessonOccurrence

    start, end = _bounds(first, last)
    rows = LessonOccurrence.objects.filter(
        tutor=tutor, start_at__lt=end, end_at__gt=start
    ).order_by("start_at", "id")
    by_day = {first + timedelta(days=i): 0 for i in range(7)}
    scheduled = completed = cancelled = lessons = 0
    for row in rows:
        minutes = _minutes(row)
        if row.state == "CANCELLED":
            cancelled += minutes
            continue
        lessons += 1
        scheduled += minutes
        if row.state == "COMPLETED":
            completed += minutes
        day = timezone.localtime(row.start_at).date()
        if day in by_day:
            by_day[day] += minutes
    return {
        "lessons": lessons,
        "scheduled_minutes": scheduled,
        "completed_minutes": completed,
        "cancelled_minutes": cancelled,
        "by_day": [{"date": d.isoformat(), "minutes": m} for d, m in by_day.items()],
        "attendance_pending": _pending_attendance(tutor, now).count(),
    }


def _own_tutor(user):
    if "TUTOR" not in active_roles(user):
        return None
    return Tutor.objects.filter(account=user).first()


def _tutor_block(user, first, last, now):
    tutor = _own_tutor(user)
    if tutor is None:
        return None
    from apps.scheduling.models import TutorOperatingPolicy

    policy = TutorOperatingPolicy.objects.filter(tutor=tutor).first()
    return {
        "tutor_id": str(tutor.id),
        "display_name": tutor.display_name,
        "limits": {
            "daily_limit_minutes": policy.daily_limit_minutes,
            "weekly_limit_minutes": policy.weekly_limit_minutes,
            "pause_minutes": policy.pause_minutes,
        }
        if policy
        else None,
        "availability": _availability_counts({"tutor": tutor}, now),
        "week": _tutor_week(tutor, first, last, now) if calendar_enabled() else None,
    }


@api_view(["GET"])
def overview(request):
    """Riepilogo del portale per il contesto attivo (multi-figlio, studente, tutor)."""
    user = request.user
    first, last = _week(request)
    now = current_time()
    center = is_center(user)
    roles = sorted(active_roles(user) | ({"CENTER"} if center else set()))
    return Response(
        {
            "context": selected_context(user)
            or ("CENTER" if center else (roles[0] if len(roles) == 1 else None)),
            "roles": roles,
            "week": {"from": first.isoformat(), "until": last.isoformat()},
            "timezone": ZONE_NAME,
            "calendar_enabled": calendar_enabled(),
            "children": [] if center else _children(user, first, last, now),
            "tutor": None if center else _tutor_block(user, first, last, now),
            "open_change_requests": _open_requests(user),
            "policies": {
                "student_can_request_changes": student_can_request_changes(),
                "decision": "D07",
                "status": "DA_APPROVARE",
            },
            "generated_at": now.isoformat(),
        }
    )


class StartCursor(CursorPagination):
    """Cursore opaco su (start_at, id): stabile anche con inserimenti concorrenti."""

    page_size = 20
    max_page_size = 50
    page_size_query_param = "page_size"
    ordering = ("start_at", "id")


def _subject_lookup(request):
    """Soggetto dell'elenco: studente visibile o tutor proprio (centro: chiunque)."""
    params = request.query_params
    if bool(params.get("student")) == bool(params.get("tutor")):
        raise serializers.ValidationError(
            {"subject": "Indicare esattamente uno tra student e tutor"}
        )
    try:
        pk = serializers.UUIDField().run_validation(
            params.get("student") or params.get("tutor")
        )
    except serializers.ValidationError:
        return None
    user = request.user
    if params.get("student"):
        student = visible_students(user).filter(pk=pk).first()
        return {"student_id": student.pk} if student else None
    tutor = Tutor.objects.filter(pk=pk).first()
    if tutor is None:
        return None
    own = _own_tutor(user)
    if is_center(user) or (own is not None and own.pk == tutor.pk):
        return {"tutor_id": tutor.pk}
    return None


@api_view(["GET"])
def availability_exceptions(request):
    """Eccezioni (aggiunte/rimozioni puntuali) del soggetto, a cursore per ``start_at``."""
    lookup = _subject_lookup(request)
    if lookup is None:
        return Response({"code": "NOT_FOUND"}, status=404)
    rows = AvailabilityException.objects.filter(**lookup)
    if request.query_params.get("past") != "1":
        rows = rows.filter(end_at__gt=current_time())
    paginator = StartCursor()
    page = paginator.paginate_queryset(rows, request)
    return paginator.get_paginated_response(
        [
            {
                "id": str(e.id),
                "kind": e.kind,
                "mode": e.mode,
                "location": e.location,
                "start_at": e.start_at.isoformat(),
                "end_at": e.end_at.isoformat(),
            }
            for e in page
        ]
    )


@api_view(["GET"])
def attendance_pending(request):
    """Lezioni concluse del tutor senza presenze complete (ultimi 14 giorni)."""
    if not calendar_enabled():
        return Response({"code": features.DISABLED_CODE}, status=503)
    tutor = _own_tutor(request.user)
    if tutor is None:
        return Response({"code": "NOT_FOUND"}, status=404)
    rows = _pending_attendance(tutor, current_time()).select_related("subject")
    paginator = StartCursor()
    page = paginator.paginate_queryset(rows, request)
    out = [
        {
            "lesson_id": str(lesson.id),
            "version": lesson.version,
            "start_at": lesson.start_at.isoformat(),
            "end_at": lesson.end_at.isoformat(),
            "subject_name": lesson.subject.name,
            "participants": [
                {"student_id": str(p.student_id), "name": p.student.display_name}
                for p in lesson.participants.select_related("student").order_by(
                    "student_id"
                )
            ],
        }
        for lesson in page
    ]
    return paginator.get_paginated_response(out)


def urlpatterns():
    from django.urls import path

    return [
        path("api/v1/portal/overview", overview),
        path("api/v1/portal/availability-exceptions", availability_exceptions),
        path("api/v1/portal/attendance-pending", attendance_pending),
    ]
