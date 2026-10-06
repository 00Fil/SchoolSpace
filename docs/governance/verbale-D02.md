# Verbale di decisione D02 — Gruppi: composizione e capienza online

| Campo | Valore |
|---|---|
| Stato | **BOZZA DI VERBALE** — da approvare |
| Versione | 0.1 — 2026-10-02 |
| GAP | GAP-A01, GAP-A06; sblocca GAP-C05 |
| Gate | G1 |
| Responsabile | Committente (A), responsabile didattico (R) — [DA COMPILARE] |
| Scadenza | [DA COMPILARE] |
| Riferimenti | Paper §1.2–1.3, I3, FR08, T03, T04, T37; `TeachingGroup.online_capacity`, `approved` |

## 1. Opzioni

| Punto | Opzioni | Raccomandazione motivata |
|---|---|---|
| Chi forma i gruppi | a) coordinatore; b) responsabile didattico; c) automatico (escluso dalla baseline §1.4) | **b approva, a propone**: la compatibilità didattica è una scelta pedagogica |
| Capienza in presenza | Fissata a 2 dal vincolo fisico (spazio da 2) | Nessuna scelta: limite fisico |
| Capienza online | a) 2 come in presenza; b) 4; c) per gruppo con massimo del centro | **c con massimo 4** [DA CONFERMARE]: il paper separa il limite online dal fisico |
| Gruppi generici fuori dai percorsi | a) sì; b) solo nei percorsi | **a**: oggi i gruppi legacy sono bloccati (GAP-C05) |
| Cambi di membri | Iscrizioni datate; partecipanti storici invariati (T37) | Confermare il default |
| Criteri di compatibilità | Stessa materia e livello; età entro [N] anni [DA COMPILARE] | Lista scritta, verificata da persona, non dal solver |

## 2. Impatto tecnico
`TeachingGroup.online_capacity` obbligatorio per gruppi online (già: `test_online_capacity_must_be_explicit`); parametro
di centro "massimo online"; rimozione del blocco sui gruppi legacy e API di gestione (s2/s4); vincolo di
non-pubblicazione di gruppi non approvati (`test_group_must_be_approved`). Privacy: nessuna visibilità dei compagni (GAP-F05).

## 3. Valori di prova
Massimo online 4; due gruppi in presenza da 2; un gruppo online da 3.

## 4. Esito e firme
☐ Approvata ☐ Con modifiche: [DA COMPILARE] ☐ Rinviata
| Ruolo | Nome | Firma | Data |
|---|---|---|---|
| Committente | [DA COMPILARE] | | |
| Responsabile didattico | [DA COMPILARE] | | |
| Architect | [DA COMPILARE] | | |
