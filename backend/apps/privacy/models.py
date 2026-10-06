"""Modelli privacy dello stream s4.

I modelli di ``apps.identity`` e ``apps.education`` non vengono modificati: i campi richiesti
dal paper (§4.2) e assenti nella v0.7 vivono qui, in relazione 1:1 (vedi README dell'app).
"""

import uuid

from django.conf import settings
from django.db import models
from django.db.models.functions import Lower


class Timestamped(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    version = models.PositiveIntegerField(default=1)

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self._state.adding:
            self.version = (self.version or 0) + 1
            if kwargs.get("update_fields") is not None:
                kwargs["update_fields"] = set(kwargs["update_fields"]) | {
                    "version",
                    "updated_at",
                }
        return super().save(*args, **kwargs)


class FamilyProfile(Timestamped):
    """Contatto autorizzato della famiglia (paper §4.2: Family). Nessuna password."""

    family = models.OneToOneField(
        "education.Family", on_delete=models.CASCADE, related_name="privacy_profile"
    )
    contact_name = models.CharField(max_length=120, blank=True)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=30, blank=True)
    anonymized_at = models.DateTimeField(null=True, blank=True)


class StudentProfile(Timestamped):
    """Dati facoltativi dello studente. La data di nascita serve solo al job della maggiore età."""

    student = models.OneToOneField(
        "education.Student", on_delete=models.CASCADE, related_name="privacy_profile"
    )
    birth_date = models.DateField(null=True, blank=True)
    anonymized_at = models.DateTimeField(null=True, blank=True)


class StudentImportKey(models.Model):
    """Chiave naturale dell'import iniziale (T17: stesse chiavi, nessun duplicato)."""

    id = models.BigAutoField(primary_key=True)
    source_key = models.CharField(max_length=80, unique=True)
    student = models.OneToOneField(
        "education.Student", on_delete=models.CASCADE, related_name="import_key"
    )
    created_at = models.DateTimeField(auto_now_add=True)


class GuardianLinkDetail(Timestamped):
    """Campi di GuardianLink previsti dal paper ma assenti nel modello v0.7."""

    class Relationship(models.TextChoices):
        PARENT = "PARENT", "Genitore"
        LEGAL_GUARDIAN = "LEGAL_GUARDIAN", "Tutore legale"
        DELEGATE = "DELEGATE", "Delegato autorizzato"

    class Reconfirmation(models.TextChoices):
        NOT_REQUIRED = "NOT_REQUIRED", "Non richiesta"
        PENDING = "PENDING", "Da riconfermare con lo studente maggiorenne"
        CONFIRMED = "CONFIRMED", "Riconfermata"
        DECLINED = "DECLINED", "Non riconfermata (revocata)"

    link = models.OneToOneField(
        "education.GuardianLink", on_delete=models.CASCADE, related_name="detail"
    )
    relationship = models.CharField(
        max_length=16, choices=Relationship.choices, default=Relationship.PARENT
    )
    can_receive_notifications = models.BooleanField(default=True)
    can_request_changes = models.BooleanField(default=False)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    verification_method = models.CharField(max_length=120, blank=True)
    revoked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    revocation_reason = models.CharField(max_length=200, blank=True)
    reconfirmation = models.CharField(
        max_length=12,
        choices=Reconfirmation.choices,
        default=Reconfirmation.NOT_REQUIRED,
    )
    reconfirmation_flagged_at = models.DateTimeField(null=True, blank=True)
    reconfirmation_due_at = models.DateTimeField(null=True, blank=True)
    reconfirmed_at = models.DateTimeField(null=True, blank=True)
    reconfirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )


class InvitationTerms(Timestamped):
    """Condizioni della delega proposte con un invito tutore di ``identity.Invitation``.

    Il sistema di inviti è unico (identity, s1): qui restano solo i campi del paper che
    l'invito non porta (relazione dichiarata, notifiche, richieste di modifica). Alla
    accettazione diventano il ``GuardianLinkDetail`` della delega creata da identity.
    """

    invitation = models.OneToOneField(
        "identity.Invitation", on_delete=models.CASCADE, related_name="privacy_terms"
    )
    relationship = models.CharField(
        max_length=16,
        choices=GuardianLinkDetail.Relationship.choices,
        default=GuardianLinkDetail.Relationship.PARENT,
    )
    can_receive_notifications = models.BooleanField(default=True)
    can_request_changes = models.BooleanField(default=False)
    import_batch = models.ForeignKey(
        "ImportBatch", on_delete=models.SET_NULL, null=True, blank=True
    )


class FamilyGuardian(Timestamped):
    """Genitore o tutore legale di una famiglia (v0.9.5).

    Nasce con l'iscrizione della famiglia, prima dei figli: l'invito di famiglia di
    identity porta il token; accettandolo l'account riceve una delega verificata su ogni
    figlio attivo della famiglia, e sui figli aggiunti dopo. Le deleghe restano
    ``GuardianLink`` per figlio: è da lì che il portale calcola cosa si vede.
    """

    family = models.ForeignKey(
        "education.Family", on_delete=models.PROTECT, related_name="guardians"
    )
    display_name = models.CharField(max_length=120)
    email = models.EmailField()
    phone = models.CharField(max_length=30, blank=True)
    relationship = models.CharField(
        max_length=16,
        choices=GuardianLinkDetail.Relationship.choices,
        default=GuardianLinkDetail.Relationship.PARENT,
    )
    can_manage_availability = models.BooleanField(default=True)
    can_receive_notifications = models.BooleanField(default=True)
    can_request_changes = models.BooleanField(default=True)
    invitation = models.OneToOneField(
        "identity.Invitation",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="family_guardian",
    )
    account = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="family_guardianships",
    )
    revoked_at = models.DateTimeField(null=True, blank=True)
    revocation_reason = models.CharField(max_length=200, blank=True)
    version = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [
            models.UniqueConstraint(
                Lower("email"),
                "family",
                condition=models.Q(revoked_at__isnull=True),
                name="family_guardian_active_unique",
            )
        ]


