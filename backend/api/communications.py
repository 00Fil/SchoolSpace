"""API comunicazioni: notifiche interne, preferenze, feed ICS, link video, stato outbox."""

from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Count, Min
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
    throttle_classes,
)
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle

from apps.calendar.models import LessonOccurrence
from apps.communications.dispatch import resolve_delivery
from apps.communications.feeds import (
    build_ics,
    create_feed_token,
    meeting_link_for,
    meeting_window,
    resolve_feed_token,
)
from apps.calendar.scope import lesson_relation
from apps.communications import video
from apps.communications.models import (
    MeetingPresence,
    CalendarFeedToken,
    Category,
    Channel,
    Delivery,
    DeliveryStatus,
    Notification,
)
from apps.communications.services import preferences_for, set_preference, MANDATORY
from apps.identity.policies import is_center
from .calendar import lesson_scope
from apps.reasons import ReasonField, reason_or_default  # noqa: F401


def now():
    return timezone.now()


NO_STORE = {"Cache-Control": "no-store", "Pragma": "no-cache"}


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = [
            "id",
            "kind",
            "category",
            "title",
            "body",
            "subject_ref",
            "created_at",
            "read_at",
        ]


class NotificationPagination(PageNumberPagination):
    page_size = 50

    def get_paginated_response(self, data):
        response = super().get_paginated_response(data)
        response.data["unread_count"] = self.unread
        response.data["pending_email_deliveries"] = self.pending
        return response


@api_view(["GET"])
def notifications(request):
    rows = Notification.objects.filter(recipient=request.user).order_by(
        "-created_at", "id"
    )
    unread = request.query_params.get("unread")
    if unread not in (None, "", "0", "1"):
        raise serializers.ValidationError({"unread": "Valori ammessi: 0 o 1"})
    if unread == "1":
        rows = rows.filter(read_at__isnull=True)
    category = request.query_params.get("category")
    if category:
        if category not in Category.values:
            raise serializers.ValidationError({"category": "Categoria non valida"})
        rows = rows.filter(category=category)
    paginator = NotificationPagination()
    paginator.unread = Notification.objects.filter(
        recipient=request.user, read_at__isnull=True
    ).count()
    paginator.pending = Delivery.objects.filter(
        recipient=request.user,
        channel=Channel.EMAIL,
        status__in=[
            DeliveryStatus.PENDING,
            DeliveryStatus.SENDING,
            DeliveryStatus.AMBIGUOUS,
        ],
    ).count()
    page = paginator.paginate_queryset(rows, request)
    return paginator.get_paginated_response(
        NotificationSerializer(page, many=True).data
    )


@api_view(["POST"])
def notification_read(request, pk):
    note = Notification.objects.filter(pk=pk, recipient=request.user).first()
    if not note:
        raise NotFound()
    if note.read_at is None:
        Notification.objects.filter(pk=pk, read_at__isnull=True).update(
            read_at=timezone.now()
        )
        note.refresh_from_db()
    return Response(NotificationSerializer(note).data)


@api_view(["POST"])
def notifications_read_all(request):
    count = Notification.objects.filter(
        recipient=request.user, read_at__isnull=True
    ).update(read_at=timezone.now())
    return Response({"marked_read": count})


class PreferenceItem(serializers.Serializer):
    category = serializers.ChoiceField(choices=Category.values)
    channel = serializers.ChoiceField(choices=Channel.values)
    enabled = serializers.BooleanField()

    def to_internal_value(self, data):
        if not isinstance(data, dict) or set(data) != {
            "category",
            "channel",
            "enabled",
        }:
            raise serializers.ValidationError(
                "Campi richiesti: category, channel, enabled"
            )
        if type(data.get("enabled")) is not bool:
            raise serializers.ValidationError({"enabled": "Booleano JSON richiesto"})
        return super().to_internal_value(data)


def _preferences(user):
    prefs = preferences_for(user)
    return {
        "preferences": [
            {
                "category": category,
                "channel": channel,
                "enabled": enabled,
                "mandatory": (category, channel) in MANDATORY,
                "available": category != Category.MARKETING
                or settings.COMMUNICATIONS_MARKETING_ENABLED,
            }
            for (category, channel), enabled in sorted(prefs.items())
        ]
    }


