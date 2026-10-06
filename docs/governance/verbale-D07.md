# Verbale di decisione D07 — Account studenti, finalità, basi giuridiche e dati minimi

| Campo | Valore |
|---|---|
| Stato | **BOZZA DI VERBALE** — valori di prova assegnati (GAP-A03); decisione definitiva prima della produzione |
| Versione | 0.1 — 2026-10-02 |
| GAP | GAP-A03, GAP-H01, GAP-B07, GAP-H11 |
| Gate | G2 (valori di prova e basi approvate), G6 (chiusura) |
| Responsabile | Titolare (A), consulente privacy (R) — [DA COMPILARE]; scadenza [DA COMPILARE] |
| Riferimenti | Paper §1.3, §10; reg2-gdpr "Basi giuridiche per flusso" e "Minori"; settings `PRIVACY_MAJORITY_GRACE_DAYS`, `PRIVACY_MAJORITY_OVERDUE_ACTION`, `PRIVACY_INVITE_TTL_HOURS` |

## 1. Punti, opzioni, raccomandazione

| Punto | Opzioni | Raccomandazione motivata | Valore di prova |
|---|---|---|---|
| Basi giuridiche per flusso | Tabella reg2-gdpr | **Approvare la tabella** (6.1.b servizio, 6.1.f sicurezza, 6.1.c diritti); nessun consenso del minore | Come raccomandato |
| Account studente minorenne | a) mai; b) dai 14 anni; c) su richiesta del genitore da [età] | **c** con età minima 11 anni [DA DECIDERE]: è un servizio contrattuale, non basato su consenso | Su invito del genitore, nessun limite tecnico |
| Diritti dell'account studente | Sola lettura proprio calendario / anche disponibilità | **Sola lettura** in prima release | Sola lettura |
| Maggiore età — periodo di riconferma | 0 / 30 / 60 giorni | **30 giorni** | `PRIVACY_MAJORITY_GRACE_DAYS=30` |
| Maggiore età — alla scadenza | REPORT (il centro decide) / SUSPEND (delega sospesa con audit) | **SUSPEND** in produzione dopo approvazione; REPORT come default prudenziale finché non approvato | `REPORT` |
| Data di nascita | Raccogliere / solo anno / non raccogliere | **Raccogliere solo se serve al job di maggiore età** (altrimenti dichiarazione del genitore) | Campo facoltativo |
| Durata inviti | 24 / 72 h / 7 giorni | **72 h** | `PRIVACY_INVITE_TTL_HOURS=72` |
| Notifiche ai genitori | Tutti i delegati / solo con `can_receive_notifications` | **Solo con permesso** | Default true alla creazione |
| Verifica della relazione | Documento a vista / dichiarazione / doppia conferma | **Documento a vista senza copia**, metodo registrato | — |

## 2. Impatto tecnico
Policy `identity.policies` da collegare a `can_receive_notifications`/`can_request_changes` e allo stato di riconferma
(punto aperto s4); selezione del contesto multi-ruolo (GAP-B07); registrazione della presa visione delle informative
[DA IMPLEMENTARE]; testi `docs/compliance/02–05`.

## 3. Esito e firme
☐ Approvata ☐ Con modifiche: [DA COMPILARE] ☐ Rinviata
| Ruolo | Nome | Firma | Data |
|---|---|---|---|
| Titolare | [DA COMPILARE] | | |
| Consulente privacy | [DA COMPILARE] | | |
| Architect | [DA COMPILARE] | | |
