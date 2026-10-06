# Verbale di decisione D03 — Priorità, domanda obbligatoria, calendario parziale ed equità

| Campo | Valore |
|---|---|
| Stato | **BOZZA DI VERBALE** — da approvare |
| Versione | 0.1 — 2026-10-02 |
| GAP | GAP-A01, GAP-A04 (politica obiettivi), GAP-A06; sblocca GAP-D02 |
| Gate | G1 |
| Responsabile | Committente (A), responsabile didattico (C), architect (R) — [DA COMPILARE] |
| Scadenza | [DA COMPILARE] |
| Riferimenti | Paper §1.3, §6 (vettore lessicografico U_P0, U_P1, U_P2, F, C, R, P, G), FR07, FR13, T26, T27; `PlanningPolicy.partial_week_rule` |

## 1. Opzioni

| Punto | Opzioni | Raccomandazione motivata |
|---|---|---|
| Livelli di priorità | P0/P1/P2 (default) oppure numerici | **P0/P1/P2**: già nel modello e nei test |
| Domanda obbligatoria (mandatory) | Non può essere scartata; pubblicazione vietata se scoperta (T26) | Confermare: tutela i percorsi e gli impegni contrattuali |
| Modalità | strict (tutto o niente) / coverage (massimizza copertura) | **coverage** come default di pianificazione, **strict** per i percorsi parentali |
| Pubblicazione parziale | a) vietata; b) ammessa con accettazione esplicita delle richieste non collocate e motivo | **b** (già: `test_partial_requires_exact_acceptance_and_reason`) |
| Unità di copertura | Minuti per beneficiario (test esistente) o numero di lezioni | **Minuti per beneficiario**: neutrale rispetto alle durate |
| Equità F | a) nessuna; b) max-min della copertura tra famiglie; c) penalità per famiglie già scoperte nella settimana precedente | **b** in prima release; c dopo il pilota |
| Ordine lessicografico | U_P0 > U_P1 > U_P2 > F > C (cambi) > R (stabilità ricorrente) > P (preferenze) > G (frammentazione) | Confermare l'ordine del paper |

## 2. Impatto tecnico
Estensione dell'obiettivo del solver (s8, GAP-D02) e versione della politica obiettivi nello snapshot (FR11); test di
priorità esistenti (`test_lexicographic_priority_above_lower_beneficiary_count`, `test_mandatory_cannot_be_dropped_for_higher_priority_optional`)
più nuovi test di equità; diagnostica UI dei non collocati.

## 3. Valori di prova
Fixture G1 con 10% P0 mandatory, 60% P1, 30% P2; equità b.

## 4. Esito e firme
☐ Approvata ☐ Con modifiche: [DA COMPILARE] ☐ Rinviata
| Ruolo | Nome | Firma | Data |
|---|---|---|---|
| Committente | [DA COMPILARE] | | |
| Responsabile didattico | [DA COMPILARE] | | |
| Architect | [DA COMPILARE] | | |
