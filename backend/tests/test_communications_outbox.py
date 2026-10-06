"""GAP-F01: outbox nello stesso commit, dispatcher, reconciler, retry, dead-letter, T22."""

import random
from datetime import timedelta

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.communications import dispatch
from apps.communications.dispatch import (
    backoff_seconds,
    process_delivery,
    reconcile,
    recover_expired_leases,
)
from apps.communications.models import (
    Delivery,
    DeliveryAttempt,
    DeliveryStatus as S,
    Notification,
    OutboxEvent,
)
from apps.communications.providers import SinkBackend, TransientError, PermanentError
from apps.communications.services import (
    MarketingDisabled,
    OutboxConflict,
    PayloadNotMinimal,
    Recipient,
    emit,
)
from apps.identity.models import Account

PAYLOAD = {"lesson_id": "l-1", "version": 1, "subject_name": "Matematica"}


@pytest.fixture(autouse=True)
def sink():
    SinkBackend.reset()
    yield SinkBackend
    SinkBackend.reset()


def account(name, verified=True, **extra):
    return Account.objects.create_user(
        username=name,
        email=f"{name}@example.invalid",
        email_verified=verified,
        password=None,
        **extra,
    )


@pytest.fixture
def people(db):
    return [account("anna"), account("bruno")]


@pytest.fixture
def no_broker(monkeypatch):
    """Il broker non c'è: si simula con una coda in memoria registrata."""
    queued = []

    class FakeTask:
        @staticmethod
        def apply_async(args, queue, retry):
            assert queue == "notifications" and retry is False
            queued.append(args[0])

    monkeypatch.setattr("apps.communications.tasks.deliver", FakeTask)
    return queued


def emit_one(people, key="k-1", payload=PAYLOAD, **kw):
    with transaction.atomic():
        return emit("lesson.published", payload, people, idempotency_key=key, **kw)


def test_event_and_deliveries_written_in_same_transaction(people):
    event = emit_one(people)
    rows = Delivery.objects.filter(event=event)
    assert rows.count() == 4  # 2 destinatari × (IN_APP, EMAIL)
    assert set(rows.values_list("status", flat=True)) == {S.PENDING}


@pytest.mark.django_db(transaction=True)
def test_rollback_of_domain_transaction_drops_outbox():
    user = account("carla")
    with pytest.raises(RuntimeError):
        with transaction.atomic():
            emit("lesson.published", PAYLOAD, [user], idempotency_key="k")
            raise RuntimeError("errore di dominio dopo emit")
    assert OutboxEvent.objects.count() == 0 and Delivery.objects.count() == 0


@pytest.mark.django_db(transaction=True)
def test_emit_requires_domain_transaction():
    with pytest.raises(RuntimeError):
        emit("lesson.published", PAYLOAD, [account("dario")], idempotency_key="k")


@pytest.mark.django_db(transaction=True)
def test_enqueue_only_after_commit(no_broker):
    user = account("elena")
    with transaction.atomic():
        emit("lesson.published", PAYLOAD, [user], idempotency_key="k")
        assert no_broker == []  # nulla in coda prima del commit
    assert len(no_broker) == 2
    assert Delivery.objects.filter(enqueued_at__isnull=False).count() == 2


def test_replay_same_key_no_new_rows(people):
    first = emit_one(people)
    again = emit_one(people)
    assert again.pk == first.pk
    assert OutboxEvent.objects.count() == 1 and Delivery.objects.count() == 4


def test_same_key_different_payload_conflict(people):
    emit_one(people)
    with pytest.raises(OutboxConflict):
        emit_one(people, payload={**PAYLOAD, "version": 2})


def test_unique_event_recipient_channel(people):
    event = emit_one(people)
    with pytest.raises(IntegrityError), transaction.atomic():
        Delivery.objects.create(
            event=event,
            recipient=people[0],
            channel="EMAIL",
            next_attempt_at=timezone.now(),
        )


