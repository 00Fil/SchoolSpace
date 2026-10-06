# Report P3 — Dalla proposta al calendario

Guida v3.1, fase P3. Criterio di uscita: prima settimana pubblicata e visibile ai portali senza passi tecnici.

## Cosa c'è
- **Proposte (Agenda → «Proposte da pubblicare»)**:
  - ciclo di vita completo dall'interfaccia: **Valida** (ricontrollo sui dati correnti), **Rifiuta** (motivo precompilato modificabile), **Pubblica**, **Crea le serie ricorrenti** dopo la pubblicazione;
  - **Confronta** due proposte: lezioni uguali, spostate o presenti in una sola, e richieste non collocate;
  - motivi dei non pianificati in linguaggio del centro (i codici del motore restano nella sezione tecnica);
  - tolta la conferma «dati sintetici di prova» dalla pubblicazione (residuo v0.8; il backend la ignora già da P0).
- **Presa visione del tutor (DC-APPROVAZIONI)**:
  - ogni tutor coinvolto in una pubblicazione riceve gli orari in «Orari da confermare» (portale tutor);
  - può confermare la presa visione oppure proporre modifiche lezione per lezione;
  - il centro vede le controproposte sotto le proposte e decide: **Chiedi alle famiglie**, **Accogli** o **Respingi** (motivo obbligatorio);
  - «Accogli» e «Chiedi alle famiglie» creano richieste di modifica nella coda esistente (origine tutor); nel secondo caso la richiesta è marcata come «serve la conferma dei genitori». «Respingi» rimanda il tutor alla presa visione.
  - Nessuna lezione si sposta in automatico: lo spostamento resta un comando del centro.
- **Laboratorio**: era già fuori dal menu del gestore da P0 (visibile solo con TECH_ADMIN).

## Backend
- Modello `TutorAcknowledgement` (migrazione `lesson_calendar 0006`), servizio `apps/calendar/acknowledgements.py`, API `api/acknowledgements.py`.
- Endpoint: `GET /api/v1/schedule-acks`, `POST /api/v1/schedule-acks/<id>/acknowledge|counter|decide`.
- BOLA: il tutor vede e modifica solo le proprie prese visione (le altrui rispondono 404); famiglie 403; decide solo il centro.
- Versione ottimistica (`expected_version`, 409) e audit append-only (`ack:acknowledge`, `ack:counter`, `ack:decide`).
- Le prese visione si creano anche per le pubblicazioni precedenti, alla prima lettura.
- Test: `tests/test_acknowledgements.py` (richiede PostgreSQL, come gli altri test di pubblicazione).

## Frontend
- `portal/PresaVisione.tsx` (portale tutor e coda del centro), `screens/Proposals.tsx` (ciclo di vita e confronto).
- Corretta una chiave duplicata nell'aiuto in linea (`tutor` usata due volte: ora `tutori` per la schermata del centro).
- E2E `frontend/e2e/orari.e2e.mjs` (`npm run e2e:orari`): presa visione da tastiera, validazione e invio della controproposta, 1440/360 px, chiaro/scuro, axe.

## Non verificato qui
Nell'ambiente di lavoro mancano Django e le dipendenze del frontend: è stata controllata solo la sintassi. Da eseguire in locale:
- `DJANGO_DEBUG=0 pytest` su PostgreSQL, `manage.py makemigrations --check`;
- rigenerare OpenAPI e `schema.gen.ts`;
- `npm run build`, `npm run e2e`, `npm run e2e:config`, `npm run e2e:orari`.

## Limiti noti
- La coda del centro per le prese visione è coperta dai test backend, non da un E2E dedicato.
- La conferma dei genitori sulle richieste girate alle famiglie e la doppia conferma centro+tutor sulle richieste delle famiglie arrivano con P4/P5 (coda «Richieste» e portali).
- Nessuna notifica email/push alla presa visione: si appoggiano al pannello comunicazioni (P4).
