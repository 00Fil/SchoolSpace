import uuid
import unicodedata

from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models
from django.db.models.functions import Lower

from apps.scheduling.revision import TrackedQuerySet


def normalize_email(value):
    """Identificativo di login: NFC, senza spazi esterni, minuscolo (GAP-B01)."""
    if value is None:
        return ""
    return unicodedata.normalize("NFC", str(value)).strip().lower()


class AccountManager(UserManager.from_queryset(TrackedQuerySet)):
    @classmethod
    def normalize_email(cls, email):
        return normalize_email(email)

    def get_by_email(self, email):
        return self.get(email__iexact=normalize_email(email))


class Account(AbstractUser):
    objects = AccountManager()
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    email_verified = models.BooleanField(default=False)
    # MFA richiesta esplicitamente per l'account, oltre ai ruoli in MFA_REQUIRED_ROLES.
    mfa_required = models.BooleanField(default=False)

    class Meta(AbstractUser.Meta):
        constraints = [
            models.UniqueConstraint(Lower("email"), name="account_email_ci_unique")
        ]

    def save(self, *args, **kwargs):
        self.email = normalize_email(self.email)
        if kwargs.get("update_fields") == ["last_login"] or kwargs.get(
            "update_fields"
        ) == {"last_login"}:
            return super().save(*args, **kwargs)
        from django.db import transaction
        from apps.scheduling.revision import lock_revision, bump_revision

        with transaction.atomic():
            lock_revision()
            result = super().save(*args, **kwargs)
            bump_revision()
            return result


class RoleGrant(models.Model):
    class Role(models.TextChoices):
        CENTER = "CENTER", "Centro"
        TUTOR = "TUTOR", "Tutor"
        GUARDIAN = "GUARDIAN", "Tutore"
        STUDENT = "STUDENT", "Studente"

    account = models.ForeignKey(
        Account, on_delete=models.PROTECT, related_name="role_grants"
    )
    role = models.CharField(max_length=12, choices=Role.choices)
    valid_from = models.DateTimeField()
    valid_until = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(valid_until__isnull=True)
                | models.Q(valid_until__gt=models.F("valid_from")),
                name="role_valid_period",
            )
        ]


class AppendOnlyQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise TypeError("Audit events are append-only")

    def delete(self):
        raise TypeError("Audit events are append-only")


