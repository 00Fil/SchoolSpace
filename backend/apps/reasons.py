"""Motivo delle operazioni: non viene più chiesto all'utente.

Le API accettano ancora il campo ``reason`` (facoltativo) per compatibilità; se manca o è
vuoto il registro delle attività riceve un testo standard, così lo storico resta completo.
"""

DEFAULT_REASON = "Operazione dal gestionale"
LIMIT = 200


def reason_or_default(value, default=DEFAULT_REASON, limit=LIMIT):
    text = value.strip() if isinstance(value, str) else ""
    return (text or default)[:limit]


def _reason_field():
    from rest_framework import serializers
    from rest_framework.fields import empty

    class ReasonField(serializers.CharField):
        """Campo ``reason`` facoltativo: vuoto o assente diventa il testo standard."""

        def __init__(self, default=DEFAULT_REASON, **kwargs):
            kwargs.pop("max_length", None)
            kwargs.update(required=False, allow_blank=True, allow_null=True, default=default)
            self.fallback = default
            super().__init__(**kwargs)

        def run_validation(self, data=empty):
            value = super().run_validation(data)
            return reason_or_default(value, self.fallback)

    return ReasonField


def ReasonField(**kwargs):  # noqa: N802 - si usa come un campo DRF
    return _reason_field()(**kwargs)