@api_view(["GET", "PUT"])
def notification_preferences(request):
    if request.method == "PUT":
        items = PreferenceItem(
            data=request.data.get("preferences")
            if isinstance(request.data, dict)
            else None,
            many=True,
        )
        items.is_valid(raise_exception=True)
        with transaction.atomic():
            for item in items.validated_data:
                try:
                    set_preference(
                        request.user, item["category"], item["channel"], item["enabled"]
                    )
                except ValueError as error:
                    transaction.set_rollback(True)
                    return Response(
                        {"code": "PREFERENCE_MANDATORY", "message": str(error)},
                        status=422,
                    )
    return Response(_preferences(request.user))


class FeedTokenSerializer(serializers.ModelSerializer):
    class Meta:
        model = CalendarFeedToken
        fields = [
            "id",
            "label",
            "created_at",
            "expires_at",
            "revoked_at",
            "last_used_at",
        ]


@api_view(["GET", "POST"])
def feed_tokens(request):
    if request.method == "POST":
        label = request.data.get("label", "") if isinstance(request.data, dict) else ""
        if not isinstance(label, str) or len(label) > 60:
            raise serializers.ValidationError(
                {"label": "Testo di al massimo 60 caratteri"}
            )
        try:
            record, raw = create_feed_token(request.user, label.strip())
        except ValueError as error:
            return Response({"code": "TOKEN_LIMIT", "message": str(error)}, status=409)
        data = FeedTokenSerializer(record).data
        # Il token in chiaro è mostrato una sola volta e mai salvato.
        data["token"] = raw
        data["feed_path"] = f"/api/v1/calendar.ics?token={raw}"
        return Response(data, status=201, headers=NO_STORE)
    rows = CalendarFeedToken.objects.filter(account=request.user).order_by(
        "-created_at"
    )
    return Response({"results": FeedTokenSerializer(rows, many=True).data})


@api_view(["POST"])
def feed_token_revoke(request, pk):
    record = CalendarFeedToken.objects.filter(pk=pk, account=request.user).first()
    if not record:
        raise NotFound()
    if record.revoked_at is None:
        CalendarFeedToken.objects.filter(pk=pk, revoked_at__isnull=True).update(
            revoked_at=timezone.now()
        )
        record.refresh_from_db()
    return Response(FeedTokenSerializer(record).data)


class FeedThrottle(AnonRateThrottle):
    scope = "anon"


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
@throttle_classes([FeedThrottle])
def calendar_ics(request):
    """Export personale minimizzato: perimetro ricalcolato a ogni richiesta (revoche)."""
    record = resolve_feed_token(request.query_params.get("token", ""))
    if not record:
        raise NotFound()
    scope, _students, _everyone = lesson_scope(record.account)
    current = now()
    rows = (
        LessonOccurrence.objects.filter(scope)
        .filter(
            start_at__lt=current
            + timedelta(days=settings.COMMUNICATIONS_ICS_FUTURE_DAYS),
            end_at__gt=current - timedelta(days=settings.COMMUNICATIONS_ICS_PAST_DAYS),
            state__in=("PUBLISHED", "CANCELLED"),
        )
        .select_related("subject")
        .distinct()
        .order_by("start_at", "id")[:500]
    )
    response = HttpResponse(
        build_ics(rows, current), content_type="text/calendar; charset=utf-8"
    )
    response["Cache-Control"] = "private, no-store"
    response["X-Robots-Tag"] = "noindex"
    response["Referrer-Policy"] = "no-referrer"
    response["Content-Disposition"] = 'inline; filename="lezioni.ics"'
    return response


