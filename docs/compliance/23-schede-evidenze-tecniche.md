# Schede dei documenti tecnici del fascicolo (n. 15–21)

| Campo | Valore |
|---|---|
| Stato | **BOZZA / MODELLI** — struttura e criteri di accettazione; i contenuti sono prodotti dagli stream tecnici e da QA/operations |
| Versione | 0.1 — 2026-10-02 |
| Documento del fascicolo | n. 15–21 |
| Responsabile | Indicato per scheda |
| Riferimenti | reg4-fascicolo; gov-gate (DoD per gate); GAP-M04 (evidenze versionate) |

Ogni evidenza va archiviata in `docs/evidence/G<n>/` con: build (commit e digest dell'immagine), input, esito, data,
approvatore.

## n. 15 — Checklist OWASP ASVS 5.0 livello 2 (security lead, GAP-I01)
Colonne: ID requisito ASVS · capitolo · applicabile (sì/no + motivo) · controllo nel sistema · evidenza (test, config,
screenshot) · stato (pass/fail/N/A) · verificato da · data. Criterio G6: tutti i requisiti L2 applicabili in "pass" o con
eccezione approvata (doc. 20 §5). Nessuna dichiarazione di "certificazione ASVS".

## n. 16 — Report del penetration test e piano di rientro (security lead, GAP-I05)
Contenuti: ambito (URL, ruoli, API), periodo, metodologia (OWASP WSTG), account di test sintetici per i quattro ruoli,
finding con gravità CVSS, riproduzione, raccomandazione. Piano di rientro: finding · gravità · responsabile · scadenza ·
retest · stato. Criterio G6: nessun critico o alto aperto.

## n. 17 — Report di restore con RPO/RTO misurati (operations, T32, GAP-L02)
Campi: data; backup usato (PITR timestamp / dump); ambiente isolato; ora inizio/fine; **RPO misurato** (ultimo dato
recuperato vs momento del guasto simulato); **RTO misurato**; verifiche post-restore (invarianti calendario,
`privacy_ledger_verify`, `privacy_reconcile`, nessun invio dall'outbox vecchio, revoche riapplicate); esito vs 15 min / 4 h;
scostamenti e azioni.

## n. 18 — Runbook approvati (operations, GAP-L04)
Sei runbook secondo il modello dell'appendice: solver bloccato; Redis indisponibile; collisione/stale; email
indisponibile; incidente di sicurezza (rinvia al doc. 14 per gli aspetti privacy); restore. Ognuno con versione,
responsabile, data dell'ultimo test.

## n. 19 — Rapporto di audit di accessibilità (QA, NFR07, T33, GAP-G07)
Automatico: axe-core (versione, stati, violazioni). Manuale: tastiera su ogni controllo, ordine del focus, NVDA + Firefox,
VoiceOver + Safari iOS, zoom 200% e reflow a 320 CSS px, contrasto, nessuna informazione solo con il colore, alternative
al drag-and-drop. Elenco delle non conformità per criterio WCAG 2.2 → alimenta la dichiarazione (doc. 19).

## n. 20 — SBOM e censimento delle licenze (tech lead, NFR08, GAP-I04)
SBOM CycloneDX o SPDX per backend e frontend generata in CI per la build candidata; tabella licenze (componente,
versione, licenza, obblighi, note: NOTICE di OR-Tools; scelta Redis/Valkey documentata); esito pip-audit/npm audit.

## n. 21 — Esito della UAT e del pilota (committente, GAP-G08, N01)
Vedi `docs/governance/piano-pilota-golive.md` §2–3: scenari UAT, esiti, differenze tra calendario attuale e sistema per
ciascun ciclo pilota, riconciliazione e decisioni.

## n. 22 — Verbale di go/no-go (committente, GAP-N04)
Vedi `docs/governance/verbale-go-no-go.md`.
