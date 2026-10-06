"""Matrice di retention D09 e job di cancellazione/minimizzazione con ricevuta (GAP-H04).

* La matrice vive nel DB (``RetentionPolicy``) ed è modificabile solo dal centro con audit.
* I default sono le *proposte tecniche* della guida (reg2, paper §10.5): stato ``PROPOSED``.
* Il job in esecuzione reale agisce solo sulle categorie ``APPROVED`` con durata definita;
  il dry-run conta sempre e non modifica nulla. Ogni run produce una ricevuta con hash,
  salvata nel DB e nel ledger esterno.
"""

import hashlib
import json
from datetime import timedelta

from django.apps import apps as django_apps
from django.db import connection, models, transaction
from django.utils import timezone

from apps.governance.audit import record

from .errors import PrivacyError
from .models import (
    ImportBatch,
    ProtectedExport,
    RetentionPolicy,
    RetentionRun,
)

A = RetentionPolicy.Action

# (categoria, etichetta, finalità, base, giorni proposti, azione, nota backup, fonte)
DEFAULT_MATRIX = [
    (
        "diagnostic_logs",
        "Log diagnostici applicativi",
        "Diagnosi e sicurezza",
        "Art. 6.1.f",
        30,
        A.EXTERNAL,
        "",
        "Paper §10.5; cancellazione nel sistema di log (fuori dall'app)",
    ),
    (
        "idempotency_keys",
        "Chiavi di idempotenza (ricevute dei comandi)",
        "Prevenire doppie esecuzioni",
        "Art. 6.1.b",
        30,
        A.DELETE,
        "",
        "Paper §10.5",
    ),
    (
        "notification_deliveries",
        "Delivery delle notifiche",
        "Prova di consegna",
        "Art. 6.1.b",
        90,
        A.EXTERNAL,
        "",
        "Paper §10.5; gestita dal modulo comunicazioni (contatori aggregati)",
    ),
    (
        "solver_snapshots",
        "Snapshot e input del solver",
        "Riproducibilità della pianificazione",
        "Art. 6.1.b",
        90,
        A.REPORT,
        "",
        "Proposta tecnica: il payload alimenta i trigger del calendario, solo conteggio",
    ),
    (
        "audit_events",
        "Audit di sicurezza e operativo",
        "Sicurezza e responsabilizzazione",
        "Art. 6.1.f, art. 32",
        None,
        A.MINIMIZE,
        "",
        "Da approvare (indicativamente 12-24 mesi); richiede ruolo owner",
    ),
    (
        "identity_audit_ip",
        "Indirizzi IP nell'audit di accesso (identity)",
        "Sicurezza degli accessi e prevenzione abusi",
        "Art. 6.1.f, art. 32",
        90,
        A.MINIMIZE,
        "",
        "Proposta tecnica: IP azzerato, evento conservato con la durata dell'audit",
    ),
    (
        "calendar_attendance",
        "Calendario, presenze, recuperi",
        "Erogazione e contestazioni",
        "Art. 6.1.b",
        None,
        A.REPORT,
        "",
        "Anno didattico + periodo da approvare con il consulente (art. 2946 c.c.)",
    ),
    (
        "revoked_accounts",
        "Account revocati",
        "Sicurezza dopo la revoca",
        "Art. 6.1.f",
        90,
        A.MINIMIZE,
        "",
        "Revoca immediata nel live; minimizzazione a 30-90 giorni",
    ),
    (
        "invitations",
        "Inviti e token",
        "Attivazione account",
        "Art. 6.1.b",
        7,
        A.DELETE,
        "",
        "Fino a scadenza o uso, poi purge (si conserva solo l'hash)",
    ),
    (
        "protected_exports",
        "File degli export protetti",
        "Esercizio dei diritti (artt. 15, 20)",
        "Art. 6.1.c",
        0,
        A.MINIMIZE,
        "",
        "Cancellazione del file alla scadenza del download; resta la riga di audit",
    ),
    (
        "import_reports",
        "Report degli import iniziali",
        "Verifica dell'import",
        "Art. 6.1.b",
        90,
        A.MINIMIZE,
        "",
        "Proposta tecnica: si conservano hash e conteggi, non gli errori per riga",
    ),
    (
        "privacy_requests",
        "Registro delle richieste privacy",
        "Responsabilizzazione (art. 5.2)",
        "Art. 6.1.c",
        None,
        A.REPORT,
        "",
        "Da approvare; il ledger esterno segue la stessa durata",
    ),
    (
        "backups_pitr",
        "Backup PITR",
        "Continuità operativa",
        "Come il dato d'origine, art. 32",
        35,
        A.EXTERNAL,
        "Finestra 7-35 giorni (D09) sul servizio gestito",
        "Scadenza automatica del provider",
    ),
    (
        "logical_exports",
        "Export logici di controllo (pg_dump)",
        "Ripristino",
        "Come il dato d'origine, art. 32",
        90,
        A.EXTERNAL,
        "Storage separato con object lock, 30-90 giorni",
        "Gestito dall'infrastruttura",
    ),
]


