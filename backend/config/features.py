"""Flag di funzione per ambiente (guida v3.1, T1 / fase P0).

Sostituiscono le condizioni ``DEBUG and EXPERIMENTAL_*``: calendario, pianificazione e
portali non dipendono più dalla modalità di sviluppo. In produzione i flag sono attivi per
default (``settings_production``); si possono spegnere per ambiente con
``FEATURE_PLANNING=0`` / ``FEATURE_CALENDAR=0``.

- ``planning_enabled``: configurazione dei dati, readiness, run del solver, proposte.
- ``calendar_enabled``: calendario, pubblicazione, operazioni sulle lezioni, portali.
  Richiede anche la pianificazione, perché il calendario nasce dalle proposte.
- ``lab_enabled``: simulazione su dati di esempio («Laboratorio»), strumento tecnico.
"""

from django.conf import settings


def planning_enabled():
    return bool(getattr(settings, "FEATURE_PLANNING", False))


def calendar_enabled():
    return bool(getattr(settings, "FEATURE_CALENDAR", False) and planning_enabled())


def lab_enabled():
    return bool(getattr(settings, "FEATURE_PLANNING_LAB", False))


DISABLED_CODE = "FEATURE_DISABLED"
