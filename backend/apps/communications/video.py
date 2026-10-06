"""Videolezioni automatiche su Jitsi Meet (open source, self-hosted) — v0.10.

Obiettivo: zero lavoro manuale per il centro. Ogni lezione ONLINE pubblicata ha già
la sua stanza, senza link da creare, copiare o incollare:

- **stanza deterministica e non indovinabile**: HMAC(segreto, id lezione). Resta la
  stessa se la lezione viene spostata o cambia tutor; due lezioni non la condividono;
- **ingresso firmato** (JWT HS256, standard ``docker-jitsi-meet`` con ``AUTH_TYPE=jwt``):
  valido solo per quella stanza e solo nella finestra della lezione. Senza token il
  server Jitsi rifiuta l'ingresso (``ENABLE_GUESTS=0``), quindi il link inoltrato a
  terzi non apre nulla fuori finestra;
- **ruoli**: tutor della lezione e centro moderatori, studenti e famiglie partecipanti;
- **dati minimi** (GDPR, minori): nel token solo il nome visualizzato e un identificativo
  pseudonimo; nessuna email; registrazione, dirette e trascrizione disattivate.

I ``MeetingLink`` manuali restano validi e hanno la precedenza (piattaforme esterne).
"""

import base64
import hashlib
import hmac
import json
import logging
from urllib.parse import quote

from django.conf import settings

PROVIDER = "jitsi"
MIN_SECRET_LENGTH = 32
log = logging.getLogger(__name__)
_warned = set()


def config_problems():
    """Motivi per cui le videolezioni automatiche non sono attive (lista vuota = ok).

    Non solleva mai: una configurazione incompleta disattiva solo la funzione,
    senza impedire l'avvio dell'applicazione o delle migrazioni.
    """
    provider = (getattr(settings, "VIDEO_PROVIDER", "") or "").strip().lower()
    if not provider:
        return []
    if provider != PROVIDER:
        return [f"VIDEO_PROVIDER='{provider}' non supportato (valori ammessi: vuoto o 'jitsi')"]
    problems = []
    url = getattr(settings, "VIDEO_JITSI_URL", "") or ""
    secret = getattr(settings, "VIDEO_JITSI_APP_SECRET", "") or ""
    if not url:
        problems.append("VIDEO_JITSI_URL assente")
    elif not url.startswith("https://"):
        problems.append("VIDEO_JITSI_URL deve iniziare con https://")
    if not secret:
        problems.append("VIDEO_JITSI_APP_SECRET (JITSI_JWT_APP_SECRET) assente")
    elif len(secret) < MIN_SECRET_LENGTH:
        problems.append(
            f"VIDEO_JITSI_APP_SECRET troppo corto ({len(secret)} caratteri, minimo {MIN_SECRET_LENGTH})"
        )
    return problems


def enabled():
    if (getattr(settings, "VIDEO_PROVIDER", "") or "").strip().lower() != PROVIDER:
        return False
    problems = config_problems()
    if problems:
        key = tuple(problems)
        if key not in _warned:
            _warned.add(key)
            log.warning("videolezioni disattivate: %s", "; ".join(problems))
        return False
    return True


def _key():
    return settings.VIDEO_JITSI_APP_SECRET.encode()


def room_name(lesson):
    """Nome stanza: minuscolo (Jitsi normalizza), 96 bit casuali non indovinabili."""
    digest = hmac.new(_key(), f"room:{lesson.id}".encode(), hashlib.sha256)
    return f"{settings.VIDEO_ROOM_PREFIX}-{digest.hexdigest()[:24]}"


def pseudonym(account):
    """Identificativo stabile per Jitsi che non rivela l'id interno dell'account."""
    return hmac.new(_key(), f"user:{account.pk}".encode(), hashlib.sha256).hexdigest()[
        :20
    ]


def _b64(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def sign(claims):
    header = _b64(
        json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode()
    )
    body = _b64(json.dumps(claims, separators=(",", ":"), sort_keys=True).encode())
    signature = hmac.new(_key(), f"{header}.{body}".encode(), hashlib.sha256).digest()
    return f"{header}.{body}.{_b64(signature)}"


def decode(token):
    """Verifica firma e restituisce i claim (usato nei test e nella diagnostica)."""
    header, body, signature = token.split(".")
    expected = hmac.new(_key(), f"{header}.{body}".encode(), hashlib.sha256).digest()
    if not hmac.compare_digest(_b64(expected), signature):
        raise ValueError("firma non valida")
    return json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))


def display_name(account, lesson, relation, students):
    """Nome mostrato in stanza: quello che tutor e studenti conoscono già."""
    if relation == "TUTOR":
        return lesson.tutor.display_name
    if relation in ("STUDENT", "GUARDIAN") and students:
        names = sorted(
            p.student.display_name
            for p in lesson.participants.select_related("student")
            if p.student_id in students
        )
        if names:
            return ", ".join(names)
    if relation == "CENTER":
        full = account.get_full_name().strip()
        return f"{full or account.get_username()} (centro)"
    return account.get_full_name().strip() or account.get_username()


def session_for(lesson, account, relation, students, *, not_before, expires):
    """Dati per entrare nella stanza: URL completo e parametri per l'integrazione."""
    room = room_name(lesson)
    moderator = relation in ("TUTOR", "CENTER")
    name = display_name(account, lesson, relation, students)
    claims = {
        "aud": settings.VIDEO_JITSI_AUDIENCE,
        "iss": settings.VIDEO_JITSI_APP_ID,
        "sub": settings.VIDEO_JITSI_SUBJECT,
        "room": room,
        "nbf": int(not_before.timestamp()) - 60,  # tolleranza orologi
        "exp": int(expires.timestamp()),
        "moderator": moderator,
        "context": {
            "user": {
                "id": pseudonym(account),
                "name": name,
                "moderator": moderator,
                "affiliation": "owner" if moderator else "member",
            },
            "features": {
                "recording": False,
                "livestreaming": False,
                "transcription": False,
                "outbound-call": False,
                "sip-outbound-call": False,
            },
        },
    }
    token = sign(claims)
    subject = lesson.subject.name
    config = {
        # Niente schermata intermedia: si entra direttamente con il nome già impostato.
        "config.prejoinConfig.enabled": False,
        "config.disableDeepLinking": True,
        "config.subject": subject,
        "config.startWithAudioMuted": not moderator,
        "config.disableInviteFunctions": True,
        "config.fileRecordingsEnabled": False,
        "config.liveStreamingEnabled": False,
        "config.transcription.enabled": False,
        "userInfo.displayName": name,
        "interfaceConfig.SHOW_JITSI_WATERMARK": False,
    }

    def fragment(extra):
        return "&".join(
            f"{k}={quote(json.dumps(v))}" for k, v in {**config, **extra}.items()
        )

    base = settings.VIDEO_JITSI_URL
    return {
        "provider": PROVIDER,
        "join_url": f"{base}/{room}?jwt={token}#{fragment({})}",
        # Integrata nel gestionale: materia e logo sono già nell'intestazione della
        # cornice, quindi Jitsi non li ripete (una sola intestazione).
        "embed_url": f"{base}/{room}?jwt={token}#"
        + fragment(
            {"config.hideConferenceSubject": True, "config.hideConferenceTimer": True}
        ),
        "starts_at": lesson.start_at.isoformat(),
        "embed": settings.VIDEO_EMBED,
        "origin": base,
        "room": room,
        "display_name": name,
        "moderator": moderator,
        "subject": subject,
    }
