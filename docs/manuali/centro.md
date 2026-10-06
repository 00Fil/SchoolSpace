# Manuale per lo staff del centro

Versione 0.8 sperimentale. Integra la documentazione operativa esistente (docs/).

## Accesso e sicurezza
- Il ruolo Centro richiede la **verifica in due passaggi** (TOTP). Al primo accesso: inquadra il QR (o inserisci la chiave), conferma con il codice e **salva i codici di recupero** (mostrati una volta; si prosegue solo confermando «Li ho salvati»).
- Codice perso: «Non hai il telefono? Usa un codice di recupero». Nuovi codici: Impostazioni → Sicurezza.
- Alcune operazioni chiedono di nuovo il codice (step-up): compare la schermata di verifica e poi si torna al lavoro.
- Impostazioni → Sicurezza: cambio password (chiude le altre sessioni), elenco sessioni con chiusura singola o «Chiudi le altre».
- Con più ruoli: menu account → «Cambia ruolo». Il server applica solo i ruoli concessi.

## Stati delle schermate
- **Ricerca non conclusiva** (solver UNKNOWN): il motore non ha trovato una risposta nel tempo concesso; non significa impossibilità. Rigenera con più tempo o meno domanda.
- **Risultato parziale**: alcune richieste non collocate; per pubblicare serve l’accettazione esplicita.
- **Dati non aggiornati**: la proposta o la lezione è cambiata; ricarica/rigenera.
- **Conflitto**: sovrapposizione con prenotazioni esistenti; nulla è stato salvato.
- I codici tecnici (HTTP, codice errore, ID) sono sotto «Dettagli tecnici».

## Portali famiglie/tutor: cosa vedono
- Le famiglie vedono i figli con delega attiva; senza permesso di modifica le schede riportano «Sola lettura» e mancano i pulsanti di modifica/richiesta.
- Le richieste di cambio/assenza arrivano all’agenda del centro; accoglierle non sposta nulla in automatico.
- Le **eccezioni di disponibilità** si registrano solo dal centro: il portale le mostra in sola lettura.
- Le richieste dirette dello studente dipendono dalla decisione D07 (impostazione `PORTAL_STUDENT_CAN_REQUEST_CHANGES`, default disattiva).

## Aiuto in linea
Ogni schermata ha «Come funziona» con i punti chiave e il riferimento a questo manuale.

## Configurazione (P2)

Menu **Configurazione**, riservato al centro. Ogni modifica chiede un motivo, che resta nel registro.

1. **Anno scolastico**: crea l'anno (es. 2026/27) con le date di inizio e fine, poi aggiungi i periodi: inizio lezioni, pausa natalizia, pasquale, estiva, altre pause e periodi per i recuperi. Le pause chiudono il centro in automatico (compaiono in «Chiusure»); i periodi per i recuperi lasciano il centro aperto.
2. **Orari del centro**: scegli In sede o Online e colora sulla griglia le fasce di apertura. Mouse o dito: trascina. Tastiera: frecce per muoverti, Spazio per attivare o disattivare. Poi premi «Salva orari». Gli orari valgono per l'anno in corso.
3. **Chiusure**: aggiungi chiusure straordinarie (es. un ponte), per tutte le modalità o una sola.
4. **Aule**: inserisci aule con capienza e canali video.
5. **Da approvare**: le disponibilità di famiglie e tutor restano in bozza e il motore non le usa finché il centro non le approva. Si possono selezionare più righe e approvarle o respingerle insieme.

Quando tutto è inserito, la verifica dei dati del Laboratorio diventa verde.

### Eccezioni, dichiarazioni e regole del motore
- **Eccezioni**: un giorno in più o in meno rispetto alle fasce settimanali di una persona.
- **Dichiarazioni**: indicano se i dati di una persona sono completi, se la persona non ha disponibilità o se i dati sono ancora incompleti.
- **Regole del motore**: tempo di ricerca, settimane parziali, uso dei canali video.

### Disponibilità sulla griglia
In **Disponibilità** scegli la vista «Griglia per persona», poi la persona e la modalità.
- Trascina per aggiungere o togliere fasce, poi premi «Salva».
- Le fasce nuove restano in bozza finché non le approvi.
- Le fasce tolte vengono revocate e serve un motivo.


## Dalla proposta al calendario (P3)
In **Agenda → Proposte da pubblicare** apri una proposta:
1. **Valida**: il controllo si ripete sui dati di oggi.
2. **Pubblica**: le lezioni entrano nel calendario e nei portali. Se resta qualcosa da pianificare, devi accettarlo e scrivere il motivo.
3. **Crea le serie ricorrenti**: le prossime proposte terranno gli stessi orari.

