# Verbale di decisione D01 — Percorsi "parentali": perimetro e dettaglio

| Campo | Valore |
|---|---|
| Stato | **BOZZA DI VERBALE** — significato confermato dal committente; dettaglio da approvare (G1 non firmato) |
| Versione | 0.1 — 2026-10-02 |
| GAP | GAP-A01, **GAP-A02**, GAP-A06 |
| Gate | G1 |
| Responsabile della decisione | Committente (A) con responsabile didattico (R) — [DA COMPILARE: nomi] |
| Scadenza proposta | [DA COMPILARE] — prima del workshop G1 |
| Riferimenti | Paper §1.3, §1.4, FR22, T31; ADR 0002; `docs/parentali.md`; registro decisioni v0.2; `Decision` D01 nel DB |

## 1. Contesto
Il committente ha confermato che "parentali" indica studenti che svolgono **tutto il programma scolastico e tutte le
materie** con il centro (istruzione parentale). La v0.7 implementa `LearningPath`, `PathEnrollment`, `TeachingGroup`,
`CurriculumBlock` con derivazione idempotente delle richieste. Restano da fissare programmi, monte ore e responsabilità.

## 2. Punti da decidere e opzioni

| # | Punto | Opzioni | Raccomandazione |
|---|---|---|---|
| 1 | Programmi per anno/livello | a) curriculum interno libero per percorso; b) catalogo per classe (es. primaria 1–5, secondaria I grado 1–3) con materie obbligatorie | **b**: rende verificabile la copertura delle materie e riusabile il percorso |
| 2 | Monte ore settimanale per materia | a) definito per percorso; b) per classe con eccezioni per studente | **b**, con eccezioni approvate dal responsabile didattico e audit |
| 3 | Responsabile didattico del percorso | a) unico per il centro; b) uno per percorso | **b** se più di 2 percorsi, altrimenti a |
| 4 | Coorti e sottogruppi | Coorte > gruppo di sessione; sottogruppi max 2 in presenza (vincolo fisico), online da D02 | Confermare il default del paper |
| 5 | Revisione del curriculum dopo la derivazione | a) blocco (oggi `test_program_frozen_after_derivation`); b) nuova versione con invalidazione degli snapshot (GAP-C04) | **b** prima di G2 |
| 6 | Limiti legali | Il centro non certifica né sostituisce gli obblighi della famiglia (comunicazione alla scuola, esami di idoneità) | Scrivere il limite nei termini d'uso e nel contratto |

## 3. Impatto tecnico (GAP-A06)
- Modelli: possibile `GradeProgram`/`ProgramSubjectQuota` (catalogo per classe); versione del curriculum (`curriculum_version` esiste) con flusso di revisione (GAP-C04).
- Vincoli: H12 (sequenze curricolari, periodi di iscrizione) da implementare (stream s8, GAP-D04).
- DTO/UI: schermata percorsi (Lumen) con monte minuti per materia e riconciliazione con presenze (T31, dipende da s2 presenze).
- Test: estendere `test_parentali.py` con monte ore per classe e revisione versionata.
- Privacy: gli obiettivi didattici non contengono valutazioni (registro TR-06).

## 4. Valori di prova (fixture G1)
Una classe di secondaria I grado con 9 materie, 24 h/settimana, 2 coorti da 4 studenti, sottogruppi da 2.

## 5. Esito
☐ Approvata come raccomandato ☐ Approvata con modifiche: [DA COMPILARE] ☐ Rinviata a: [DA COMPILARE]
Evidenza archiviata: `docs/evidence/G1/D01-verbale.pdf` [DA COMPILARE]. Aggiornare `Decision(code="D01").status = APPROVED`.

| Ruolo | Nome | Firma | Data |
|---|---|---|---|
| Committente | [DA COMPILARE] | | |
| Responsabile didattico | [DA COMPILARE] | | |
| Architect | [DA COMPILARE] | | |