def test_duplicate_recipients_merged(people):
    event = emit_one(
        [
            Recipient(people[0], {"student_names": ["Sara"]}),
            Recipient(people[0], {"student_names": ["Luca"]}),
        ]
    )
    rows = Delivery.objects.filter(event=event)
    assert rows.count() == 2
    assert rows.first().context["student_names"] == ["Luca", "Sara"]


@pytest.mark.parametrize(
    "event_type,key",
    [("Lesson Published", "k"), ("lesson.published", ""), ("lesson.published", "a b")],
)
def test_invalid_event_type_or_key(people, event_type, key):
    with pytest.raises(ValueError), transaction.atomic():
        emit(event_type, PAYLOAD, people, idempotency_key=key)


def test_marketing_category_separated_and_disabled(people):
    with pytest.raises(MarketingDisabled):
        emit_one(people, category="MARKETING")


def test_marketing_when_enabled_respects_default_opt_out(people, settings):
    settings.COMMUNICATIONS_MARKETING_ENABLED = True
    event = emit_one(people, category="MARKETING")
    assert set(
        Delivery.objects.filter(event=event).values_list("status", flat=True)
    ) == {S.SKIPPED}


def test_inactive_and_unverified_recipients_skipped(db):
    inactive = account("fabio", is_active=False)
    unverified = account("gina", verified=False)
    event = emit_one([inactive, unverified])
    codes = dict(
        Delivery.objects.filter(event=event, channel="EMAIL").values_list(
            "recipient__username", "last_error_code"
        )
    )
    assert codes == {"fabio": "RECIPIENT_INACTIVE", "gina": "EMAIL_NOT_VERIFIED"}
    assert (
        Delivery.objects.get(recipient=unverified, channel="IN_APP").status == S.PENDING
    )
    assert DeliveryAttempt.objects.filter(outcome="SKIPPED").count() == 3


def test_in_app_delivery_deduplicated_on_retry(people):
    event = emit_one(people[:1], channels=("IN_APP",))
    delivery = Delivery.objects.get(event=event)
    assert process_delivery(delivery.pk) == S.SENT
    # Task duplicato (es. broker che riconsegna): nessuna seconda notifica.
    assert process_delivery(delivery.pk) == S.SENT
    assert Notification.objects.filter(recipient=people[0]).count() == 1
    # Anche forzando un nuovo tentativo, il vincolo DB sopprime il duplicato.
    Delivery.objects.filter(pk=delivery.pk).update(status=S.PENDING)
    assert process_delivery(delivery.pk) == S.SENT
    assert Notification.objects.filter(recipient=people[0]).count() == 1
    outcomes = list(
        DeliveryAttempt.objects.filter(delivery=delivery).values_list(
            "outcome", flat=True
        )
    )
    assert outcomes == ["ACCEPTED", "DUPLICATE_SUPPRESSED"]


def test_email_delivery_single_recipient_sink(people, sink):
    event = emit_one(people[:1], channels=("EMAIL",))
    delivery = Delivery.objects.get(event=event)
    assert process_delivery(delivery.pk) == S.SENT
    assert len(sink.messages) == 1 and sink.messages[0].to == "anna@example.invalid"
    delivery.refresh_from_db()
    assert delivery.provider == "sink" and delivery.provider_message_id.startswith(
        "sink-"
    )
    assert delivery.attempts == 1 and delivery.completed_at


def test_backoff_exponential_with_jitter_bounds():
    rng = random.Random(7)
    for attempt in range(1, 10):
        ceiling = min(3600, 30 * 2 ** (attempt - 1))
        values = [backoff_seconds(attempt, rng) for _ in range(50)]
        assert all(ceiling / 2 <= v <= ceiling for v in values)
        assert len(set(values)) > 1  # jitter effettivo


