# Verbale di decisione D09 — Conservazione, cancellazione ed esportazione

| Campo | Valore |
|---|---|
| Stato | **BOZZA DI VERBALE** — valori di prova assegnati; durate definitive da approvare con il consulente |
| Versione | 0.1 — 2026-10-02 |
| GAP | GAP-A03, GAP-H04, GAP-L01 |
| Gate | G2 (valori di prova), G6 (matrice approvata) |
| Responsabile | Titolare (A), consulente (R) — [DA COMPILARE]; scadenza [DA COMPILARE] |
| Riferimenti | Paper §10.5; `docs/compliance/11-matrice-retention-d09.md`; `apps/privacy/retention.py` |

## 1. Punti da decidere
Le righe "[DA DECIDERE]" della matrice: audit (12/18/24 mesi); calendario e presenze (fine anno + N); registro richieste
privacy e registro violazioni (suggeriti 5 anni); PITR (7–35 giorni, proposta 14); export logici (30–90, proposta 35).
Inoltre: legal hold (chi lo attiva e come); TTL degli export protetti (24 h); attivazione dell'esecuzione automatica
(`PRIVACY_RETENTION_AUTORUN`).

| Punto | Opzioni | Raccomandazione motivata |
|---|---|---|
| Audit | 12 / 18 / 24 mesi | **24 mesi** con minimizzazione dopo 12: copre un anno didattico completo più contestazioni [DA VALUTARE] |
| Calendario/presenze | fine anno + 12 mesi / + 5 anni / + 10 anni | Da valutare col consulente alla luce degli artt. 2955 n. 1 e 2946 c.c.; proposta tecnica **fine anno + 12 mesi** con minimizzazione successiva |
| PITR | 7 / 14 / 35 giorni | **14 giorni**: copre due cicli settimanali di pianificazione |
| Esecuzione automatica | Manuale con dry-run / automatica giornaliera | **Automatica solo dopo** due cicli di dry-run verificati in staging |

## 2. Impatto tecnico
Approvazione via API (`/api/v1/privacy/retention-policies`, ogni modifica torna PROPOSED); job `privacy_retention`;
configurazione PITR e lifecycle storage (s5); flag di legal hold [DA IMPLEMENTARE].

## 3. Esito e firme
☐ Approvata ☐ Con modifiche: [DA COMPILARE] ☐ Rinviata
| Ruolo | Nome | Firma | Data |
|---|---|---|---|
| Titolare | [DA COMPILARE] | | |
| Consulente | [DA COMPILARE] | | |
| Operations | [DA COMPILARE] | | |
