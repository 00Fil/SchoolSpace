# Contratto del dominio per G1 — scheda di firma (catalogo H01–H12, politica obiettivi, dizionario, stati, unità)

| Campo | Valore |
|---|---|
| Stato | **BOZZA** — scheda di firma; i contenuti tecnici di riferimento sono nel paper e nei contratti del repository |
| Versione | 0.1 — 2026-10-02 |
| GAP | GAP-A04 (con GAP-A01–A03) |
| Gate | G1 |
| Responsabile | Architect (R), committente (A), responsabile didattico (C) — [DA COMPILARE] |
| Riferimenti | Paper §2.2 (I1–I10), §4, §6.3; `contracts/planning-input.schema.json`, `planning-result.schema.json`, `openapi.yaml`, `calendar-postgres.sql`; `tracciabilita-test.md` |

## 1. Catalogo dei vincoli obbligatori

| ID | Vincolo | Stato v0.7 | Dipende da | Approvato (☐) |
|---|---|---|---|---|
| H01 | Una sola alternativa per unità di domanda | Implementato | — | ☐ |
| H02 | Skill valida per materia, livello, modalità sull'intero intervallo | Implementato (T01) | D01 | ☐ |
| H03 | Durata da catalogo, contenimento in aperture e disponibilità di tutti i partecipanti | Implementato (T02, T03) | D04, GAP-C01 | ☐ |
| H04 | NoOverlap per tutor e studenti tra modalità | Implementato (T06, T07) | — | ☐ |
| H05 | Capienza 2 in presenza; capienza online esplicita | Implementato (T04) | D02 | ☐ |
| H06 | Spazi esclusivi; online in sede occupa uno spazio; buffer | Implementato, anche DB (T05, T08) | D04, D05 | ☐ |
| H07 | Canali video come risorse esclusive | Implementato senza canali reali | D04, D08 | ☐ |
| H08 | Lezioni bloccate/pubblicate mantenute | Implementato | — | ☐ |
| H09 | strict/coverage; mandatory vincolante | Implementato (T26) | D03 | ☐ |
| H10 | Carichi giornalieri/settimanali in minuti e pause | Implementato, valori da D05 (T15, T36) | D05 | ☐ |
| H11 | Transizioni di localizzazione; vincoli familiari; sincronizzazioni | Parziale | D05, GAP-C02 | ☐ |
| H12 | Sequenze curricolari, correlazioni, periodi di iscrizione | Assente | D01, D06 | ☐ |

## 2. Politica degli obiettivi
Ordine lessicografico (U_P0, U_P1, U_P2, F, C, R, P, G) come da verbale D03, versionato nello snapshot (FR11). Firma: ☐

## 3. Dizionario, stati e unità canoniche (elenco da firmare)
- Entità: Family, Student, GuardianLink, Tutor, Subject, Resource, TeachingRequest, TeachingGroup, LearningPath, CurriculumBlock, DemandUnit, PlanningSnapshot, Plan, Publication, LessonOccurrence, ResourceBooking, LessonSeries*, RecoveryObligation*, Attendance*, ConflictCase*, OutboxEvent* (* in arrivo dagli stream s2/s3).
- Distinzioni obbligatorie: coorte ≠ gruppo di sessione; richiesta ≠ serie ≠ occorrenza; famiglia ≠ diritto di accesso (I1).
- Stati: disponibilità DRAFT/APPROVED/REVOKED; dichiarazione UNKNOWN/DECLARED_NONE; esito solver OPTIMAL/FEASIBLE/INFEASIBLE/UNKNOWN/MODEL_INVALID/BLOCKED; piano DRAFT→VALIDATED→PUBLISHED/STALE/REJECTED (GAP-E07); delega con riconferma NOT_REQUIRED/PENDING/CONFIRMED/DECLINED.
- Unità: minuti interi; griglia 15'; intervalli semiaperti [s, e); fuso Europe/Rome con UTC in persistenza; settimana ISO lunedì–domenica; unità di domanda canonica per richiesta × settimana × indice.
Firma: ☐

## 4. Policy delle autorizzazioni
Matrice del paper §10.1 e profili di `docs/compliance/12-designazione-autorizzati.md`. Firma: ☐

## 5. Fixture con risultati attesi
Fixture per T01–T42 con expected come **invarianti e obiettivi**, non layout (paper §12.3); elenco e stato in
`tracciabilita-test.md` §3. Fixture di riferimento 720 unità (s8). Firma: ☐

## 6. Firme G1

| Ruolo | Nome | Firma | Data |
|---|---|---|---|
| Committente | [DA COMPILARE] | | |
| Responsabile didattico | [DA COMPILARE] | | |
| Architect | [DA COMPILARE] | | |