def seed_default_matrix(using="default"):
    """Idempotente: non sovrascrive righe già modificate o approvate."""
    created = 0
    for row in DEFAULT_MATRIX:
        category, label, purpose, basis, days, action, backup, source = row
        _, was_created = RetentionPolicy.objects.using(using).get_or_create(
            category=category,
            defaults=dict(
                label=label,
                purpose=purpose,
                legal_basis=basis,
                duration_days=days,
                action=action,
                backup_note=backup,
                source=source,
            ),
        )
        created += int(was_created)
    return created


# --- Gestione della matrice -------------------------------------------------

EDITABLE = {"duration_days", "action", "purpose", "legal_basis", "backup_note"}


@transaction.atomic
def update_policy(actor, policy, *, expected_version, changes, reason):
    from .registry import check_version, require_center, require_reason

    require_center(actor)
    reason = require_reason(reason)
    policy = RetentionPolicy.objects.select_for_update().get(pk=policy.pk)
    check_version(policy, expected_version)
    unknown = set(changes) - EDITABLE
    if unknown:
        raise PrivacyError("NOT_EDITABLE", ", ".join(sorted(unknown)))
    before = {k: getattr(policy, k) for k in changes}
    for key, value in changes.items():
        setattr(policy, key, value)
    # Ogni modifica sostanziale torna "da approvare".
    policy.status = RetentionPolicy.Status.PROPOSED
    policy.approved_by = None
    policy.approved_at = None
    policy.save()
    record(
        "RETENTION",
        "POLICY_UPDATED",
        actor=actor,
        obj=policy,
        reason=reason,
        details={"before": before, "after": changes},
    )
    return policy


@transaction.atomic
def approve_policy(actor, policy, *, expected_version, reference, reason):
    from .registry import check_version, require_center, require_reason

    require_center(actor)
    reason = require_reason(reason)
    policy = RetentionPolicy.objects.select_for_update().get(pk=policy.pk)
    check_version(policy, expected_version)
    if policy.action in (A.DELETE, A.MINIMIZE) and policy.duration_days is None:
        raise PrivacyError(
            "DURATION_REQUIRED", "Durata da definire prima dell'approvazione"
        )
    if not isinstance(reference, str) or not reference.strip():
        raise PrivacyError(
            "REFERENCE_REQUIRED", "Indicare il verbale D09 di approvazione"
        )
    policy.status = RetentionPolicy.Status.APPROVED
    policy.approved_by = actor
    policy.approved_at = timezone.now()
    policy.approval_reference = reference.strip()[:200]
    policy.save()
    record(
        "RETENTION",
        "POLICY_APPROVED",
        actor=actor,
        obj=policy,
        reason=reason,
        details={"reference": policy.approval_reference},
    )
    return policy


# --- Handler per categoria ----------------------------------------------------


class Handler:
    """``count`` e ``apply`` ricevono il limite temporale (righe più vecchie del cutoff)."""

    available = True

    def queryset(self, cutoff):
        raise NotImplementedError

    def count(self, cutoff):
        return self.queryset(cutoff).count()

    def apply(self, cutoff, action):
        raise NotImplementedError


class IdempotencyKeys(Handler):
    def queryset(self, cutoff):
        from apps.governance.models import CommandReceipt

        return CommandReceipt.objects.filter(created_at__lt=cutoff)

    def apply(self, cutoff, action):
        return self.queryset(cutoff).delete()[0]


class Invitations(Handler):
    """Inviti di identity chiusi (accettati/revocati) o scaduti da prima del cutoff.

    Contengono l'email dell'invitato; il token in chiaro non è mai stato salvato.
    """

    def queryset(self, cutoff):
        from apps.identity.models import Invitation

        return Invitation.objects.filter(
            models.Q(status="SENT", expires_at__lt=cutoff)
            | models.Q(status="ACCEPTED", accepted_at__lt=cutoff)
            | models.Q(status="REVOKED", revoked_at__lt=cutoff)
        )

    def apply(self, cutoff, action):
        return self.queryset(cutoff).delete()[0]


