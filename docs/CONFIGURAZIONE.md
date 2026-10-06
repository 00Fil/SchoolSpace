# Configurazione guidata · gestionale ripetizioni v0.9

Ogni passo ha un **controllo**: se non dà il risultato atteso, fermati e annota l'errore (comando + ultime 30 righe).

## 0. Prerequisiti
- Docker con Compose v2 (`docker compose version`), 4 GB di RAM liberi, rete per il primo build.
- Senza Docker: Python 3.13, Node ≥ 22.12, PostgreSQL 17, Redis 7.

## 1. Variabili d'ambiente
```bash
cp .env.example .env
python3 -c "import secrets;print(secrets.token_urlsafe(64))"   # incollare in DJANGO_SECRET_KEY
python3 -c "import secrets;print(secrets.token_urlsafe(32))"   # POSTGRES_PASSWORD e REDIS_PASSWORD (due valori diversi)
```
Regole del centro (decisioni già prese):

| Variabile | Valore | Decisione |
|---|---|---|
| `RECOVERY_NOTICE_HOURS` | 24 | preavviso per il recupero (P4) |
| `TUTOR_CHANGES_REQUIRE_GUARDIANS` | 1 | i genitori confermano sempre le modifiche del tutor (P5) |
| `PORTAL_STUDENT_CAN_REQUEST_CHANGES` | 0 | studente minorenne: solo visione (P5) |
| `PRIVACY_NOTICE_VERSION` | 2026-10 | cambiarla quando cambia l'informativa (P6) |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | `http://localhost:5173` in locale, `https://…` in produzione | obbligatoria con DEBUG=0 |

## 2. Avvio
```bash
docker compose up -d --build
docker compose ps          # controllo: db, redis, backend, frontend, worker-solver, beat "running"/"healthy"
```

## 3. Database
```bash
docker compose exec backend python manage.py migrate
docker compose exec backend python manage.py makemigrations --check --dry-run   # controllo: "No changes detected"
docker compose exec backend python manage.py bootstrap_center
docker compose exec backend python manage.py record_parentali_scope
docker compose exec backend python manage.py createsuperuser
```

## 4. Controllo automatico
```bash
docker compose exec backend python manage.py preflight
```
Controllo: nessuna riga ERRORE. In locale sono normali gli avvisi su DEBUG e sull'invio email.

## 5. Test
```bash
bash scripts/test-backend.sh   # suite su PostgreSQL come la CI, ambiente pulito (il .env non entra nei test)
bash scripts/test-backend.sh tests/test_p6_privacy.py -x   # solo alcuni file
```
Controllo: nessun test fallito. I nuovi test delle fasi sono `test_p4_*`, `test_p5_*`, `test_p6_privacy.py`: se falliscono per fixture mancanti (`center`, `guardian_of`, `publish`) segnalalo, non sono stati eseguiti nell'ambiente di sviluppo.

## 6. Frontend
```bash
python3 -m pip install pyyaml          # serve a gen:api
cd frontend && npm ci
npm run gen:api && npm run check:api   # rigenera i tipi dall'OpenAPI
npm run build                          # include tsc --noEmit: controllo dei tipi completo
npx playwright install chromium
npm run e2e && npm run e2e:config && npm run e2e:orari && npm run e2e:operativita && npm run e2e:dati
```
Controllo: build senza errori; ogni E2E scrive un report in `docs/evidence/` con 0 violazioni axe.

## 7. Prova manuale per ruolo (http://localhost:5173)
1. **Centro** (superuser): Configurazione → anno scolastico, chiusure, periodi di recupero, aule, materie. Anagrafica → importa famiglie dal CSV (anteprima, poi applica). Privacy → Conservazione: approva le regole.
2. **Tutor**: invito → attivazione → disponibilità → presa visione degli orari, contro-proposta.
3. **Genitore**: invito → informativa al primo accesso → disponibilità del figlio → richiesta di modifica → conferma delle modifiche del tutor → I miei dati (export).
4. **Studente ≥ 14 anni**: account proprio, solo visione di lezioni e link; maggiorenne: riconferma deleghe.
5. **Centro**: Proposte → genera il piano → accetta → pubblica; Da gestire → approva richieste, recuperi, conflitti.

## 8. Produzione (solo dopo i gate)
`infra/env/production.env.example` → segreti come file (`*_FILE`), `DJANGO_DEBUG=0`, nessun `EXPERIMENTAL_*`, SMTP reale, TLS (`scripts/tls-bootstrap.sh`), backup (`scripts/backup.sh`) e prova di ripristino (`scripts/restore-drill.sh`), `preflight` senza errori.

## Mancanze note (non bloccano la prova locale)
- Testo ufficiale dell'informativa e documenti C03/C05/C06: a cura del titolare.
- Durate di conservazione (D09) da approvare.
- E2E dell'area Privacy e ricerca dell'interessato per nome: P7.
- Penetration test, staging, pilota, firme D01–D09: P7.


## Note per Windows (Git Bash)

- I percorsi che iniziano con `/` vanno protetti con `MSYS_NO_PATHCONV=1` (lo script lo fa da solo).
- Il nome della cartella decide il nome del progetto Docker: una cartella nuova = database nuovo, quindi vanno rifatti migrate, bootstrap_center, record_parentali_scope, createsuperuser.
- Non usare `DJANGO_DEBUG=0` per i test: attiva il redirect HTTPS (301) e falsa tutta la suite.
