# REPORT P2 — Vincoli e configurazione (guida v3.1)

## Decisioni del committente applicate
Vedi `docs/decision-register.md` (DC-ANNO, DC-APPROVAZIONI, D07 parziale).

## Backend
- Modelli `SchoolYear` e `StudyPeriod` (migrazione `scheduling/0004_school_year`). Servizio auditato in `apps/scheduling/school_year.py`.
  - Le pause (natalizia, pasquale, estiva, altre) creano e aggiornano in automatico una chiusura «tutte le modalità», quindi il motore le rispetta senza modifiche.
  - Inizio lezioni e periodi per i recuperi non chiudono il centro.
  - Controlli: periodi dentro l'anno, niente sovrapposizioni tra pause e recuperi, anni senza sovrapposizioni.
- API (`api/school_year.py`):
  - `GET/POST /planning/school-years`, `GET /planning/school-years/current`, `PATCH /planning/school-years/<id>`
  - `POST /planning/school-years/<id>/periods`, `PATCH /planning/study-periods/<id>`, `POST /planning/study-periods/<id>/delete`
  - `POST /planning/service-windows/replace`: salva gli orari dipinti nella griglia (per modalità, periodo = anno).
  - `POST /availability/bulk-review`: approvazione o rifiuto in blocco, solo centro.
  - Ogni scrittura: solo centro, motivo, versione attesa dove serve, PlanningAudit, revisione di pianificazione incrementata.

## Frontend
- `ui/WeekGrid.tsx`: griglia settimanale «trascina per dipingere», con mouse, tocco e tastiera (frecce, Spazio, Maiusc+freccia), etichette accessibili per ogni cella e scorrimento orizzontale su schermi stretti.
- Schermata **Configurazione** (menu del centro): Anno scolastico, Orari del centro (griglia sede/online), Chiusure, Aule e capienze, Disponibilità da approvare (in blocco).
- Aiuto in linea `configurazione`.

## Completamento P2 (seconda consegna)
- **Disponibilità → vista «Griglia per persona»**: si sceglie uno studente o un tutor e si dipingono le fasce settimanali (sede/online).
  - Le fasce nuove vengono inviate in bozza per l'anno scolastico in corso.
  - Il centro può anche togliere fasce: vengono revocate in blocco, con un motivo.
  - Nei portali (famiglia con delega, tutor) si possono solo aggiungere fasce; per toglierle bisogna scrivere al centro. Coerente con DC-APPROVAZIONI: decide solo il gestore.
- **Configurazione → Eccezioni, Dichiarazioni, Regole del motore**: elenco e modifica con il modulo guidato, con controllo di versione. Tutto ciò che chiede la verifica dei dati è ora inseribile dall'interfaccia.
- **Test E2E** `frontend/e2e/configurazione.e2e.mjs` (`npm run e2e:config`), a 1440 e 360 px in tema chiaro e scuro. Controlla:
  - anno con pause e recuperi;
  - griglia da tastiera e salvataggio con motivo;
  - approvazione in blocco;
  - stato vuoto delle regole;
  - griglia per persona;
  - assenza di scorrimento orizzontale;
  - axe WCAG 2.2 AA (fallisce con violazioni serie o critiche).

## Limiti noti
- Il motore non usa ancora i periodi per i recuperi (P4).
- La griglia lavora a passi di 30 minuti: le fasce esistenti a quarti d'ora compaiono solo per le mezz'ore piene.
- La rimozione di fasce dal portale passa dal centro: manca ancora una richiesta strutturata (arriverà con le richieste di modifica in P3/P4).

## Non verificato in questo ambiente
Django e le dipendenze del frontend non sono installabili (niente rete): superato solo `py_compile`.
In locale: `pytest` con `DJANGO_DEBUG=0`, `makemigrations --check`, rigenerazione OpenAPI e `schema.gen.ts`, build e typecheck del frontend.
