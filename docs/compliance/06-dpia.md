# Valutazione d'impatto sulla protezione dei dati (DPIA) — prevalutazione e bozza strutturata

| Campo | Valore |
|---|---|
| Stato | **BOZZA** — prevalutazione completa; valutazione dei rischi da validare con il consulente; non firmata |
| Versione | 0.1 — 2026-10-02 |
| Documento del fascicolo | n. 4 — gate G6 (da completare **prima del pilota con dati reali**) |
| GAP | GAP-H02 |
| Responsabile | Titolare del trattamento con consulente qualificato: [DA COMPILARE] |
| Contributi | Architect/tech lead (misure tecniche), operations (continuità), responsabile didattico (contesto) |
| Riferimenti normativi | GDPR artt. 25, 32, 35, 36; Linee guida WP248 rev.01 (Gruppo Art. 29, fatte proprie dall'EDPB); Provv. Garante 11 ottobre 2018, n. 467 (elenco dei trattamenti soggetti a DPIA); ISO/IEC 29134 (metodo, facoltativo) |
| Prossimo riesame | Prima del go-live; poi annuale e a ogni modifica rilevante (nuovi moduli, nuovi fornitori, categorie di dati, fine delle esclusioni del §1.4 del paper) |

> Non è un parere legale. La metodologia segue l'indice dell'appendice "Modelli operativi" della guida e gli allegati 2
> delle WP248. Le valutazioni di probabilità e gravità sono proposte tecniche da discutere.

## Parte A — Prevalutazione (necessità della DPIA)

### A.1 Criteri WP248 rev.01

| # | Criterio | Presente | Motivazione |
|---|---|---|---|
| 1 | Valutazione o assegnazione di un punteggio (profilazione, previsione) | No | Il sistema non valuta rendimento, comportamento o affidabilità |
| 2 | Decisione automatizzata con effetti giuridici o analoghi | No | Il solver propone; la pubblicazione è decisa da un coordinatore (FR14/FR15) |
| 3 | Monitoraggio sistematico | Parziale | Presenze degli studenti e carichi/disponibilità dei tutor; limitati alla finalità di erogazione (doc. 15) |
| 4 | Dati sensibili o di natura altamente personale | No per progetto | Categorie art. 9 escluse; rischio residuo nelle note libere |
| 5 | Trattamento su larga scala | Probabilmente no | Circa 10 tutor e 50 famiglie (paper §1.2); studenti [DA COMPILARE dal censimento GAP-A05] |
| 6 | Combinazione o raffronto di insiemi di dati | No | Nessun incrocio con fonti esterne |
| 7 | **Interessati vulnerabili** | **Sì** | Minori; inoltre dipendenti/collaboratori in rapporto di subordinazione rispetto al titolare |
| 8 | Uso innovativo o applicazione di nuove soluzioni tecnologiche | Limitato | Ottimizzazione a vincoli senza apprendimento automatico |
| 9 | Trattamento che impedisce di esercitare un diritto o di avvalersi di un servizio | No | — |

### A.2 Elenco del Garante (provv. n. 467/2018)
L'elenco comprende i trattamenti **non occasionali** di dati relativi a **soggetti vulnerabili** (tra cui i minori) e
i trattamenti effettuati nell'ambito del rapporto di lavoro mediante sistemi che consentono il monitoraggio. Il primo
punto ricorre; il secondo va valutato rispetto all'audit e ai carichi dei tutor (proposta: non ricorre, perché il sistema
non è uno strumento di monitoraggio dell'attività, vedi doc. 15) [DA VALUTARE con il consulente].

### A.3 Esito della prevalutazione (proposta)
Ricorre almeno un criterio WP248 (n. 7) con un criterio parziale (n. 3) e il trattamento rientra nell'elenco del Garante.
**Proposta: eseguire la DPIA** (le WP248 indicano che due criteri rendono la DPIA di norma necessaria; l'inserimento
nell'elenco nazionale la rende comunque dovuta). Documentarla costa meno che motivarne l'esclusione.

Decisione del titolare: ☐ DPIA dovuta — si procede ☐ DPIA non dovuta — motivazione: [DA COMPILARE]
Firma: ______________________ Data: __________

## Parte B — Descrizione sistematica del trattamento (art. 35.7.a)

### B.1 Contesto
Centro privato di ripetizioni con una sede, tre spazi da massimo due studenti, lezioni individuali e di gruppo in
presenza e online, circa 10 tutor e 50 famiglie. Sistema web autonomo con portali per centro, tutor, genitori e studenti.
Esclusi per baseline: pagamenti, fatturazione, chat, videoconferenza proprietaria, app native, raggruppamento pedagogico
automatico (paper §1.4).

### B.2 Trattamenti coperti
Schede TR-01…TR-12 del registro (`01-registro-trattamenti.md`).

### B.3 Ciclo di vita del dato

| Fase | Descrizione | Componenti |
|---|---|---|
| Raccolta | Iscrizione presso il centro; import iniziale (CSV versionato, dry-run, nessun invito in dry-run); inserimento da portali | `apps/privacy` importer, API registro |
| Uso | Pianificazione (snapshot immutabile → solver CP-SAT → validatore indipendente → pubblicazione umana); calendario; presenze | `apps/scheduling`, `apps/calendar` |
| Comunicazione | Notifiche transazionali via outbox; portali in lettura con scope per studente | `apps/communications`, `api/portals` |
| Conservazione | PostgreSQL gestito UE con cifratura a riposo; PITR; export logici | infrastruttura (GAP-J04, L01) |
| Cancellazione | Job di retention con dry-run, approvazione e ricevuta; anonimizzazione su richiesta; scadenza dei backup; riconciliazione dopo restore | `privacy_retention`, `privacy_reconcile` |

### B.4 Flussi e attori
```
Genitore/Studente ──HTTPS──► Reverse proxy ──► Backend (Django/DRF) ──► PostgreSQL (UE, cifrato)
Tutor/Centro      ──HTTPS──►        │                 │                     │
                                    │                 ├──► Redis/Celery (code, solver) — dati minimi
                                    │                 ├──► Provider email UE (solo destinatario + evento)
                                    │                 └──► Error tracking UE (scrubbing)
                                    └──► Backup PITR / export logici (storage separato)
Fornitore di manutenzione ──(accesso nominativo, MFA, log)──► ambienti di produzione solo su richiesta
```

### B.5 Fornitori
Vedi `09-fornitori-checklist.md`. [DA COMPILARE dopo D08: elenco nominativo].

## Parte C — Necessità e proporzionalità (art. 35.7.b)

| Elemento | Valutazione | Riferimento |
|---|---|---|
| Finalità determinate e legittime | Sì: erogazione del servizio; sicurezza | Registro |
| Basi giuridiche | Art. 6.1.b per i flussi di servizio; 6.1.f per sicurezza; 6.1.c per diritti e violazioni. Nessun trattamento fondato sul consenso del minore | D07 (verbale `governance/verbale-D07.md`) |
| Bilanciamento del legittimo interesse (audit e log) | Interesse: integrità del calendario, sicurezza, ricostruzione. Necessità: senza audit non si ricostruiscono modifiche e accessi. Impatto: basso (dati di attività, nessun contenuto), retention breve, accesso ristretto, nessun uso per valutare il personale. Esito proposto: interesse prevalente con garanzie | TR-09, doc. 15 |
| Minimizzazione | Serializer per ruolo; nessun elenco dei compagni di gruppo; snapshot senza contatti/note/link; data di nascita solo se necessaria; note con limiti | GAP-F05, B08 |
| Esattezza | Rettifica dai portali/centro con audit; disponibilità con stato e versione; UNKNOWN non diventa "sempre disponibile" | T10, FR06 |
| Limitazione della conservazione | Matrice D09 con job governato | doc. 11 |
| Trasparenza | Quattro informative versionate con presa visione; spiegazione del ruolo del solver | doc. 2–5 |
| Diritti | Procedura e funzioni FR24 | doc. 13 |
| Art. 22 | Non applicabile: intervento umano obbligatorio e significativo (il coordinatore può modificare, scartare, ripianificare) | doc. 18 |
| Responsabili e trasferimenti | Contratti art. 28; preferenza UE; TIA se extra-SEE | doc. 8–10 |
| Pareri degli interessati (art. 35.9) | Proposta: consultazione leggera di 3–5 famiglie e dei tutor durante la UAT sui testi delle informative e sulla visibilità dei dati [DA COMPILARE: esito o motivazione dell'omissione] | GAP-G08 |

## Parte D — Rischi per i diritti e le libertà degli interessati (art. 35.7.c)

Scala: probabilità (P) e gravità (G) da 1 (trascurabile) a 4 (massima); livello = P × G (1–4 basso, 5–8 medio, 9–16 alto).
"Inerente" = senza misure; "residuo" = con le misure della Parte E effettivamente verificate.

| ID | Rischio (evento → impatto sugli interessati) | Fonte | P×G inerente | Misure principali (Parte E) | P×G residuo (proposto) |
|---|---|---|---|---|---|
| R1 | Accesso non autorizzato ai dati di un minore da parte di un altro genitore o utente esterno (IDOR/BOLA, delega errata) → esposizione di orari e abitudini del minore | Applicazione | 3×4=12 | M1, M2, M3, M9 | 1×4=4 |
| R2 | Delega attribuita a persona senza responsabilità genitoriale (es. genitore con limitazioni giudiziarie) → accesso illegittimo | Processo | 2×4=8 | M2, M14 | 1×4=4 |
| R3 | Notifica al destinatario errato o con elenco dei membri del gruppo → divulgazione | Comunicazioni | 3×3=9 | M4, M5 | 1×3=3 |
| R4 | Calendario errato pubblicato o perdita/alterazione delle lezioni → minore atteso nel luogo/ora sbagliati, mancata sorveglianza | Integrità | 2×3=6 | M6, M7, M10 | 1×3=3 |
| R5 | Furto di credenziali dello staff → accesso massivo | Sicurezza | 3×4=12 | M8, M9, M11 | 1×4=4 |
| R6 | Inserimento di categorie particolari nelle note libere (diagnosi, DSA) → trattamento non previsto e non protetto | Utenti | 3×3=9 | M12, M13 | 2×3=6 |
| R7 | Uso dei dati dei tutor (carichi, audit) per controllo a distanza non dichiarato → lesione dei diritti del lavoratore | Organizzazione | 2×3=6 | M15 | 1×3=3 |
| R8 | Conservazione eccessiva → esposizione prolungata in caso di violazione | Organizzazione | 3×2=6 | M16 | 1×2=2 |
| R9 | Riattivazione di accessi revocati o di dati cancellati dopo un restore | Esercizio | 2×4=8 | M17 | 1×4=4 |
| R10 | Fornitore che tratta dati fuori SEE o per fini propri; sub-responsabili non controllati | Fornitori | 2×3=6 | M18 | 1×3=3 |
| R11 | Dati reali di minori usati in test, demo o staging | Sviluppo | 2×4=8 | M19 | 1×4=4 |
| R12 | Indisponibilità prolungata (ransomware, guasto) → impossibilità di sapere dove/quando sono le lezioni | Disponibilità | 2×2=4 | M10, M20 | 1×2=2 |
| R13 | Account del minore usato da terzi o senza accordo del genitore | Processo | 2×3=6 | M2, M14 | 1×3=3 |
| R14 | Mancato passaggio di controllo alla maggiore età (accesso dei genitori mantenuto o revocato in silenzio) | Processo | 3×2=6 | M21 | 1×2=2 |
| R15 | Export di dati (diritti, controllo) intercettato o conservato oltre il necessario | Applicazione | 2×3=6 | M22 | 1×3=3 |
| R16 | Segreti, token, URL video o note nei log o nei sistemi di error tracking | Applicazione | 3×3=9 | M23 | 1×3=3 |

## Parte E — Misure previste (art. 35.7.d) ed evidenze

| ID | Misura | Evidenza richiesta per G6 | Stato [DA AGGIORNARE al merge] |
|---|---|---|---|
| M1 | Scope per singolo studente ricontrollato a ogni richiesta; queryset filtrati; serializer per ruolo | T24 completo (GAP-B08), test BOLA s1 | Parziale v0.7 → in corso |
| M2 | Inviti monouso con hash, scadenza, solo dopo verifica della relazione; revoca immediata | T25; `test_families_api.py` | Implementato (s4) |
| M3 | Bozze invisibili ai portali esterni | `test_family_cannot_read_experimental_calendar`, T24 | Implementato |
| M4 | Payload minimi; nessun elenco membri gruppo; link video solo via endpoint autorizzato a scadenza | GAP-F05, F04; test s3 | In corso (s3) |
| M5 | Destinatari calcolati dal server sulle deleghe attive al momento dell'invio | test outbox s3 | In corso (s3) |
| M6 | Validatore indipendente; pubblicazione atomica e umana; constraint DB anti-collisione | T18–T21, T29; test PG | Implementato (PG da eseguire in CI) |
| M7 | Storico e audit append-only anche contro SQL diretto | GAP-E08; `test_privacy_postgres.py` | Implementato (PG da eseguire in CI) |
| M8 | MFA obbligatoria per lo staff, sessioni revocabili, timeout | GAP-B04 | In corso (s1) |
| M9 | Rate limit, risposte non enumeranti, Argon2id | GAP-B03, B05 | In corso (s1) |
| M10 | Backup PITR, restore provato con RPO 15 min / RTO 4 h | T32, report di restore (GAP-L02) | Da eseguire |
| M11 | Admin Django protetto o disattivato in produzione; azioni admin auditate | GAP-I06; `test_admin_actions_are_audited` | Parziale |
| M12 | Avvisi e limiti di lunghezza sulle note; divieto nelle istruzioni agli autorizzati | Screenshot UI, doc. 12 | Da verificare |
| M13 | Formazione dello staff sui dati da non inserire | Registro formazione (piano N02) | Da eseguire |
| M14 | Procedura di verifica della responsabilità genitoriale (documenti visionati, non conservati; casi di affidamento) | Procedura doc. 13 §3 | Bozza |
| M15 | Policy d'uso dell'audit; nessuna metrica di produttività; accesso all'audit ristretto e tracciato | doc. 15 | Bozza |
| M16 | Matrice D09 approvata e job con ricevuta | `test_privacy_retention.py`; verbale D09 | Implementato, valori da approvare |
| M17 | Ledger esterno e riconciliazione dopo restore | `test_restore_reconciliation_reapplies_erasure_and_revocation`, T32 | Implementato; prova in staging da fare |
| M18 | Contratti art. 28, checklist fornitori, TIA | doc. 8–10 firmati | Da firmare |
| M19 | Dati sintetici per default; dati reali solo dopo G6 e con atto art. 28 per il fornitore | Seed sintetici; `test_optional_demo_is_idempotent_and_synthetic` | Implementato |
| M20 | Piano di continuità, runbook, comunicazione alle famiglie in caso di fermo | doc. 21, runbook GAP-L04 | Bozza |
| M21 | Job maggiore età senza revoca silenziosa; informativa maggiorenni | `test_privacy_majority.py` | Implementato, azione D07 da approvare |
| M22 | Export protetti: audience, token monouso nel corpo, scadenza 24 h, cancellazione al download, audit | `test_privacy_exports.py`, T42 | Implementato |
| M23 | Redazione dei log, scrubbing error tracking, test CI su pattern | GAP-I07; `test_redaction_of_synthetic_secrets` | Parziale |

## Parte F — Rischio residuo, pareri e consultazione preventiva

| Voce | Contenuto |
|---|---|
| Rischio residuo complessivo (proposta) | **Basso–medio**, condizionato all'esecuzione delle evidenze marcate "da eseguire" (T24 completo, MFA, restore, contratti). R6 (note libere) resta il rischio residuo più alto e dipende dal comportamento degli utenti |
| Parere del consulente / DPO | [DA COMPILARE] |
| Pareri degli interessati | [DA COMPILARE] |
| Consultazione preventiva del Garante (art. 36) | Non necessaria se il rischio residuo non è elevato [DA CONFERMARE] |
| Condizioni per il pilota con dati reali | Tutte le misure M1–M3, M6–M8, M10, M16–M19 con evidenza archiviata in `docs/evidence/G6/`; contratti art. 28 firmati |
| Piano di riesame | Annuale; a ogni modifica di categorie di dati, fornitori, moduli (es. pagamenti, chat, allegati), esiti di incidenti |

## Parte G — Approvazione

| Ruolo | Nome | Firma | Data |
|---|---|---|---|
| Titolare del trattamento | [DA COMPILARE] | | |
| Consulente privacy / DPO | [DA COMPILARE] | | |
| Architect / tech lead | [DA COMPILARE] | | |
| Operations | [DA COMPILARE] | | |
