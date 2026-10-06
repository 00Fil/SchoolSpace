"""Astrazione del provider email (GAP-F02).

Backend disponibili, scelti con ``COMMUNICATIONS_EMAIL_BACKEND``:
- ``sink``: nessun invio reale; memoria di processo, idempotente per chiave. Unico
  backend ammesso fuori da ``COMMUNICATIONS_ENV=production`` (test, sviluppo, staging).
- ``smtp``: SMTP con STARTTLS/TLS verso un relay transazionale UE (D08 da approvare).
- ``api``: API HTTPS JSON generica di un provider transazionale UE, con header
  ``Idempotency-Key`` e lookup opzionale dello stato.

Ogni backend restituisce ``Accepted`` oppure solleva ``TransientError`` (riprovabile),
``PermanentError`` (dead-letter) o ``AmbiguousError`` (richiesta forse accettata,
risposta persa: T23). Nessun backend promette exactly-once se il fornitore non
supporta l'idempotenza.
"""

import json
import smtplib
import socket
import ssl
import threading
import uuid
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from urllib import error as urlerror, request as urlrequest

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


@dataclass(frozen=True)
class OutgoingEmail:
    to: str
    subject: str
    body: str
    idempotency_key: str
    headers: dict = field(default_factory=dict)
    html: str = ""  # alternativa HTML (layout Lumen); il testo resta sempre presente


@dataclass(frozen=True)
class Accepted:
    provider_message_id: str


class ProviderError(Exception):
    def __init__(self, code, message=""):
        super().__init__(message or code)
        self.code = code[:60]


class TransientError(ProviderError):
    pass


class PermanentError(ProviderError):
    pass


class AmbiguousError(ProviderError):
    pass


# Esiti di ``lookup``: messaggio trovato (Accepted), sicuramente non ricevuto, ignoto.
NOT_FOUND = "NOT_FOUND"


class EmailBackend:
    name = "base"
    supports_idempotency = False

    def send(self, message):  # pragma: no cover - interfaccia
        raise NotImplementedError

    def lookup(self, idempotency_key):
        """Stato presso il provider: ``Accepted``, ``NOT_FOUND`` o ``None`` se ignoto."""
        return None


class SinkBackend(EmailBackend):
    """Nessun invio reale. Conserva in memoria al massimo ``limit`` messaggi."""

    name = "sink"
    supports_idempotency = True
    _lock = threading.Lock()
    messages = []
    _by_key = {}
    limit = 500

    def send(self, message):
        with self._lock:
            if message.idempotency_key in self._by_key:
                return Accepted(self._by_key[message.idempotency_key])
            provider_id = f"sink-{uuid.uuid4()}"
            self._by_key[message.idempotency_key] = provider_id
            self.messages.append(message)
            del self.messages[: -self.limit]
            return Accepted(provider_id)

    def lookup(self, idempotency_key):
        with self._lock:
            found = self._by_key.get(idempotency_key)
        return Accepted(found) if found else NOT_FOUND

    @classmethod
    def reset(cls):
        with cls._lock:
            cls.messages.clear()
            cls._by_key.clear()


def build_mime(message, sender, domain):
    mime = EmailMessage()
    mime["From"] = sender
    mime["To"] = message.to  # un solo destinatario: nessun CC/BCC (GAP-F05)
    mime["Subject"] = message.subject
    mime["Date"] = formatdate(localtime=False)
    # Message-ID derivato dalla chiave: i client possono riconoscere un duplicato.
    mime["Message-ID"] = make_msgid(
        idstring=message.idempotency_key.replace("@", "-"), domain=domain
    )
    mime["Auto-Submitted"] = "auto-generated"
    mime["Content-Language"] = "it"
    for key, value in message.headers.items():
        mime[key] = value
    mime.set_content(message.body, charset="utf-8")
    if message.html:
        mime.add_alternative(message.html, subtype="html", charset="utf-8")
    return mime


