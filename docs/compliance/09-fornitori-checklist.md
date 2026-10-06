# Checklist di selezione e verifica dei fornitori ed elenco dei sub-responsabili

| Campo | Valore |
|---|---|
| Stato | **BOZZA** — da compilare durante la selezione (D08) |
| Versione | 0.1 — 2026-10-02 |
| Documento del fascicolo | n. 6 (con il doc. 8) — gate G6 |
| GAP | GAP-H03, GAP-J01, GAP-F02, GAP-K01 |
| Responsabile | Titolare con consulente; supporto tecnico architect/operations |
| Riferimenti normativi | GDPR artt. 28, 32, 44–49; D.Lgs. 138/2024 (NIS2) come criterio di selezione; ISO/IEC 27001/27017/27018 |

## 1. Censimento dei fornitori (da compilare)

| Categoria | Fornitore | Dati trattati | Region dati / backup | DPA (art. 28) | Sub-responsabili | Extra-SEE | Esito |
|---|---|---|---|---|---|---|---|
| Hosting e calcolo | [DA COMPILARE] | Tutti | [ ] | ☐ standard ☐ modello doc. 8 | [ ] | ☐ no ☐ sì → doc. 10 | ☐ approvato |
| PostgreSQL gestito, PITR, storage export | [DA COMPILARE] | Tutti, in copia | [ ] | ☐ | [ ] | ☐ | ☐ |
| Redis gestito (se esterno) | [DA COMPILARE] | Code, ID tecnici | [ ] | ☐ | [ ] | ☐ | ☐ |
| Email transazionale | [DA COMPILARE] | Email, evento, data/ora | [ ] | ☐ | [ ] | ☐ | ☐ |
| Error tracking / monitoraggio / uptime | [DA COMPILARE] | ID pseudonimi, IP, metadati | [ ] | ☐ | [ ] | ☐ | ☐ |
| DNS / CDN / certificati | [DA COMPILARE] | IP, metadati di traffico | [ ] | ☐ | [ ] | ☐ | ☐ |
| Videoconferenza (link esterni) | [DA COMPILARE] | Nominativi, orari (gestiti dal fornitore) | [ ] | ☐ trattamento a sé del centro | [ ] | ☐ | ☐ |
| Sviluppo e manutenzione | [DA COMPILARE] | Accesso in assistenza | [ ] | ☐ modello doc. 8 | [ ] | ☐ | ☐ |
| Repository e CI (GitHub o altro) | [DA COMPILARE] | Solo codice e dati sintetici | [ ] | ☐ (nessun dato reale ammesso) | [ ] | ☐ | ☐ |

## 2. Checklist per ciascun fornitore

### 2.1 Requisiti bloccanti
- [ ] Contratto con DPA art. 28 conforme (confronto con allegato C del doc. 8).
- [ ] Region di trattamento e **backup** nello SEE, oppure strumento del Capo V + TIA (doc. 10).
- [ ] Elenco dei sub-responsabili pubblicato, con preavviso delle modifiche.
- [ ] Notifica delle violazioni al cliente con termine dichiarato (≤ 24–48 h consigliato).
- [ ] Cifratura in transito e a riposo; chiavi gestite dal fornitore approvato o dal centro.
- [ ] Cancellazione o restituzione a fine rapporto con attestazione; possibilità di export dei dati (exit plan).
- [ ] Nessun uso dei dati del cliente per finalità proprie (incluso addestramento di modelli).
- [ ] MFA per gli account amministrativi della console; account intestati al centro.

### 2.2 Requisiti valutativi (punteggio 0–2)
- [ ] Certificazioni: ISO/IEC 27001 (con 27017/27018 per il cloud), SOC 2 Tipo II, qualificazione ACN per il cloud [facoltativa per i privati].
- [ ] Soggetto NIS2 o fornitore con programma di sicurezza documentato.
- [ ] Log di accesso amministrativo disponibili al cliente.
- [ ] Specifiche: PITR con retention configurabile 7–35 giorni (DB); estensione `btree_gist` (DB); SPF/DKIM/DMARC e log con retention breve (email); scrubbing lato client e hosting UE (error tracking).
- [ ] Supporto in lingua italiana o inglese con tempi di risposta coerenti con gli SLO (doc. `governance/piano-manutenzione-slo.md`).
- [ ] Prezzo ricorrente noto e prevedibile (budget D08) [DA COMPILARE].

### 2.3 Verifiche periodiche
- [ ] Riesame annuale di DPA, sub-responsabili, certificazioni e incidenti.
- [ ] Verifica della retention effettiva dei log del fornitore.
- [ ] Prova di export/uscita almeno una volta prima del go-live (per hosting e DB).

## 3. Registro delle verifiche

| Data | Fornitore | Verifica | Esito | Azione | Responsabile |
|---|---|---|---|---|---|
| [DA COMPILARE] | | | | | |

Firma del titolare (approvazione dell'elenco): ______________________ Data: __________