@api_view(["GET"])
def meeting(request, pk):
    """Link video solo a chi partecipa (o al centro), solo nella finestra della lezione."""
    scope, _students, everyone = lesson_scope(request.user)
    lesson = LessonOccurrence.objects.filter(scope).filter(pk=pk).distinct().first()
    if not lesson:
        raise NotFound()  # nessuna distinzione tra inesistente e fuori perimetro
    if lesson.state != "PUBLISHED" or lesson.mode != "ONLINE":
        return Response(
            {
                "code": "MEETING_NOT_AVAILABLE",
                "message": "Lezione non online o non attiva",
            },
            status=409,
            headers=NO_STORE,
        )
    opens, closes = meeting_window(lesson)
    if not everyone and not opens <= now() < closes:
        return Response(
            {
                "code": "MEETING_NOT_OPEN",
                "message": "Il link è disponibile solo poco prima e durante la lezione",
                "opens_at": opens.isoformat(),
                "closes_at": closes.isoformat(),
            },
            status=403,
            headers=NO_STORE,
        )
    base = {"lesson_id": str(lesson.id), "version": lesson.version}
    link = meeting_link_for(lesson)
    if link:  # link manuale (piattaforma esterna): ha la precedenza
        return Response(
            {**base, "join_url": link.join_url, "expires_at": closes.isoformat()},
            headers={**NO_STORE, "Referrer-Policy": "no-referrer"},
        )
    if video.enabled():  # v0.10: stanza Jitsi automatica, nessun link da configurare
        relation, students = lesson_relation(request.user, lesson)
        if relation is None:
            raise NotFound()
        current = now()
        expires = closes + timedelta(minutes=settings.VIDEO_GRACE_MINUTES)
        session = video.session_for(
            lesson,
            request.user,
            relation,
            students or set(),
            not_before=min(opens, current),
            expires=max(expires, current + timedelta(minutes=30)) if everyone else expires,
        )
        return Response(
            {**base, **session, "expires_at": closes.isoformat()},
            headers={**NO_STORE, "Referrer-Policy": "no-referrer"},
        )
    return Response(
        {
            "code": "MEETING_NOT_CONFIGURED",
            "message": "Link non ancora configurato dal centro",
        },
        status=409,
        headers=NO_STORE,
    )


class PresenceCmd(serializers.Serializer):
    event = serializers.ChoiceField(choices=["join", "heartbeat", "leave"])


# Un heartbeat ogni 60 s dal client: oltre 3 minuti di silenzio non si conta (scheda chiusa).
PRESENCE_MAX_GAP = timedelta(minutes=3)


@api_view(["GET", "POST"])
def meeting_presence(request, pk):
    """v0.10 · Presenza nella videolezione integrata.

    POST (partecipanti, tutor, centro): ``join`` / ``heartbeat`` / ``leave`` dal client
    mentre la stanza è aperta, solo nella finestra della lezione.
    GET (tutor della lezione o centro): minuti per studente, per precompilare le presenze.
    """
    scope, _students, _everyone = lesson_scope(request.user)
    lesson = (
        LessonOccurrence.objects.filter(scope)
        .filter(pk=pk)
        .select_related("tutor")
        .distinct()
        .first()
    )
    if not lesson:
        raise NotFound()
    relation, students = lesson_relation(request.user, lesson)
    if relation is None:
        raise NotFound()
    if request.method == "GET":
        if relation not in ("CENTER", "TUTOR"):
            raise PermissionDenied()
        return Response(presence_summary(lesson), headers=NO_STORE)
    body = PresenceCmd(data=request.data)
    body.is_valid(raise_exception=True)
    if lesson.state != "PUBLISHED" or lesson.mode != "ONLINE":
        return Response({"code": "MEETING_NOT_AVAILABLE"}, status=409)
    opens, closes = meeting_window(lesson)
    current = now()
    grace = timedelta(minutes=settings.VIDEO_GRACE_MINUTES)
    if not opens <= current < closes + grace:
        return Response({"code": "MEETING_NOT_OPEN"}, status=403)
    with transaction.atomic():
        row = (
            MeetingPresence.objects.select_for_update()
            .filter(lesson=lesson, account=request.user)
            .first()
        )
        if row is None:
            row = MeetingPresence.objects.create(
                lesson=lesson,
                account=request.user,
                relation=relation,
                student_ids=sorted(str(s) for s in (students or ())),
                first_joined_at=current,
                last_seen_at=current,
            )
        else:
            gap = current - row.last_seen_at
            if row.left_at is None and timedelta(0) < gap <= PRESENCE_MAX_GAP:
                # Si conta solo il tempo dentro l'orario della lezione.
                start = max(row.last_seen_at, lesson.start_at)
                end = min(current, lesson.end_at)
                if end > start:
                    row.seconds += int((end - start).total_seconds())
            row.last_seen_at = current
            row.left_at = current if body.validated_data["event"] == "leave" else None
            row.save(update_fields=["seconds", "last_seen_at", "left_at"])
    return Response({"ok": True, "seconds": row.seconds}, headers=NO_STORE)


