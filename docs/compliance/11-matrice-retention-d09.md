# Matrice di retention proposta (decisione D09)

| Campo | Valore |
|---|---|
| Stato | **BOZZA — PROPOSTA DA APPROVARE**. Nessuna durata è un termine legale o fiscale |
| Versione | 0.1 — 2026-10-02 (allineata a reg2-gdpr "Matrice di retention" e a `apps/privacy/retention.py` `DEFAULT_MATRIX`) |
| Documento del fascicolo | n. 8 — gate G6 |
| GAP | GAP-H04, GAP-L01, GAP-A03 (valori di prova) |
| Responsabile | Titolare del trattamento con consulente (RACI: Tit. A, Cons. R) |
| Riferimenti normativi | GDPR artt. 5.1.e, 17, 25, 30.1.f, 32; paper §10.5; c.c. artt. 2946, 2955 n. 1 (da valutare); verbale `governance/verbale-D09.md` |

> **Come si applica nel software.** Ogni riga corrisponde a una `RetentionPolicy` (categoria tecnica nella colonna
> "Cat."). Le righe sono caricate con stato **PROPOSED**: il job `privacy_retention` esegue in dry-run e non cancella nulla
> finché la riga non è approvata via API (con audit). Ogni modifica riporta la riga a "da approvare". Le righe EXTERNAL
> sono applicate da infrastruttura o da altri moduli e vanno verificate con evidenza separata.

## 1. Matrice

