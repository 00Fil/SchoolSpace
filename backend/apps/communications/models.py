"""Outbox persistente, consegne tracciate, notifiche interne, preferenze, feed ICS e link video.

Principi (paper §7.4, FR20, T22, T23):
- ``OutboxEvent`` e ``Delivery`` sono scritti nella stessa transazione del cambiamento di
  dominio (vedi ``services.emit``); code e broker non sono fonte di verità.
- ``event + recipient + channel`` è chiave univoca della consegna.
- ``DeliveryAttempt`` è append-only: ogni tentativo resta tracciato.
- Le notifiche interne sono deduplicate da un vincolo di unicità nel database.
- Le email non promettono exactly-once: l'esito ambiguo è uno stato esplicito.
"""

import uuid
from django.conf import settings
from django.db import models
from django.db.models import Q


class Category(models.TextChoices):
    SERVICE = "SERVICE", "Servizio"
    # Categoria separata: la baseline non invia marketing (paper §7.4).
    MARKETING = "MARKETING", "Promozionale"


class Channel(models.TextChoices):
    IN_APP = "IN_APP", "Notifica nel portale"
    EMAIL = "EMAIL", "Email"


class OutboxEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event_type = models.CharField(max_length=60)
    category = models.CharField(
        max_length=10, choices=Category.choices, default=Category.SERVICE
    )
    idempotency_key = models.CharField(max_length=200, unique=True)
    payload_hash = models.CharField(max_length=64)
    payload = models.JSONField(default=dict)
    subject_ref = models.CharField(max_length=100, blank=True, db_index=True)
    # Nome dell'autorizzatore (``authorization.AUTHORIZERS``) ricontrollato all'invio.
    audience = models.CharField(max_length=40, blank=True)
    # Messaggi di sicurezza (inviti, reset): non disattivabili dalle preferenze.
    essential = models.BooleanField(default=False)
    # Le consegne hanno un ``SealedSecret``: senza segreto valido non si invia.
    sealed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=Q(category__in=["SERVICE", "MARKETING"]),
                name="outbox_category_enum",
            )
        ]

    def __str__(self):
        return f"{self.event_type} {self.idempotency_key}"


class DeliveryStatus(models.TextChoices):
    PENDING = "PENDING", "In attesa"
    SENDING = "SENDING", "In invio"
    SENT = "SENT", "Consegnata al canale"
    AMBIGUOUS = "AMBIGUOUS", "Esito ambiguo: in riconciliazione"
    DEAD = "DEAD", "Dead-letter: da verificare"
    SKIPPED = "SKIPPED", "Non inviata (preferenze o recapito assente)"
    CANCELLED = "CANCELLED", "Annullata dal centro"
    REVOKED = "REVOKED", "Annullata: destinatario non più autorizzato"
    EXPIRED = "EXPIRED", "Annullata: contenuto riservato scaduto"


DELIVERY_STATES = [s.value for s in DeliveryStatus]


class Delivery(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey(
        OutboxEvent, on_delete=models.PROTECT, related_name="deliveries"
    )
    # Account destinatario; nullo solo per inviti a indirizzi senza account.
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
    )
    # Indirizzo fissato all'emissione (inviti/reset); vuoto = email corrente dell'account.
    address = models.EmailField(blank=True)
    channel = models.CharField(max_length=8, choices=Channel.choices)
    # Contesto minimo e specifico del destinatario (es. nomi dei propri figli).
    context = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=10, choices=DeliveryStatus.choices, default=DeliveryStatus.PENDING
    )
    attempts = models.PositiveSmallIntegerField(default=0)
    next_attempt_at = models.DateTimeField()
    lease_until = models.DateTimeField(null=True, blank=True)
    enqueued_at = models.DateTimeField(null=True, blank=True)
    provider = models.CharField(max_length=20, blank=True)
    provider_message_id = models.CharField(max_length=200, blank=True)
    last_error_code = models.CharField(max_length=60, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["event", "recipient", "channel"],
                name="delivery_event_recipient_channel_uq",
            ),
            models.UniqueConstraint(
                fields=["event", "address", "channel"],
                condition=Q(recipient__isnull=True),
                name="delivery_event_address_channel_uq",
            ),
            models.CheckConstraint(
                condition=Q(recipient__isnull=False)
                | (~Q(address="") & Q(channel="EMAIL")),
                name="delivery_has_target",
            ),
            models.CheckConstraint(
                condition=Q(status__in=DELIVERY_STATES)
                & Q(channel__in=["IN_APP", "EMAIL"]),
                name="delivery_enums",
            ),
        ]
        indexes = [models.Index(fields=["status", "next_attempt_at"])]

    @property
    def idempotency_key(self):
        """Chiave stabile verso il provider: una per event+recipient+channel."""
        return f"delivery-{self.id}"


class AppendOnlyModel(models.Model):
    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise RuntimeError("Registro append-only: modifica non consentita")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise RuntimeError("Registro append-only: cancellazione non consentita")