def presence_summary(lesson):
    participants = list(
        lesson.participants.select_related("student").order_by("student__display_name")
    )
    rows = list(MeetingPresence.objects.filter(lesson=lesson))
    per_student = {}
    tutor_seconds = 0
    for row in rows:
        if row.relation == "TUTOR":
            tutor_seconds = max(tutor_seconds, row.seconds)
        for sid in row.student_ids:
            per_student[sid] = max(per_student.get(sid, 0), row.seconds)
    return {
        "lesson_id": str(lesson.id),
        "lesson_minutes": int((lesson.end_at - lesson.start_at).total_seconds() // 60),
        "tutor_minutes": tutor_seconds // 60,
        "students": [
            {
                "student_id": str(p.student_id),
                "name": p.student.display_name,
                "joined": str(p.student_id) in per_student,
                "minutes": per_student.get(str(p.student_id), 0) // 60,
            }
            for p in participants
        ],
    }


@api_view(["GET"])
def communications_status(request):
    """Stato aggregato dell'outbox per il centro: nessun destinatario esposto."""
    if not is_center(request.user):
        raise PermissionDenied()
    counts = {}
    for row in Delivery.objects.values("channel", "status").annotate(n=Count("id")):
        counts.setdefault(row["channel"], {})[row["status"]] = row["n"]
    oldest = Delivery.objects.filter(status=DeliveryStatus.PENDING).aggregate(
        m=Min("created_at")
    )["m"]
    return Response(
        {
            "counts": counts,
            "oldest_pending_seconds": int((timezone.now() - oldest).total_seconds())
            if oldest
            else None,
            "dead_letter": Delivery.objects.filter(status=DeliveryStatus.DEAD).count(),
            "ambiguous": Delivery.objects.filter(
                status=DeliveryStatus.AMBIGUOUS
            ).count(),
            "email_backend": settings.COMMUNICATIONS_EMAIL["BACKEND"],
            "environment": settings.COMMUNICATIONS_ENV,
        }
    )


class ResolveCommand(serializers.Serializer):
    resolution = serializers.ChoiceField(choices=["MARK_SENT", "RETRY", "ABANDON"])
    reason = ReasonField()


@api_view(["POST"])
def delivery_resolve(request, pk):
    if not is_center(request.user):
        raise PermissionDenied()
    get_object_or_404(Delivery, pk=pk)
    command = ResolveCommand(data=request.data)
    command.is_valid(raise_exception=True)
    try:
        delivery = resolve_delivery(
            pk,
            request.user,
            command.validated_data["resolution"],
            command.validated_data["reason"],
        )
    except ValueError as error:
        return Response(
            {"code": "DELIVERY_NOT_RESOLVABLE", "message": str(error)}, status=409
        )
    return Response(
        {
            "id": str(delivery.id),
            "status": delivery.status,
            "attempts": delivery.attempts,
        }
    )


@api_view(["GET"])
def deliveries_problems(request):
    """P4: invii da controllare (falliti o incerti) per il pannello del centro, senza destinatari."""
    if not is_center(request.user):
        raise PermissionDenied()
    wanted = [x for x in request.query_params.get("status", "DEAD,AMBIGUOUS").split(",") if x in DeliveryStatus.values]
    rows = (
        Delivery.objects.filter(status__in=wanted)
        .select_related("event")
        .order_by("-created_at")[:100]
    )
    return Response(
        {
            "results": [
                {
                    "id": str(r.id),
                    "channel": r.channel,
                    "status": r.status,
                    "attempts": r.attempts,
                    "error": r.last_error_code,
                    "event_type": r.event.event_type,
                    "created_at": r.created_at.isoformat(),
                }
                for r in rows
            ],
            "next": None,
        }
    )
