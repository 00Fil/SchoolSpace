"""GAP-F02: provider email astratto, nessun invio reale, template italiani, T23."""

import io
import json
import smtplib
import socket
from urllib import error as urlerror

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.db import transaction

from apps.communications import providers
from apps.communications.checks import communications_config
from apps.communications.dispatch import process_delivery, reconcile_ambiguous
from apps.communications.models import Delivery, DeliveryAttempt, DeliveryStatus as S
from apps.communications.providers import (
    NOT_FOUND,
    Accepted,
    AmbiguousError,
    ApiBackend,
    OutgoingEmail,
    PermanentError,
    ResendBackend,
    SinkBackend,
    SmtpBackend,
    TransientError,
    build_mime,
    get_backend,
)
from apps.communications.rendering import italian_datetime, render_email
from apps.communications.services import Recipient, emit
from apps.identity.models import Account

PAYLOAD = {
    "lesson_id": "l-1",
    "version": 2,
    "subject_name": "Fisica",
    "mode": "ONLINE",
    "location": "REMOTE",
    "start_at": "2026-10-26T14:00:00+00:00",  # dopo il cambio d'ora: 15:00 a Roma
    "end_at": "2026-10-26T15:00:00+00:00",
    "previous_start_at": "2026-10-23T13:00:00+00:00",  # 15:00 ora legale
    "state": "PUBLISHED",
}
MESSAGE = OutgoingEmail(
    to="anna@example.invalid",
    subject="Prova",
    body="Testo",
    idempotency_key="delivery-1",
)


@pytest.fixture(autouse=True)
def sink():
    SinkBackend.reset()
    yield SinkBackend
    SinkBackend.reset()


@pytest.fixture
def user(db):
    return Account.objects.create_user(
        username="anna",
        email="anna@example.invalid",
        email_verified=True,
        password=None,
    )


def email_delivery(user, event_type="lesson.rescheduled", context=None, key="e-1"):
    with transaction.atomic():
        event = emit(
            event_type,
            PAYLOAD,
            [
                Recipient(
                    user, context or {"role": "guardian", "student_names": ["Sara"]}
                )
            ],
            idempotency_key=key,
            channels=("EMAIL",),
        )
    return Delivery.objects.get(event=event)


def production(settings, backend, **extra):
    settings.COMMUNICATIONS_ENV = "production"
    settings.COMMUNICATIONS_EMAIL = {
        **settings.COMMUNICATIONS_EMAIL,
        "BACKEND": backend,
        **extra,
    }


# --- selezione backend --------------------------------------------------------


def test_default_backend_is_sink():
    assert isinstance(get_backend(), SinkBackend)


@pytest.mark.parametrize("env", ["development", "test", "staging"])
@pytest.mark.parametrize("backend", ["smtp", "api"])
def test_real_backends_refused_outside_production(settings, env, backend):
    settings.COMMUNICATIONS_ENV = env
    settings.COMMUNICATIONS_EMAIL = {
        **settings.COMMUNICATIONS_EMAIL,
        "BACKEND": backend,
    }
    with pytest.raises(ImproperlyConfigured):
        get_backend()
    assert any(i.id == "communications.E002" for i in communications_config(None))


def test_production_selects_configured_backends(settings):
    production(settings, "smtp", SMTP_HOST="smtp.example.invalid")
    assert isinstance(get_backend(), SmtpBackend)
    production(
        settings, "api", API_URL="https://api.example.invalid/send", API_TOKEN="t"
    )
    assert isinstance(get_backend(), ApiBackend)
    production(settings, "api", API_URL="http://api.example.invalid", API_TOKEN="t")
    with pytest.raises(ImproperlyConfigured):
        get_backend()
    production(settings, "sink")
    assert any(i.id == "communications.W001" for i in communications_config(None))


def test_sink_is_idempotent_by_key(sink):
    first = SinkBackend().send(MESSAGE)
    assert SinkBackend().send(MESSAGE) == first and len(sink.messages) == 1
    assert SinkBackend().lookup("delivery-1") == first
    assert SinkBackend().lookup("other") == NOT_FOUND


# --- SMTP (smtplib simulato, nessuna connessione) -----------------------------


class FakeSMTP:
    behaviour = None
    sent = []

    def __init__(self, host, port, timeout):
        if FakeSMTP.behaviour == "connect":
            raise ConnectionRefusedError()

    def starttls(self, context):
        pass

    def login(self, user, password):
        pass

    def send_message(self, mime):
        b = FakeSMTP.behaviour
        if b == "refused":
            raise smtplib.SMTPRecipientsRefused({mime["To"]: (550, b"no")})
        if b == "busy":
            raise smtplib.SMTPDataError(451, b"try later")
        if b == "rejected":
            raise smtplib.SMTPDataError(554, b"rejected")
        if b == "lost":
            FakeSMTP.sent.append(mime)  # il server ha accettato, la risposta si perde
            raise smtplib.SMTPServerDisconnected()
        FakeSMTP.sent.append(mime)
        return {}

    def quit(self):
        pass


