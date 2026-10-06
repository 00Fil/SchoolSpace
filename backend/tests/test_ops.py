"""Test di esercizio (s5-infra): log JSON e redazione, health/readiness, metriche,
heartbeat, propagazione del correlation_id, riconciliazione post-restore."""

import io
import json
import logging
import logging.config
import re
import uuid
from datetime import date, timedelta
from io import StringIO

import pytest
from django.core.management import CommandError, call_command
from django.test import Client
from django.utils import timezone

from apps.ops import logs, metrics, readiness, restore, signals
from apps.ops.context import correlation_id_var, sanitize_correlation_id
from apps.ops.heartbeat import beat, stale_queues
from apps.ops.models import WorkerHeartbeat

pytestmark = pytest.mark.django_db

SECRETS = [
    "mario.rossi@example.invalid",
    "synthetic-Passw0rd!",
    "abc-defg-hij",  # path di una stanza video
    "RSSMRA80A01H501U",  # codice fiscale sintetico
    "nota-riservata-sul-minore",
    "s3cr3tT0kenValue1234567890abcdefXYZ",
]


@pytest.fixture
def json_logs():
    """Cattura l'output reale del formatter JSON con i filtri di produzione."""
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logs.JsonFormatter())
    handler.addFilter(logs.CorrelationFilter())
    handler.addFilter(logs.RedactFilter())
    root = logging.getLogger()
    old_level = root.level
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)
    access = logging.getLogger("ops.access")
    old_access = access.level
    access.setLevel(logging.DEBUG)
    try:
        yield stream
    finally:
        root.removeHandler(handler)
        root.setLevel(old_level)
        access.setLevel(old_access)


def lines(stream):
    return [json.loads(x) for x in stream.getvalue().splitlines() if x.strip()]


# ------------------------------------------------------------------ redazione


@pytest.mark.parametrize(
    "raw, leaked",
    [
        ("contatto mario.rossi@example.invalid", "mario.rossi@example.invalid"),
        (
            "Authorization: Bearer s3cr3tT0kenValue1234567890",
            "s3cr3tT0kenValue1234567890",
        ),
        ("GET /invite?token=abcdef123456&x=1", "abcdef123456"),
        ("password=synthetic-Passw0rd!", "synthetic-Passw0rd!"),
        ("link https://meet.google.com/abc-defg-hij?pwd=1", "abc-defg-hij"),
        ("zoom https://us02web.zoom.us/j/81234567890?pwd=XyZ", "81234567890"),
        ("CF RSSMRA80A01H501U", "RSSMRA80A01H501U"),
        ("IBAN IT60X0542811101000000123456", "IT60X0542811101000000123456"),
        ("chiamare +39 333 123 4567", "333 123 4567"),
        ("cell 333-1234567", "333-1234567"),
        ("jwt eyJhbGciOi.eyJzdWIiOiIx.c2lnbmF0dXJlX3Rlc3Q", "eyJzdWIiOiIx"),
        (
            "signed abc123def:1tXyZq:Zk9pL0aBcDeFgHiJkLmNoPqRsTu",
            "Zk9pL0aBcDeFgHiJkLmNoPqRsTu",
        ),
        ("sessionid=0123456789abcdef", "0123456789abcdef"),
    ],
)
def test_redact_text_removes_sensitive_values(raw, leaked):
    out = logs.redact_text(raw)
    assert leaked not in out
    assert logs.REDACTED in out


def test_redaction_keeps_technical_identifiers():
    run_id = str(uuid.uuid4())
    text = f"run {run_id} STALE_INPUT error_code=STALE_INPUT duration 120 ms 2026-10-05"
    assert logs.redact_text(text) == text
    assert (
        logs.redact_text("https://app.example.it/")
        == "https://app.example.it/[REDACTED]"
    )


