# Gestionale centro ripetizioni — v0.7 sperimentale

Settimo incremento di sviluppo basato sul paper tecnico v1.0 del 29 settembre 2026.
**Non è un gestionale finito, non è pronto per produzione e non dimostra il superamento di G1–G6. Usare solo dati sintetici.**

## Cosa è presente
- Backend Django 5.2 LTS / DRF, struttura modulare e migrazioni iniziali.
- Modelli esplorativi account/ruoli/deleghe, famiglie/studenti/tutor, spazi, richieste individuali/gruppi e disponibilità settimanali.
- Percorsi parentali per programma scolastico completo: curriculum, iscrizioni, sottogruppi, copertura per materia e richieste canoniche versionate/idempotenti.
- API con sessioni/CSRF, scope per studente e revoca controllata a ogni richiesta; creazione disponibilità solo in bozza.
- Funzioni pure per intervalli semiaperti, intersezioni, rimozioni prevalenti, ricorrenza settimanale e DST Europe/Rome.
- Registro D01–D09 e readiness operativa ancora bloccata.
- Solver CP-SAT reale in simulazione sintetica, validatore indipendente, modalità strict/coverage e priorità P0/P1/P2.
- Bridge sperimentale dal database: competenze datate, aperture/chiusure, approvazione disponibilità, unità settimanali canoniche e snapshot con hash/revisione/metadati ambiente.
- Calendario sperimentale del centro con lezioni/partecipanti/prenotazioni, pubblicazione atomica, replay, spostamento e cancellazione di lezioni future.
- PostgreSQL: GiST anti-sovrapposizione, trigger differibili di completezza e coerenza delle occupazioni.
- Job persistenti con dispatcher post-commit, replay idempotente, cancellazione, lease e recupero; risultati separati dal calendario pubblico.
- Portali sperimentali in sola lettura per tutor, tutori legali e studenti («La mia settimana»), con perimetro per ruolo e nomi altrui nascosti.
- UI React responsive sullo standard Lumen: panoramica, agenda a griglia tutor × orari, studenti, disponibilità, richieste, percorsi parentali, proposte (generazione, configurazione e calcoli), laboratorio CP-SAT, decisioni e impostazioni; tema chiaro/scuro e palette comandi.
- Configurazione Docker Compose locale con PostgreSQL 17, Redis privato, worker Celery e beat.

## Standard UI
Tutta la UI segue **Lumen v5.2**: regole in `docs/design/ui-standard.md`, decisione in `adr/0006-lumen-ui-standard.md`, base di codice in `frontend/src/lumen/`. Dalla v0.6 guscio e schermate sono conformi; le primitive React sono in `frontend/src/ui/`.

## Avvio locale consigliato — Docker
Serve Docker con Compose. Le immagini e dipendenze richiedono rete al primo build.

```bash
cp .env.example .env
# Modificare DJANGO_SECRET_KEY, POSTGRES_PASSWORD e REDIS_PASSWORD con valori casuali locali.
docker compose up -d --build
docker compose exec backend python manage.py migrate
docker compose exec backend python manage.py bootstrap_center
docker compose exec backend python manage.py record_parentali_scope
docker compose exec backend python manage.py createsuperuser
```

Aprire http://localhost:5173 e accedere con il nome utente scelto.
Admin: http://localhost:8000/admin/ (stessa autenticazione, origine differente da 5173).
Nell'admin inserire **solo dati sintetici**. Creare Family prima di Student. RoleGrant e GuardianLink hanno validità e verifica esplicite.
Per tutor: Account + Tutor + RoleGrant TUTOR. Per tutori: RoleGrant GUARDIAN e GuardianLink verificato. Gli studenti non si autoconcedono deleghe.
`bootstrap_center` è idempotente e crea solo tre spazi capienza due e decisioni aperte; non crea credenziali.
Le porte sono vincolate a localhost. Non esporre il server di sviluppo o l'admin su internet.