@pytest.mark.parametrize(
    "behaviour,error",
    [
        ("connect", TransientError),
        ("refused", PermanentError),
        ("busy", TransientError),
        ("rejected", PermanentError),
        ("lost", AmbiguousError),
        (None, None),
    ],
)
def test_smtp_error_mapping(settings, monkeypatch, behaviour, error):
    production(settings, "smtp", SMTP_HOST="smtp.example.invalid")
    monkeypatch.setattr(providers.smtplib, "SMTP", FakeSMTP)
    FakeSMTP.behaviour, FakeSMTP.sent = behaviour, []
    backend = get_backend()
    if error:
        with pytest.raises(error):
            backend.send(MESSAGE)
    else:
        result = backend.send(MESSAGE)
        assert result.provider_message_id == FakeSMTP.sent[0]["Message-ID"]


def test_mime_single_recipient_and_headers():
    mime = build_mime(MESSAGE, "Centro <no-reply@example.invalid>", "example.invalid")
    assert mime["To"] == "anna@example.invalid"
    assert mime["Cc"] is None and mime["Bcc"] is None
    assert "delivery-1" in mime["Message-ID"]
    assert mime["Auto-Submitted"] == "auto-generated"


# --- API HTTPS (urlopen simulato) ----------------------------------------------


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def http_error(code):
    return urlerror.HTTPError("https://api.example.invalid", code, "x", {}, None)


@pytest.mark.parametrize(
    "outcome,error",
    [
        (http_error(429), TransientError),
        (http_error(503), TransientError),
        (http_error(422), PermanentError),
        (urlerror.URLError(ConnectionRefusedError()), TransientError),
        (socket.timeout(), AmbiguousError),
        (urlerror.URLError(socket.timeout()), AmbiguousError),
    ],
)
def test_api_error_mapping(settings, monkeypatch, outcome, error):
    production(
        settings, "api", API_URL="https://api.example.invalid/send", API_TOKEN="t"
    )

    def urlopen(req, timeout):
        raise outcome

    monkeypatch.setattr(providers.urlrequest, "urlopen", urlopen)
    with pytest.raises(error):
        get_backend().send(MESSAGE)


def test_api_sends_idempotency_key_and_single_recipient(settings, monkeypatch):
    production(
        settings, "api", API_URL="https://api.example.invalid/send", API_TOKEN="t"
    )
    seen = {}

    def urlopen(req, timeout):
        seen["headers"] = dict(req.header_items())
        seen["body"] = json.loads(req.data)
        return Response(b'{"id": "prov-1"}')

    monkeypatch.setattr(providers.urlrequest, "urlopen", urlopen)
    assert get_backend().send(MESSAGE) == Accepted("prov-1")
    assert seen["headers"]["Idempotency-key"] == "delivery-1"
    assert seen["body"]["to"] == ["anna@example.invalid"]
    assert "cc" not in seen["body"] and "bcc" not in seen["body"]


def test_api_lookup(settings, monkeypatch):
    production(
        settings,
        "api",
        API_URL="https://api.example.invalid/send",
        API_STATUS_URL="https://api.example.invalid/messages/{key}",
        API_TOKEN="t",
    )
    responses = iter([Response(b'{"id": "prov-9"}'), http_error(404), http_error(500)])

    def urlopen(req, timeout):
        assert req.full_url.endswith("/messages/delivery-1")
        item = next(responses)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(providers.urlrequest, "urlopen", urlopen)
    backend = get_backend()
    assert backend.lookup("delivery-1") == Accepted("prov-9")
    assert backend.lookup("delivery-1") == NOT_FOUND
    assert backend.lookup("delivery-1") is None


# --- T23: provider accetta, risposta persa --------------------------------------


class LostResponseSink(SinkBackend):
    """Il messaggio entra nel sink (accettato) ma il worker riceve un timeout."""

    supports_idempotency = False

    def send(self, message):
        super().send(message)
        raise AmbiguousError("API_RESPONSE_LOST")


class NoLookup(LostResponseSink):
    def lookup(self, key):
        return None


def run_ambiguous(user, monkeypatch, backend_cls):
    monkeypatch.setattr(providers, "SinkBackend", backend_cls)
    monkeypatch.setattr(
        "apps.communications.dispatch.get_backend", lambda: backend_cls()
    )
    delivery = email_delivery(user)
    assert process_delivery(delivery.pk) == S.AMBIGUOUS
    Delivery.objects.filter(pk=delivery.pk).update(next_attempt_at=delivery.created_at)
    return delivery


def test_t23_ambiguous_reconciled_by_lookup_without_resend(user, monkeypatch, sink):
    delivery = run_ambiguous(user, monkeypatch, LostResponseSink)
    assert reconcile_ambiguous() == {S.SENT: 1}
    delivery.refresh_from_db()
    assert delivery.status == S.SENT and delivery.provider_message_id.startswith(
        "sink-"
    )
    assert len(sink.messages) == 1  # nessun secondo invio
    assert reconcile_ambiguous() == {}  # idempotente
    outcomes = list(delivery.attempt_log.values_list("outcome", flat=True))
    assert outcomes == ["AMBIGUOUS", "RECONCILED_SENT"]