def test_redact_value_by_key_recursively():
    value = {
        "student": {"notes": "nota-riservata-sul-minore", "id": 7},
        "video_url": "https://meet.google.com/abc-defg-hij",
        "items": [{"email": "a@b.it"}, {"password": "p"}],
        "status": "ok",
    }
    out = logs.redact_value(value)
    assert out["student"] == {"notes": logs.REDACTED, "id": 7}
    assert out["video_url"] == logs.REDACTED
    assert out["items"] == [{"email": logs.REDACTED}, {"password": logs.REDACTED}]
    assert out["status"] == "ok"


def test_json_formatter_required_fields_and_redaction(json_logs, settings):
    settings.BUILD_VERSION = "1.0.0+abc123"
    settings.DEPLOY_ENVIRONMENT = "test"
    token = correlation_id_var.set("req-12345678")
    try:
        logging.getLogger("apps.test").warning(
            "invio a %s fallito",
            "mario.rossi@example.invalid",
            extra={
                "action": "mail.send",
                "outcome": "fail",
                "duration_ms": 12.5,
                "note": "nota-riservata-sul-minore",
            },
        )
        try:
            raise ValueError(
                "token=s3cr3tT0kenValue1234567890abcdefXYZ per mario.rossi@example.invalid"
            )
        except ValueError:
            logging.getLogger("apps.test").exception("errore")
    finally:
        correlation_id_var.reset(token)
    first, second = lines(json_logs)[-2:]
    for key in ("ts", "level", "logger", "message", "correlation_id", "build", "env"):
        assert key in first
    assert first["correlation_id"] == "req-12345678"
    assert first["build"] == "1.0.0+abc123" and first["env"] == "test"
    assert first["action"] == "mail.send" and first["duration_ms"] == 12.5
    assert first["note"] == logs.REDACTED
    assert second["exc_type"] == "ValueError"
    raw = json_logs.getvalue()
    for secret in SECRETS:
        assert secret not in raw


def test_formatter_redacts_even_without_filter():
    record = logging.LogRecord(
        "x", logging.INFO, __file__, 1, "mail %s", ("a.b@example.invalid",), None
    )
    out = json.loads(logs.JsonFormatter().format(record))
    assert "example.invalid" not in out["message"]


def test_logging_config_builds_and_disables_raw_access_logs():
    from django.conf import settings

    cfg = logs.build_logging_config()
    assert cfg["handlers"]["stdout"]["filters"] == ["context", "redact"]
    assert cfg["loggers"]["gunicorn.access"]["level"] == "CRITICAL"
    logging.config.dictConfig(cfg)  # configurazione valida
    logging.config.dictConfig(settings.LOGGING)


# ------------------------------------------------------ middleware e access log


