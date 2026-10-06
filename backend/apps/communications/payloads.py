"""Minimizzazione dei payload (GAP-F05, paper §7.4).

Il payload di un ``OutboxEvent`` è condiviso da tutti i destinatari: non può contenere
elenchi di persone (membri del gruppo, partecipanti, altri tutori), recapiti né link
(in particolare link video), che finirebbero in copie multiple. Il contesto per
destinatario può contenere solo dati di cui quel destinatario è titolare.
"""

import json
import re

MAX_PAYLOAD_BYTES = 2048
MAX_CONTEXT_BYTES = 1024

# Chiavi vietate ovunque (payload e contesto).
FORBIDDEN_KEYS = {
    "participants",
    "participant_ids",
    "participant_names",
    "members",
    "member_ids",
    "member_names",
    "group_members",
    "students",
    "student_ids",
    "tutors",
    "guardians",
    "recipients",
    "email",
    "emails",
    "phone",
    "phones",
    "address",
    "join_url",
    "meeting_url",
    "video_url",
    "video_link",
    "meeting_link",
    "url",
    "link",
    "password",
    "token",
}
# Chiavi ammesse solo nel contesto del singolo destinatario.
CONTEXT_ONLY_KEYS = {"student_names"}
URL_PATTERN = re.compile(r"(?i)\b(?:https?://|www\.)")
EMAIL_PATTERN = re.compile(r"[^@\s]+@[^@\s]+\.[a-z]{2,}", re.I)


class PayloadNotMinimal(ValueError):
    pass


def _walk(value, path, allow_context_keys):
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise PayloadNotMinimal(f"{path}: chiavi solo stringa")
            lowered = key.lower()
            if lowered in FORBIDDEN_KEYS:
                raise PayloadNotMinimal(f"{path}.{key}: dato non minimo vietato")
            if lowered in CONTEXT_ONLY_KEYS and not allow_context_keys:
                raise PayloadNotMinimal(
                    f"{path}.{key}: ammesso solo nel contesto del destinatario"
                )
            _walk(item, f"{path}.{key}", allow_context_keys)
    elif isinstance(value, (list, tuple)):
        if any(isinstance(item, (dict, list, tuple)) for item in value):
            raise PayloadNotMinimal(f"{path}: elenchi di oggetti non ammessi")
        for index, item in enumerate(value):
            _walk(item, f"{path}[{index}]", allow_context_keys)
    elif isinstance(value, str):
        if URL_PATTERN.search(value):
            raise PayloadNotMinimal(f"{path}: link non ammessi nel payload")
        if EMAIL_PATTERN.search(value):
            raise PayloadNotMinimal(f"{path}: indirizzi email non ammessi")
    elif value is not None and not isinstance(value, (int, float, bool)):
        raise PayloadNotMinimal(f"{path}: tipo non serializzabile")


def _size(value):
    return len(json.dumps(value, sort_keys=True, default=str).encode())


def check_payload(payload):
    if not isinstance(payload, dict):
        raise PayloadNotMinimal("payload: oggetto JSON richiesto")
    _walk(payload, "payload", allow_context_keys=False)
    if _size(payload) > MAX_PAYLOAD_BYTES:
        raise PayloadNotMinimal("payload: troppo grande per un messaggio minimo")
    return payload


def check_context(context):
    if not isinstance(context, dict):
        raise PayloadNotMinimal("context: oggetto JSON richiesto")
    _walk(context, "context", allow_context_keys=True)
    names = context.get("student_names", [])
    if not isinstance(names, list) or len(names) > 6:
        raise PayloadNotMinimal("context.student_names: al massimo i propri studenti")
    if _size(context) > MAX_CONTEXT_BYTES:
        raise PayloadNotMinimal("context: troppo grande")
    return context