def test_t23_unknown_outcome_goes_to_review_not_false_guarantee(
    user, monkeypatch, sink
):
    delivery = run_ambiguous(user, monkeypatch, NoLookup)
    assert reconcile_ambiguous() == {S.DEAD: 1}
    delivery.refresh_from_db()
    assert delivery.status == S.DEAD and delivery.last_error_code == "AMBIGUOUS_OUTCOME"
    assert len(sink.messages) == 1


def test_t23_retry_policy_is_explicit_at_least_once(user, monkeypatch, settings, sink):
    settings.COMMUNICATIONS_AMBIGUOUS_POLICY = "retry"
    delivery = run_ambiguous(user, monkeypatch, NoLookup)
    assert reconcile_ambiguous() == {S.PENDING: 1}
    assert DeliveryAttempt.objects.filter(
        delivery=delivery, error_code="RETRY_AFTER_AMBIGUOUS"
    ).exists()


def test_t23_not_found_is_safe_to_resend(user, monkeypatch, sink):
    class LostBeforeAccept(SinkBackend):
        calls = 0

        def send(self, message):
            LostBeforeAccept.calls += 1
            if LostBeforeAccept.calls == 1:
                raise AmbiguousError("API_RESPONSE_LOST")  # mai arrivato al provider
            return super().send(message)

    delivery = run_ambiguous(user, monkeypatch, LostBeforeAccept)
    assert reconcile_ambiguous() == {S.PENDING: 1}
    assert process_delivery(delivery.pk) == S.SENT
    assert len(sink.messages) == 1


# --- template italiani e minimizzazione -----------------------------------------


def test_italian_template_rome_time_no_link_no_other_names(user):
    delivery = email_delivery(user)
    subject, body = render_email(delivery.event, delivery)
    assert subject == "Lezione di Fisica spostata: lunedì 26 ottobre 2026, ore 15:00"
    assert "Prima: venerdì 23 ottobre 2026, ore 15:00" in body
    assert "per Sara" in body and "solo nel portale" in body
    assert "http" not in body and "@" not in body
    assert "non contiene dati di altri partecipanti" in body


def test_all_calendar_templates_render_in_italian(user):
    for n, kind in enumerate(("lesson.published", "lesson.cancelled", "other.event")):
        delivery = email_delivery(user, kind, key=f"t-{n}")
        subject, body = render_email(delivery.event, delivery)
        assert subject and "Gentile utente" in body and "{{" not in body
    assert italian_datetime("2026-03-29T00:30:00+00:00").startswith("domenica 29 marzo")


def test_email_through_sink_end_to_end(user, sink):
    delivery = email_delivery(user)
    assert process_delivery(delivery.pk) == S.SENT
    message = sink.messages[0]
    assert (
        message.to == user.email
        and message.idempotency_key == f"delivery-{delivery.pk}"
    )
    assert "Sara" in message.body


@pytest.mark.django_db
def test_dispatch_command_inline():
    out = io.StringIO()
    call_command("dispatch_communications", "--inline", stdout=out)
    assert json.loads(out.getvalue())["due"] == 0


# --- D08: Resend ------------------------------------------------------------------


def test_resend_selected_and_idempotent(settings, monkeypatch):
    production(settings, "resend", RESEND_API_KEY="re_test")
    backend = get_backend()
    assert isinstance(backend, ResendBackend) and backend.supports_idempotency
    seen = {}

    def urlopen(req, timeout):
        seen["url"] = req.full_url
        seen["headers"] = dict(req.header_items())
        seen["body"] = json.loads(req.data)
        return Response(b'{"id": "re-1"}')

    monkeypatch.setattr(providers.urlrequest, "urlopen", urlopen)
    assert backend.send(MESSAGE) == Accepted("re-1")
    assert seen["url"] == "https://api.resend.com/emails"
    assert seen["headers"]["Idempotency-key"] == "delivery-1"
    assert seen["headers"]["Authorization"] == "Bearer re_test"
    assert seen["body"]["to"] == ["anna@example.invalid"]
    assert "reference" not in seen["body"]
    assert backend.lookup("delivery-1") is None


@pytest.mark.parametrize(
    "outcome,error",
    [
        (http_error(409), TransientError),
        (http_error(429), TransientError),
        (http_error(500), TransientError),
        (http_error(422), PermanentError),
        (http_error(403), PermanentError),
        (socket.timeout(), AmbiguousError),
    ],
)
def test_resend_error_mapping(settings, monkeypatch, outcome, error):
    production(settings, "resend", RESEND_API_KEY="re_test")

    def urlopen(req, timeout):
        raise outcome

    monkeypatch.setattr(providers.urlrequest, "urlopen", urlopen)
    with pytest.raises(error):
        get_backend().send(MESSAGE)


def test_resend_requires_key(settings):
    production(settings, "resend", RESEND_API_KEY="", API_TOKEN="")
    with pytest.raises(ImproperlyConfigured):
        get_backend()