class RetentionPolicy(Timestamped):
    """Riga della matrice D09. Le durate di default sono proposte tecniche *da approvare*."""

    class Action(models.TextChoices):
        DELETE = "DELETE", "Cancellazione"
        MINIMIZE = "MINIMIZE", "Minimizzazione"
        REPORT = "REPORT", "Solo conteggio (nessuna azione automatica)"
        EXTERNAL = "EXTERNAL", "Gestita fuori dall'applicazione"

    class Status(models.TextChoices):
        PROPOSED = "PROPOSED", "Da approvare"
        APPROVED = "APPROVED", "Approvata"
        SUSPENDED = "SUSPENDED", "Sospesa"

    category = models.CharField(max_length=40, unique=True)
    label = models.CharField(max_length=120)
    purpose = models.CharField(max_length=200, blank=True)
    legal_basis = models.CharField(max_length=120, blank=True)
    duration_days = models.PositiveIntegerField(null=True, blank=True)
    action = models.CharField(max_length=10, choices=Action.choices)
    backup_note = models.CharField(max_length=200, blank=True)
    source = models.CharField(max_length=200, blank=True)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PROPOSED
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    approval_reference = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["category"]


class RetentionRun(models.Model):
    """Ricevuta del job di cancellazione/minimizzazione (paper §10.5)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    dry_run = models.BooleanField(default=True)
    reference_time = models.DateTimeField()
    results = models.JSONField(default=list)
    receipt_hash = models.CharField(max_length=64, blank=True)

    class Meta:
        ordering = ["-started_at"]


class PrivacyRequest(Timestamped):
    """Registro delle richieste degli interessati (artt. 12, 15-22).

    Nessuna FK verso l'interessato: il registro sopravvive a cancellazione e anonimizzazione.
    Ogni transizione viene anche scritta nel ledger esterno (``PRIVACY_LEDGER_PATH``).
    """

    class Kind(models.TextChoices):
        ACCESS = "ACCESS", "Accesso (art. 15)"
        RECTIFICATION = "RECTIFICATION", "Rettifica (art. 16)"
        ERASURE = "ERASURE", "Cancellazione (art. 17)"
        RESTRICTION = "RESTRICTION", "Limitazione (art. 18)"
        PORTABILITY = "PORTABILITY", "Portabilità (art. 20)"
        OBJECTION = "OBJECTION", "Opposizione (art. 21)"

    class SubjectType(models.TextChoices):
        STUDENT = "STUDENT", "Studente"
        ACCOUNT = "ACCOUNT", "Account (genitore, tutor, staff)"

    class Status(models.TextChoices):
        RECEIVED = "RECEIVED", "Ricevuta"
        VERIFIED = "VERIFIED", "Identità verificata"
        EXTENDED = "EXTENDED", "Prorogata (art. 12.3)"
        COMPLETED = "COMPLETED", "Evasa"
        REJECTED = "REJECTED", "Respinta"

    kind = models.CharField(max_length=14, choices=Kind.choices)
    subject_type = models.CharField(max_length=8, choices=SubjectType.choices)
    subject_id = models.UUIDField(db_index=True)
    subject_pseudonym = models.CharField(max_length=24)
    channel = models.CharField(max_length=60)
    requester_role = models.CharField(max_length=60)
    received_at = models.DateTimeField()
    due_at = models.DateTimeField()
    status = models.CharField(
        max_length=9, choices=Status.choices, default=Status.RECEIVED
    )
    identity_verified_at = models.DateTimeField(null=True, blank=True)
    identity_verification = models.CharField(max_length=200, blank=True)
    extension_reason = models.CharField(max_length=200, blank=True)
    outcome = models.CharField(max_length=40, blank=True)
    motivation = models.CharField(max_length=500, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    handled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        ordering = ["due_at"]


class ProtectedExport(models.Model):
    """Export protetto: audience nominativa, scadenza e token monouso (GAP-H07, T42)."""

    class Format(models.TextChoices):
        JSON = "json", "JSON"
        CSV = "csv", "CSV"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    audience = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    purpose = models.CharField(max_length=60)
    privacy_request = models.ForeignKey(
        PrivacyRequest, on_delete=models.PROTECT, null=True, blank=True
    )
    format = models.CharField(max_length=4, choices=Format.choices)
    filename = models.CharField(max_length=120)
    storage_name = models.CharField(max_length=80, blank=True)
    size_bytes = models.PositiveIntegerField(default=0)
    sha256 = models.CharField(max_length=64)
    token_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    downloaded_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    purged_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]


class ImportBatch(models.Model):
    """Esecuzione dell'import iniziale da template CSV versionato (GAP-H06, T17)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    template_version = models.CharField(max_length=10)
    file_sha256 = models.CharField(max_length=64)
    dry_run = models.BooleanField()
    status = models.CharField(max_length=10)
    rows = models.PositiveIntegerField(default=0)
    summary = models.JSONField(default=dict)
    errors = models.JSONField(default=list)
    minimized_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]


class NoticeAcknowledgement(models.Model):
    """P6 · C04: presa visione esplicita e versionata dell'informativa (artt. 12-14 GDPR).
    Una riga per account e versione; una nuova versione richiede una nuova presa visione."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notice_acks"
    )
    version = models.CharField(max_length=20)
    channel = models.CharField(max_length=20, default="PORTALE")
    acknowledged_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["account", "version"], name="notice_ack_once_per_version")
        ]
