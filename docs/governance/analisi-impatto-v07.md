# Analisi d'impatto del prototipo v0.7 rispetto alle decisioni D01–D09

| Campo | Valore |
|---|---|
| Stato | **BOZZA** — impatti stimati sulle raccomandazioni dei verbali; da ricalcolare a decisioni chiuse |
| Versione | 0.1 — 2026-10-02 |
| GAP | GAP-A06 |
| Gate | G1 (piano di modifica approvato) |
| Responsabile | Architect (R/A) |
| Riferimenti | Verbali `verbale-D01.md`…`verbale-D09.md`; guida sez7-piano ("riallineare, non riscrivere") |

Legenda impatto: ● alto (nuovi modelli/migrazioni e test) · ◐ medio (configurazione, estensione) · ○ basso (solo valori/seed).

| Decisione | Modelli e migrazioni | Vincoli e solver | DTO / API | UI | Test | Impatto | Stream |
|---|---|---|---|---|---|---|---|
| D01 | Catalogo per classe; versioni del curriculum (C04) | H12 | Endpoint percorsi | Percorsi, monte minuti | `test_parentali.py` + T31 completo | ● | s2, s8, s6 |
| D02 | Gruppi generici (C05); massimo online di centro | H05 | Gestione gruppi | Gruppi | T37 completo | ◐ | s2, s6 |
| D03 | Versione politica obiettivi | Vettore completo F…G (D02) | Diagnostica | Proposte | Equità, stabilità | ● | s8 |
| D04 | Seed finestre e canali video | H03, H07 | — | Configurazione | readiness | ○ | s8 |
| D05 | `TutorOperatingPolicy` completa, matrice transizioni (C03) | H10, H11 | — | Portale tutor (lettura) | T16 | ◐ | s8 |
| D06 | LessonSeries, RecoveryObligation, job estensione | Orizzonte 6 settimane | `/makeup`, serie | Agenda | T13, T14, T40 | ● | s2, s8 |
| D07 | Presa visione informative (nuovo); permessi delega nelle policy | — | Selezione contesto (B07) | Informative, riconferma | majority, T24 | ◐ | s1, s4, s6 |
| D08 | — | — | Provider email | — | T23 | ◐ | s3, s5 |
| D09 | Approvazione righe `RetentionPolicy`; legal hold (nuovo) | — | — | — | retention | ○ | s4, s5 |

## Piano di modifica (ordine proposto)
1. Valori e seed (D04, D05, D09) → nessuna migrazione strutturale.
2. Contratti e migrazioni expand (D01, D02, D06, D07) → migrate → contract dopo la verifica.
3. Solver (D03, H11, H12) con benchmark G3.
4. UI e testi (D07, informative) per G5.
Ogni passo aggiorna `tracciabilita-test.md`.
