# Pianificazione in produzione — v0.9.4

## Flusso
1. Il centro crea richieste (già approvate) o le famiglie le inviano (`PENDING`); il centro le approva da **Calendario › Pianificazione** o **Didattica › Richieste**. Solo le richieste `APPROVED` entrano nello snapshot.
2. Vincoli rispettati dal motore: disponibilità approvate di studenti (inserite dai genitori) e tutor, aperture e chiusure del centro, competenze approvate (materia, livello, modalità), carichi e pause dei tutor, aule/canali, tutor obbligatorio (`REQUIRED`, vincolo duro). Il tutor preferito (`PREFERRED`) è un termine morbido P: non toglie mai copertura (P0–P2) né equità (F).
3. `GET /api/v1/planning/overview?horizon_start=<lunedì>` compila lo stesso snapshot del motore e i candidati: per richiesta tutor competenti, orari possibili, margine minimo e motivi; ore disponibili/richieste per tutor e studenti. Sola lettura.
4. `POST /api/v1/schedule-runs` con `effort`: `STANDARD` (budget della policy, ≤ 30 s) o `THOROUGH`.
5. La proposta validata si rivede e pubblica dall'Agenda, settimana per settimana.

## Profilo accurato (THOROUGH)
| Impostazione | Default | Note |
|---|---|---|
| `PLANNING_THOROUGH_BUDGET_SECONDS` | 21600 (6 h) | massimo 43200 (schema 0.5) |
| `PLANNING_THOROUGH_WORKERS` | core disponibili, max 8 | allineare ai `cpus` del servizio |
| `PLANNING_THOROUGH_QUEUE` | `solver` (dev), `solver_long` (prod) | servizio `worker-solver-long` |

Invarianti per run (`runs.run_limits`): budget < soft (budget + 600 s) < hard (+60 s) < lease (+120 s). Un watchdog aggiorna il battito ogni 20 s e ferma CP-SAT se il run viene annullato. Un riavvio del worker durante il calcolo lo rimette in coda (acks_late) e lo riesegue da capo, massimo 3 tentativi. Il presolve completo di CP-SAT è attivo solo per budget > 30 s.

Benchmark sintetico (240 unità, 2 settimane, stessa macchina): 10 s/1 processo → P1 non coperto 1140 min; 120 s/4 processi → 960 min. Entrambe validate dal validatore indipendente.

## Limiti noti
- Dimensioni per run: 720 unità, 10 tutor (schema fino a 20), 120 studenti, 150.000 candidati, orizzonte fino a 6 settimane; durate 60/90/120 min.
- Oltre i limiti il bridge si ferma (`DEMAND_LIMIT`), non tronca la domanda.
- Su istanze grandi il risultato può essere «buona soluzione» (FEASIBLE) e non ottimo dimostrato: la UI lo indica.

# Motore di simulazione CP-SAT — build 0.8 (contratto 0.5)

