# 03 — Collisioni e conflitti stale

**Alert**: `ConflittiCommitAnomali` (SEV3): molte risposte 409 su pubblicazione o spostamento lezioni.
**Impatto**: gli utenti ricevono "dati cambiati, ricarica" — il sistema sta **proteggendo** il
calendario (revisioni attese, vincolo di esclusione GiST sulle prenotazioni delle risorse).

## Diagnosi

- Log JSON con `status=409` e la `route` (`publish`, `reschedule`, `cancel`): stesso utente ripetuto
  (doppio click / UI vecchia dopo un rilascio) o molti utenti (lavoro concorrente reale)?
- Dopo un rilascio: cache del frontend? `index.html` è servito con `no-cache`; chiedere un ricaricamento.
- Un picco di 409 con errori 5xx o `IntegrityError` nei log è un bug: aprire incidente SEV2.

## Intervento

1. Nessuna correzione manuale dei dati: il vincolo di esclusione e le revisioni sono la protezione.
2. Comunicare al centro (CEN) di ricaricare e ripetere l'operazione; per una pubblicazione, rigenerare
   la proposta sulla revisione corrente.
3. Verificare invarianti: `docker compose -f compose.prod.yaml exec web python manage.py post_restore_reconcile --restore-point $(date -u +%FT%TZ)`
   in dry-run (passo `calendar.booking_overlaps` = 0 sovrapposizioni).
