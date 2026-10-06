# Piano di manutenzione, SLO, assistenza e budget ricorrente

| Campo | Valore |
|---|---|
| Stato | **BOZZA** — obiettivi proposti, non garanzie; da approvare in D08 |
| Versione | 0.1 — 2026-10-02 |
| GAP | GAP-N05, GAP-N06 |
| Gate | G6 |
| Responsabile | Committente (A), operations e tech lead (R) — [DA COMPILARE] |
| Riferimenti | Paper NFR05, NFR08; guida tec5-esercizio ("SLO ed error budget", "Manutenzione e ciclo di vita"); verbale D08 |

## 1. SLO (proposta)
| SLO | Misura | Obiettivo | Finestra |
|---|---|---|---|
| Disponibilità | Probe esterno su `/api/v1/ready` ogni minuto | 99,5% (≈ 3 h 36 min/mese di indisponibilità ammessa) | Mensile, escluse manutenzioni annunciate |
| Latenza | p95 delle API ordinarie | ≤ 500 ms nel 95% dei giorni | Mensile |
| Freschezza notifiche | Delivery entro 5 min dall'evento | 95% | Mensile |
| Solver | Proposta valida entro 60 s end-to-end sul fixture; job terminato entro 90 s | 95% dei run | Mensile |
**Error budget**: se esaurito, si congelano le release di funzionalità fino alla rimozione delle cause.

## 2. Finestre di manutenzione
Proposta: [DA COMPILARE: es. domenica 7:00–9:00], annunciate con 48 h di anticipo nel portale; mai nelle fasce di
lezione; pagina di manutenzione statica (GAP-J08).

## 3. Assistenza
| Livello | Esempi | Presa in carico | Canale |
|---|---|---|---|
| SEV1 | Sospetta violazione; calendario errato pubblicato; fermo in orario di lezione | 30 min nelle fasce di reperibilità D08 | Telefono di reperibilità [DA COMPILARE] |
| SEV2 | Solver o notifiche bloccati; backup fallito | 2 h lavorative | Telefono/ticket |
| SEV3 | Difetto su una funzione | giorno lavorativo successivo | Ticket/email |
Famiglie e tutor: primo livello presso la segreteria del centro [DA COMPILARE: orari]; secondo livello fornitore.

## 4. Manutenzione del software (GAP-N05)
| Attività | Frequenza | Responsabile |
|---|---|---|
| Controllo dipendenze (pip-audit, npm audit, immagini) | Settimanale automatico, revisione mensile | Tech lead |
| Patch di sicurezza | Critiche 72 h, alte 7 giorni, medie 30 giorni [DA APPROVARE] | Fornitore |
| Aggiornamenti minori Django/DRF/Celery/OR-Tools | Entro 30 giorni dal rilascio | Fornitore |
| Migrazione Django 5.2 LTS → LTS successiva | **Entro il quarto trimestre 2027** (fine supporto 5.2: aprile 2028) | Fornitore |
| PostgreSQL 17 (supporto fino a novembre 2029), Python 3.13 (fino a ottobre 2029) | Pianificare l'aggiornamento 12 mesi prima | Operations |
| Redis: versione fissata o Valkey (BSD), scelta documentata | Al go-live | Operations |
| Test di restore | Trimestrale | Operations |
| Test di carico (25 utenti) | A ogni release minor | QA |
| Revisione capacità del solver | Trimestrale | Architect |
| Riesame annuale: DPIA, registro, fornitori, ASVS, restore, runbook, formazione | Annuale | Titolare + team |

## 5. Proprietà e continuità del fornitore
Repository, contratti (OpenAPI, schemi), IaC e account cloud intestati al centro; deposito del codice aggiornato a ogni
release; documentazione di esercizio e runbook consegnati; clausola di uscita con trasferimento di conoscenza
[DA COMPILARE nel contratto].

## 6. Budget ricorrente (da compilare, nessun prezzo stimato da questo documento)
| Voce | Fornitore | Costo mensile | Note |
|---|---|---|---|
| Hosting applicazione | [DA COMPILARE] | [DA COMPILARE] | |
| PostgreSQL gestito + PITR + storage export | [DA COMPILARE] | [DA COMPILARE] | |
| Redis | [DA COMPILARE] | [DA COMPILARE] | |
| Email transazionale | [DA COMPILARE] | [DA COMPILARE] | |
| Monitoraggio, uptime, error tracking | [DA COMPILARE] | [DA COMPILARE] | |
| Dominio, DNS, certificati | [DA COMPILARE] | [DA COMPILARE] | |
| Manutenzione e reperibilità | [DA COMPILARE] | [DA COMPILARE] | |
| Pentest annuale, consulenza privacy | [DA COMPILARE] | [DA COMPILARE] | |

Approvazione: Committente ______________ Data __________
