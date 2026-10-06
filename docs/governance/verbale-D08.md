# Verbale di decisione D08 — Fornitori, team, budget e livello di servizio

| Campo | Valore |
|---|---|
| Stato | **BOZZA DI VERBALE** — valori di prova assegnati; scelta fornitori da completare |
| Versione | 0.1 — 2026-10-02 |
| GAP | GAP-A03, GAP-J01, GAP-F02, GAP-H03, GAP-N06 |
| Gate | G2 (valori di prova), G6 (contratti firmati) |
| Responsabile | Committente (A), titolare per gli aspetti privacy, operations (R) — [DA COMPILARE]; scadenza [DA COMPILARE] |
| Riferimenti | Paper §1.3, NFR05, §11; `docs/compliance/09-fornitori-checklist.md`, `10-trasferimenti-extra-ue.md`; `piano-manutenzione-slo.md` |

## 1. Punti, opzioni, raccomandazione

| Punto | Opzioni | Raccomandazione motivata | Valore di prova |
|---|---|---|---|
| Hosting | a) PaaS/IaaS UE; b) hyperscaler con region UE; c) on-premise | **a o b con region UE**, PostgreSQL 17 gestito con PITR e `btree_gist`; scelta dopo checklist | Region UE generica in IaC |
| Email transazionale | Provider UE / provider globale con DPF | **Provider UE** con SPF/DKIM/DMARC | Provider mock (nessun invio reale) |
| Video | Link manuale a servizio esterno / integrazione | **Link manuale** (paper) | Link sintetici |
| Error tracking | SaaS UE / self-hosted | **SaaS UE con scrubbing** | Disattivato in dev |
| SLO | 99,0 / **99,5** / 99,9% mensile | **99,5%** come obiettivo non garantito | 99,5% |
| Reperibilità | Solo orario lavorativo / fasce di lezione / 24×7 | **Fasce di lezione** (es. 14–20 feriali, sab mattina) | SEV1 30 min in fascia |
| Team e manutenzione | Fornitore esterno / interno | Contratto con obblighi di manutenzione di sicurezza e consegna del repository | — |
| Budget ricorrente | [DA COMPILARE: hosting, DB/PITR, email, monitoraggio, dominio, manutenzione] | Approvazione annuale | — |

## 2. Impatto tecnico
IaC e ambienti (s5); settings di produzione; DPA e checklist; testi delle informative §6–7.

## 3. Esito e firme
☐ Approvata ☐ Con modifiche: [DA COMPILARE] ☐ Rinviata
| Ruolo | Nome | Firma | Data |
|---|---|---|---|
| Committente | [DA COMPILARE] | | |
| Titolare | [DA COMPILARE] | | |
| Operations | [DA COMPILARE] | | |