class DeliveryAttempt(AppendOnlyModel):
    class Outcome(models.TextChoices):
        ACCEPTED = "ACCEPTED", "Accettata"
        DUPLICATE_SUPPRESSED = "DUPLICATE_SUPPRESSED", "Duplicato soppresso"
        TRANSIENT_ERROR = "TRANSIENT_ERROR", "Errore temporaneo"
        PERMANENT_ERROR = "PERMANENT_ERROR", "Errore permanente"
        AMBIGUOUS = "AMBIGUOUS", "Esito ambiguo"
        LEASE_EXPIRED = "LEASE_EXPIRED", "Worker interrotto durante l'invio"
        RECONCILED_SENT = "RECONCILED_SENT", "Riconciliata: accettata dal provider"
        RECONCILED_NOT_FOUND = "RECONCILED_NOT_FOUND", "Riconciliata: non ricevuta"
        RECONCILED_UNKNOWN = "RECONCILED_UNKNOWN", "Riconciliazione non conclusiva"
        SKIPPED = "SKIPPED", "Non inviata"
        REVOKED = "REVOKED", "Destinatario non più autorizzato"
        EXPIRED = "EXPIRED", "Contenuto riservato scaduto o non disponibile"
        MANUAL = "MANUAL", "Decisione manuale del centro"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    delivery = models.ForeignKey(
        Delivery, on_delete=models.PROTECT, related_name="attempt_log"
    )
    number = models.PositiveSmallIntegerField()
    outcome = models.CharField(max_length=24, choices=Outcome.choices)
    error_code = models.CharField(max_length=60, blank=True)
    provider_message_id = models.CharField(max_length=200, blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    note = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [models.Index(fields=["delivery", "created_at"])]


class SealedSecret(models.Model):
    """Segreto effimero di una consegna (es. token di invito), cifrato con Fernet.

    Il chiaro esiste solo in memoria al momento dell'emissione e nel corpo dell'email
    renderizzata all'invio. Il record è cancellato appena la consegna raggiunge uno
    stato finale e scade comunque con il token che protegge.
    """

    delivery = models.OneToOneField(
        Delivery, on_delete=models.CASCADE, primary_key=True, related_name="sealed"
    )
    ciphertext = models.TextField()
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)


class Notification(models.Model):
    """Notifica interna; ``event + recipient`` unico: un retry non crea un duplicato."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    event = models.ForeignKey(
        OutboxEvent, on_delete=models.PROTECT, related_name="notifications"
    )
    category = models.CharField(max_length=10, choices=Category.choices)
    kind = models.CharField(max_length=60)
    title = models.CharField(max_length=160)
    body = models.CharField(max_length=500)
    subject_ref = models.CharField(max_length=100, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["event", "recipient"], name="notification_event_recipient_uq"
            )
        ]
        indexes = [models.Index(fields=["recipient", "read_at", "created_at"])]


class ChannelPreference(models.Model):
    account = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+"
    )
    category = models.CharField(max_length=10, choices=Category.choices)
    channel = models.CharField(max_length=8, choices=Channel.choices)
    enabled = models.BooleanField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["account", "category", "channel"],
                name="preference_account_category_channel_uq",
            )
        ]


class CalendarFeedToken(models.Model):
    """Token personale per l'export ICS. Solo l'hash SHA-256 è salvato."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    token_hash = models.CharField(max_length=64, unique=True)
    label = models.CharField(max_length=60, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)


class MeetingLink(models.Model):
    """Link video gestito dal centro: per singola lezione (preferito) o per canale video.

    Mai incluso in payload, email, notifiche o export ICS: si ottiene solo da
    ``GET /api/v1/occurrences/{id}/meeting`` con autorizzazione e finestra temporale.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    lesson = models.OneToOneField(
        "lesson_calendar.LessonOccurrence",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    resource = models.OneToOneField(
        "education.Resource",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )
    join_url = models.URLField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(Q(lesson__isnull=False) & Q(resource__isnull=True))
                | (Q(lesson__isnull=True) & Q(resource__isnull=False)),
                name="meeting_link_exactly_one_target",
            ),
            models.CheckConstraint(
                condition=Q(join_url__startswith="https://"),
                name="meeting_link_https",
            ),
        ]


class MeetingPresence(models.Model):
    """v0.10 · Tempo trascorso nella videolezione integrata, per account e lezione.

    Serve a precompilare le presenze a fine lezione (il tutor conferma): non è una
    prova legale di presenza e non registra audio, video o contenuti. Si conserva
    con le stesse regole delle presenze della lezione.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    lesson = models.ForeignKey(
        "lesson_calendar.LessonOccurrence",
        on_delete=models.PROTECT,
        related_name="+",
    )
    account = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    relation = models.CharField(
        max_length=8,
        choices=[
            ("CENTER", "Centro"),
            ("TUTOR", "Tutor"),
            ("GUARDIAN", "Tutore legale"),
            ("STUDENT", "Studente"),
        ],
    )
    # Studenti della lezione per cui l'account è entrato (sé stesso o figli).
    student_ids = models.JSONField(default=list)
    first_joined_at = models.DateTimeField()
    last_seen_at = models.DateTimeField()
    left_at = models.DateTimeField(null=True, blank=True)
    seconds = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["lesson", "account"], name="unique_meeting_presence"
            )
        ]