def test_transient_errors_retry_with_backoff_then_dead(people, monkeypatch, settings):
    settings.COMMUNICATIONS_DELIVERY = {
        **settings.COMMUNICATIONS_DELIVERY,
        "MAX_ATTEMPTS": 3,
    }

    def fail(self, message):
        raise TransientError("SMTP_CONNECT")

    monkeypatch.setattr(SinkBackend, "send", fail)
    event = emit_one(people[:1], channels=("EMAIL",))
    delivery = Delivery.objects.get(event=event)
    delays = []
    for expected in (S.PENDING, S.PENDING, S.DEAD):
        before = timezone.now()
        assert process_delivery(delivery.pk) == expected
        delivery.refresh_from_db()
        if expected == S.PENDING:
            delays.append((delivery.next_attempt_at - before).total_seconds())
            # Non dovuta prima del backoff: un task anticipato non fa nulla.
            assert process_delivery(delivery.pk) is None
            Delivery.objects.filter(pk=delivery.pk).update(
                next_attempt_at=timezone.now()
            )
    assert 15 <= delays[0] <= 31 and 30 <= delays[1] <= 61
    assert delivery.status == S.DEAD and delivery.last_error_code == "SMTP_CONNECT"
    assert DeliveryAttempt.objects.filter(delivery=delivery).count() == 3


def test_permanent_error_goes_to_dead_letter(people, monkeypatch):
    def fail(self, message):
        raise PermanentError("SMTP_RECIPIENT_REFUSED")

    monkeypatch.setattr(SinkBackend, "send", fail)
    event = emit_one(people[:1], channels=("EMAIL",))
    delivery = Delivery.objects.get(event=event)
    assert process_delivery(delivery.pk) == S.DEAD
    assert reconcile(inline=True)["due"] == 0  # nessun reinvio automatico


def test_attempt_log_is_append_only(people):
    event = emit_one(people[:1], channels=("IN_APP",))
    delivery = Delivery.objects.get(event=event)
    process_delivery(delivery.pk)
    attempt = DeliveryAttempt.objects.get(delivery=delivery)
    attempt.note = "modifica"
    with pytest.raises(RuntimeError):
        attempt.save()
    with pytest.raises(RuntimeError):
        attempt.delete()


@pytest.mark.django_db(transaction=True)
def test_t22_crash_after_commit_before_enqueue_recovered(monkeypatch, no_broker):
    user = account("ivo")
    # Il processo "muore" dopo il commit: la callback di accodamento non arriva mai.
    monkeypatch.setattr(dispatch, "enqueue", lambda ids: 0)
    with transaction.atomic():
        emit("lesson.published", PAYLOAD, [user], idempotency_key="crash")
    assert no_broker == [] and Delivery.objects.filter(status=S.PENDING).count() == 2
    monkeypatch.undo()
    from apps.communications import tasks  # noqa: F401

    monkeypatch.setattr(
        "apps.communications.tasks.deliver",
        type(
            "T",
            (),
            {
                "apply_async": staticmethod(
                    lambda args, queue, retry: no_broker.append(args[0])
                )
            },
        ),
    )
    result = reconcile()
    assert result["due"] == 2 and result["dispatched"] == 2 and len(no_broker) == 2
    for delivery_id in no_broker:
        process_delivery(delivery_id)
    assert Notification.objects.filter(recipient=user).count() == 1
    assert Delivery.objects.filter(status=S.SENT).count() == 2
    assert reconcile()["due"] == 0  # nessun doppio invio


@pytest.mark.django_db(transaction=True)
def test_broker_down_keeps_obligation(monkeypatch):
    user = account("lia")

    class Down:
        @staticmethod
        def apply_async(**kwargs):
            raise ConnectionError("redis assente")

    monkeypatch.setattr("apps.communications.tasks.deliver", Down)
    with transaction.atomic():
        emit("lesson.published", PAYLOAD, [user], idempotency_key="down")
    assert (
        Delivery.objects.filter(status=S.PENDING, enqueued_at__isnull=True).count() == 2
    )
    result = reconcile(inline=True)  # comando di emergenza senza broker
    assert result["dispatched"] == 2
    assert Delivery.objects.filter(status=S.SENT).count() == 2


