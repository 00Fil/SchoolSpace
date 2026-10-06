# Procedura di gestione delle violazioni di dati personali, registro e modelli di notifica

| Campo | Valore |
|---|---|
| Stato | **BOZZA** — tempi interni proposti; da integrare nel runbook "incidente di sicurezza" (GAP-L04) |
| Versione | 0.1 — 2026-10-02 |
| Documento del fascicolo | n. 11 — gate G6 |
| GAP | GAP-H08 |
| Responsabile | Titolare (A); consulente (R per la valutazione); operations (R per contenimento) |
| Riferimenti normativi | GDPR artt. 4.12, 33, 34, 28.3.f; Linee guida EDPB 9/2022 sulla notifica delle violazioni; Linee guida EDPB 01/2021 (esempi); metodologia ENISA 2013 per la valutazione della gravità |

> Non è un parere legale. Le 72 ore decorrono da quando il **titolare** ha una ragionevole certezza che si sia verificata
> una violazione. I tempi interni (1 h, 4 h, 24 h) sono proposte operative.

## 1. Che cos'è una violazione (esempi per questo sistema)

| Tipo | Esempi |
|---|---|
| Riservatezza | Un genitore vede il calendario di un altro minore (BOLA); notifica inviata all'indirizzo sbagliato; email con i nomi di tutti i membri del gruppo; export inoltrato o scaricato da terzi; credenziali dello staff compromesse; log con token o URL video esposto a un fornitore non previsto |
| Integrità | Calendario pubblicato alterato; presenze modificate senza autorizzazione; restore che riattiva deleghe revocate |
| Disponibilità | Indisponibilità prolungata o cancellazione del DB senza backup utilizzabile; ransomware |

## 2. Fasi e tempi

| Tempo | Fase | Chi | Azioni |
|---|---|---|---|
| T0 | Rilevazione | Chiunque; alert (accessi anomali, validatore, backup, rate limit) | Segnalare subito al referente incidenti [DA COMPILARE: nome, telefono reperibilità, email]; aprire una pratica nel registro (§5) con ora di scoperta |
| T0 + 1 h | Triage | Operations / referente | Classificare SEV (SEV1 = sospetta violazione di dati); informare il **titolare** e annotare l'ora della sua presa di conoscenza |
| T0 + 4 h | Contenimento | Operations, fornitore | Revocare sessioni e credenziali coinvolte; sospendere deleghe o account; disattivare l'invio notifiche se la causa è nell'outbox; bloccare export; **preservare** audit, log e snapshot (nessuna cancellazione, nessun restore che sovrascriva le evidenze); attivare il legal hold sulle categorie coinvolte |
| T0 + 24 h | Valutazione del rischio | Titolare con consulente | Applicare il §3; decidere notifica al Garante e comunicazione agli interessati |
| ≤ 72 h dalla presa di conoscenza del titolare | Notifica al Garante | Titolare | Se il rischio **non è improbabile**: notifica tramite la procedura telematica sul sito del Garante (modello §6); se mancano informazioni, notifica per fasi (art. 33.4); se oltre 72 h, motivare il ritardo |
| Senza ingiustificato ritardo | Comunicazione agli interessati | Titolare | Se il rischio è **elevato** (art. 34): modello §7, linguaggio semplice; per i minori la comunicazione va ai genitori/tutori |
| Entro 5 giorni lavorativi | Post-mortem | Operations, architect | Cronologia, causa, impatto sui dati, azioni con responsabile e scadenza; aggiornamento DPIA e runbook |
| Chiusura | Registro | Referente | Completare la scheda §5 anche se non notificata (art. 33.5) |

Se la violazione avviene presso un **responsabile** (hosting, email, fornitore di sviluppo), questi deve avvisare il
titolare entro il termine contrattuale (accordo art. 28, art. 4: [DA COMPILARE] ore) e il calcolo delle 72 ore parte dalla
presa di conoscenza del titolare.

## 3. Valutazione del rischio (proposta operativa)

Fattori (EDPB 9/2022): tipo di violazione; natura, sensibilità e volume dei dati; facilità di identificazione;
gravità delle conseguenze; caratteristiche speciali degli interessati (**minori**: fattore aggravante); numero di
interessati; caratteristiche del titolare.

Punteggio orientativo (metodo ENISA semplificato): **Gravità = DPC × EI + CB**
- DPC (contesto del dato): 1 dati semplici (nome, email); 2 dati comportamentali/di localizzazione temporale (orari e luogo delle lezioni di un minore); 3 dati che consentono contatto o ricostruzione delle abitudini di un minore; 4 categorie particolari (non dovrebbero esistere — se presenti, verificare la causa).
- EI (facilità di identificazione): 0,25 trascurabile … 1 massima (nome completo + contesto).
- CB (circostanze): + 0,5 accesso da parte di terzi malintenzionati; + 0,5 dati di minori; − 0,5 dati cifrati con chiave non compromessa; + 0,25 perdita di integrità o disponibilità prolungata.

| Esito | Gravità | Azione |
|---|---|---|
| Rischio improbabile | < 2 | Solo registro interno, con motivazione |
| Rischio | 2 – < 3 | Notifica al Garante |
| Rischio elevato | ≥ 3 | Notifica al Garante **e** comunicazione agli interessati, salvo eccezioni art. 34.3 (dati resi incomprensibili, misure successive che escludono il rischio, sforzo sproporzionato → comunicazione pubblica) |

Il punteggio supporta la decisione, non la sostituisce: la valutazione finale è del titolare con il consulente.

## 4. Casi tipici (orientamento da validare)

