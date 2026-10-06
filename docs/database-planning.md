# Database → pianificatore — v0.4 sperimentale

## Perimetro
È un bridge tecnico di una settimana locale, non il calendario operativo del paper. Legge richieste individuali esplicite e richieste derivate dal curriculum parentale, con membri materializzati e fingerprint coerente. Il percorso deve avere copertura delle materie dichiarate. Nessun programma scolastico ufficiale viene dedotto o certificato.

Usare solo dati sintetici. G1/G2/G3 non dichiarati superati. Flag DEBUG=1 ed EXPERIMENTAL_DB_PLANNING=1 necessari per nuovi job/configurazioni; il flag G1_APPROVED non certifica nulla. Solo centro; account non autorizzati non vedono proposte.

## Dati necessari
1. Richieste con materia, livello, durata 60/90/120, quantità settimanale, priorità, periodo e modalità espliciti. Gruppi legacy senza curriculum canonico bloccati, non reinterpretati.
2. Tutor con account attivo, competenze approvate per materia/livello/modalità/periodo e TutorOperatingPolicy con carichi, pause e transizioni dichiarati.
3. AvailabilityDeclaration per ogni soggetto pertinente: UNKNOWN blocca; DECLARED_NONE non è disponibilità totale. Regole DRAFT nel periodo richiedono approvazione o revoca. Conflitti aperti bloccano; le rimozioni datate prevalgono sulle aggiunte.
4. ServiceWindow generali e ResourceTiming per ogni risorsa attiva. Ereditarietà delle aperture e buffer zero richiedono valori espliciti. Closure restringe le finestre.
5. PlanningPolicy approvata **per esplorazione**, budget 0.1–10 s, policy sulle settimane parziali, online in sede e risorse video. Nessun vincolo obbligatorio noto va omesso: dichiarazioni unsupported bloccano.

La console tecnica crea/modifica questi record via JSON chiuso; PATCH richiede expected_version. Gli esempi UI sono valori sintetici da verificare, non politiche approvate del centro. Per i riferimenti UUID consultare le API/anagrafiche. La sezione Disponibilità approva/revoca le regole con motivo e versione attesa; non conferisce disponibilità in assenza della dichiarazione.

## Pipeline e API
- GET /planning/data-readiness?policy_id=UUID&horizon_start=2026-10-05&mode=STRICT restituisce revisione, completezza e primo blocco rilevato. Nessuna unità/snapshot salvata durante la verifica; non è un diagnostico esaustivo.
- POST /schedule-runs (senza slash finale): body policy_id, horizon_start (lunedì), expected_revision, mode STRICT/COVERAGE; header Idempotency-Key obbligatorio.
- Commit breve: lock revisione, lettura dati, unità canoniche, snapshot, run QUEUED, dispatch PENDING, risposta idempotente e audit minimale. Solo dopo commit contatto con broker.
- GET /schedule-runs/ e /schedule-runs/{id}/: polling; stato job distinto da esito solver; fasi reali, nessuna percentuale inventata. Le liste sono paginabili.
- POST /schedule-runs/{id}/cancel/: richiesta idempotente di annullamento. In esecuzione viene rilevata alle fasi e prima del salvataggio; non promette interruzione istantanea della ricerca CP-SAT.
- GET /schedule-plans/: sole proposte immutabili validate. Stato STALE derivato se revisione corrente differisce. Nella v0.4 nessuna booking; la v0.5 aggiunge il comando separato e protetto di pubblicazione **sperimentale**, documentato in calendar.md. Nessuna email.
- POST /availability-rules/{id}/approve/ o /revoke/: expected_version e reason.

## Identità, revisioni e immutabilità
DemandUnit identifica richiesta + settimana locale + progressivo. Ripetere generazione non duplica la domanda, ma un comando distinto può creare una nuova proposta. La v0.5 riconcilia le lezioni attive pubblicate del calendario sintetico come blocchi e non duplica la loro domanda. Lezioni svolte/recuperi e calendario reale di produzione non supportati.

Snapshot JSON minimizzato con UUID, hash SHA-256 canonico, policy/versione, revisione, Python/build/OR-Tools e hash del file timezone Europe/Rome effettivo. Non contiene email, nomi, link video o credenziali. Questi dati restano pseudonimi, non automaticamente anonimi. I livelli sono identificatori hash derivati dall'etichetta dichiarata.

Le scritture applicative ORM tracciate acquisiscono lock globale e incrementano la revisione; m2m del curriculum e operazioni bulk principali sono intercettate. Il controllo è conservativo (anche modifiche descrittive invalidano). **Raw SQL, scritture dirette alle tabelle through e ruoli amministrativi DB non sono protetti da un trigger universale.** Snapshot e proposta protetti dal manager/model ORM e da admin read-only; nessuna garanzia append-only contro accesso diretto DB. Metadati registrati/fence non garantiscono identica soluzione su hardware o versioni differenti.