class IdentityAuditIp(Handler):
    """IP nell'audit di identity (s1): azzerato dopo la durata approvata."""

    def queryset(self, cutoff):
        from apps.identity.models import IdentityAuditEvent

        return IdentityAuditEvent.objects.filter(
            occurred_at__lt=cutoff, ip__isnull=False
        )

    def apply(self, cutoff, action):
        return _maintenance_update(self.queryset(cutoff), ip=None)


def _maintenance_update(queryset, **values):
    """UPDATE su tabelle append-only: consentito solo al proprietario (trigger GAP-E08)."""
    with transaction.atomic():
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL app.audit_maintenance = 'on'")
        return models.QuerySet.update(queryset, **values)


class Exports(Handler):
    def queryset(self, cutoff):
        return ProtectedExport.objects.filter(purged_at__isnull=True).filter(
            models.Q(expires_at__lt=cutoff)
            | models.Q(downloaded_at__lt=cutoff)
            | models.Q(revoked_at__lt=cutoff)
        )

    def apply(self, cutoff, action):
        from .exports import purge_file

        done = 0
        for export in self.queryset(cutoff):
            purge_file(export)
            done += 1
        return done + sweep_orphan_files()


def sweep_orphan_files(min_age_seconds=3600):
    """File rimasti senza riga (es. rollback dopo la scrittura): si cancellano."""
    import time

    from .exports import export_dir

    known = set(
        ProtectedExport.objects.exclude(storage_name="").values_list(
            "storage_name", flat=True
        )
    )
    removed = 0
    for path in export_dir().iterdir():
        if (
            path.is_file()
            and path.name not in known
            and time.time() - path.stat().st_mtime > min_age_seconds
        ):
            path.unlink()
            removed += 1
    return removed


class ImportReports(Handler):
    def queryset(self, cutoff):
        return ImportBatch.objects.filter(
            created_at__lt=cutoff, minimized_at__isnull=True
        )

    def apply(self, cutoff, action):
        return self.queryset(cutoff).update(errors=[], minimized_at=timezone.now())


class RevokedAccounts(Handler):
    """Account disattivati e senza ruoli attivi da prima del cutoff: si pseudonimizzano."""

    def queryset(self, cutoff):
        from django.contrib.auth import get_user_model

        Account = get_user_model()
        now = timezone.now()
        active_grants = models.Q(
            role_grants__revoked_at__isnull=True,
            role_grants__valid_from__lte=now,
        ) & (
            models.Q(role_grants__valid_until__isnull=True)
            | models.Q(role_grants__valid_until__gt=now)
        )
        candidates = (
            Account.objects.filter(is_active=False, is_superuser=False)
            .exclude(email__endswith="@anonimizzato.invalid")
            .exclude(active_grants)
        )
        # Il riferimento temporale è l'ultima revoca registrata nell'audit o nei ruoli.
        recent = Account.objects.filter(
            role_grants__revoked_at__gte=cutoff
        ).values_list("pk", flat=True)
        never_used = models.Q(last_login__isnull=True, date_joined__lt=cutoff)
        old_login = models.Q(last_login__lt=cutoff)
        return (
            candidates.exclude(pk__in=recent).filter(never_used | old_login).distinct()
        )

    def apply(self, cutoff, action):
        from .subjects import anonymize_account

        done = 0
        for account in self.queryset(cutoff):
            anonymize_account(account, reason="retention: account revocato")
            done += 1
        return done


class AuditEvents(Handler):
    """Minimizzazione dell'audit unificato e di quello identity: restano operazione,
    data e oggetto; spariscono attore, dettagli e IP."""

    def _identity(self, cutoff):
        from apps.identity.models import IdentityAuditEvent

        return IdentityAuditEvent.objects.filter(occurred_at__lt=cutoff).exclude(
            details={"minimized": True}
        )

    def queryset(self, cutoff):
        from apps.governance.models import AuditEvent

        return AuditEvent.objects.filter(occurred_at__lt=cutoff).exclude(
            details={"minimized": True}
        )

    def count(self, cutoff):
        return self.queryset(cutoff).count() + self._identity(cutoff).count()

    def apply(self, cutoff, action):
        done = _maintenance_update(
            self.queryset(cutoff), actor=None, details={"minimized": True}, reason=""
        )
        return done + _maintenance_update(
            self._identity(cutoff),
            actor=None,
            ip=None,
            details={"minimized": True},
        )