## Avvio senza Docker — smoke test limitato
Python 3.13 e Node >=22.12 (o >=20.19). SQLite è ammesso **solo per prove esplorative del core**, non per calendario, booking, vincoli temporali, concorrenza o produzione.

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r backend/requirements-dev.txt
cd backend
export DJANGO_SECRET_KEY="valore-casuale-per-sviluppo"
export DJANGO_DEBUG=1
export EXPERIMENTAL_DB_PLANNING=1
export USE_SQLITE_FOR_TESTS=1
python manage.py migrate
python manage.py bootstrap_center
python manage.py createsuperuser
python manage.py runserver
# In un secondo terminale, dalla radice:
cd frontend
npm ci
npm run dev
```

## Test e build

```bash
cd backend
pytest
# Per ripetere gli stessi test su PostgreSQL locale (nessun substituto per race test futuri):
USE_SQLITE_FOR_TESTS=0 DB_HOST=localhost POSTGRES_DB=ripetizioni POSTGRES_USER=ripetizioni POSTGRES_PASSWORD=... pytest
cd ../frontend
npm ci
npm run build
```

Il ruolo PostgreSQL dei test deve poter creare il database di test. Non usare quello di produzione.
Il flag `G1_APPROVED=1` **non basta**: servono approvazioni e artefatti reali. `POST /schedule-runs` ora accoda **job sperimentali**, solo con DEBUG=1 ed EXPERIMENTAL_DB_PLANNING=1. Non pubblica calendari automaticamente e non sostituisce i gate. La pubblicazione sperimentale è un comando separato e protetto. `/planning/readiness` operativa resta false.

## Limiti espliciti / blocchi di rilascio
Non implementati: pianificazione operativa di produzione, vettore completo degli obiettivi, revisione dei curriculum già derivati, verifiche/avanzamento didattico, riconciliazione con lezioni svolte e recuperi, calendario di produzione, presenze, recuperi formalizzati, outbox/email e delivery, audit completo, import/export, inviti/reset/MFA, backup/restore e portali completi.
I modelli non coprono il dizionario completo e l'admin Django non sostituisce servizi di dominio auditati.
Login via username e throttle in memoria sono temporanei; il login API è disabilitato con DEBUG=0. Sicurezza, privacy e accessibilità non certificate né completamente verificate.
Versioni pin effettive in requirements.txt/requirements-dev.txt/package-lock.json; review di sicurezza prima di ogni rilascio.
`docs/qa-report.md` distingue prove realmente eseguite da verifiche ancora mancanti.

## Struttura
- `backend/apps/`: identity, education, availability, governance, scheduling e calendar sperimentali; communications riservato.
- `backend/domain/`: prototipi puri senza I/O.
- `backend/api/`: subset API v1 (liste a pagina, non ancora cursor normativo).
- `frontend/src/`: UI e client sperimentali.
- `contracts/`: contratto OpenAPI del solo subset implementato.
- `docs/`: decision register, backlog, QA e checklist G1.
- `infra/`: configurazione esclusivamente di sviluppo.

Il significato dei parentali è confermato: intero programma scolastico con il centro. La configurazione concreta richiede classe/livello, materie e monte ore. D02–D06 e tutti gli artefatti G1 restano da approvare.

La guida al modulo e al demo opzionale è `docs/parentali.md`. Migrazione da v0.1: eseguire `migrate` dopo l’aggiornamento dei sorgenti; nessun dato personale di esempio è incluso nell’archivio.

Il motore di simulazione e i suoi limiti sono documentati in `docs/planner.md`. Il laboratorio sincrono resta separato; il nuovo bridge legge richieste dei percorsi dal database. Entrambi non creano lezioni e non approvano gate.

## Demo del bridge: database → worker → proposta
Dopo la creazione del superuser:
```bash
docker compose exec backend python manage.py seed_planning_demo --actor NOME_UTENTE_CENTRO
# Recupero manuale della coda persistente se necessario:
docker compose exec backend python manage.py dispatch_pending_runs
```
Aprire **Proposte**, scegliere la politica DEMO DB e la settimana di lunedì **5 ottobre 2026** dal calendario, poi «Verifica i dati» e «Genera la proposta». Il worker solver è un processo separato. Il demo contiene 4 studenti, 2 tutor, 3 spazi e 6 unità, esclusivamente sintetici. Non rappresenta un programma scolastico ufficiale completo.

Per avvio senza Docker occorre un Redis separato (REDIS_HOST=localhost e password configurata), poi `celery -A config worker --concurrency=1 -Q solver` e `celery -A config beat` dalla cartella backend. Non viene eseguito un fallback sincrono nascosto quando il broker è indisponibile. Il trasporto filesystem usato nel collaudo è solo una prova locale, non una configurazione distribuita consigliata.

Guida dei dati, comandi e limiti: **docs/database-planning.md**. PostgreSQL 17.10 locale è stato collaudato con veri vincoli e connessioni concorrenti. Redis e Compose end-to-end non eseguiti qui; non usare SQLite come prova di lock o concorrenza.

## v0.7 — motivi di rifiuto, portali, moduli e accessibilità
Nessuna migrazione. Ricostruire backend e frontend. Novità operative:
- **Spostamenti spiegati**: un rifiuto del validatore include `violations` (codici puntuali); `GET /api/v1/occurrences/<id>/reschedule-options/?date=AAAA-MM-GG` (solo centro, sola lettura) restituisce per ogni inizio a 15' `{start_at, ok, codes}`. La modale «Sposta» li usa per marcare la ruota e spiegare il motivo.
- **Seed su più giorni**: `seed_planning_demo` crea disponibilità e aperture lunedì, mercoledì e giovedì 10–16 (`--days 0,2,3` di default; `--days 0` per il solo lunedì). Sui database già popolati il comando aggiunge solo i giorni mancanti.
- **Portali**: `GET /api/v1/my/lessons?from=&until=` (sviluppo sperimentale, massimo 62 giorni) restituisce le lezioni del tutor collegato all'account o degli studenti visibili (STUDENT, GUARDIAN con delega verificata); gli altri partecipanti sono solo conteggiati. Per provarli:
  ```bash
  docker compose exec backend python manage.py seed_portal_demo --actor NOME_UTENTE_CENTRO
  # Gli account tutor-planning-demo-1, portale-famiglia-demo e portale-studente-demo hanno password inutilizzabili.
  # Solo in locale, impostare una password temporanea e rimuoverla dopo la prova:
  docker compose exec backend python manage.py changepassword portale-famiglia-demo
  ```
- **Configurazione e Laboratorio** con moduli strutturati e riepiloghi leggibili; JSON disponibile come «JSON avanzato».
- **Accessibilità**: audit axe-core (WCAG 2.2 AA automatico) senza violazioni su schermate, modali e portali; esito in `docs/evidence/v0.7-axe.json`. La verifica manuale con lettori di schermo resta da fare.

## v0.6 — interfaccia Lumen
Solo frontend: nessuna migrazione o modifica API rispetto alla v0.5. Ricostruire l'immagine/il bundle del frontend (`npm run build` in `frontend/`). Le preferenze di tema e movimento restano nel browser (`localStorage`). Dettagli in `docs/design/ui-standard.md` §14 e `docs/changelog.md`.

## v0.5 — calendario sintetico del centro
La pubblicazione è disabilitata per default. Solo per collaudo con dati sintetici, impostare in `.env` **EXPERIMENTAL_CALENDAR=1** (DEBUG e EXPERIMENTAL_DB_PLANNING devono essere 1) e riavviare i container. Il database deve essere PostgreSQL **UTF8**, con estensione btree_gist e tutte le migrazioni. In impostazioni normali SQLite rifiuta questi comandi.

```bash
docker compose up -d --build
docker compose exec backend python manage.py migrate
# Creare il proprio superuser e il demo se non già fatto:
docker compose exec backend python manage.py seed_planning_demo --actor NOME_UTENTE_CENTRO
```
Prima generare una nuova proposta in **Proposte**. Poi aprire **Agenda**, sezione «Proposte da pubblicare»: rivedere lezioni e richieste non collocate, scrivere il motivo se parziale e confermare esplicitamente l'uso sintetico. La pubblicazione salva nella stessa transazione lezioni, partecipanti, prenotazioni, audit minimale ed eventi; nessuna email viene inviata.

Spostamenti: dall'Agenda trascinando la lezione o con «Sposta» (giorno della stessa settimana e ruota oraria, motivo obbligatorio); tutor/durata/partecipanti/risorse invariati; subito dopo è disponibile «Annulla». Cancellazione: libera solo le proprie prenotazioni, conserva storico e lascia la domanda canonica da gestire; non crea automaticamente recuperi. Una nuova proposta mantiene le altre lezioni bloccate e può proporre nuovamente la sola unità libera.

Da v0.4: eseguire migrate e generare nuove proposte. Gli artefatti delle build precedenti restano storici e non vengono aggiornati o pubblicati automaticamente.

Guida completa: **docs/calendar.md**. Gli endpoint del calendario sono per il solo centro; dalla v0.7 tutor e famiglie leggono le proprie lezioni da `/api/v1/my/lessons`. Azioni dai portali, presenze, workflow dei conflitti e recuperi sono incrementi successivi.