def test_lost_job_reenqueued_after_stale_window(people, no_broker):
    emit_one(people[:1], channels=("IN_APP",))
    stale = timezone.now() - timedelta(minutes=10)
    Delivery.objects.update(enqueued_at=stale)
    assert reconcile()["dispatched"] == 1
    Delivery.objects.update(enqueued_at=timezone.now())
    assert reconcile()["due"] == 0


def test_expired_lease_in_app_retried_email_ambiguous(people):
    emit_one(people[:1])
    past = timezone.now() - timedelta(minutes=5)
    Delivery.objects.update(status=S.SENDING, lease_until=past, attempts=1)
    assert recover_expired_leases() == 2
    assert Delivery.objects.get(channel="IN_APP").status == S.PENDING
    assert Delivery.objects.get(channel="EMAIL").status == S.AMBIGUOUS
    assert DeliveryAttempt.objects.filter(outcome="LEASE_EXPIRED").count() == 2


def test_payload_guard_rejects_member_lists_and_links(people):
    for payload in (
        {**PAYLOAD, "participants": ["a", "b"]},
        {**PAYLOAD, "join_url": "https://video.example.invalid/x"},
        {**PAYLOAD, "note": "collegati a https://video.example.invalid/x"},
        {**PAYLOAD, "note": "scrivi a tutor@example.invalid"},
        {**PAYLOAD, "student_names": ["Sara", "Luca"]},  # solo nel contesto
        {**PAYLOAD, "rows": [{"name": "Sara"}]},
    ):
        with pytest.raises(PayloadNotMinimal), transaction.atomic():
            emit("lesson.published", payload, people, idempotency_key="g")
    with pytest.raises(PayloadNotMinimal), transaction.atomic():
        emit(
            "lesson.published",
            PAYLOAD,
            [Recipient(people[0], {"members": ["x"]})],
            idempotency_key="g2",
        )
    assert OutboxEvent.objects.count() == 0


# --- PostgreSQL: concorrenza reale (skipped su SQLite) ---------------------------

from concurrent.futures import ThreadPoolExecutor  # noqa: E402
from threading import Barrier  # noqa: E402

from django.db import connection, connections  # noqa: E402

PG_ONLY = pytest.mark.skipif(
    connection.vendor != "postgresql",
    reason="Concorrenza e vincoli verificati solo su PostgreSQL reale",
)


def _race(fn, n=2):
    barrier = Barrier(n)

    def worker(i):
        try:
            barrier.wait(timeout=10)
            return fn(i)
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=n) as executor:
        return [
            f.result(timeout=30) for f in [executor.submit(worker, i) for i in range(n)]
        ]


@PG_ONLY
@pytest.mark.django_db(transaction=True)
def test_pg_concurrent_emit_same_key_single_event():
    user = account("rita")

    def run(i):
        with transaction.atomic():
            return emit("lesson.published", PAYLOAD, [user], idempotency_key="race").pk

    assert len(set(_race(run))) == 1
    assert OutboxEvent.objects.count() == 1 and Delivery.objects.count() == 2


@PG_ONLY
@pytest.mark.django_db(transaction=True)
def test_pg_concurrent_workers_single_notification():
    user = account("sara")
    with transaction.atomic():
        event = emit(
            "lesson.published",
            PAYLOAD,
            [user],
            idempotency_key="w",
            channels=("IN_APP",),
        )
    delivery = Delivery.objects.get(event=event)
    _race(lambda i: process_delivery(delivery.pk), n=3)
    assert Notification.objects.filter(recipient=user).count() == 1
    assert DeliveryAttempt.objects.filter(delivery=delivery).count() == 1
