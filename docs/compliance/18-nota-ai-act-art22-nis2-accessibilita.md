# Nota di inquadramento: AI Act, art. 22 GDPR, NIS2 e accessibilità

| Campo | Valore |
|---|---|
| Stato | **BOZZA** — nota tecnica di una pagina per il fascicolo G6; da validare con il consulente |
| Versione | 0.1 — 2026-10-02 |
| Documento del fascicolo | n. 14 — gate G3 (art. 22, pubblicazione umana) e G6 |
| GAP | GAP-H11 |
| Responsabile | Architect con consulente |
| Riferimenti normativi | Reg. (UE) 2024/1689 (AI Act) art. 3.1, art. 5, art. 6 e all. III punto 3; L. 23 settembre 2025, n. 132 (legge italiana sull'IA) [DA VERIFICARE applicabilità]; GDPR art. 22; D.Lgs. 138/2024 (NIS2); D.Lgs. 82/2022; L. 4/2004; WCAG 2.2 |

> Non è un parere legale. Le conclusioni sono "probabili" e vanno confermate o corrette dal consulente.

## 1. AI Act
**Fatti tecnici.** Il motore (OR-Tools CP-SAT) risolve un modello a vincoli scritto dalle persone (H01–H12 e obiettivo
lessicografico approvato in D03); non apprende dai dati, non usa modelli statistici né addestramento; lo stesso input
produce soluzioni equivalenti rispetto agli obiettivi; un validatore indipendente verifica i vincoli prima di ogni uso.

**Valutazione proposta.**
1. È **dubbio** che sia un "sistema di IA" (art. 3.1): le linee guida della Commissione sulla definizione escludono i sistemi basati su regole definite unicamente da persone fisiche e l'ottimizzazione matematica classica [DA VERIFICARE testo vigente].
2. Anche se lo fosse, non è ad **alto rischio**: l'all. III punto 3 riguarda accesso o ammissione, valutazione dei risultati dell'apprendimento, livello di istruzione adeguato e sorveglianza durante le prove; la pianificazione degli orari non rientra.
3. Nessuna pratica vietata (art. 5).
4. Se il consulente lo qualificasse come sistema di IA: valutare gli obblighi di alfabetizzazione (art. 4) per lo staff che lo usa (coperti dalla formazione N02) e la L. 132/2025.

**Condizioni da mantenere (vincoli di progetto).** Pubblicazione sempre umana; diagnostica spiegabile (vincoli violati,
alternative marcate come ipotesi); vietato introdurre moduli che assegnino automaticamente studenti a gruppi o livelli,
che usino modelli appresi o che valutino il rendimento senza una nuova valutazione (il raggruppamento pedagogico automatico
è già escluso dal paper §1.4).

## 2. Art. 22 GDPR
Non c'è una decisione "basata unicamente sul trattamento automatizzato": il coordinatore valida e pubblica ogni piano
(FR14/FR15), può modificarlo, scartarlo o spostarne le lezioni (FR16) e conosce i motivi delle richieste non collocate
(FR13). L'intervento è **significativo** e non un'approvazione formale: per questo la formazione dei coordinatori include
la lettura della diagnostica e la UAT verifica che le modifiche manuali siano possibili. Le informative spiegano il ruolo
del solver. Evidenze: test di pubblicazione (`test_calendar.py`), separazione bozza/pubblicato (T24), diagnostica (T27, T28).

## 3. NIS2 (D.Lgs. 138/2024)
Un centro privato di ripetizioni non rientra nei settori degli allegati e normalmente è sotto le soglie dimensionali
(media impresa: ≥ 50 dipendenti o fatturato/bilancio oltre le soglie UE). **Esito proposto: non soggetto.**
Autovalutazione: dipendenti [DA COMPILARE]; fatturato [DA COMPILARE]; settore ATECO [DA COMPILARE]; esito confermato il
[DA COMPILARE]. I fornitori cloud possono essere soggetti NIS2: è un criterio di selezione (doc. 9). L'art. 32 GDPR
resta comunque applicabile.

## 4. Accessibilità
Per un piccolo centro privato l'obbligo è dubbio: il D.Lgs. 82/2022 (dal 28 giugno 2025) esenta le microimprese che
forniscono servizi (< 10 addetti e fatturato o bilancio ≤ 2 milioni di euro) e la L. 4/2004 riguarda soprattutto PA e
soggetti di grandi dimensioni. Verifica: addetti [DA COMPILARE], fatturato [DA COMPILARE]. **Il requisito di progetto non
cambia**: WCAG 2.2 AA sui flussi principali (NFR07, T33, GAP-G07) con verifica automatica (axe) e manuale (tastiera,
NVDA/VoiceOver, zoom 200%). Si propone una dichiarazione di accessibilità volontaria (doc. `19-dichiarazione-accessibilita.md`).

## 5. Firme
Architect: ______________ Consulente: ______________ Titolare: ______________ Data: __________
