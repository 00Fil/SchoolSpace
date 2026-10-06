# REPORT P4 · Operatività quotidiana (parti 1 e 2)

Decisioni del committente del 3/10/2026 (vedi `docs/decision-register.md`, DC-RECUPERI … DC-NOTIFICHE).

## Fatto

| Area guida | Cosa | File |
|---|---|---|
| Recuperi: obblighi, recupero, rinuncia | Regola 24 ore con concessione manuale del centro (`LATE_NOTICE`, `grant_late_notice`), scadenza a fine anno (`RECOVERY_PAST_DUE`), periodi per i recuperi esposti; coda «Recuperi» | `apps/calendar/recovery_policy.py`, `operations.py`, `screens/Operativita.tsx` |
| Richieste di cambio delle famiglie | Coda «Richieste»; doppia conferma centro → tutor (`awaiting`, `CHANGE_CENTER_ACCEPTED`, `CHANGE_TUTOR_CONFIRM/REJECT`); endpoint `POST /api/v1/change-requests/<id>/tutor-confirm/`; sezione nel portale tutor | `conflicts.py`, `api/calendar_ops.py`, `portal/PresaVisione.tsx` |
| Conflitti | Coda «Conflitti»: rileva, annulla con/senza recupero (anche oltre le 24 ore se concesso), conferma | `screens/Operativita.tsx` |
| Comunicazioni | Solo portale (`COMMUNICATIONS_CHANNELS=IN_APP`), email solo essenziali; pannello invii con riprova/abbandona; `GET /api/v1/communications/deliveries` (solo centro, senza indirizzi) | `services.py`, `api/communications.py` |
| §8 | Motivo precompilato modificabile, stati vuoto/caricamento/errore/conflitto di versione, tabelle con `scope`, colonne nascoste a 360px, aiuto in linea e manuali | |

Test: `tests/test_p4_operativita.py` (7 casi) e aggiornato `test_calendar_conflicts.py` per la doppia conferma.

## Verifiche eseguite qui

- `py_compile` su tutti i file Python modificati: OK.
- Controllo sintattico TypeScript (transpile) sulle schermate nuove/modificate: OK.
- **Non eseguiti** (sandbox senza Django e senza internet): pytest, makemigrations, build, E2E.

## Da eseguire in locale

```
cd backend && DJANGO_DEBUG=0 pytest tests/test_p4_operativita.py tests/test_calendar_conflicts.py && pytest
python manage.py makemigrations --check   # nessuna migrazione attesa: i nuovi dati stanno in ChangeRequest.proposal
# rigenerare OpenAPI e frontend/src/api/schema.gen.ts, poi npm run build
```

## Parte 2

| Area guida | Cosa | File |
|---|---|---|
| Agenda: modifica/scambia/completa/correzione/link video | Azioni nella scheda della lezione con motivo precompilato, conflitto di versione gestito | `screens/LessonActions.tsx`, `screens/Agenda.tsx` |
| Serie: «questa e successive» | Scelta «Solo questa lezione / Da questa in poi» per modifica e sostituto (split della serie dalla data della lezione) | `screens/LessonActions.tsx` |
| Assenza del tutor | Ricerca sostituti in sola lettura (savepoint annullato) con motivi di esclusione; in mancanza, annulla con recupero | `apps/calendar/substitutes.py`, `GET /api/v1/occurrences/<id>/substitutes/` |
| Criterio d'uscita | E2E scenari UAT: assenza, spostamento, recupero, chiusura imprevista, pannello comunicazioni (1440/360 px, chiaro/scuro, axe) | `e2e/operativita.e2e.mjs`, `npm run e2e:operativita` |

Nota: lo scenario UAT «eseguito dal gestore» resta da far svolgere a una persona del centro sull'ambiente di prova (vedi `docs/manuali/centro.md`); l'E2E ne è la versione automatica.

Non coperto (motivato): cambio di aula o canale video dalla scheda (servono gli elenchi risorse in P6); «da questa in poi» per lo spostamento di orario e la cancellazione (oggi: «Sposta» su singola lezione; per la serie si usa la modifica orario della serie in Configurazione).

## Da eseguire in locale (aggiornato)

```
cd backend && DJANGO_DEBUG=0 pytest tests/test_p4_operativita.py tests/test_calendar_conflicts.py && pytest
python manage.py makemigrations --check   # nessuna migrazione attesa
# rigenerare OpenAPI e frontend/src/api/schema.gen.ts, poi
cd frontend && npm run build && npm run e2e:operativita
```
