# Verbale di decisione D05 — Spostamenti, pause e limiti di lavoro dei tutor

| Campo | Valore |
|---|---|
| Stato | **BOZZA DI VERBALE** — da approvare (anche con consulente del lavoro per i dipendenti) |
| Versione | 0.1 — 2026-10-02 |
| GAP | GAP-A01, GAP-A06; sblocca GAP-C03 |
| Gate | G1 |
| Responsabile | Committente (A), coordinatore (R) — [DA COMPILARE] |
| Scadenza | [DA COMPILARE] |
| Riferimenti | Paper §1.3, H10, H11, T15, T16, T36; `TutorOperatingPolicy`, `ResourceTiming.buffer_minutes` |

## 1. Opzioni

| Punto | Opzioni | Raccomandazione motivata |
|---|---|---|
| Pausa minima tra lezioni | 0 / 10 / 15 min | **10 min** default, per tutor configurabile; 0 solo se dichiarato (T36) |
| Transizione sede → remoto e remoto → sede | Istantanea (vietata per default) / valori per tutor | **Valori per tutor obbligatori** prima di pianificare giornate miste (es. 30/45 min) |
| Limite giornaliero | In minuti, per tutor | Valori concordati nei contratti [DA COMPILARE]; mai inferiori alle tutele di legge |
| Limite settimanale ISO | In minuti, per tutor | Idem |
| Buffer degli spazi (pulizia, cambio) | 0 / 5 / 10 min | **5 min** [DA CONFERMARE]; occupa lo spazio, non il tutor (`test_cleanup_buffer_occupies_space`) |

Nota privacy/lavoro: i limiti servono alla pianificazione, non alla valutazione (doc. compliance 15).

## 2. Impatto tecnico
Compilazione `TutorOperatingPolicy` per tutti i tutor (readiness blocca se mancante); matrice di transizione completa
(GAP-C03, s8); UI tutor per visualizzare (non modificare) i propri limiti.

## 3. Valori di prova
Pausa 10; transizioni 30/45; giornaliero 360; settimanale 1500; buffer 5.

## 4. Esito e firme
☐ Approvata ☐ Con modifiche: [DA COMPILARE] ☐ Rinviata
| Ruolo | Nome | Firma | Data |
|---|---|---|---|
| Committente | [DA COMPILARE] | | |
| Coordinatore | [DA COMPILARE] | | |
| Architect | [DA COMPILARE] | | |