| Scenario | Orientamento |
|---|---|
| Email di variazione inviata al genitore sbagliato con nome dello studente, materia e orario | Probabile notifica (dati di un minore con luogo/orario); comunicazione alla famiglia interessata da valutare |
| Un genitore accede per errore al calendario di un altro minore per difetto di autorizzazione | Notifica; correzione urgente; verifica nell'audit di quanti accessi impropri ci sono stati |
| Laptop cifrato di un coordinatore smarrito, sessione chiusa | Rischio improbabile se cifratura e MFA verificate; registro interno |
| Indisponibilità di 3 ore senza perdita di dati | Di norma registro interno; comunicazione di servizio alle famiglie |
| Restore che riattiva deleghe revocate prima della riconciliazione | Valutare gli accessi effettivi nell'audit; notifica se ci sono stati accessi |

## 5. Registro interno delle violazioni (art. 33.5)

Il registro è tenuto [DA DECIDERE: in un foglio protetto del titolare / in una sezione dedicata del sistema], separato
dall'applicazione per restare disponibile anche quando questa non lo è.

| Campo | Contenuto |
|---|---|
| ID | VDP-AAAA-NNN |
| Date e ore | Evento (stimata); scoperta; presa di conoscenza del titolare; notifica al Garante; comunicazione agli interessati; chiusura |
| Rilevato da | Persona / alert / fornitore |
| Descrizione | Natura (riservatezza / integrità / disponibilità); sistemi coinvolti; causa (accertata / presunta) |
| Dati e interessati | Categorie di dati; categorie di interessati; numero approssimativo di interessati e di registrazioni; **presenza di minori** (sì/no) |
| Valutazione | Punteggio §3 e motivazione; parere del consulente |
| Notifica al Garante | Sì/No; data e ora; numero di protocollo; notifica per fasi; motivazione del ritardo o della mancata notifica |
| Comunicazione agli interessati | Sì/No; data; modalità; testo allegato; motivazione in caso di esclusione (art. 34.3) |
| Responsabili coinvolti | Fornitore; data della sua segnalazione |
| Misure | Contenimento; correzione; prevenzione; responsabile; scadenza; stato |
| Evidenze | Riferimenti a audit, log, ticket, post-mortem |
| Chiusura | Data; firma del titolare |

## 6. Modello di notifica al Garante (contenuti dell'art. 33.3)

> La notifica si invia con la procedura telematica disponibile sul sito del Garante; il modello raccoglie in anticipo
> le informazioni richieste. [DA VERIFICARE i campi del modulo vigente al momento dell'uso.]

1. **Titolare**: [ragione sociale, C.F./P. IVA, indirizzo, PEC]; DPO o referente: [nome, contatti].
2. **Tipo di notifica**: completa / preliminare (per fasi) / integrativa della n. [—].
3. **Tempi**: data e ora della violazione [—] (o periodo); della scoperta [—]; della presa di conoscenza del titolare [—]; motivi dell'eventuale ritardo oltre 72 h [—].
4. **Natura della violazione**: riservatezza / integrità / disponibilità; descrizione sintetica [es. "a causa di un errore di configurazione, il calendario di N studenti è stato visibile a M genitori non autorizzati tra le ore … e le ore …"]; causa [—]; sistemi coinvolti [gestionale web; fornitore …].
5. **Categorie e numero approssimativo di interessati**: studenti minorenni [n], genitori [n], tutor [n].
6. **Categorie e numero approssimativo di registrazioni**: dati anagrafici [n], dati di calendario [n], contatti [n].
7. **Probabili conseguenze**: [es. conoscenza da parte di terzi degli orari e dei luoghi frequentati da minori].
8. **Misure adottate o proposte**: contenimento [—]; correzione [—]; misure per attenuare gli effetti [—].
9. **Comunicazione agli interessati**: effettuata il [—] / prevista il [—] / non effettuata perché [art. 34.3 lett. …].
10. **Trasferimenti o interessati in altri Stati membri**: [no / sì].
11. **Contatto per informazioni**: [nome, telefono, email].

## 7. Modello di comunicazione agli interessati (art. 34)

Oggetto: Comunicazione importante sulla sicurezza dei dati di [nome dello studente]

"Gentile [genitore / studente maggiorenne / tutor],
il [data] abbiamo scoperto che [descrizione in parole semplici, senza tecnicismi: cosa è successo e quali dati sono
coinvolti]. Questo potrebbe comportare [possibili conseguenze].
Appena ce ne siamo accorti abbiamo [misure adottate: es. bloccato l'accesso, corretto l'errore, avvisato il Garante].
Le consigliamo di [azioni utili: es. cambiare la password del portale, prestare attenzione a email sospette che citino
il centro].
Per qualsiasi domanda può contattare [nome del referente] a [email/telefono].
Ci scusiamo per quanto accaduto. [Firma del titolare]"

Requisiti: linguaggio chiaro e semplice; un messaggio per destinatario (mai in copia visibile); canale diretto (email
o lettera), non solo un avviso generico nel portale; per i minori indirizzato a chi esercita la responsabilità genitoriale.

## 8. Modello di segnalazione da un responsabile al titolare
"Violazione rilevata il [data/ora] presso [fornitore]; natura [—]; dati e interessati presumibilmente coinvolti [—];
misure in corso [—]; prossimo aggiornamento entro [—]; referente [—]."

## 9. Esercitazione
Prima del go-live: esercitazione tabletop (scenario "email al destinatario sbagliato") con titolare, coordinatore,
operations e fornitore; misurare i tempi T0→triage→valutazione; archiviare l'esito in `docs/evidence/G6/`.
