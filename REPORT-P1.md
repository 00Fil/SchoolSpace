# REPORT P1 — Anagrafica e utenti (guida v3.1)

## Backend
- **T2 Tutor**: `Tutor.account` ora facoltativo (+ `email`, `active`), migrazione `education/0005_tutor_registry`.
  Servizi auditati in `apps/education/tutors.py`; API in `api/staff.py`:
  - `GET/POST /api/v1/registry/tutors` (filtri `q`, `active`; `invite: true` invia subito l'invito)
  - `GET/PATCH /api/v1/registry/tutors/<id>` (`expected_version` + `reason`)
  - `POST /api/v1/registry/tutors/<id>/{invite|deactivate|reactivate}`
  - all'accettazione di un invito TUTOR l'account viene collegato alla scheda con la stessa email (`identity.services.accept_invitation`).
  - la disattivazione revoca il ruolo TUTOR e gli inviti aperti; lo storico resta.
- **T3 Utenti del centro**: `GET /api/v1/identity/center-users`, `GET/POST /api/v1/identity/center-invitations` (solo CENTER),
  `POST /api/v1/identity/center-users/<id>/revoke-role` (vietata l'auto-revoca e la rimozione dell'ultimo gestore).
  Reset MFA e chiusura sessioni riusano gli endpoint esistenti.
- Nuova categoria di audit `STAFF` (migrazione `governance/0006`).
- Pianificazione: i tutor senza account restano pianificabili; esclusi i tutor disattivati (`scheduling/source.py`).
- Notifiche lezione: gestito il tutor senza account (`communications/calendar_hooks.py`).

## Frontend (menu del centro)
- **Anagrafica** (`screens/Anagrafica.tsx`): famiglie → figli → genitori; crea/modifica famiglia e figlio; invito genitore,
  verifica relazione, reinvio, revoca; import CSV guidato con anteprima errori (dry-run) e conferma.
- **Tutor** (`screens/Tutor.tsx`): scheda, invito, disattiva/riattiva, competenze materia × livello × modalità con approvazione,
  regole di carico/pause/spostamenti.
- **Utenti e ruoli** (`screens/Utenti.tsx`): elenco gestori e tutor, invito gestore, revoca ruolo, azzera MFA, chiudi sessioni, inviti in attesa.
- Stati gestiti: caricamento, vuoto, errore con riprova, conflitto di versione (messaggio dedicato), permesso negato. Aiuto in linea in `help.ts`.

## Documentazione e test
- `docs/runbooks/07-primo-gestore.md`: `createsuperuser` + MFA al primo accesso + secondo gestore + prova di uscita P1.
- `backend/tests/test_registry_tutors.py`: CRUD con audit, conflitto di versione, motivo obbligatorio, collegamento account all'accettazione, BOLA per TUTOR/GUARDIAN/STUDENT, protezione ultimo gestore, inviti CENTER — tutto con `DEBUG=False`.

## Non verificato in questo ambiente (da fare in locale)
- Esecuzione di pytest (Django non installabile: niente rete) e build/test del frontend (niente `node_modules`). Solo `py_compile` superato.
- `makemigrations --check`, rigenerazione `contracts/openapi.yaml` e `schema.gen.ts`.
- Test E2E Playwright delle tre schermate, axe e verifica a 360px: non scritti/eseguiti.
- Formato errori dell'import CSV: l'anteprima mostra il campo `errors` della risposta; da allineare a `batch_json` se diverso.
- Le azioni di revoca invito usano ancora un `prompt()` del browser per il motivo: da sostituire con una modale.
