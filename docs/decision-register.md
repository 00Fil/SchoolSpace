# Registro decisioni — aggiornamento v0.2

| ID | Decisione | Da raccogliere per approvazione |
|---|---|---|
| D01 | Parentali: significato confermato dal committente | Studenti che svolgono tutto il programma scolastico e tutte le materie con il centro. Restano da dettagliare programmi per anno/livello, monte ore e responsabilità; G1 non è firmato automaticamente. |
| D02 | Gruppi | Responsabile composizione, compatibilità didattica, capienza online |
| D03 | Priorità e parziale | P0/P1/P2, mandatory, strict/coverage, unità di copertura ed equità |
| D04 | Aperture | Finestre presenza/online, online in sede, risorse video |
| D05 | Lavoro e transizioni | Pause, carichi tutor, matrice remoto/sede, buffer spazio |
| D06 | Periodi e recuperi | Anno, orizzonte, festività, cancellazioni e recuperi individuali/gruppo |
| D07 | Accessi studenti/privacy | Inviti, finalità, basi giuridiche e dati minimi |
| D08 | Fornitori e servizio | Team, budget, hosting, email, video, SLO |
| D09 | Retention | Matrice per categoria, backup, cancellazione e export |

Per ogni decisione servono responsabile, scadenza, alternative, esito, evidenza e impatto.
G1 richiede inoltre dizionario/stati/unità canoniche, policy autorizzazioni, H01–H12, fixture con expected e baseline firmata.
Il PDF è materiale iniziale, non evidenza di approvazione.


## Decisioni del committente raccolte il 3/10/2026 (guida v3.1, §10)

| ID | Decisione | Esito | Impatto |
|---|---|---|---|
| DC-ANNO (D06 parziale) | Struttura dell'anno scolastico | Il centro configura l'anno (inizio e fine) e i periodi di studio: inizi delle lezioni, pausa natalizia, pasquale, estiva, altre pause e periodi per i recuperi. Interessano solo le pause dello studio. | P2: `SchoolYear` e `StudyPeriod`; le pause generano chiusure; l'anno è il periodo di default di orari e disponibilità. I periodi per i recuperi si usano in P4. |
| DC-APPROVAZIONI | Chi approva disponibilità e orari | Il motore prepara la proposta; **solo il gestore accetta**. Il tutor conferma la presa visione degli orari e può fare una controproposta, che torna al gestore: il gestore decide e, se serve, chiede conferma ai genitori. Viceversa, una modifica chiesta dai genitori arriva al gestore e va confermata da lui e dal tutor. | P2: le disponibilità di famiglie e tutor restano in bozza finché il gestore non le approva (anche in blocco). P3/P4: presa visione del tutor, controproposte e conferme incrociate nella coda «Richieste». |
| D07 (parziale) | Account dello studente minorenne | Sì, lo studente minorenne ha un proprio account, insieme a quelli dei genitori. | P5: invito allo studente accanto a quello del genitore. **Da definire**: età minima, cosa vede e può fare lo studente, chi autorizza il suo account. |

Resta da registrare la firma formale (responsabile, data, evidenza) per G1.


## Decisioni del 3/10/2026 (P4)

| ID | Tema | Decisione | Dove è applicata |
|---|---|---|---|
| DC-RECUPERI (D06) | Diritto al recupero | Recupero se l'assenza è avvisata **almeno 24 ore prima**; il centro può concederlo manualmente anche con preavviso più breve (scelta esplicita e tracciata). | `recovery_policy.check_entitlement`, codice `LATE_NOTICE`, opzione `grant_late_notice` |
| DC-RECUPERI-SCADENZA | Scadenza | Entro la fine dell'anno scolastico della lezione persa. | `recovery_policy.due_by`, codice `RECOVERY_PAST_DUE` |
| DC-GRUPPO | Assenza a lezione di gruppo | Decide il centro caso per caso (nessuna regola automatica). | Coda «Conflitti» / «Recuperi» |
| DC-CHIUSURE | Chiusura imprevista | Decide il centro caso per caso. | Coda «Conflitti» (annulla con o senza recupero) |
| DC-TUTOR-ASSENTE | Assenza del tutor | Sostituto abilitato, altrimenti recupero. | P4 parte 2: ricerca sostituti; oggi: annulla con recupero `TUTOR_ABSENCE` |
| DC-NOTIFICHE | Canale | Solo avvisi nel portale; email solo per messaggi essenziali (inviti, sicurezza). | `COMMUNICATIONS_CHANNELS=IN_APP` |

| DC-TUTOR-ASSENTE (attuazione) | Sostituto del tutor | Ricerca sostituti nella scheda lezione (`GET /occurrences/<id>/substitutes/`, solo lettura); senza sostituti: annullamento con recupero `TUTOR_ABSENCE`. | P4 parte 2 |
| D07 | Account dello studente | Account proprio da 14 anni, attestato dal centro all'invito; oltre a quello dei genitori. Il minorenne vede solo lezioni e link video. | Committente, 3/10/2026 |
| DC-CONFERMA-GENITORI | Modifiche chieste dal tutor | Dopo l'accoglimento del centro servono sempre la conferma dei genitori; poi il centro applica. | Committente, 3/10/2026 |
