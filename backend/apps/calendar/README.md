# apps.calendar

Calendario sperimentale (vedi `docs/calendar.md`). Moduli:

- `models.py` — lezioni, prenotazioni, audit append-only, serie, recuperi, presenze, pratiche, richieste, PlanReview, HorizonProposal.
- `services.py` — pubblicazione, spostamento/cancellazione nella settimana, verifiche (`verify_plan`).
- `context.py` — DTO della settimana con lezioni pubblicate, unità sintetiche (spostate/makeup) e proiezione delle serie.
- `recurrence.py` — sottoinsieme RRULE puro (WEEKLY/INTERVAL/BYDAY/UNTIL, EXDATE, override, DST).
- `commands.py` — ricevuta idempotente, autorizzazione, audit/eventi comuni.
- `operations.py` — move/modify/swap, recuperi e makeup, presenze, COMPLETED, correzione amministrativa.
- `series.py` — serie, EXDATE, override, split "questa e successive".
- `conflicts.py` / `signals.py` — ConflictCase automatiche e ChangeRequest.
- `lifecycle.py` — stato del piano e proposta dell'orizzonte (`tasks.py`, management commands).
- `notifications.py` — notifiche outbox (s3) per i comandi del calendario.
