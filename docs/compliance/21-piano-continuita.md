# Piano di continuità operativa

| Campo | Valore |
|---|---|
| Stato | **BOZZA** — obiettivi proposti (NFR05), da misurare con il restore di G6 |
| Versione | 0.1 — 2026-10-02 |
| Documento del fascicolo | supporto ai n. 17 e 18 (restore e runbook) — gate G6 |
| GAP | GAP-L01–L04, GAP-K03, GAP-N04 |
| Responsabile | Operations (A/R); titolare informato |
| Riferimenti | GDPR art. 32.1.b–c; paper §11; guida tec5-esercizio; ISO 22301 (riferimento metodologico) |

## 1. Analisi d'impatto sul servizio (BIA) — proposta

| Processo | Criticità | Tolleranza all'interruzione | RPO | RTO | Soluzione manuale temporanea |
|---|---|---|---|---|---|
| Consultazione del calendario pubblicato (famiglie, tutor) | Alta nei giorni di lezione | 4 h | 15 min | 4 h | Calendario settimanale esportato (PDF/ICS) la sera prima; comunicazione via email/telefono della segreteria |
| Registrazione presenze | Media | 2 giorni | 15 min | 1 giorno | Foglio presenze cartaceo, inserimento a posteriori con correzione auditata |
| Modifiche e cancellazioni del giorno | Alta | 4 h | 15 min | 4 h | Avviso telefonico alle famiglie; registrazione nel sistema al ripristino |
| Pianificazione (solver) | Bassa | 1 settimana | 15 min | 2 giorni | Rinvio della pubblicazione; nessuna modifica del calendario già pubblicato |
| Notifiche email | Media | 1 giorno | — (outbox nel DB) | 1 giorno | Comunicazione diretta della segreteria; l'outbox recupera gli invii senza duplicati |
| Portale famiglie (disponibilità, richieste) | Bassa | 3 giorni | 15 min | 2 giorni | Richieste via email |

## 2. Scenari e strategie

| Scenario | Strategia | Runbook (GAP-L04) |
|---|---|---|
| Guasto dell'applicazione o del deploy | Rollback all'immagine precedente; migrazioni expand–contract | Pipeline CD |
| Perdita o corruzione del DB | Restore PITR al punto precedente; verifica invarianti; `privacy_ledger_verify` + `privacy_reconcile`; nessun vecchio invio dall'outbox | Restore |
| Redis indisponibile | Il DB è la fonte di verità; job PENDING durevoli e reconciler | Redis indisponibile |
| Solver bloccato | Timeout hard; job non conclusivo; il calendario pubblicato non cambia | Solver bloccato |
| Provider email indisponibile | Outbox con retry e backoff; comunicazione manuale per le variazioni del giorno | Email indisponibile |
| Collisione o input obsoleto | Pubblicazione respinta (stale); rigenerare | Collisione/stale |
| Incidente di sicurezza / ransomware | Isolamento, credenziali ruotate, restore da backup non compromessi (export logici con object lock), procedura violazioni | Incidente di sicurezza |
| Indisponibilità del fornitore cloud (region) | Export logici fuori region [DA DECIDERE]; ricostruzione IaC su altra region entro [DA COMPILARE] | Restore |
| Indisponibilità di persone chiave | Almeno due persone abilitate per pubblicazione e restore; credenziali di emergenza in busta sigillata/cassaforte digitale del titolare | — |

## 3. Backup
PITR del DB gestito (retention D09: 7–35 giorni); export logico giornaliero cifrato su storage separato con versioning e
blocco della cancellazione (30–90 giorni); alert se il backup manca da oltre 26 h; test di restore isolato almeno
**trimestrale** e prima del go-live, con RPO/RTO misurati e confrontati con 15 min / 4 h (T32).

## 4. Attivazione e comunicazione
| Chi | Quando | Come |
|---|---|---|
| Operations dichiara l'incidente | SEV1/SEV2 | Canale di reperibilità [DA COMPILARE] |
| Coordinatore del centro | Entro 30 min (SEV1) / 2 h (SEV2) | Telefono |
| Famiglie e tutor | Se l'interruzione tocca le lezioni del giorno | Email/telefono con modello: "Il portale è temporaneamente non disponibile. Le lezioni di oggi restano confermate come da ultimo calendario ricevuto; eventuali variazioni vi saranno comunicate da [segreteria]." |
| Titolare | Sempre per SEV1; se c'è possibile violazione → doc. 14 | Telefono + email |

## 5. Ritorno alla normalità
Verifica delle invarianti (nessuna collisione, prenotazioni coerenti), riconciliazione privacy, inserimento dei dati
raccolti manualmente, comunicazione di chiusura, post-mortem entro 5 giorni lavorativi.

## 6. Prove e manutenzione del piano
Restore trimestrale; esercitazione tabletop annuale; riesame dopo ogni incidente e a ogni cambio di fornitore.

| Data prova | Scenario | RPO misurato | RTO misurato | Esito | Evidenza |
|---|---|---|---|---|---|
| [DA COMPILARE] | | | | | `docs/evidence/G6/` |

Approvazione: Operations ______________ Titolare ______________ Data __________