class SolverSnapshots(Handler):
    def queryset(self, cutoff):
        from apps.scheduling.models import PlanningSnapshot

        return PlanningSnapshot.objects.filter(created_at__lt=cutoff)


class CalendarAttendance(Handler):
    def queryset(self, cutoff):
        model = _optional_model("lesson_calendar", "LessonOccurrence")
        return model.objects.filter(end_at__lt=cutoff)


class PrivacyRequests(Handler):
    def queryset(self, cutoff):
        from .models import PrivacyRequest

        return PrivacyRequest.objects.filter(closed_at__lt=cutoff)


class External(Handler):
    available = False


def _optional_model(app_label, name):
    return django_apps.get_model(app_label, name)


HANDLERS = {
    "idempotency_keys": IdempotencyKeys(),
    "invitations": Invitations(),
    "identity_audit_ip": IdentityAuditIp(),
    "protected_exports": Exports(),
    "import_reports": ImportReports(),
    "revoked_accounts": RevokedAccounts(),
    "audit_events": AuditEvents(),
    "solver_snapshots": SolverSnapshots(),
    "calendar_attendance": CalendarAttendance(),
    "privacy_requests": PrivacyRequests(),
}


def receipt_digest(payload):
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(body.encode()).hexdigest()


def run_retention(*, actor=None, dry_run=True, categories=None, now=None):
    """Esegue (o simula) la matrice. Restituisce la ``RetentionRun`` con ricevuta."""
    now = now or timezone.now()
    policies = RetentionPolicy.objects.all()
    if categories:
        unknown = set(categories) - set(policies.values_list("category", flat=True))
        if unknown:
            raise PrivacyError("UNKNOWN_CATEGORY", ", ".join(sorted(unknown)))
        policies = policies.filter(category__in=categories)
    results = []
    for policy in policies.order_by("category"):
        handler = HANDLERS.get(policy.category, External())
        entry = {
            "category": policy.category,
            "policy_version": policy.version,
            "status": policy.status,
            "action": policy.action,
            "duration_days": policy.duration_days,
        }
        if policy.action == A.EXTERNAL or not handler.available:
            entry.update(outcome="EXTERNAL", affected=None)
        elif policy.duration_days is None:
            entry.update(outcome="DURATION_UNDEFINED", affected=None)
        else:
            cutoff = now - timedelta(days=policy.duration_days)
            entry["cutoff"] = cutoff.isoformat()
            try:
                eligible = handler.count(cutoff)
            except LookupError:
                entry.update(outcome="NOT_INSTALLED", affected=None)
                results.append(entry)
                continue
            entry["eligible"] = eligible
            if dry_run:
                entry.update(outcome="DRY_RUN", affected=0)
            elif policy.status != RetentionPolicy.Status.APPROVED:
                entry.update(outcome="NOT_APPROVED", affected=0)
            elif policy.action == A.REPORT:
                entry.update(outcome="REPORTED", affected=0)
            else:
                with transaction.atomic():
                    affected = handler.apply(cutoff, policy.action)
                entry.update(outcome="APPLIED", affected=affected)
        results.append(entry)
    run = RetentionRun(
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        dry_run=dry_run,
        reference_time=now,
        results=results,
    )
    run.finished_at = timezone.now()
    run.receipt_hash = receipt_digest(
        {
            "id": str(run.id),
            "dry_run": dry_run,
            "reference_time": now.isoformat(),
            "results": results,
        }
    )
    with transaction.atomic():
        run.save()
        record(
            "RETENTION",
            "RETENTION_DRY_RUN" if dry_run else "RETENTION_EXECUTED",
            actor=actor,
            obj=run,
            command="privacy_retention",
            details={
                "receipt_hash": run.receipt_hash,
                "applied": {
                    r["category"]: r["affected"]
                    for r in results
                    if r["outcome"] == "APPLIED"
                },
            },
        )
    if not dry_run:
        from .ledger import append

        append(
            "RETENTION_EXECUTED",
            run=str(run.id),
            receipt=run.receipt_hash,
            applied={
                r["category"]: r["affected"]
                for r in results
                if r["outcome"] == "APPLIED"
            },
        )
    return run
