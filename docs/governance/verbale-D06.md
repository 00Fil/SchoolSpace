# Verbale di decisione D06 — Anno didattico, orizzonte, festività, cancellazioni e recuperi

| Campo | Valore |
|---|---|
| Stato | **BOZZA DI VERBALE** — da approvare |
| Versione | 0.1 — 2026-10-02 |
| GAP | GAP-A01, GAP-A06; sblocca GAP-D01, E01, E03, E06 |
| Gate | G1 |
| Responsabile | Committente (A), coordinatore (R) — [DA COMPILARE] |
| Scadenza | [DA COMPILARE] |
| Riferimenti | Paper §1.3, FR10, FR17, T13, T14, T40, T41 |

## 1. Opzioni

| Punto | Opzioni | Raccomandazione motivata |
|---|---|---|
| Anno didattico | [DA COMPILARE: es. 14 settembre 2026 – 12 giugno 2027] + eventuale estivo | Date del centro |
| Orizzonte di pianificazione | 2 / 4 / **6** settimane mobili | **6** (paper); solo le date pubblicate sono impegnative |
| Estensione dell'orizzonte | Manuale / job settimanale che **propone** l'estensione | **Job che propone** (GAP-E06), con controllo dei conflitti aperti |
| Festività e chiusure | Calendario nazionale + patrono [DA COMPILARE] + ponti del centro | Caricate come `Closure` entro G1 |
| Cancellazione da famiglia | Preavviso minimo [DA COMPILARE: es. 24 h]; oltre → lezione persa o recupero a discrezione | Regola scritta nel contratto; il sistema registra il motivo |
| Cancellazione dal centro/tutor | Sempre recupero | Una sola obbligazione di recupero per unità (T40) |
| Recuperi di gruppo | a) recupero di gruppo se tutti assenti per causa del centro; b) individuale per singolo assente | **a + b** con approvazione del coordinatore |
| Scadenza dei recuperi | Entro [DA COMPILARE: 30 giorni / fine periodo] | Scadenza esplicita, poi decade con audit |
| Modifiche "questa e successive" | Segmentazione della serie; lezioni concluse intatte (T14) | Confermare |

## 2. Impatto tecnico
`LessonSeries` e RRULE (s2, GAP-E01); `RecoveryObligation` con identità canonica (GAP-E03); job di estensione (E06);
fixture 6 settimane / 720 unità (s8, GAP-D01).

## 3. Valori di prova
Orizzonte 6 settimane; preavviso 24 h; scadenza recuperi 30 giorni.

## 4. Esito e firme
☐ Approvata ☐ Con modifiche: [DA COMPILARE] ☐ Rinviata
| Ruolo | Nome | Firma | Data |
|---|---|---|---|
| Committente | [DA COMPILARE] | | |
| Coordinatore | [DA COMPILARE] | | |
| Architect | [DA COMPILARE] | | |
