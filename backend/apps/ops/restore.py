"""Riconciliazione dopo un restore (GAP-L03).

``manage.py post_restore_reconcile`` esegue, in ordine e in transazioni separate:

1. ``ops.heartbeats``                 azzera gli heartbeat ripristinati (falsi positivi);
2. ``scheduling.interrupted_runs``    run QUEUED/RUNNING -> FAILED ``RESTORE_INTERRUPTED``
                                      (mai ripresi da soli: si rilanciano a mano);
3. ``identity.sessions_and_tokens``   revoca tutte le sessioni, gli inviti aperti e i token
                                      di reset ripristinati (s1: ``UserSession``, ``Invitation``);
4. ``privacy.ledger``                 ``apps.privacy.reconcile`` (s4): verifica la catena del
                                      ledger esterno e riapplica revoche/anonimizzazioni
                                      successive al restore; richieste mancanti = blocco;
5. ``communications.quarantine``      (s3) consegne EMAIL PENDING/SENDING -> AMBIGUOUS
                                      ``RESTORE_UNKNOWN``: nessun vecchio invio automatico,
                                      decide il centro (RETRY/MARK_SENT/ABANDON); poi, con
                                      ``--apply``, ``apps.communications.dispatch.reconcile``;
6. ``calendar.booking_overlaps``      nessuna sovrapposizione per risorsa ``[start, end)``;
7. hook aggiuntivi da ``settings.OPS_POST_RESTORE_HOOKS`` (es. invarianti di calendario s2).

Contratto di un hook (funzione importabile, idempotente; in dry-run non deve scrivere)::

    def hook(ctx: RestoreContext) -> dict:
        return {"ok": True, "changed": 3, "notes": "..."}

Un passo fallito o un hook ``required`` mancante blocca la riapertura (exit code != 0).
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import logging
from importlib import import_module
from typing import Callable

from django.db import connection, transaction
from django.utils import timezone

log = logging.getLogger("ops.restore")

DEFAULT_HOOKS = (
    # s2-calendario: invarianti complete (GiST, completezza booking, revisioni). Facoltativo
    # finché non esiste: il controllo sovrapposizioni integrato resta comunque obbligatorio.
    {
        "name": "calendar.invariants",
        "path": "apps.calendar.restore.check_invariants",
        "required": False,
    },
)


@dataclasses.dataclass
class RestoreContext:
    restore_point: dt.datetime
    apply: bool
    external_events: list[dict]
    started_at: dt.datetime = dataclasses.field(default_factory=timezone.now)

    def events(self, kind_prefix: str) -> list[dict]:
        """Eventi del registro esterno successivi al restore point, filtrati per tipo."""
        out = []
        for event in self.external_events:
            if not str(event.get("kind", "")).startswith(kind_prefix):
                continue
            at = parse_ts(event.get("at"))
            if at and at > self.restore_point:
                out.append(event)
        return out


def parse_ts(value):
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_default_timezone())
    return parsed


def load_external_log(path: str | None) -> list[dict]:
    """Registro JSON Lines esterno al DB ripristinato: {"at": ISO, "kind": "...", "ref": "..."}."""
    if not path:
        return []
    events = []
    with open(path, encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except ValueError as exc:
                raise ValueError(
                    f"riga {lineno} non valida nel registro esterno"
                ) from exc
            if not isinstance(item, dict) or "kind" not in item or "at" not in item:
                raise ValueError(f"riga {lineno}: servono i campi 'at' e 'kind'")
            events.append(item)
    return events


# ---------------------------------------------------------------- passi integrati


def step_heartbeats(ctx: RestoreContext) -> dict:
    """Gli heartbeat ripristinati sono falsi positivi di vitalità: si azzerano."""
    from .models import WorkerHeartbeat

    n = WorkerHeartbeat.objects.count()
    if ctx.apply:
        WorkerHeartbeat.objects.all().delete()
    return {
        "ok": True,
        "changed": n,
        "notes": "heartbeat azzerati; i worker li ricreano all'avvio",
    }


def step_interrupted_runs(ctx: RestoreContext) -> dict:
    """Run non conclusi al restore point: mai ripresi automaticamente, marcati FAILED."""
    from apps.scheduling.models import ScheduleRun

    qs = ScheduleRun.objects.filter(status__in=("QUEUED", "RUNNING"))
    n = qs.count()
    if ctx.apply and n:
        qs.update(
            status="FAILED",
            phase="RESTORE_INTERRUPTED",
            error_code="RESTORE_INTERRUPTED",
            finished_at=timezone.now(),
            lease_expires_at=None,
            claim_token=None,
        )
    return {
        "ok": True,
        "changed": n,
        "notes": "run non conclusi marcati RESTORE_INTERRUPTED (da rilanciare a mano)",
    }


def step_identity(ctx: RestoreContext) -> dict:
    """Sessioni, inviti e reset ripristinati potrebbero essere già stati chiusi dopo il
    restore point: si invalidano tutti (gli utenti rifanno login, il centro reinvia)."""
    from apps.identity.models import Invitation, PasswordResetToken, UserSession

    now = timezone.now()
    sessions = UserSession.objects.filter(revoked_at__isnull=True)
    open_states = (Invitation.Status.PENDING_VERIFICATION, Invitation.Status.SENT)
    invitations = Invitation.objects.filter(status__in=open_states)
    resets = PasswordResetToken.objects.filter(used_at__isnull=True, expires_at__gt=now)
    counts = (sessions.count(), invitations.count(), resets.count())
    if ctx.apply:
        sessions.update(revoked_at=now, revoked_reason="restore")
        for inv in invitations.select_for_update():
            inv.status = Invitation.Status.REVOKED
            inv.revoked_at = now
            inv.token_hash = None
            inv.version += 1
            inv.save(update_fields=["status", "revoked_at", "token_hash", "version"])
        resets.update(used_at=now)
    return {
        "ok": True,
        "changed": sum(counts),
        "notes": "sessioni %d, inviti aperti %d, token reset %d invalidati" % counts,
    }


def step_privacy(ctx: RestoreContext) -> dict:
    from apps.privacy import ledger
    from apps.privacy.reconcile import apply, plan

    ok, index = ledger.verify_chain()
    if not ok:
        return {
            "ok": False,
            "changed": 0,
            "notes": f"ledger privacy alterato alla voce {index}",
        }
    actions = plan()
    missing = [a for a in actions if a["action"] == "MISSING_REQUEST"]
    done = apply(actions) if ctx.apply else []
    return {
        "ok": not missing,
        "changed": len(done) if ctx.apply else len(actions) - len(missing),
        "notes": (
            f"azioni pianificate {len(actions)}, applicate {len(done)}, "
            f"richieste privacy assenti dal DB {len(missing)} (da registrare a mano)"
        ),
    }


def step_communications(ctx: RestoreContext) -> dict:
    from apps.communications.models import Delivery

    email = Delivery.objects.filter(channel="EMAIL", status__in=("PENDING", "SENDING"))
    n = email.count()
    notes = f"email PENDING/SENDING messe in AMBIGUOUS: {n}"
    if ctx.apply:
        email.update(
            status="AMBIGUOUS",
            lease_until=None,
            enqueued_at=None,
            last_error_code="RESTORE_UNKNOWN",
        )
        try:
            from apps.communications.dispatch import reconcile

            result = reconcile()
            notes += f"; reconcile comunicazioni: {result}"
        except Exception as exc:  # broker giù durante il restore: ci penserà il beat
            notes += f"; reconcile comunicazioni rinviato ({type(exc).__name__})"
    return {"ok": True, "changed": n, "notes": notes}


def step_booking_overlaps(ctx: RestoreContext) -> dict:
    """Controllo indipendente dal vincolo GiST: nessuna sovrapposizione per risorsa
    (intervalli semiaperti [start, end))."""
    from apps.calendar.models import ResourceBooking

    table = connection.ops.quote_name(ResourceBooking._meta.db_table)
    sql = (
        f"SELECT COUNT(*) FROM {table} a JOIN {table} b "
        "ON a.resource_id = b.resource_id AND a.id < b.id "
        "AND a.start_at < b.end_at AND b.start_at < a.end_at"
    )
    with connection.cursor() as cursor:
        cursor.execute(sql)
        overlaps = cursor.fetchone()[0]
    return {
        "ok": overlaps == 0,
        "changed": 0,
        "notes": f"sovrapposizioni trovate: {overlaps}",
    }


BUILTIN_STEPS: tuple[tuple[str, Callable[[RestoreContext], dict]], ...] = (
    ("ops.heartbeats", step_heartbeats),
    ("scheduling.interrupted_runs", step_interrupted_runs),
    ("identity.sessions_and_tokens", step_identity),
    ("privacy.ledger", step_privacy),
    ("communications.quarantine", step_communications),
    ("calendar.booking_overlaps", step_booking_overlaps),
)


def resolve(path: str):
    module, _, attr = path.rpartition(".")
    return getattr(import_module(module), attr)


def run(ctx: RestoreContext, hooks=None, allow_missing: bool = False) -> dict:
    hooks = list(hooks if hooks is not None else DEFAULT_HOOKS)
    steps = []
    for name, func in BUILTIN_STEPS:
        steps.append(
            {
                "name": name,
                "path": f"{func.__module__}.{func.__name__}",
                "required": True,
                "func": func,
            }
        )
    for hook in hooks:
        try:
            func = resolve(hook["path"])
        except (ImportError, AttributeError):
            func = None
        steps.append({**hook, "func": func})

    results = []
    ok = True
    for step in steps:
        entry = {
            "name": step["name"],
            "path": step["path"],
            "required": bool(step.get("required", True)),
        }
        func = step["func"]
        if func is None:
            entry.update(status="MISSING", ok=allow_missing or not entry["required"])
        else:
            try:
                with transaction.atomic():
                    outcome = func(ctx) or {}
                    if not ctx.apply:
                        transaction.set_rollback(
                            True
                        )  # difesa: un dry-run non scrive mai
                entry.update(
                    status="OK" if outcome.get("ok", True) else "FAILED",
                    ok=bool(outcome.get("ok", True)),
                    changed=int(outcome.get("changed", 0)),
                    notes=str(outcome.get("notes", ""))[:500],
                )
            except Exception as exc:
                entry.update(status="ERROR", ok=False, notes=type(exc).__name__)
                log.error(
                    "restore step failed",
                    extra={"step": step["name"], "exc_type": type(exc).__name__},
                )
        ok = ok and entry["ok"]
        results.append(entry)
    report = {
        "restore_point": ctx.restore_point.isoformat(),
        "mode": "apply" if ctx.apply else "dry-run",
        "started_at": ctx.started_at.isoformat(),
        "finished_at": timezone.now().isoformat(),
        "external_events": len(ctx.external_events),
        "ok": ok,
        "steps": results,
    }
    log.info(
        "post-restore reconciliation",
        extra={
            "action": "restore.reconcile",
            "outcome": "ok" if ok else "blocked",
            "mode": report["mode"],
        },
    )
    return report
