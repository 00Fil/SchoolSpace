# REPORT — stream s7-conformita

Branch `s7-conformita` (baseline v0.7 + merge di `main`, che contiene lo stream s4-privacy). Solo documenti Markdown in
`docs/compliance/` e `docs/governance/`; **nessun file di codice, settings, urls o requirements toccato**.
Tutti i documenti hanno stato BOZZA, versione, responsabile, riferimenti normativi e campi `[DA COMPILARE]`; nessuno è
presentato come parere legale; le decisioni D01–D09 restano "da approvare" (raccomandazioni e valori di prova, non esiti).

## Indice dei documenti

### docs/compliance/ (fascicolo reg4-fascicolo, 22 voci → indice in `docs/compliance/README.md`)
| File | Contenuto | Fascicolo |
|---|---|---|
| 01-registro-trattamenti.md | Registro art. 30: dati comuni + 12 schede (anagrafiche, tutor, pianificazione, calendario, presenze, parentali, account, notifiche, sicurezza/audit, backup, diritti, violazioni) + registro 30.2 | 2 |
| 02-informativa-famiglie.md | Art. 13/14 genitori e tutori legali, con appendice di tracciamento | 3 |
| 03-informativa-studenti-minorenni.md | Versione in linguaggio semplice per i minori | 3 |
| 04-informativa-studenti-maggiorenni.md | Maggiorenni e passaggio alla maggiore età | 3 |
| 05-informativa-tutor-staff.md | Tutor, collaboratori, staff | 3 |
| 06-dpia.md | Prevalutazione WP248 + provv. 467/2018; descrizione, necessità/proporzionalità, 16 rischi, 23 misure con evidenze, rischio residuo, firme | 4 |
| 07-valutazione-dpo.md | Valutazione art. 37 | 5 |
| 08-accordo-art28-modello.md | Modello DPA art. 28 (+ obblighi fornitore di sviluppo, allegati A–E) | 6 |
| 09-fornitori-checklist.md | Censimento fornitori, checklist bloccante/valutativa, verifiche | 6 |
| 10-trasferimenti-extra-ue.md | Albero decisionale Capo V e modello TIA | 7 |
| 11-matrice-retention-d09.md | Matrice D09 (18 righe) allineata a guida e `apps/privacy` `DEFAULT_MATRIX`, valori di prova | 8 |
| 12-designazione-autorizzati.md | Profili, atto di designazione, 14 istruzioni, registro | 9 |
| 13-procedura-diritti-interessati.md | Flusso con tempi, verifica legittimazione minori, esecuzione per diritto, modelli A–E | 10 |
| 14-procedura-data-breach.md | Fasi/tempi, valutazione del rischio (ENISA), casi tipici, registro art. 33.5, modelli Garante/interessati/responsabile | 11 |
| 15-informativa-lavoratori-art4.md | Informativa art. 4 Statuto + policy d'uso dell'audit | 12 |
| 16-termini-di-servizio.md, 17-informativa-cookie.md | Termini d'uso; cookie verificati sul codice (sessionid, csrftoken + 2 chiavi localStorage tecniche) | 13 |
| 18-nota-ai-act-art22-nis2-accessibilita.md, 19-dichiarazione-accessibilita.md | Nota di inquadramento; dichiarazione di accessibilità volontaria modello | 14 |
| 20-politica-sicurezza-informazioni.md, 21-piano-continuita.md | Politica di sicurezza; piano di continuità (BIA, scenari, comunicazione) | supporto 15–18 |
| 22-registro-conformita.md | 25 catene obbligo→requisito→controllo→evidenza con stato | trasversale |
| 23-schede-evidenze-tecniche.md | Struttura e criteri dei documenti tecnici 15–22 | 15–22 |

### docs/governance/
| File | GAP |
|---|---|
| verbale-D01.md … verbale-D09.md | A01, A02, A03 |
| g1-contratto-dominio.md | A04 (scheda firma H01–H12, obiettivi, dizionario, stati, unità) |
| tracciabilita-test.md | A04, M04 — matrice reale da `backend/tests/` (16 moduli, 251 funzioni, 316 casi) |
| censimento-dati-reali.md | A05 |
| analisi-impatto-v07.md | A06 |
| piano-pilota-golive.md, verbale-go-no-go.md | N01, N02, N03, N04, G08 |
| piano-manutenzione-slo.md | N05, N06 |

## GAP chiusi (lato documentale; restano firme e dati del titolare)
GAP-A06 (analisi d'impatto e piano di modifica), GAP-A04 parte "matrice di tracciabilità" (manuale, completa sulla suite
attuale). Per gli altri GAP la bozza è completa ma la chiusura richiede approvazioni esterne → vedi sotto.

## GAP parziali (bozza completa, manca approvazione/compilazione/evidenza)
- A01, A02, A03: verbali con opzioni, raccomandazione, impatto, valori di prova; mancano firme ed esiti.
- A04: manca la firma G1 e l'automazione in CI (proposta marcatore `req` + report JSON, §9 della matrice).
- A05: modello pronto, dati da raccogliere dal centro.
- H01, H02, H03, H05, H08, H09, H10, H11 (nota): testi pronti; mancano consulente, firme, scelta fornitori (D08), presa visione nel software.
- H04: matrice proposta coerente con il codice s4; durate da decidere.
- N01–N06: piani pronti; date, persone e budget da compilare; esecuzione del pilota fuori dal perimetro.

## Risultati della matrice di tracciabilità (T01–T42, su questo branch)
25 coperti, 11 parziali, 6 assenti (stima guida v0.7: 26/8/8). Assenti: T14, T22, T23, T30, T33, T34. Solo PostgreSQL
(skipped): 9 funzioni/12 casi. T12 è declassato a parziale (manca il caso letterale del paper). Rigenerare dopo il merge di s1, s2, s3, s8.

## Controlli software mancanti emersi (da assegnare ad altri stream)
Presa visione versionata delle informative; flag di limitazione (art. 18) e legal hold; audit delle letture dell'audit e
permesso dedicato; policy identità collegate ai permessi della delega e alla riconferma; alert sulle richieste privacy in
scadenza; profili distinti nel ruolo CENTER.

## File toccati fuori dalla proprietà
Nessuno. Il merge di `main` (s4) è stato fatto senza conflitti per analizzare la suite aggiornata.

## Settings / urls / requirements / dipendenze
Nessuna modifica; nessuna nuova dipendenza.

## Test
Suite completa (SQLite): **304 passed, 12 skipped** in 121 s. `ruff check` ok, `ruff format --check` ok,
`manage.py check` ok, `makemigrations --check` nessuna modifica.

## Rischi / punti aperti
- I riferimenti normativi vanno verificati dal consulente al momento della firma (in particolare: applicabilità della L. 132/2025, qualificazione AI Act, prescrizione art. 2955 n. 1 c.c., campi della procedura telematica del Garante).
- I documenti descrivono funzioni degli stream s1/s2/s3/s5/s8 non ancora su `main`: aggiornare la colonna "Stato" della DPIA (Parte E) e del registro di conformità a ogni merge.
- Il ruolo applicativo CENTER è unico: i profili A–D della designazione sono oggi solo organizzativi.