| # | Categoria | Cat. tecnica | Finalità | Base | Durata proposta | Azione alla scadenza | Backup | Origine |
|---|---|---|---|---|---|---|---|---|
| 1 | Log diagnostici applicativi | `diagnostic_logs` | Diagnosi e sicurezza | 6.1.f | 30 giorni | Cancellazione automatica nel sistema di log (EXTERNAL) | Non inclusi nei backup DB | Paper §10.5 |
| 2 | Chiavi di idempotenza / ricevute dei comandi | `idempotency_keys` | Prevenire doppie esecuzioni | 6.1.b | 30 giorni | Purge (DELETE) | Scadono con il PITR | Paper §10.5 |
| 3 | Delivery delle notifiche | `notification_deliveries` | Prova di consegna | 6.1.b | 90 giorni | Purge mantenendo contatori aggregati (modulo comunicazioni) | Idem | Paper §10.5 |
| 4 | Snapshot e input del solver | `solver_snapshots` | Riproducibilità | 6.1.b | 90 giorni dopo pubblicazione o scarto | Cancellare il payload, mantenere hash e statistiche (oggi solo REPORT: il payload degli snapshot pubblicati serve ai trigger del calendario) | Idem | Proposta tecnica |
| 5 | Audit di sicurezza e operativo | `audit_events` | Sicurezza, responsabilizzazione | 6.1.f, 32 | **[DA DECIDERE: 12 / 18 / 24 mesi]** | Minimizzazione (pseudonimizzazione dell'attore, rimozione dei dettagli), append-only | Idem | Guida: indicativamente 12–24 mesi |
| 6 | Calendario, presenze, recuperi, percorsi | `calendar_attendance` | Erogazione e contestazioni | 6.1.b | **[DA DECIDERE: fine anno didattico + N mesi/anni]** | Minimizzazione o cancellazione (oggi REPORT) | Idem | Da valutare con il consulente: art. 2955 n. 1 c.c. (1 anno, retribuzione delle lezioni), art. 2946 c.c. (10 anni, ordinaria) |
| 7 | Anagrafiche famiglie/studenti/tutor | (con #6) | Rapporto di servizio | 6.1.b | Come #6 dalla fine del rapporto | Anonimizzazione governata (stessa funzione dei diritti art. 17) | Idem | Proposta |
| 8 | Account revocati | `revoked_accounts` | Sicurezza dopo la revoca | 6.1.f | Disattivazione immediata; minimizzazione a **90 giorni** (intervallo ammesso 30–90) | Pseudonimizzazione dei riferimenti in audit | Idem | Paper §10.5 |
| 9 | Inviti e token di reset | `invitations` | Attivazione account | 6.1.b | Fino a uso o scadenza (invito 72 h), purge dopo 7 giorni | DELETE; si conserva solo l'hash fino al purge | Idem | Guida |
| 10 | File degli export protetti | `protected_exports` | Diritti artt. 15/20 | 6.1.c | Fino al download o a 24 h | Cancellazione del file; resta la riga di audit | Mai nei backup (directory privata) [DA VERIFICARE con s5] | Implementazione s4 |
| 11 | Report degli import | `import_reports` | Verifica dell'import | 6.1.b | 90 giorni | Si conservano hash e conteggi, non gli errori per riga | Idem | Proposta tecnica |
| 12 | Registro delle richieste privacy e ledger | `privacy_requests` | Responsabilizzazione (5.2) | 6.1.c | **[DA DECIDERE: suggerito 5 anni dalla chiusura]** | REPORT, poi cancellazione | Ledger su storage separato con object lock | Proposta |
| 13 | Registro delle violazioni | (manuale, doc. 14) | Art. 33.5 | 6.1.c | **[DA DECIDERE: suggerito 5 anni]** | Cancellazione manuale con verbale | — | Proposta |
| 14 | Backup PITR | `backups_pitr` | Continuità | come d'origine, 32 | **[DA DECIDERE: 7–35 giorni]** — proposta 14 giorni | Scadenza automatica del provider (EXTERNAL) | — | D09 |
| 15 | Export logici di controllo (pg_dump) | `logical_exports` | Ripristino | come d'origine, 32 | 30–90 giorni, cifrati — proposta 35 giorni | Scadenza con object lock/versioning (EXTERNAL) | — | Guida |
| 16 | Log del provider email | (fornitore) | Consegna | 6.1.b | ≤ 30 giorni [DA VERIFICARE nel DPA] | Fornitore | — | doc. 9 |
| 17 | Eventi di error tracking | (fornitore) | Diagnosi | 6.1.f | ≤ 30 giorni | Fornitore | — | doc. 9 |
| 18 | Presa visione delle informative | (da implementare) | Responsabilizzazione | 6.1.c | Durata dell'account + come #5 | Minimizzazione con l'account | Idem | Proposta |

## 2. Regole trasversali
1. **Revoca immediata nel live** di account e deleghe; la retention riguarda solo le tracce residue.
2. **Restore**: dopo ogni ripristino si eseguono `privacy_ledger_verify` e `privacy_reconcile` prima di riaprire il servizio: le cancellazioni, anonimizzazioni e revoche registrate nel ledger vengono riapplicate e l'outbox non reinvia vecchie notifiche (T32, GAP-L03).
3. **Conflitto tra cancellazione e obbligo di conservazione**: prevale la minimizzazione, con motivazione registrata nella richiesta.
4. **Contenziosi o richieste delle autorità**: sospensione della cancellazione (legal hold) solo con decisione scritta del titolare, registrata nell'audit [DA IMPLEMENTARE: flag di hold per categoria].
5. I backup non vengono modificati selettivamente: si attende la scadenza naturale e si riconcilia al restore.
6. I dati sintetici di test e demo non sono soggetti alla matrice ma non devono mai contenere dati reali.

## 3. Valori di prova per G2 (GAP-A03)
Per i test e lo staging si usano i valori della colonna "Durata proposta"; per le righe "[DA DECIDERE]" il valore di
prova è il minimo dell'intervallo (audit 12 mesi; calendario fine anno + 12 mesi; PITR 7 giorni; richieste privacy 5 anni).

## 4. Approvazione

| Riga | Valore approvato | Note | Approvato da | Data |
|---|---|---|---|---|
| 1–18 | [DA COMPILARE] | | | |

Firma del titolare: ______________________ Data: __________ Parere del consulente: ☐ allegato