Se la proposta non va, premi **Rifiuta** e scrivi il motivo. Con **Confronta** vedi cosa cambia tra due proposte.

### Prese visione dei tutor
Sotto le proposte vedi chi deve ancora confermare e le controproposte dei tutor. Per ognuna scegli:
- **Chiedi alle famiglie**: crea le richieste di modifica, che restano in attesa della conferma dei genitori;
- **Accogli**: crea le richieste di modifica nella coda Richieste;
- **Respingi**: il tutor deve confermare di nuovo gli orari.


## Da gestire (P4)

La sezione **Da gestire** raccoglie le decisioni di ogni giorno in quattro code.

1. **Richieste**: richieste di cambio di famiglie e tutor. Accetti o rifiuti con un motivo (precompilato, modificabile). Se la richiesta viene da una famiglia, dopo il tuo sì resta «Attende il tutor»: la lezione cambia solo quando il tutor conferma.
2. **Recuperi**: lezioni perse da recuperare, con la scadenza (fine dell'anno scolastico) e il primo periodo per i recuperi. *Fissa* propone giorno, ora e tutor; il controllo verifica disponibilità, aule e chiusure. *Rinuncia* chiude il recupero.
3. **Conflitti**: *Cerca conflitti* controlla le lezioni pubblicate. *Risolvi* annulla la lezione (con o senza recupero) o la conferma.
4. **Comunicazioni**: avvisi del portale e invii falliti, che puoi riprovare o abbandonare.

**Regola dei recuperi**: spettano se l'assenza è avvisata almeno 24 ore prima. Con preavviso più breve il sistema chiede una scelta esplicita («Concedi comunque il recupero»), che resta nello storico. Lezioni di gruppo e chiusure impreviste: decidi caso per caso. Assenza del tutor: prima un sostituto, altrimenti recupero.


## Scheda della lezione (P4)

Nell'Agenda, aprendo una lezione trovi:

- **Sostituisci il tutor**: elenca i tutor disponibili e abilitati per quell'orario (e perché gli altri no). Se nessuno può, il pulsante diventa **Annulla con recupero**: il recupero compare in *Da gestire → Recuperi*.
- **Modifica**: cambia la modalità (in presenza / online). Per le lezioni ricorrenti scegli **Solo questa lezione** o **Da questa in poi**: nel secondo caso cambiano tutte le lezioni successive della serie, quelle precedenti restano com'erano.
- **Sposta** e **Cancella lezione**: come prima.
- **Scambia con un'altra**: le due lezioni si scambiano giorno e ora, se entrambe restano valide.
- **Presenze e conclusione** (lezioni finite): segni presenti/assenti e chiudi la lezione.
- **Correggi le presenze** (lezioni concluse): correzione con motivo e conferma esplicita, tracciata nello storico.
- **Link video** (lezioni online): mostra il link della videolezione.

Ogni azione chiede un motivo già compilato, che puoi cambiare. Se qualcuno ha modificato la lezione nel frattempo, il sistema te lo dice e non sovrascrive nulla.


## Modifiche proposte dal tutor: conferma dei genitori (P5)

Quando accogli le modifiche proposte da un tutor, nella coda *Richieste* la richiesta risulta «Attende i genitori»: non puoi accettarla finché un genitore non conferma. Dopo la conferma torna a te: applica la modifica dalla scheda lezione e chiudi la richiesta. Puoi sempre rifiutarla.

## Invito dello studente

L'accesso proprio dello studente si crea solo se confermi che ha almeno 14 anni.


## Richieste arrivate dal portale (P5)

Le richieste che famiglie, studenti e tutor fanno da *I miei dati* arrivano nel registro privacy con canale «PORTALE» e scadenza a un mese, come quelle raccolte a voce. Le copie dei dati scaricate dal portale aprono automaticamente una richiesta di accesso.


## Area Privacy (P6)

Menu **Privacy**, cinque sezioni:

1. **Richieste**: aperte, scadute, tutte. Per ogni richiesta: *Verifica identità* → poi *Evadi con export* (accesso, portabilità), *Cancella* (cancellazione), *Chiudi con esito* (rettifica, limitazione, opposizione). *Proroga* e *Respingi* chiedono una motivazione da comunicare all'interessato.
2. **Export**: tutti i file protetti, con stato (da scaricare, scaricato, revocato); *Revoca* distrugge il file.
3. **Conservazione**: le regole della matrice (D09). Solo quelle *approvate* vengono applicate; *Simula* prima di *Esegui*; ogni esecuzione lascia una ricevuta.
4. **Registro**: le operazioni registrate, filtrabili per categoria e oggetto. Sola lettura.
5. **Maggiore età**: *Controlla* elenca gli studenti che diventano maggiorenni; *Avvia le riconferme* chiede loro di confermare le deleghe dal portale.