class SmtpBackend(EmailBackend):
    name = "smtp"
    supports_idempotency = False

    def __init__(self, conf):
        self.host = conf["SMTP_HOST"]
        self.port = int(conf["SMTP_PORT"])
        self.user = conf["SMTP_USER"]
        self.password = conf["SMTP_PASSWORD"]
        self.security = conf["SMTP_SECURITY"]  # "starttls" | "tls"
        self.timeout = float(conf["TIMEOUT_SECONDS"])
        self.sender = conf["FROM"]
        self.domain = conf["MESSAGE_ID_DOMAIN"]
        if not self.host or self.security not in ("starttls", "tls"):
            raise ImproperlyConfigured(
                "SMTP: host e sicurezza (starttls/tls) richiesti"
            )

    def _connect(self):
        context = ssl.create_default_context()
        if self.security == "tls":
            client = smtplib.SMTP_SSL(
                self.host, self.port, timeout=self.timeout, context=context
            )
        else:
            client = smtplib.SMTP(self.host, self.port, timeout=self.timeout)
            client.starttls(context=context)
        if self.user:
            client.login(self.user, self.password)
        return client

    def send(self, message):
        try:
            client = self._connect()
        except smtplib.SMTPAuthenticationError as exc:
            raise TransientError("SMTP_AUTH", "Autenticazione SMTP rifiutata") from exc
        except (OSError, smtplib.SMTPException) as exc:
            raise TransientError(
                "SMTP_CONNECT", "Relay SMTP non raggiungibile"
            ) from exc
        mime = build_mime(message, self.sender, self.domain)
        try:
            refused = client.send_message(mime)
        except smtplib.SMTPRecipientsRefused as exc:
            raise PermanentError("SMTP_RECIPIENT_REFUSED") from exc
        except smtplib.SMTPSenderRefused as exc:
            raise PermanentError("SMTP_SENDER_REFUSED") from exc
        except smtplib.SMTPResponseException as exc:
            if 400 <= exc.smtp_code < 500:
                raise TransientError(f"SMTP_{exc.smtp_code}") from exc
            raise PermanentError(f"SMTP_{exc.smtp_code}") from exc
        except (smtplib.SMTPServerDisconnected, socket.timeout, OSError) as exc:
            # Il server può aver accettato il DATA prima della disconnessione: T23.
            raise AmbiguousError("SMTP_RESPONSE_LOST") from exc
        finally:
            try:
                client.quit()
            except Exception:
                pass
        if refused:
            raise PermanentError("SMTP_RECIPIENT_REFUSED")
        return Accepted(mime["Message-ID"])


class ApiBackend(EmailBackend):
    """Provider HTTPS generico (JSON). Nessuna chiamata in test: ``urlopen`` va simulato."""

    name = "api"

    def __init__(self, conf):
        self.url = conf["API_URL"]
        self.status_url = conf["API_STATUS_URL"]
        self.token = conf["API_TOKEN"]
        self.timeout = float(conf["TIMEOUT_SECONDS"])
        self.sender = conf["FROM"]
        self.supports_idempotency = bool(conf["API_IDEMPOTENT"])
        for url in filter(None, (self.url, self.status_url)):
            if not url.startswith("https://"):
                raise ImproperlyConfigured("API email: solo URL https://")
        if not self.url or not self.token:
            raise ImproperlyConfigured("API email: URL e token richiesti")

    def _headers(self, key):
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Idempotency-Key": key,
        }

    def send(self, message):
        body = json.dumps(
            {
                "from": self.sender,
                "to": [message.to],
                "subject": message.subject,
                "text": message.body,
                **({"html": message.html} if message.html else {}),
                "headers": {"Auto-Submitted": "auto-generated", **message.headers},
                "reference": message.idempotency_key,
            }
        ).encode()
        req = urlrequest.Request(
            self.url,
            data=body,
            headers=self._headers(message.idempotency_key),
            method="POST",
        )
        try:
            with urlrequest.urlopen(req, timeout=self.timeout) as response:
                data = json.loads(response.read() or b"{}")
                return Accepted(str(data.get("id") or message.idempotency_key))
        except urlerror.HTTPError as exc:
            if exc.code == 409 and self.supports_idempotency:
                # Richiesta già accettata con la stessa chiave.
                return Accepted(message.idempotency_key)
            if exc.code in (408, 425, 429) or exc.code >= 500:
                raise TransientError(f"API_{exc.code}") from exc
            raise PermanentError(f"API_{exc.code}") from exc
        except urlerror.URLError as exc:
            if isinstance(exc.reason, (ConnectionRefusedError, socket.gaierror)):
                raise TransientError("API_CONNECT") from exc
            raise AmbiguousError("API_RESPONSE_LOST") from exc
        except (socket.timeout, TimeoutError, ConnectionResetError) as exc:
            raise AmbiguousError("API_RESPONSE_LOST") from exc
        except ValueError as exc:
            raise AmbiguousError("API_BAD_RESPONSE") from exc

    def lookup(self, idempotency_key):
        if not self.status_url:
            return None
        req = urlrequest.Request(
            self.status_url.replace("{key}", idempotency_key),
            headers=self._headers(idempotency_key),
            method="GET",
        )
        try:
            with urlrequest.urlopen(req, timeout=self.timeout) as response:
                data = json.loads(response.read() or b"{}")
                return Accepted(str(data.get("id") or idempotency_key))
        except urlerror.HTTPError as exc:
            return NOT_FOUND if exc.code == 404 else None
        except (OSError, ValueError):
            return None


