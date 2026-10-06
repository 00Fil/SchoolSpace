"""Inviti e reset di s1 consegnati via outbox: token mai in chiaro a riposo, nei log o
nell'audit; ricontrollo all'invio (reinvio, revoca, uso) e segreti effimeri."""

import json
import logging
import re

import pytest
from cryptography.fernet import Fernet
from django.core import mail
from django.core.cache import cache
from django.db import connection, transaction

from apps.communications.dispatch import process_delivery, reconcile
from apps.communications.models import (
    ChannelPreference,
    Delivery,
    DeliveryStatus as S,
    OutboxEvent,
    SealedSecret,
)
from apps.communications.providers import SinkBackend
from apps.communications.sealing import seal, unseal
from apps.communications.services import Recipient, emit
from apps.identity.models import Invitation, PasswordResetToken
from apps.identity.tokens import hash_token
from tests.identity_helpers import Api, Clock, enroll_staff, make_account

pytestmark = pytest.mark.django_db(transaction=True)
NEW_PW = "Password-Nuova-Sintetica-9"
TOKEN_RE = re.compile(r"#token=([A-Za-z0-9_\-]+)")


@pytest.fixture(autouse=True)
def clean():
    cache.clear()
    SinkBackend.reset()
    yield
    SinkBackend.reset()
    cache.clear()


@pytest.fixture
def center(monkeypatch):
    clock = Clock(monkeypatch)
    make_account("centro@example.invalid", roles=["CENTER"])
    api = Api()
    enroll_staff(api, clock, "centro@example.invalid")
    return api


def pending(kind):
    return list(
        Delivery.objects.filter(event__event_type=kind, status=S.PENDING).order_by(
            "created_at"
        )
    )


def tokens_in_sink():
    return [TOKEN_RE.search(m.body).group(1) for m in SinkBackend.messages]


def dump_database():
    """Testo di tutte le tabelle: il token non deve comparire da nessuna parte."""
    parts = []
    with connection.cursor() as cursor:
        for table in connection.introspection.table_names():
            cursor.execute(f'SELECT * FROM "{table}"')
            parts.extend(json.dumps(row, default=str) for row in cursor.fetchall())
    return "\n".join(parts)


def test_invitation_via_outbox_token_only_in_email_body(center, caplog):
    caplog.set_level(logging.DEBUG)
    response = center.post(
        "/api/v1/invitations", {"email": "tutor@example.invalid", "role": "TUTOR"}
    )
    assert response.status_code == 201
    assert mail.outbox == []  # nessun invio sincrono: solo outbox
    event = OutboxEvent.objects.get(event_type="identity.invitation")
    invitation = Invitation.objects.get()
    assert event.payload["invitation_id"] == str(invitation.id) and event.essential
    [delivery] = pending("identity.invitation")
    assert delivery.recipient is None and delivery.address == "tutor@example.invalid"
    assert SealedSecret.objects.filter(delivery=delivery).exists()
    snapshot_before_send = dump_database()
    assert process_delivery(delivery.pk) == S.SENT
    [token] = tokens_in_sink()
    assert invitation.token_hash == hash_token(token)
    # Il chiaro non è mai stato a riposo nel DB (né payload, né audit, né ciphertext)…
    assert token not in snapshot_before_send
    # …e dopo l'invio non resta neppure il segreto cifrato.
    assert not SealedSecret.objects.exists()
    assert token not in dump_database()
    assert token not in caplog.text
    message = SinkBackend.messages[0]
    assert message.to == "tutor@example.invalid" and "72 ore" in message.body
    assert "Messaggio di sicurezza" in message.body
    accepted = Api().post(
        "/api/v1/invitations/accept", {"token": token, "password": NEW_PW}
    )
    assert accepted.status_code == 201