## Novità del contratto 0.5
Il contratto `0.4` resta accettato con i limiti e la semantica storici (archivio in `contracts/versions/`). Un DTO con `schema_version: "0.5"` abilita:
- **Orizzonte fino a 6 settimane locali** (`horizon_days` ≤ 42, fino a 60.540 minuti con i cambi d'ora). Limiti di default 0.5: 720 unità, 10 tutor, 120 studenti, 150.000 candidati, sovrascrivibili in `limits` solo verso il basso o entro i massimi dello schema. Superamento → BLOCKED, mai troncamento.
- **Vettore lessicografico completo** `objective_order` su P0, P1, P2, F (equità), C (stabilità ricorrente), R (ripianificazione minima), P (preferenze), G (frammentazione: proxy giorni attivi per partecipante). Ogni fase fissa il proprio valore solo dopo OPTIMAL e passa la soluzione come hint alla fase successiva. Il risultato riporta `objective_scope: LEXICOGRAPHIC_VECTOR`, `objective_vector`, `evaluated_objectives` (ricalcolati da `objectives.py`, indipendente dal modello: discordanza → OBJECTIVE_MISMATCH) e lo stato di ottimalità di ogni livello.
- **Politiche da approvare (D03)**: ordine del vettore, posizione dell'equità e definizione `fairness-default` v1 (max deficit relativo per studente, minuti per beneficiario) sono marcati `PENDING_APPROVAL`, riportati in `policy_approvals` e nei `warnings`. Una nuova definizione richiede una nuova versione registrata.
- **Serie e famiglie**: `series` (stesso slot settimanale, REQUIRED o PREFERRED), `family_constraints` (SAME_START, SAME_INTERVAL, SAME_DAY, DIFFERENT_DAYS, NO_OVERLAP), `sequences` (ordine curricolare tra unità), `enrollments` (periodi di iscrizione), `preferences` pesate.
- **Studente online dalla sede**: finestra con `location`, occupazione di uno spazio dichiarata come `student_space_id` nell'assegnazione. Buffer studente (`student_buffer_minutes`) e lezioni oltre la mezzanotte locale (`allow_cross_local_midnight`) sono ora modellati e verificati dal validatore.
- **Ripianificazione locale (D05)**: `replanning` con unità sbloccate esplicitamente e `previous_assignment`; l'obiettivo R minimizza gli spostamenti. Con `propose_scope_expansion` il risultato può contenere `scope_expansion`, una **proposta** di ulteriori unità da sbloccare, mai applicata.

## Prestazioni (NFR04)
In 0.5 il budget (`budget_seconds` ≤ 30, default di policy) parte **dopo** la costruzione del modello; `statistics` separa build, ricerca, validazione e diagnostica. Il modello usa pool di spazi identici via cumulative, transizioni a clique, riuso degli intervalli, rottura delle simmetrie e un warm start greedy usato solo come hint (`warmstart.py`). Parametri CP-SAT 0.5: `num_search_workers` da `search_workers`, probing 0, una iterazione di presolve, symmetry level 1. Benchmark riproducibile:

```bash
cd backend
python manage.py benchmark_solver --runs 20 --output ../docs/evidence/v0.8-solver-benchmark
```

Ogni esecuzione gira in un sottoprocesso separato (CPU e RSS da `wait4`) sulla fixture `contracts/fixtures/planning-benchmark-720.json` (10 tutor, 80 studenti in 50 famiglie, 3 spazi, 120 sessioni a settimana × 6 = 720 unità, con cambio d'ora). Risultati misurati: `docs/evidence/v0.8-solver-benchmark.md`.

## Diagnostica (D06)
- `hypotheses`: per unità non collocate, spostamenti entro disponibilità già dichiarate (MOVE_WITHIN_DECLARED) o richieste di nuova disponibilità (REQUEST_NEW_AVAILABILITY). Sempre `booking_allowed=false`; budget massimo 3 s.
- `conflict_analysis`: sottomodelli isolati per unità e insieme di assunzioni sufficiente (`sufficient_assumptions`) quando CP-SAT lo fornisce. Non è un unsat core minimo e non attribuisce colpe a famiglie.

Il testo seguente descrive il comportamento storico del contratto 0.4, ancora valido per DTO 0.4.

# Motore di simulazione CP-SAT — v0.4

## Cosa fa realmente
Esegue OR-Tools CP-SAT su un DTO JSON sintetico chiuso e limitato; produce assegnazioni proposte, verifica ogni risultato con un validatore separato e restituisce hash input, policy e versione solver.
Il laboratorio sincrono **non** legge dati del database e non crea ScheduleRun; il nuovo bridge documentato in database-planning.md lo fa in un job separato. Il laboratorio non non prenota spazi, non pubblica lezioni e non invia notifiche. Non sostituisce G1/G2/G3.

## Avvio
Usare le istruzioni di sviluppo del README e accedere come centro. Aprire **Simulazione**, caricare il demo, selezionare strict/coverage e premere **Calcola proposta non pubblicabile**.
L'interfaccia mostra lo stato reale, le assegnazioni in Europe/Rome, i livelli di copertura provati, le unità non assegnate e la validazione. Il risultato è esportabile come JSON.

Da terminale locale, con ambiente virtuale e variabili di sviluppo già impostate:

```bash
cd backend
python manage.py simulate_plan --output ../simulazione.json
# Oppure con DTO esplicito:
python manage.py simulate_plan --input ../contracts/fixtures/planning-demo.json --output ../simulazione.json
```

Con Docker:

```bash
docker compose up -d --build
docker compose exec backend python manage.py simulate_plan --output /tmp/simulazione.json
docker compose cp backend:/tmp/simulazione.json ./simulazione.json
```

Il comando non richiede il seed dei percorsi parentali: i dati sono uno scenario indipendente. Il demo CP-SAT rappresenta 6 unità di lezione di una settimana per 4 studenti sintetici, 2 tutor e 3 spazi. Non è un programma scolastico reale.

## DTO e convenzioni
Contratti: `contracts/planning-input.schema.json` e `contracts/planning-result.schema.json`. Il primo è copiato nella cartella schemas dell'app per il container. Nessuna email, password, contatto, nome di minore o URL video richiesto dal DTO.
- Epoca UTC esplicita, allineata al quarto d'ora; start/end interi in minuti dall'epoca.
- Fuso Europe/Rome, orizzonte massimo una settimana locale (fino a 169 ore UTC); finestre sono intervalli semiaperti.
- Catalogo dichiarato fra 60/90/120 minuti; inizi sulla griglia 15 minuti.
- Ogni unità ha chiave canonica univoca, partecipanti espliciti, materia/livello, priorità, obbligatorietà, modalità, tutor ammessi e periodo.
- Stato UNKNOWN blocca la ricerca; DECLARED_NONE richiede finestre vuote; anche unrestricted ha finestre esplicite limitate all'orizzonte.
- Competenze, disponibilità, servizio, chiusure, capienze, carichi, pause e matrice remoto/sede sono esplicitamente forniti, non dedotti dal database.
- Lezioni oltre mezzanotte locale e buffer studente diversi da zero non sono supportati: il DTO richiede esplicitamente `allow_cross_local_midnight=false` e `student_buffer_minutes=0`; valori diversi vengono rifiutati.
- `unsupported_constraints` deve dichiarare vincoli ancora fuori modello: se non è vuoto la simulazione è BLOCKED. Non usarlo per omettere regole effettivamente obbligatorie.

Lo stesso DTO v0.4 è ora costruito dal bridge DB su snapshot/revisione e metadati ambiente. Riconciliazione con calendario pubblico e modello completo del paper restano da integrare.

## Vincoli implementati nel prototipo
Un'alternativa per unità; durata; intersezione di tutti i partecipanti; materia/livello e skill valide sull'intero intervallo; modalità/localizzazione; finestre di servizio e chiusure; tutor e studenti esclusivi tra online/presenza; spazi esclusivi (massimo tre, capienza due); online in sede con spazio quando dichiarato; canali video esclusivi quando richiesti; appuntamenti bloccati validi; carichi giornalieri/ISO-settimanali in minuti; pause e transizioni.
Un gruppo di tre in presenza non viene diviso dal motore. La coorte resta distinta dal gruppo di una lezione.
Il buffer di spazio e la pausa del tutor occupano risorse differenti. La distanza tra lezioni di un tutor è `max(pausa, transizione)` per non contare due volte una pausa già incorporata. La diagonale della matrice è zero; le pause per stessa localizzazione sono dichiarate a parte.

## Ricerca e obiettivi
Il prototipo enumera tutti gli inizi ammissibili nei dati limitati, non usa top-k. Limite 40 unità, 10 tutor, 120 studenti e 3.000 candidati. Se il limite viene superato, risponde BLOCKED, non INFEASIBLE.
Strict assegna tutte le unità. Coverage mantiene mandatory e locked come vincoli e minimizza lessicograficamente minuti non assegnati per beneficiario in P0, P1, P2.
Un livello viene fissato solo dopo OPTIMAL. FEASIBLE o tempo esaurito ferma la sequenza, senza attribuire ottimalità ai livelli inferiori. Un incumbente valido di un livello precedente viene conservato se il budget termina dopo quel livello.
Equità, stabilità ricorrente, preferenze, frammentazione e sequenze curricolari del vettore completo del paper **non** sono implementate. `OPTIMAL` si riferisce esclusivamente a `COVERAGE_P0_P1_P2_ONLY`.
Il budget massimo di ricerca è 10 secondi nella simulazione; non è un timeout hard di processo né una garanzia end-to-end. Preparazione del modello, validazione e condizioni macchina possono aggiungere tempo.

## Validazione e diagnostica
Il validatore non chiama il generatore dei candidati o il solver: rilegge il DTO, fa contenimento tramite sweep di intervalli, ricalcola prenotazioni, carichi, transizioni, eligibilità, blocchi e copertura obbligatoria.
Un risultato alterato o invalido è VALIDATION_FAILED e viene scartato. Lo stato UNKNOWN non significa impossibilità. MODEL_INVALID è un errore tecnico, non un problema attribuito a una famiglia.
Diagnostica dei domini vuoti e motivi di esclusione sono osservazioni del compilatore, non un unsat core minimo. Il conflitto globale non viene spiegato come impossibilità individuale di ogni richiesta.

## Blocco operativo
Endpoint `/planning/example` e `/planning/simulate`: solo centro e DEBUG=1; fuori sviluppo sono disabilitati. Un semaforo limita una simulazione per processo, non un sistema distribuito di code. `/schedule-runs` è ora un job sperimentale; readiness operativa resta false.
La v0.5 aggiunge una API separata di pubblicazione nel solo calendario sintetico del centro. Non esiste pubblicazione di produzione. Tutti i risultati hanno `publishable=false` e `calendar_changed=false`, anche se il solver prova un optimum del prototipo.
Il bridge v0.4 integra i dati e i job di prova; il calendario transazionale non è ancora implementato.

La source pipeline v0.5 mantiene le lezioni attive come locked_assignment. Le operazioni sul calendario restano separate da solve(): vedere calendar.md.