def test_request_id_generated_and_echoed(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    generated = r["X-Request-ID"]
    assert len(generated) == 32
    r = client.get("/healthz", HTTP_X_REQUEST_ID="edge-req-0001")
    assert r["X-Request-ID"] == "edge-req-0001"
    r = client.get("/healthz", HTTP_X_REQUEST_ID="mario.rossi@example.invalid")
    assert "@" not in r["X-Request-ID"]


def test_sanitize_correlation_id():
    assert sanitize_correlation_id("abcDEF12-_.x") == "abcDEF12-_.x"
    assert sanitize_correlation_id("short") != "short"
    assert sanitize_correlation_id("a" * 65) != "a" * 65
    assert sanitize_correlation_id(None)


def test_access_log_has_route_duration_and_no_sensitive_data(json_logs):
    """GAP-I07: password nel corpo, token e URL video nella query non finiscono nei log."""
    c = Client()
    c.get("/api/v1/auth/csrf")
    csrf = c.cookies["csrftoken"].value
    c.post(
        "/api/v1/auth/login?token=s3cr3tT0kenValue1234567890abcdefXYZ"
        "&video_url=https://meet.google.com/abc-defg-hij",
        data=json.dumps(
            {
                "username": "mario.rossi@example.invalid",
                "password": "synthetic-Passw0rd!",
            }
        ),
        content_type="application/json",
        HTTP_X_CSRFTOKEN=csrf,
        HTTP_X_REQUEST_ID="trace-login-0001",
    )
    raw = json_logs.getvalue()
    for secret in SECRETS + [csrf]:
        assert secret not in raw
    access = [
        x
        for x in lines(json_logs)
        if x.get("action") == "http.request" and x.get("route") == "api/v1/auth/login"
    ]
    assert access, raw
    entry = access[-1]
    assert entry["correlation_id"] == "trace-login-0001"
    assert entry["method"] == "POST" and entry["status"] in (400, 401, 403, 503)
    assert isinstance(entry["duration_ms"], float)
    assert "path" not in entry and "query" not in entry


def test_access_log_uses_route_template_not_raw_path(json_logs, client):
    pk = uuid.uuid4()
    client.post(f"/api/v1/occurrences/{pk}/cancel/")
    raw = json_logs.getvalue()
    assert str(pk) not in raw
    assert "api/v1/occurrences/<uuid:pk>/cancel/" in raw


def test_access_log_actor_is_pseudonymous(json_logs, django_user_model):
    user = django_user_model.objects.create_user(
        username="mario.rossi", email="mario.rossi@example.invalid", password="x"
    )
    c = Client()
    c.force_login(user)
    c.get("/api/v1/me")
    entry = [x for x in lines(json_logs) if x.get("route") == "api/v1/me"][-1]
    assert entry["actor_id"] and len(entry["actor_id"]) == 16
    assert "mario.rossi" not in json_logs.getvalue()


# ----------------------------------------------------------- health/readiness


def test_healthz_has_no_dependencies(client, monkeypatch):
    monkeypatch.setitem(readiness.CHECKS, "database", lambda: 1 / 0)
    r = client.get("/healthz")
    assert r.status_code == 200 and r.json()["status"] == "ok"
    assert "no-store" in r["Cache-Control"]


def test_readyz_ok(client):
    r = client.get("/readyz")
    assert r.status_code == 200, r.content
    body = r.json()
    assert body["status"] == "ok"
    assert {"database", "migrations", "cache", "broker", "workers"} <= set(
        body["checks"]
    )


def test_readyz_fails_without_leaking_details(client, monkeypatch):
    def boom():
        raise RuntimeError(
            "connection to db.internal:5432 password=synthetic-Passw0rd! failed"
        )

    monkeypatch.setitem(readiness.CHECKS, "database", boom)
    r = client.get("/readyz")
    assert r.status_code == 503
    assert r.json()["checks"]["database"] == "fail"
    assert r.json()["checks"]["migrations"] == "skipped"
    assert b"db.internal" not in r.content and b"Passw0rd" not in r.content
    public = client.get("/api/v1/ready")
    assert public.status_code == 503 and public.json() == {"status": "fail"}


def test_readyz_broker_and_cache_failures(client, monkeypatch):
    monkeypatch.setitem(readiness.CHECKS, "broker", lambda: False)
    assert client.get("/readyz").status_code == 503
    monkeypatch.setitem(readiness.CHECKS, "broker", lambda: True)
    monkeypatch.setitem(readiness.CHECKS, "cache", lambda: False)
    assert client.get("/readyz").status_code == 503


def test_readyz_pending_migrations(client, monkeypatch):
    monkeypatch.setattr(readiness, "_migrations_ok_until", 0.0)

    class Graph:
        def leaf_nodes(self):
            return []

    class FakeExecutor:
        def __init__(self, conn):
            self.loader = type("L", (), {"graph": Graph()})()

        def migration_plan(self, targets):
            return [("ops", "9999_pending")]

    monkeypatch.setattr("django.db.migrations.executor.MigrationExecutor", FakeExecutor)
    r = client.get("/readyz")
    assert r.status_code == 503 and r.json()["checks"]["migrations"] == "fail"


def test_broker_check_uses_real_connection_for_redis(settings, monkeypatch):
    settings.CELERY_BROKER_URL = "redis://:pw@127.0.0.1:1/0"
    calls = {}

    class Conn:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def ensure_connection(self, **kw):
            calls.update(kw)
            raise ConnectionError("refused")

    from config.celery import app

    monkeypatch.setattr(app, "connection_for_write", lambda: Conn())
    healthy, results = readiness.run_checks(["broker"])
    assert not healthy and results == {"broker": "fail"}
    assert calls["max_retries"] == 1 and calls["timeout"] == 2


def test_workers_heartbeat_readiness(client, settings):
    settings.OPS_WORKER_QUEUES = ("solver", "notifications")
    assert stale_queues() == ["solver", "notifications"]
    body = client.get("/readyz").json()
    # Il worker assente è un alert, non rende il web "non pronto" per default.
    assert body["checks"]["workers"] == "fail" and body["status"] == "ok"
    settings.OPS_READY_REQUIRED_CHECKS = ("database", "workers")
    assert client.get("/readyz").status_code == 503
    beat("solver", "w1")
    beat("notifications", "w2")
    assert client.get("/readyz").status_code == 200
    WorkerHeartbeat.objects.filter(queue="notifications").update(
        seen_at=timezone.now() - timedelta(minutes=5)
    )
    assert stale_queues() == ["notifications"]


def test_ops_check_command(settings):
    out = StringIO()
    call_command("ops_check", "--checks", "database,cache,broker", stdout=out)
    assert json.loads(out.getvalue())["status"] == "ok"
    settings.OPS_WORKER_QUEUES = ("solver",)
    with pytest.raises(CommandError):
        call_command("ops_check", "--checks", "workers", stdout=StringIO())
    with pytest.raises(CommandError):
        call_command("ops_check", "--checks", "nope", stdout=StringIO())


# --------------------------------------------------------------------- metriche


def test_metrics_access_control(client, settings):
    settings.DEBUG = False
    settings.OPS_METRICS_TOKEN = ""
    assert client.get("/metrics").status_code == 404
    settings.OPS_METRICS_TOKEN = "metrics-test-token"
    assert client.get("/metrics").status_code == 401
    assert client.get("/metrics", HTTP_AUTHORIZATION="Bearer wrong").status_code == 401
    ok = client.get("/metrics", HTTP_AUTHORIZATION="Bearer metrics-test-token")
    assert ok.status_code == 200


def test_metrics_exposition(client, settings):
    settings.OPS_METRICS_TOKEN = "t0ken-for-tests"
    settings.OPS_WORKER_QUEUES = ("solver",)
    metrics.STATE.invalidate()
    pk = uuid.uuid4()
    client.get(f"/api/v1/occurrences/{pk}/reschedule-options/")
    client.get("/healthz")
    beat("solver", "w1")
    metrics.record_event("commit_conflict")
    metrics.record_event("unbounded-label-from-bug")
    r = client.get("/metrics", HTTP_AUTHORIZATION="Bearer t0ken-for-tests")
    text = r.content.decode()
    assert r["Content-Type"].startswith("text/plain")
    assert (
        'ripetizioni_http_request_duration_seconds_bucket{le="0.5",method="GET",'
        'route="healthz",status="200"}' in text
    )
    assert "api/v1/occurrences/<uuid:pk>/reschedule-options/" in text
    assert str(pk) not in text
    assert 'ripetizioni_domain_events_total{kind="commit_conflict"}' in text
    assert 'ripetizioni_domain_events_total{kind="other"}' in text
    assert 'ripetizioni_schedule_runs{status="QUEUED"} 0.0' in text
    assert "ripetizioni_schedule_run_oldest_queued_age_seconds 0.0" in text
    assert "ripetizioni_schedule_runs_over_hard_limit 0.0" in text
    assert 'ripetizioni_schedule_runs_failed{error_code="VALIDATION_FAILED"}' in text
    assert 'ripetizioni_worker_heartbeat_age_seconds{queue="solver"}' in text
    assert "ripetizioni_build_info{" in text
    assert "ripetizioni_metrics_provider_errors 0.0" in text


def broken_provider(now):
    raise RuntimeError("provider rotto")


def test_metrics_backup_status_and_failing_provider(settings, tmp_path):
    status = tmp_path / "backup-status.json"
    status.write_text(
        json.dumps({"last_success_epoch": 1790000000, "size_bytes": 1234})
    )
    settings.OPS_BACKUP_STATUS_FILE = str(status)
    settings.OPS_DB_STORAGE_LIMIT_BYTES = 10 * 2**30
    settings.OPS_METRIC_PROVIDERS = (
        "tests.test_ops.broken_provider",
        "no.such.module.provider",
    )
    metrics.STATE.invalidate()
    text = metrics.render_latest().decode()
    assert "ripetizioni_backup_last_success_timestamp_seconds 1.79e+09" in text
    assert "ripetizioni_backup_last_size_bytes 1234.0" in text
    assert "ripetizioni_metrics_provider_errors 1.0" in text
    assert "ripetizioni_db_storage_limit_bytes 1.073741824e+10" in text
    assert "ripetizioni_db_wal_limit_bytes" not in text
    metrics.STATE.invalidate()


def test_metrics_communications_backlog_and_attempts(django_user_model):
    from apps.communications.models import Delivery, DeliveryAttempt, OutboxEvent

    user = django_user_model.objects.create_user(username="ops-metrics", password="x")
    event = OutboxEvent.objects.create(
        event_type="lesson.changed", idempotency_key="ops-m-1", payload_hash="0" * 64
    )
    old = timezone.now() - timedelta(minutes=20)
    d = Delivery.objects.create(
        event=event, recipient=user, channel="EMAIL", next_attempt_at=old
    )
    Delivery.objects.filter(pk=d.pk).update(created_at=old)
    Delivery.objects.create(
        event=event,
        recipient=user,
        channel="IN_APP",
        status="DEAD",
        next_attempt_at=old,
    )
    DeliveryAttempt.objects.create(delivery=d, number=1, outcome="TRANSIENT_ERROR")
    metrics.STATE.invalidate()
    text = metrics.render_latest().decode()
    metrics.STATE.invalidate()
    assert 'ripetizioni_delivery_backlog{channel="EMAIL",status="PENDING"} 1.0' in text
    assert "ripetizioni_outbox_pending 1.0" in text
    age = float(
        re.search(r"^ripetizioni_outbox_oldest_pending_age_seconds (\S+)$", text, re.M)[
            1
        ]
    )
    assert 1150 < age < 1300
    assert "ripetizioni_delivery_dead 1.0" in text
    assert 'ripetizioni_delivery_attempts_total{outcome="TRANSIENT_ERROR"} 1.0' in text


def test_alert_rules_reference_only_exported_metrics():
    """Ogni metrica applicativa usata negli alert deve esistere nel codice (niente alert muti)."""
    import pathlib

    import yaml

    root = pathlib.Path(__file__).resolve().parents[2]
    rules = yaml.safe_load((root / "infra/monitoring/alerts.yml").read_text())
    exprs = " ".join(
        str(r.get("expr", "")) for g in rules["groups"] for r in g["rules"]
    )
    recorded = {
        r["record"] for g in rules["groups"] for r in g["rules"] if "record" in r
    }
    used = set(re.findall(r"\b(ripetizioni_[a-z0-9_]+)", exprs)) - recorded
    source = (root / "backend/apps/ops/metrics.py").read_text()
    missing = set()
    for name in used:
        base = re.sub(r"_(total|bucket|count|sum)$", "", name)
        if f'"{name}"' not in source and f'"{base}"' not in source:
            missing.add(name)
    assert not missing, missing


def test_metrics_state_is_cached(django_assert_max_num_queries):
    metrics.STATE.invalidate()
    metrics.STATE.collect()
    with django_assert_max_num_queries(0):
        metrics.STATE.collect()
    metrics.STATE.invalidate()


# ------------------------------------------------------------ Celery e heartbeat


def test_heartbeat_task_and_beat_schedule():
    from django.conf import settings as live

    from apps.ops.tasks import heartbeat

    assert heartbeat.run("solver") == "solver"
    hb = WorkerHeartbeat.objects.get(queue="solver")
    assert hb.seen_at > timezone.now() - timedelta(seconds=5)
    entry = live.CELERY_BEAT_SCHEDULE["ops-heartbeat-solver"]
    assert entry["options"]["queue"] == "solver"
    assert entry["options"]["expires"] < entry["schedule"]


def test_correlation_id_propagates_to_celery_tasks():
    headers = {}
    token = correlation_id_var.set("req-abcdef12")
    try:
        signals.add_correlation_header(headers=headers)
    finally:
        correlation_id_var.reset(token)
    assert headers["correlation_id"] == "req-abcdef12"

    class Req:
        correlation_id = "req-abcdef12"

    class Task:
        request = Req()

    signals.bind_correlation(task=Task())
    assert correlation_id_var.get() == "req-abcdef12"
    signals.unbind_correlation(task=Task())
    assert correlation_id_var.get() is None
    fresh = {}
    signals.add_correlation_header(headers=fresh)
    assert len(fresh["correlation_id"]) == 32


def test_worker_ready_signal_records_queues():
    class Q:
        def __init__(self, name):
            self.name = name

    class Consumer:
        task_consumer = type("TC", (), {"queues": [Q("solver"), Q("notifications")]})()

    class Sender:
        hostname = "celery@test"
        consumer = Consumer()

    signals.heartbeat_on_ready(sender=Sender())
    queues = set(WorkerHeartbeat.objects.values_list("queue", flat=True))
    assert queues == {"solver", "notifications"}
    signals.heartbeat_on_ready(sender=None)  # non solleva


# ---------------------------------------------------- riconciliazione post-restore

WEEK = date(2026, 10, 5)


@pytest.fixture
def queued_run(settings, monkeypatch):
    from apps.identity.models import Account
    from apps.scheduling.models import PlanningPolicy, PlanningRevision, ScheduleRun
    from apps.scheduling.runs import submit_run

    settings.DEBUG = True
    settings.EXPERIMENTAL_DB_PLANNING = True
    actor = Account.objects.create_superuser(
        username="ops-center", email="ops@example.invalid", password="synthetic"
    )
    call_command(
        "seed_planning_demo", actor=actor.username, days="0", stdout=StringIO()
    )
    monkeypatch.setattr("apps.scheduling.runs.dispatch_one", lambda run_id: False)
    response = submit_run(
        actor,
        PlanningPolicy.objects.get().id,
        WEEK,
        PlanningRevision.objects.get(pk=1).revision,
        "STRICT",
        "ops-k",
    )
    return ScheduleRun.objects.get(pk=response["run_id"])


def ok_hook(ctx):
    return {
        "ok": True,
        "changed": len(ctx.events("privacy.")),
        "notes": f"apply={ctx.apply}",
    }


def writing_hook(ctx):
    WorkerHeartbeat.objects.create(queue="from-hook", seen_at=timezone.now())
    return {"ok": True}


def failing_hook(ctx):
    return {"ok": False, "notes": "invariante violata"}


HOOKS = [{"name": "test.ok", "path": "tests.test_ops.ok_hook", "required": True}]
POINT = "2026-10-02T10:00:00Z"


def reconcile(*args, **kw):
    out = StringIO()
    call_command(
        "post_restore_reconcile",
        "--restore-point",
        POINT,
        *args,
        stdout=out,
        stderr=StringIO(),
        **kw,
    )
    return json.loads(out.getvalue())


def test_restore_dry_run_does_not_write(queued_run):
    beat("solver", "w1")
    report = reconcile("--allow-missing")
    assert report["mode"] == "dry-run" and report["ok"] is True
    steps = {s["name"]: s for s in report["steps"]}
    assert steps["scheduling.interrupted_runs"]["changed"] == 1
    assert steps["ops.heartbeats"]["changed"] == 1
    assert steps["calendar.booking_overlaps"]["status"] == "OK"
    assert steps["privacy.ledger"]["status"] == "OK"
    assert steps["communications.quarantine"]["status"] == "OK"
    queued_run.refresh_from_db()
    assert queued_run.status == "QUEUED"
    assert WorkerHeartbeat.objects.exists()


def test_restore_missing_required_hooks_block_reopening(settings):
    settings.OPS_POST_RESTORE_HOOKS = [
        {
            "name": "x.required",
            "path": "apps.nonexistent.restore.hook",
            "required": True,
        }
    ]
    with pytest.raises(CommandError, match="riapertura bloccata"):
        reconcile()
    report = reconcile("--allow-missing")
    assert [s for s in report["steps"] if s["name"] == "x.required"][0][
        "status"
    ] == "MISSING"


def test_restore_default_hooks_do_not_block():
    report = reconcile()
    names = [s["name"] for s in report["steps"]]
    assert names[:6] == [
        "ops.heartbeats",
        "scheduling.interrupted_runs",
        "identity.sessions_and_tokens",
        "privacy.ledger",
        "communications.quarantine",
        "calendar.booking_overlaps",
    ]
    assert report["ok"]


def test_restore_apply_marks_runs_and_reports(queued_run, settings, tmp_path):
    settings.OPS_POST_RESTORE_HOOKS = HOOKS
    log_file = tmp_path / "external.jsonl"
    events = [
        {"at": "2026-10-02T09:00:00Z", "kind": "privacy.erasure", "ref": "old"},
        {"at": "2026-10-02T11:00:00Z", "kind": "privacy.erasure", "ref": "new"},
        {"at": "2026-10-02T11:30:00Z", "kind": "identity.revocation", "ref": "r"},
    ]
    log_file.write_text("\n".join(json.dumps(e) for e in events) + "\n\n")
    report_file = tmp_path / "report.json"
    reconcile("--external-log", str(log_file), "--apply", "--report", str(report_file))
    report = json.loads(report_file.read_text())
    assert report["ok"] and report["mode"] == "apply" and report["external_events"] == 3
    hook = [s for s in report["steps"] if s["name"] == "test.ok"][0]
    assert hook["changed"] == 1 and hook["notes"] == "apply=True"
    queued_run.refresh_from_db()
    assert (
        queued_run.status == "FAILED" and queued_run.error_code == "RESTORE_INTERRUPTED"
    )
    assert queued_run.claim_token is None
    # Idempotente: una seconda esecuzione non trova più nulla da cambiare.
    steps = {s["name"]: s for s in reconcile("--apply")["steps"]}
    assert steps["scheduling.interrupted_runs"]["changed"] == 0


def test_restore_dry_run_rolls_back_hook_writes(settings):
    settings.OPS_POST_RESTORE_HOOKS = [
        {"name": "w", "path": "tests.test_ops.writing_hook", "required": True}
    ]
    reconcile()
    assert not WorkerHeartbeat.objects.filter(queue="from-hook").exists()


def test_restore_failing_hook_blocks(settings):
    settings.OPS_POST_RESTORE_HOOKS = [
        {"name": "f", "path": "tests.test_ops.failing_hook", "required": True}
    ]
    with pytest.raises(CommandError):
        reconcile()


def test_restore_input_validation(tmp_path):
    with pytest.raises(CommandError, match="restore-point"):
        call_command(
            "post_restore_reconcile", "--restore-point", "ieri", stdout=StringIO()
        )
    bad = tmp_path / "bad.jsonl"
    bad.write_text('{"at": "2026-10-02T10:00:00Z"}\n')
    with pytest.raises(CommandError, match="registro esterno"):
        reconcile("--external-log", str(bad))


def test_restore_context_event_filter():
    ctx = restore.RestoreContext(
        restore_point=restore.parse_ts(POINT),
        apply=False,
        external_events=[
            {"at": "2026-10-02T10:00:00Z", "kind": "privacy.erasure"},  # già nel backup
            {"at": "2026-10-02T12:00:00+02:00", "kind": "privacy.erasure"},  # = 10:00Z
            {"at": "2026-10-02T12:00:01+02:00", "kind": "privacy.erasure"},
            {"at": "2026-10-02T11:00:00Z", "kind": "identity.revocation"},
        ],
    )
    assert len(ctx.events("privacy.")) == 1
    assert len(ctx.events("identity.")) == 1


def test_restore_identity_step_invalidates_sessions_and_invites(django_user_model):
    from apps.identity.models import Invitation, UserSession

    actor = django_user_model.objects.create_user(username="ops-staff", password="x")
    UserSession.objects.create(account=actor, last_seen_at=timezone.now())
    inv = Invitation.objects.create(
        email="famiglia@example.invalid",
        role="TUTOR",
        status=Invitation.Status.SENT,
        token_hash="a" * 64,
        expires_at=timezone.now() + timedelta(days=1),
        created_by=actor,
    )
    dry = {s["name"]: s for s in reconcile()["steps"]}
    assert dry["identity.sessions_and_tokens"]["changed"] == 2
    assert UserSession.objects.filter(revoked_at__isnull=True).count() == 1
    reconcile("--apply")
    assert UserSession.objects.filter(revoked_at__isnull=True).count() == 0
    inv.refresh_from_db()
    assert inv.status == Invitation.Status.REVOKED and inv.token_hash is None


def test_restore_communications_step_quarantines_old_email(
    django_user_model, monkeypatch
):
    from apps.communications import dispatch
    from apps.communications.models import Delivery, OutboxEvent

    seen = {}

    def fake_reconcile():
        # La riconciliazione s3 (lookup provider) deve vedere le email già in quarantena.
        seen["statuses"] = sorted(
            Delivery.objects.filter(channel="EMAIL").values_list("status", flat=True)
        )
        return {}

    monkeypatch.setattr(dispatch, "reconcile", fake_reconcile)

    user = django_user_model.objects.create_user(username="ops-fam", password="x")
    event = OutboxEvent.objects.create(
        event_type="lesson.changed",
        idempotency_key="ops-restore-1",
        payload_hash="0" * 64,
    )
    email = Delivery.objects.create(
        event=event, recipient=user, channel="EMAIL", next_attempt_at=timezone.now()
    )
    in_app = Delivery.objects.create(
        event=event, recipient=user, channel="IN_APP", next_attempt_at=timezone.now()
    )
    reconcile("--apply")
    email.refresh_from_db()
    in_app.refresh_from_db()
    assert seen["statuses"] == ["AMBIGUOUS"]
    assert email.status == "AMBIGUOUS" and email.last_error_code == "RESTORE_UNKNOWN"
    assert in_app.status != "AMBIGUOUS"


def test_django_request_log_keeps_correlation_id(client, settings, caplog):
    settings.OPS_METRICS_TOKEN = ""
    with caplog.at_level(logging.WARNING, logger="django.request"):
        client.get("/readyz-not-found-xyz", HTTP_X_REQUEST_ID="cid-django-request-1")
    from apps.ops.logs import CorrelationFilter

    records = [r for r in caplog.records if r.name == "django.request"]
    assert records
    CorrelationFilter().filter(records[-1])
    assert records[-1].correlation_id == "cid-django-request-1"
