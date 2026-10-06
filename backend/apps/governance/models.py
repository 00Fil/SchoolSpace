import uuid
from django.db import models
from apps.education.models import Entity


class Decision(Entity):
    code = models.CharField(max_length=3, unique=True)
    title = models.CharField(max_length=180)
    proposed_default = models.TextField(blank=True)
    status = models.CharField(
        max_length=10,
        choices=[
            ("OPEN", "Aperta"),
            ("PROPOSED", "Proposta"),
            ("APPROVED", "Approvata"),
        ],
        default="OPEN",
    )
    owner = models.CharField(max_length=120, blank=True)
    outcome = models.TextField(blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return f"{self.code}: {self.title}"


class CommandReceipt(Entity):
    actor = models.ForeignKey("identity.Account", on_delete=models.PROTECT)
    operation = models.CharField(max_length=60)
    key = models.CharField(max_length=255)
    body_hash = models.CharField(max_length=64)
    response = models.JSONField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["actor", "operation", "key"], name="command_receipt_unique"
            )
        ]


class PathAuditEvent(models.Model):
    """Only the path service writes these; broader application audit remains pending."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    path = models.ForeignKey("education.LearningPath", on_delete=models.PROTECT)
    actor = models.ForeignKey("identity.Account", on_delete=models.PROTECT)
    operation = models.CharField(max_length=60)
    occurred_at = models.DateTimeField(auto_now_add=True)
    details = models.JSONField(default=dict)


class AppendOnlyQuerySet(models.QuerySet):
    """Nessuna modifica o cancellazione via ORM; in PostgreSQL vale anche il trigger (GAP-E08)."""

    def update(self, **kwargs):
        raise PermissionError("Registro append-only: modifica non consentita")

    def delete(self):
        raise PermissionError("Registro append-only: cancellazione non consentita")

    def bulk_update(self, *args, **kwargs):
        raise PermissionError("Registro append-only: modifica non consentita")


class AuditEvent(models.Model):
    """Audit unificato di inviti, deleghe, anagrafiche, export, privacy e admin (FR23)."""

    class Category(models.TextChoices):
        FAMILY = "FAMILY", "Famiglie e studenti"
        GUARDIANSHIP = "GUARDIANSHIP", "Deleghe"
        INVITE = "INVITE", "Inviti"
        EXPORT = "EXPORT", "Esportazioni"
        IMPORT = "IMPORT", "Importazioni"
        PRIVACY = "PRIVACY", "Diritti degli interessati"
        RETENTION = "RETENTION", "Conservazione"
        ADMIN = "ADMIN", "Amministrazione di emergenza"
        STAFF = "STAFF", "Tutor e utenti del centro"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    occurred_at = models.DateTimeField(auto_now_add=True, db_index=True)
    category = models.CharField(max_length=16, choices=Category.choices)
    operation = models.CharField(max_length=60)
    actor = models.ForeignKey(
        "identity.Account",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    object_type = models.CharField(max_length=80, blank=True)
    object_id = models.CharField(max_length=64, blank=True, db_index=True)
    object_version = models.PositiveIntegerField(null=True, blank=True)
    purpose = models.CharField(max_length=120, blank=True)
    reason = models.CharField(max_length=200, blank=True)
    command = models.CharField(max_length=120, blank=True)
    correlation_id = models.UUIDField(default=uuid.uuid4, db_index=True)
    details = models.JSONField(default=dict)

    objects = AppendOnlyQuerySet.as_manager()

    class Meta:
        ordering = ["occurred_at", "id"]
        indexes = [models.Index(fields=["category", "occurred_at"])]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise PermissionError("Registro append-only: modifica non consentita")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError("Registro append-only: cancellazione non consentita")