## Coda e recupero
Redis è solo trasporto, RunDispatch è il registro persistente. Crash/perdita messaggio vengono recuperati da beat ogni 15 s o dal comando dispatch_pending_runs. Un messaggio duplicato non reclama un job già terminale/in corso. Lease 120 s, massimo 3 claim; claim_token impedisce a un vecchio worker di committare dopo riconciliazione. Coda PENDING conserva l'errore genericamente, senza URL/segreti.

Input obsoleto prima del claim: FAILED / STALE_INPUT, senza ricerca. Modifica durante ricerca: proposta non pubblicabile e STALE. Attore revocato: risultato scartato. Job SUCCEEDED con INFEASIBLE/UNKNOWN resta un esito matematico non pubblicabile, non un successo di copertura. Errori tecnici non vengono attribuiti a famiglie.

Celery prefork configurato soft limit 60 s e hard limit 90 s; ricerca interna ≤10 s. Timeout di processo **non verificati** qui. Lease/reconciler fanno recupero, non rendono exactly-once il trasporto. Nessun parallellismo reale DB validato su SQLite.

## Tempo e limiti
Una settimana Rome può essere 167/168/169 ore UTC. Inizi griglia 15 minuti, precisione minuto; orari ambigui/inesistenti rifiutati, mai spostati implicitamente. Settimana parziale BLOCK oppure quantità piena entro date attive, esplicitamente selezionata; nessun prorata inventato.

Limiti: 40 unità, 10 tutor, 120 studenti, 3000 candidati; superamento blocca, non tronca. Solo obiettivi P0/P1/P2; non implementati equità completa, slot ricorrente stabile, preferenze, frammentazione, sequenze curricolari/sincronizzazione familiare. Studenti online dalla sede bloccati (occupazioni non modellate). Durate extra/catalogo persistente e buffer studente non implementati. Nessuna estensione automatica a sei settimane.

## Verifica e prossimo passo
Vedere qa-report.md per prove realmente eseguite e limiti PostgreSQL/Redis. Prima di calendario pubblico: policy residue approvate, modello dominio definitivo, race test su PostgreSQL reale, ResourceBooking/GiST, validazione transazionale e commit atomico, audit/outbox, presenze/recuperi e sicurezza. Non bypassare questi controlli con un bottone Pubblica.

## Aggiornamento v0.5
Vedere calendar.md: lezioni attive KEEP, prenotazioni e pubblicazione sperimentale. Snapshot/app delle build precedenti non convertiti: nuova generazione necessaria. Ruoli e deleghe entrano nella fence conservativa; cambi descrittivi/versioni possono rendere obsolete proposte e policy pubblicate.

## Aggiornamento v0.8 — bridge multi-settimana e contratto 0.5
- PlanningPolicy aggiunge `horizon_weeks` (1–6), `objective_order`, `fairness_policy_id/version`, `recurring_stability`, `student_buffer_minutes`, `allow_cross_local_midnight`; budget ammesso fino a 30 s (vincolo `planning_budget_range_v05`). Migrazione `0003_v05_policy_series`. Una policy con questi campi produce DTO 0.5; le altre restano 0.4. Ordine obiettivi e politica di equità sono validati e restano **da approvare** (D03).
- Il bridge genera unità per ogni settimana dell'orizzonte (richiesta + settimana + progressivo), allega il calendario pubblicato settimana per settimana e compila le LessonSeries in `series`.
- `LessonSeries` (configurazione `lesson-series`, tracciata nella revisione): slot settimanale stabile per richiesta e progressivo. `POST /schedule-plans/{id}/derive-series/` deriva le serie da una proposta validata, con audit; non pubblica nulla.
- Ripianificazione locale (D05): `POST /schedule-runs` accetta `unlock: [{lesson_id, reason}]` e `propose_scope_expansion`. Ogni sblocco è autorizzato e registrato in PlanningAudit (`authorize_unlock`); le lezioni sbloccate diventano `previous_assignment`, le altre restano bloccate. L'eventuale estensione del perimetro è solo proposta.
- Worker: lease 120 s, massimo 3 tentativi; `SoftTimeLimitExceeded` termina il run come FAILED / SOFT_TIME_LIMIT senza salvare risultati parziali. Prove in `tests/test_solver_celery.py` (il test con Redis reale si attiva con `SOLVER_TEST_REDIS_URL`).
- Limite noto: la pubblicazione nel calendario sintetico resta per una settimana alla volta (`active_week`); una proposta di 6 settimane va pubblicata settimana per settimana.
