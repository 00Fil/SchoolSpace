# Registro di conformità — catene obbligo → requisito → controllo → evidenza

| Campo | Valore |
|---|---|
| Stato | **BOZZA** — stato dei controlli da aggiornare a ogni merge e a ogni gate |
| Versione | 0.1 — 2026-10-02 |
| Documento del fascicolo | trasversale (reg1-quadro "Principio di traduzione") |
| Responsabile | Architect (R), titolare (A) |
| Riferimenti | reg1-quadro, reg2-gdpr, reg3-altre; `docs/governance/tracciabilita-test.md` |

Regola: un obbligo senza controllo è una lacuna; un controllo senza evidenza non conta per il gate.
Stato: ✅ evidenza disponibile · 🟡 implementato, evidenza da produrre in ambiente previsto · 🟠 bozza documentale · ❌ assente.

| # | Obbligo | Requisito | Controllo | Evidenza | Stato |
|---|---|---|---|---|---|
| C01 | GDPR art. 5.1.c, 25 minimizzazione | FR19, F05 | Serializer per ruolo; nomi altrui nascosti | `test_guardian_sees_children_and_hides_other_names`, `test_group_request_does_not_leak_other_participants` | 🟡 |
| C02 | GDPR art. 32 riservatezza; art. 8/minori | FR01, T24, T25 | Scope per studente, revoca immediata | `test_api.py`, `test_portals.py`, `test_families_api.py` | 🟡 (T24 completo da chiudere, GAP-B08) |
| C03 | GDPR art. 30 | GAP-H01 | Registro | doc. 01 firmato | 🟠 |
| C04 | GDPR artt. 12–14 | GAP-H01 | Quattro informative versionate con presa visione | doc. 02–05; presa visione versionata e bloccante nel portale (`NoticeAcknowledgement`, `test_p6_privacy.py`) | 🟠 (testi) / 🟡 (software) |
| C05 | GDPR art. 35; provv. 467/2018 | GAP-H02 | DPIA | doc. 06 firmato | 🟠 |
| C06 | GDPR art. 37 | GAP-H02 | Valutazione DPO | doc. 07 | 🟠 |
| C07 | GDPR art. 28 | GAP-H03 | Contratti con fornitori | doc. 08–09 firmati | 🟠 |
| C08 | GDPR Capo V | GAP-H03 | TIA o "nessun trasferimento" | doc. 10 | 🟠 |
| C09 | GDPR art. 5.1.e | GAP-H04, D09 | Matrice + job con ricevuta | doc. 11; `test_privacy_retention.py` | 🟡 (valori da approvare) |
| C10 | Codice art. 2-quaterdecies; GDPR art. 29 | GAP-H10 | Designazioni + ruoli coerenti | doc. 12; registro designazioni | 🟠 |
| C11 | GDPR artt. 15–22 | FR24, GAP-H05 | Registro richieste, export, anonimizzazione | doc. 13; `test_privacy_rights.py`, `test_privacy_exports.py`; area Privacy del centro e «I miei dati» (P5–P6); `fascicolo-P6.md` | 🟡 |
| C12 | GDPR artt. 33–34 | GAP-H08 | Procedura + registro + esercitazione | doc. 14; esito tabletop | 🟠 |
| C13 | L. 300/1970 art. 4 | GAP-H10 | Informativa + policy audit + nessuna metrica di produttività | doc. 15; revisione cruscotti | 🟠 |
| C14 | Codice art. 122; Linee guida cookie 2021 | GAP-H09 | Solo strumenti tecnici; CSP | doc. 17; checklist release | 🟡 |
| C15 | Codice del consumo / c.c. | GAP-H09 | Termini d'uso | doc. 16 | 🟠 |
| C16 | GDPR art. 22; AI Act | GAP-H11, FR14 | Pubblicazione umana obbligatoria; diagnostica | doc. 18; `test_calendar.py` pubblicazione | 🟡 |
| C17 | NIS2 | GAP-H11 | Autovalutazione | doc. 18 §3 | 🟠 |
| C18 | Accessibilità (volontaria) | NFR07, T33 | WCAG 2.2 AA auto + manuale | `docs/evidence/v0.7-axe.json` (automatico); audit manuale | 🟡 / ❌ (manuale) |
| C19 | GDPR art. 32 integrità | NFR01, E08 | Constraint, validatore, audit append-only DB | test PG (skipped su SQLite) | 🟡 (CI PG da eseguire) |
| C20 | GDPR art. 32 autenticazione | NFR06, B04 | MFA staff | test s1 | 🟡 |
| C21 | GDPR art. 32.1.c disponibilità | NFR05, T32 | PITR + restore misurato | doc. 21; report di restore | ❌ |
| C22 | GDPR art. 32 / NFR06 | ASVS L2 | Checklist ASVS | fascicolo n. 15 | ❌ |
| C23 | Licenze OSS | NFR08 | SBOM e censimento | fascicolo n. 20 | ❌ |
| C24 | GDPR art. 28 (fornitore sviluppo) / dati sintetici | GAP-H06 | Nessun dato reale prima di G6 e atto art. 28 | seed sintetici; doc. 08 firmato | 🟡 |
| C25 | Riconferma alla maggiore età (D07) | GAP-H11 | Job senza revoca silenziosa | `test_privacy_majority.py` | 🟡 |
