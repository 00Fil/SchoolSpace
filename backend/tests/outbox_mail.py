"""Casella di test per le email consegnate tramite l'outbox (backend ``sink``).

Dopo l'integrazione s1/s3 inviti e reset non usano più ``django.core.mail`` in modo
sincrono: vengono scritti in outbox e consegnati dal dispatcher. Questa casella esegue
la riconciliazione inline (come il comando di emergenza) a ogni lettura e restituisce i
messaggi accettati dal sink, così i test verificano il flusso reale.
"""

import pytest

from apps.communications.dispatch import reconcile
from apps.communications.providers import SinkBackend


class DeliveredMail:
    def _messages(self):
        reconcile(inline=True)
        return list(SinkBackend.messages)

    def __len__(self):
        return len(self._messages())

    def __getitem__(self, index):
        return self._messages()[index]

    def __iter__(self):
        return iter(self._messages())

    def __eq__(self, other):
        return self._messages() == list(other)


@pytest.fixture
def mailoutbox():
    SinkBackend.reset()
    yield DeliveredMail()
    SinkBackend.reset()