class ResendBackend(EmailBackend):
    """Resend (D08, approvata il 3/10/2026): POST https://api.resend.com/emails.

    Idempotenza nativa tramite header ``Idempotency-Key`` (stessa chiave = nessun
    doppione), quindi un esito ambiguo si risolve reinviando con la stessa chiave.
    Resend non consente la ricerca per chiave: ``lookup`` restituisce sempre "ignoto".
    """

    name = "resend"
    supports_idempotency = True
    DEFAULT_URL = "https://api.resend.com/emails"

    def __init__(self, conf):
        self.url = conf.get("RESEND_URL") or self.DEFAULT_URL
        self.token = conf.get("RESEND_API_KEY") or conf["API_TOKEN"]
        self.timeout = float(conf["TIMEOUT_SECONDS"])
        self.sender = conf["FROM"]
        if not self.url.startswith("https://"):
            raise ImproperlyConfigured("Resend: solo URL https://")
        if not self.token:
            raise ImproperlyConfigured("Resend: chiave API richiesta (COMMUNICATIONS_RESEND_API_KEY)")

    def send(self, message):
        body = json.dumps(
            {
                "from": self.sender,
                "to": [message.to],
                "subject": message.subject,
                "text": message.body,
                **({"html": message.html} if message.html else {}),
                "headers": {"Auto-Submitted": "auto-generated", **message.headers},
            }
        ).encode()
        req = urlrequest.Request(
            self.url,
            data=body,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "gestionale-ripetizioni",
                "Idempotency-Key": message.idempotency_key[:256],
            },
            method="POST",
        )
        try:
            with urlrequest.urlopen(req, timeout=self.timeout) as response:
                data = json.loads(response.read() or b"{}")
                return Accepted(str(data.get("id") or message.idempotency_key))
        except urlerror.HTTPError as exc:
            # 409: richiesta concorrente con la stessa chiave -> si ritenta più tardi.
            if exc.code in (408, 409, 425, 429) or exc.code >= 500:
                raise TransientError(f"RESEND_{exc.code}") from exc
            raise PermanentError(f"RESEND_{exc.code}") from exc
        except urlerror.URLError as exc:
            if isinstance(exc.reason, (ConnectionRefusedError, socket.gaierror)):
                raise TransientError("RESEND_CONNECT") from exc
            raise AmbiguousError("RESEND_RESPONSE_LOST") from exc
        except (socket.timeout, TimeoutError, ConnectionResetError) as exc:
            raise AmbiguousError("RESEND_RESPONSE_LOST") from exc
        except ValueError as exc:
            raise AmbiguousError("RESEND_BAD_RESPONSE") from exc

    def lookup(self, idempotency_key):
        return None


BACKENDS = {
    "sink": SinkBackend,
    "smtp": SmtpBackend,
    "api": ApiBackend,
    "resend": ResendBackend,
}


def get_backend():
    conf = settings.COMMUNICATIONS_EMAIL
    name = conf["BACKEND"]
    if name not in BACKENDS:
        raise ImproperlyConfigured(f"Backend email sconosciuto: {name}")
    if name != "sink" and settings.COMMUNICATIONS_ENV != "production":
        # Regola: nessun invio reale in sviluppo, test o staging.
        raise ImproperlyConfigured(
            "Invio email reale consentito solo con COMMUNICATIONS_ENV=production"
        )
    if name == "sink":
        return SinkBackend()
    return BACKENDS[name](conf)
