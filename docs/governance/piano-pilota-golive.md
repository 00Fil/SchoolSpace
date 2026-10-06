# Piano di pilota, formazione, inviti progressivi, cutover e go/no-go

| Campo | Valore |
|---|---|
| Stato | **BOZZA** — date e persone da compilare; criteri proposti |
| Versione | 0.1 — 2026-10-02 |
| GAP | GAP-N01, GAP-N02, GAP-N03, GAP-N04 (con GAP-G08 UAT) |
| Gate | G5 (UAT) → G6 (go/no-go) |
| Responsabile | Committente (A); architect (R pilota); coordinatore (R operativo); operations (R cutover) |
| Riferimenti | Paper §13 fase 6; guida sez7-piano; fascicolo n. 21–22; `docs/compliance/06-dpia.md` Parte F (condizioni per dati reali) |

## 1. Prerequisiti al primo dato reale
- [ ] DPIA con condizioni Parte F soddisfatte; contratti art. 28 firmati (incluso fornitore di sviluppo).
- [ ] Informative pubblicate in staging con presa visione; designazioni firmate; formazione base completata.
- [ ] Produzione e staging isolati; backup e restore provati; MFA staff attiva.
- [ ] Import con template versionato in **dry-run** verificato dal coordinatore (T17), poi esecuzione senza inviti.

## 2. UAT (G5, GAP-G08)
Una settimana completa con dati sintetici realistici derivati dal censimento: pianificazione, pubblicazione, assenza di un
tutor, recupero, calendario parziale accettato, spostamento, presenze di gruppo, portali dei quattro ruoli, accesso
revocato. Esito per scenario: superato / non superato / differito con motivo. Firma: committente, QA, responsabile didattico.

## 3. Pilota in parallelo (GAP-N01)
- Durata: **almeno due cicli di pianificazione** (proposta: 2 orizzonti × 2 settimane pubblicate = 4 settimane) [DA COMPILARE: date].
- Il calendario attuale del centro resta la **fonte ufficiale**; il sistema produce il calendario in parallelo, visibile solo allo staff (nessun invito alle famiglie in questa fase).
- Ogni settimana: confronto lezione per lezione tra calendario attuale e sistema; registro delle differenze con classificazione (errore di dati / regola mancante / scelta diversa ma valida / difetto del software), responsabile e azione.
- Metriche: domanda coperta per priorità; collisioni (atteso 0); tempo di pianificazione; numero di interventi manuali; tempo di risposta del solver; incidenti.
- Criterio di uscita: due cicli consecutivi senza difetti bloccanti, differenze tutte riconciliate o accettate, nessuna collisione, nessun incidente privacy.

## 4. Inviti progressivi (GAP-N03)
| Ondata | Chi | Dimensione | Condizione per proseguire |
|---|---|---|---|
| 0 | Staff e tutor | tutti (~10) | Accesso, MFA staff, presenze provate |
| 1 | Famiglie volontarie | 3–5 | Nessun problema di scope, feedback sulle informative |
| 2 | Famiglie | ~25% | Tasso di attivazione e richieste di assistenza gestibili |
| 3 | Tutte | restanti | Go/no-go confermato |
Regole: nessun invio massivo non verificato; ogni ondata dopo controllo dei destinatari (deleghe verificate) e invio di prova
interno; inviti con scadenza 72 h e reinvio manuale.

## 5. Formazione (GAP-N02)
| Destinatari | Contenuti | Durata | Evidenza |
|---|---|---|---|
| Coordinatori | Pianificazione, lettura della diagnostica e ruolo umano nella pubblicazione (art. 22), conflitti, recuperi, export protetti, procedura diritti e violazioni | 2 × 2 h + affiancamento | Registro presenze |
| Segreteria | Anagrafiche, verifica relazione e inviti, dati vietati, richieste privacy | 2 h | Registro |
| Tutor | Disponibilità, presenze, privacy dei gruppi, sicurezza dell'account | 1 h | Registro |
| Famiglie | Guida di onboarding (GAP-G09), video breve, sportello telefonico nelle prime 4 settimane | — | Richieste di assistenza |
Aggiornamento annuale; nuovi assunti prima dell'accesso a dati reali.

## 6. Cutover (GAP-N04)
1. Congelamento delle modifiche al calendario attuale (T-1 giorno, ora [DA COMPILARE]).
2. Backup verificato < 24 h; import finale in dry-run → verifica → esecuzione.
3. Pubblicazione del primo orizzonte nel sistema; confronto finale con il calendario attuale.
4. Smoke test di produzione; monitoraggio rafforzato per 30 min e reperibilità per la prima settimana.
5. Ondate di inviti secondo il §4.
**Rollback operativo** senza perdere lezioni confermate: se il go-live fallisce entro [DA COMPILARE: 2 settimane], il
calendario attuale torna fonte ufficiale con l'export (PDF/ICS) delle lezioni pubblicate nel sistema; le modifiche fatte
nel sistema vengono riportate manualmente; gli inviti già inviati restano ma il portale mostra un avviso; nessuna
cancellazione dei dati (si applica la matrice D09).

## 7. Go/no-go
Riunione con committente, operations, QA, titolare. Verbale: `verbale-go-no-go.md`.