class IdentityAuditEvent(models.Model):
    """Audit append-only di accessi, inviti, MFA, sessioni e deleghe (FR23, GAP-B06).

    Non contiene mai password, token, codici MFA o segreti: solo identificativi e metadati.
    Su PostgreSQL un trigger rifiuta UPDATE e DELETE (migrazione 0004).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    occurred_at = models.DateTimeField(auto_now_add=True, db_index=True)
    actor = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="identity_actions",
    )
    subject = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="identity_events",
    )
    operation = models.CharField(max_length=60, db_index=True)
    object_id = models.UUIDField(null=True, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    details = models.JSONField(default=dict, blank=True)

    objects = AppendOnlyQuerySet.as_manager()

    class Meta:
        ordering = ["occurred_at", "id"]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise TypeError("Audit events are append-only")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise TypeError("Audit events are append-only")


class Invitation(models.Model):
    """Invito monouso (GAP-B02). Il token in chiaro esiste solo nel messaggio inviato."""

    class Status(models.TextChoices):
        PENDING_VERIFICATION = "PENDING_VERIFICATION", "Relazione da verificare"
        SENT = "SENT", "Inviato"
        ACCEPTED = "ACCEPTED", "Accettato"
        REVOKED = "REVOKED", "Revocato"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField()
    role = models.CharField(max_length=12, choices=RoleGrant.Role.choices)
    student = models.ForeignKey(
        "education.Student",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="invitations",
    )
    # v0.9.5: invito di famiglia. Il genitore/tutore entra prima dei figli e, accettando,
    # riceve la delega su tutti i figli attivi della famiglia (e su quelli aggiunti dopo).
    family = models.ForeignKey(
        "education.Family",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="invitations",
    )
    can_manage_availability = models.BooleanField(default=False)
    status = models.CharField(
        max_length=24, choices=Status.choices, default=Status.PENDING_VERIFICATION
    )
    token_hash = models.CharField(max_length=64, unique=True, null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    # Accesso immediato via QR mostrato dal centro: token separato e breve, così l'email
    # già inviata resta valida (la sua consegna è legata alla versione dell'invito).
    qr_token_hash = models.CharField(max_length=64, unique=True, null=True, blank=True)
    qr_expires_at = models.DateTimeField(null=True, blank=True)
    send_count = models.PositiveSmallIntegerField(default=0)
    created_by = models.ForeignKey(
        Account, on_delete=models.PROTECT, related_name="invitations_created"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    relation_verified_by = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="invitation_relations_verified",
    )
    relation_verified_at = models.DateTimeField(null=True, blank=True)
    relation_evidence = models.CharField(max_length=200, blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    accepted_account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="invitations_accepted",
    )
    revoked_at = models.DateTimeField(null=True, blank=True)
    version = models.PositiveIntegerField(default=1)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(role__in=["GUARDIAN", "STUDENT"])
                | models.Q(student__isnull=False)
                | models.Q(role="GUARDIAN", family__isnull=False),
                name="invitation_student_required",
            ),
            models.CheckConstraint(
                condition=~models.Q(role="GUARDIAN")
                | models.Q(token_hash__isnull=True)
                | models.Q(relation_verified_at__isnull=False),
                name="invitation_guardian_verified_before_token",
            ),
            models.CheckConstraint(
                condition=models.Q(token_hash__isnull=True)
                | models.Q(expires_at__isnull=False),
                name="invitation_token_expires",
            ),
            # Un solo invito aperto per email+ruolo(+studente); due vincoli parziali perché
            # NULLS NOT DISTINCT non è portabile (PostgreSQL < 15, SQLite).
            models.UniqueConstraint(
                Lower("email"),
                "role",
                "student",
                condition=models.Q(
                    status__in=["PENDING_VERIFICATION", "SENT"], student__isnull=False
                ),
                name="invitation_open_unique_student",
            ),
            models.UniqueConstraint(
                Lower("email"),
                "role",
                condition=models.Q(
                    status__in=["PENDING_VERIFICATION", "SENT"],
                    student__isnull=True,
                    family__isnull=True,
                ),
                name="invitation_open_unique",
            ),
            models.UniqueConstraint(
                Lower("email"),
                "role",
                "family",
                condition=models.Q(
                    status__in=["PENDING_VERIFICATION", "SENT"], family__isnull=False
                ),
                name="invitation_open_unique_family",
            ),
        ]

    def save(self, *args, **kwargs):
        self.email = normalize_email(self.email)
        return super().save(*args, **kwargs)


class PasswordResetToken(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(
        Account, on_delete=models.CASCADE, related_name="password_reset_tokens"
    )
    token_hash = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)


class TOTPDevice(models.Model):
    """Dispositivo TOTP (RFC 6238). Il segreto non è mai esposto dopo la configurazione."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.OneToOneField(
        Account, on_delete=models.CASCADE, related_name="totp_device"
    )
    secret = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    last_used_step = models.BigIntegerField(default=0)


class RecoveryCode(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(
        Account, on_delete=models.CASCADE, related_name="recovery_codes"
    )
    code_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["account", "code_hash"], name="recovery_code_unique"
            )
        ]


class UserSession(models.Model):
    """Registro server-side delle sessioni attive (revoca singola o totale, GAP-B04).

    Conserva solo l'hash della chiave di sessione; la sessione Django contiene l'id del record.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(
        Account, on_delete=models.CASCADE, related_name="sessions"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField()
    mfa_verified_at = models.DateTimeField(null=True, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=200, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_reason = models.CharField(max_length=40, blank=True)

    class Meta:
        indexes = [models.Index(fields=["account", "revoked_at"])]


class StudentAccessPolicy(models.Model):
    """Policy esplicita per lo studente maggiorenne (D07, GAP-B07).

    L'età da sola non cambia gli accessi: il centro conferma la maggiore età e la modalità
    d'accesso dei tutori; senza record valgono le deleghe ordinarie.
    """

    class GuardianAccess(models.TextChoices):
        DEFAULT = "DEFAULT", "Default configurato"
        KEEP = "KEEP", "Mantieni le deleghe esistenti"
        CONSENT_REQUIRED = "CONSENT_REQUIRED", "Solo con consenso dello studente"
        NONE = "NONE", "Nessun accesso dei tutori"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.OneToOneField(
        "education.Student", on_delete=models.PROTECT, related_name="access_policy"
    )
    adult_confirmed = models.BooleanField(default=False)
    guardian_access = models.CharField(
        max_length=20, choices=GuardianAccess.choices, default=GuardianAccess.DEFAULT
    )
    student_consent_at = models.DateTimeField(null=True, blank=True)
    confirmed_by = models.ForeignKey(
        Account, on_delete=models.PROTECT, related_name="student_policies_confirmed"
    )
    updated_at = models.DateTimeField(auto_now=True)
    version = models.PositiveIntegerField(default=1)
