/** Testi di aiuto in linea per ruolo; i manuali estesi sono in docs/manuali/. */
type H = { title: string; points: string[]; manual: string };
export const HELP: Record<string, H> = {
  login: { title: "Accedere", manual: "docs/manuali/onboarding-famiglie.md", points: [
    "Usa l’email con cui il centro ti ha invitato e la password scelta all’accettazione dell’invito.",
    "Lo staff del centro conferma l’accesso con un codice a 6 cifre generato da un’app di autenticazione.",
    "Hai dimenticato la password? Chiedi un link di reimpostazione: vale 30 minuti e una sola volta."] },
  famiglia: { title: "La panoramica della famiglia", manual: "docs/manuali/famiglie.md", points: [
    "Ogni scheda riguarda uno studente collegato a te da una delega verificata dal centro.",
    "«Sola lettura» significa che la delega permette di vedere ma non di modificare: per cambiarla parla con il centro.",
    "I minuti e le lezioni si riferiscono alla settimana mostrata, nel fuso orario di Roma."] },
  studente: { title: "Il tuo spazio", manual: "docs/manuali/studenti.md", points: [
    "Vedi solo le tue lezioni e le tue disponibilità: i nomi degli altri partecipanti restano riservati.",
    "Le richieste di cambio dallo studente dipendono da una decisione del centro ancora da approvare."] },
  figlio: { title: "Disponibilità ed eccezioni", manual: "docs/manuali/famiglie.md", points: [
    "Le fasce settimanali sono le disponibilità ricorrenti; restano in bozza finché il centro non le approva.",
    "Le eccezioni sono giorni puntuali in cui la disponibilità si aggiunge o si toglie; le registra il centro.",
    "Ciò che non è dichiarato non viene mai considerato libero."] },
  cambi: { title: "Richieste di cambio e assenza", manual: "docs/manuali/famiglie.md", points: [
    "Una richiesta non sposta nulla da sola: il centro la valuta e ti risponde qui e nelle notifiche.",
    "Puoi ritirare una richiesta finché è in attesa.",
    "Per chiedere cambi serve una delega con il permesso «richieste di modifica»."] },
  tutor: { title: "Il tuo carico e le presenze", manual: "docs/manuali/tutor.md", points: [
    "Il carico è la somma in minuti delle lezioni non cancellate della settimana, confrontata con i limiti concordati.",
    "Dopo ogni lezione registra le presenze di ciascun partecipante entro 14 giorni.",
    "Per un’assenza tua apri la lezione nella settimana e scegli «Segnala assenza»: il centro organizza la sostituzione."] },
  privacy: { title: "Privacy", manual: "docs/manuali/centro.md", points: [
    "Ogni richiesta va evasa entro un mese dalla ricezione (prorogabile di due mesi, art. 12.3): le scadute sono in rosso.",
    "Prima di evadere, verifica l’identità di chi ha chiesto; per le richieste dal portale basta l’accesso autenticato.",
    "La pulizia applica solo le regole di conservazione approvate dal titolare; simula sempre prima di eseguire.",
    "Il registro è in sola aggiunta e serve a ricostruire chi ha fatto cosa, non a misurare il lavoro delle persone.",
  ] },
  dati: { title: "I miei dati", manual: "docs/manuali/famiglie.md", points: [
    "La copia dei dati si scarica una sola volta e scade: conservala con cura.",
    "Correzione, cancellazione, limitazione e opposizione arrivano al centro, che risponde entro un mese.",
    "Il genitore può chiedere anche per i figli collegati; lo studente minorenne solo per sé.",
  ] },
  operativita: { title: "Da gestire", manual: "docs/manuali/centro.md", points: [
    "Richieste: accetti o rifiuti con un clic. Le richieste delle famiglie cambiano la lezione solo dopo la conferma del tutor.",
    "Recuperi: spettano con assenza avvisata almeno 24 ore prima; puoi concederli anche dopo. Vanno fatti entro la fine dell’anno scolastico.",
    "Conflitti: per l’assenza del tutor cerca prima un sostituto; se non c’è, annulla con recupero. Chiusure impreviste e lezioni di gruppo: decidi tu caso per caso.",
    "Comunicazioni: gli avvisi arrivano nel portale; qui riprovi o chiudi gli invii falliti."] },
  orari: { title: "Orari da confermare", manual: "docs/manuali/tutor.md", points: [
    "Dopo ogni pubblicazione conferma di aver visto i tuoi orari.",
    "Se qualcosa non va, proponi le modifiche lezione per lezione: decide il centro, che può chiedere conferma alle famiglie.",
    "Le lezioni non cambiano finché il centro non decide."] },
  account: { title: "Sicurezza e preferenze", manual: "docs/manuali/centro.md", points: [
    "Le sessioni elencate sono i browser in cui hai effettuato l’accesso; puoi chiuderle da qui.",
    "Il link del calendario personale si vede una volta sola: trattalo come una password e revocalo se lo condividi per errore.",
    "Le notifiche di servizio nell’app non si possono disattivare; quelle email sì, salvo le essenziali."] },
  centro: { title: "Il gestionale del centro", manual: "docs/manuali/centro.md", points: [
    "Le proposte di calendario si generano dai dati approvati e si pubblicano solo dopo la validazione.",
    "Gli errori mostrano il motivo e il prossimo passo; i codici tecnici sono nei dettagli richiudibili."] },
  agenda: { title: "L’agenda del centro", manual: "docs/manuali/centro.md", points: [
    "Mostra le lezioni pubblicate; spostamenti e cancellazioni passano da un controllo automatico.",
    "Le richieste di cambio delle famiglie e dei tutor si valutano qui: accoglierle non sposta nulla in automatico.",
    "Se un’azione dice «dati non aggiornati», ricarica: qualcun altro ha modificato la lezione."] },
  disponibilita: { title: "Disponibilità", manual: "docs/manuali/centro.md", points: [
    "Le fasce si disegnano sul calendario trascinando; quelle proposte da famiglie e tutor arrivano in bozza: approvale con un clic.",
    "Solo le fasce approvate entrano nelle proposte di calendario; ciò che manca non è mai libero.",
    "Una famiglia senza permesso di gestione vede le fasce in sola lettura."] },
  proposte: { title: "Dati e proposte", manual: "docs/manuali/centro.md", points: [
    "Una proposta si valida, poi si pubblica; se non va, si rifiuta. Dopo la pubblicazione puoi crearne le serie ricorrenti.",
    "Con «Confronta» vedi quali lezioni cambiano tra due proposte.",
    "Una proposta nasce dai dati approvati; se i dati cambiano diventa obsoleta e va rigenerata.",
    "«Ricerca non conclusiva» significa che il motore non ha trovato una risposta nel tempo concesso, non che sia impossibile.",
    "Una proposta parziale si pubblica solo accettando esplicitamente le richieste escluse."] },
  studenti: { title: "Studenti", manual: "docs/manuali/centro.md", points: [
    "Vedi solo gli studenti autorizzati al tuo ruolo.",
    "Il centro gestisce figli, genitori e inviti dalla schermata Famiglie."] },
  anagrafica: { title: "Famiglie", manual: "docs/manuali/centro.md", points: [
    "Si parte dal genitore o tutore: con «Nuova famiglia» lo inviti, poi aggiungi i figli (anche più tardi). Vedrà tutti i figli della famiglia.",
    "L’invito parte solo dopo che hai verificato la relazione: annota come l’hai verificata, senza allegare documenti.",
    "Se il genitore è con te, «Mostra QR code»: lo inquadra con il telefono, sceglie la password ed entra subito. Il codice vale 15 minuti; l’email resta valida.",
    "Con l’import CSV vedi prima l’anteprima degli errori: nulla si salva finché non confermi.",
    "Se compare «Qualcun altro ha modificato questo dato», ricarica: la tua modifica non è stata applicata."] },
  tutori: { title: "Tutor", manual: "docs/manuali/centro.md", points: [
    "Puoi registrare un tutor prima che abbia un account: l’invito lo collega quando lo accetta.",
    "Il motore pianifica solo competenze approvate e valide nella settimana.",
    "Le regole di lavoro limitano minuti al giorno e alla settimana, pause e tempi di spostamento sede/online.",
    "Disattivare un tutor non cancella lo storico: revoca l’accesso e lo esclude dalle nuove proposte."] },
  configurazione: { title: "Configurazione", manual: "docs/manuali/centro.md", points: [
    "Parti dall’anno scolastico: le sue date sono il periodo di default per orari e disponibilità.",
    "Le pause (natale, pasqua, estate e altre) chiudono il centro in automatico; i periodi per i recuperi no.",
    "Gli orari del centro si dipingono sulla griglia, separati per sede e online.",
    "Le disponibilità di famiglie e tutor valgono solo dopo l’approvazione del centro, anche in blocco.",
    "Eccezioni, dichiarazioni e regole del motore completano i dati richiesti dalla verifica."] },
  utenti: { title: "Utenti e ruoli", manual: "docs/runbooks/07-primo-gestore.md", points: [
    "Qui vedi solo gestori e tutor; famiglie e figli sono in Famiglie.",
    "Deve sempre restare almeno un gestore attivo e non puoi revocare il tuo ruolo.",
    "L’azzeramento della MFA di un collega chiude le sue sessioni; la tua MFA la azzera un altro gestore."] },
};