def test_resend_revokes_previous_pending_delivery(center):
    row = center.post(
        "/api/v1/invitations", {"email": "t@example.invalid", "role": "TUTOR"}
    ).json()
    center.post(f"/api/v1/invitations/{row['id']}/resend")
    first, second = pending("identity.invitation")
    # Il primo invio arriva dopo il reinvio: token sostituito, nessun link morto.
    assert process_delivery(first.pk) == S.REVOKED
    assert process_delivery(second.pk) == S.SENT
    first.refresh_from_db()
    assert first.last_error_code == "RECIPIENT_NOT_AUTHORIZED"
    assert first.attempt_log.filter(outcome="REVOKED").exists()
    assert len(SinkBackend.messages) == 1
    assert not SealedSecret.objects.exists()


def test_revoked_invitation_not_sent(center):
    row = center.post(
        "/api/v1/invitations", {"email": "r@example.invalid", "role": "TUTOR"}
    ).json()
    center.post(f"/api/v1/invitations/{row['id']}/revoke")
    assert reconcile(inline=True)["dispatched"] >= 1
    assert Delivery.objects.get(event__event_type="identity.invitation").status == (
        S.REVOKED
    )
    assert SinkBackend.messages == []


def test_password_reset_via_outbox_and_superseded_request(center):
    user = make_account("f@example.invalid", roles=["GUARDIAN"])
    ChannelPreference.objects.create(
        account=user, category="SERVICE", channel="EMAIL", enabled=False
    )
    api = Api()
    assert (
        api.post("/api/v1/auth/password-reset", {"email": user.email}).status_code
        == 202
    )
    cache.clear()
    assert (
        api.post("/api/v1/auth/password-reset", {"email": user.email}).status_code
        == 202
    )
    first, second = pending("identity.password_reset")
    assert process_delivery(first.pk) == S.REVOKED  # richiesta superata
    # Messaggio di sicurezza: le preferenze email non lo sopprimono.
    assert process_delivery(second.pk) == S.SENT
    [token] = tokens_in_sink()
    assert PasswordResetToken.objects.get(used_at__isnull=True).token_hash == (
        hash_token(token)
    )
    done = api.post(
        "/api/v1/auth/password-reset/confirm", {"token": token, "password": NEW_PW}
    )
    assert done.status_code == 200
    assert token not in dump_database()


def test_unknown_account_reset_creates_nothing():
    Api().post("/api/v1/auth/password-reset", {"email": "nessuno@example.invalid"})
    assert OutboxEvent.objects.count() == 0


def test_missing_or_expired_secret_is_explicit_expired_state(center):
    center.post("/api/v1/invitations", {"email": "e@example.invalid", "role": "TUTOR"})
    [delivery] = pending("identity.invitation")
    SealedSecret.objects.filter(delivery=delivery).delete()
    assert process_delivery(delivery.pk) == S.EXPIRED
    delivery.refresh_from_db()
    assert delivery.last_error_code == "SECRET_EXPIRED"
    assert SinkBackend.messages == []


def test_secret_never_accepted_in_payload_or_in_app():
    user = make_account("p@example.invalid")
    with pytest.raises(Exception), transaction.atomic():
        emit("identity.invitation", {"token": "x"}, [user], idempotency_key="a")
    with pytest.raises(ValueError), transaction.atomic():
        emit(
            "identity.invitation",
            {"x": 1},
            [user],
            idempotency_key="b",
            secrets={"token": "x"},
        )  # senza scadenza e con canale in-app
    with pytest.raises(ValueError), transaction.atomic():
        emit(
            "identity.invitation",
            {"x": 1},
            [Recipient(None, {}, address="z@example.invalid")],
            idempotency_key="c",
            audience="sconosciuto",
            channels=("EMAIL",),
        )


def test_seal_key_rotation(settings):
    old, new = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    settings.COMMUNICATIONS_SEAL_KEYS = [old]
    ciphertext = seal({"token": "segreto-sintetico"})
    assert "segreto-sintetico" not in ciphertext
    settings.COMMUNICATIONS_SEAL_KEYS = [new, old]
    assert unseal(ciphertext) == {"token": "segreto-sintetico"}
