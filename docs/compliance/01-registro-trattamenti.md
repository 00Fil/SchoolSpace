# Registro delle attività di trattamento (art. 30 GDPR)

| Campo | Valore |
|---|---|
| Stato | **BOZZA** — da revisionare con il consulente privacy e approvare dal titolare |
| Versione | 0.1 — 2026-10-02 |
| Documento del fascicolo | n. 2 (reg4-fascicolo) — gate G6 |
| GAP | GAP-H01 (con D07, D09) |
| Responsabile del documento | Titolare del trattamento: [DA COMPILARE: ragione sociale del centro] |
| Redatto da | Team di progetto (stream s7-conformita) — bozza tecnica |
| Revisore | [DA COMPILARE: consulente privacy] |
| Riferimenti normativi | Reg. (UE) 2016/679 (GDPR) artt. 5, 6, 24, 28, 30, 32; D.Lgs. 196/2003 (Codice) come modificato dal D.Lgs. 101/2018; matrice di retention D09 (`11-matrice-retention-d09.md`) |
| Prossimo riesame | [DA COMPILARE] — almeno annuale e a ogni modifica rilevante |

> **Avvertenza.** Questo documento è una bozza tecnica predisposta dal team di sviluppo per facilitare il lavoro del
> titolare e del consulente. Non è un parere legale. Le basi giuridiche sono la proposta della guida (D07) e diventano
> definitive solo con l'approvazione del titolare. Tutti i campi `[DA COMPILARE]` contengono dati che solo il titolare conosce.

## 1. Perché il registro è obbligatorio

L'esenzione dell'art. 30.5 (organizzazioni con meno di 250 dipendenti) non si applica perché il trattamento **non è
occasionale** e riguarda dati di **minori**. Il registro è tenuto in forma scritta (anche elettronica), è versionato in
questo repository e va esibito al Garante su richiesta (art. 30.4).

## 2. Dati comuni a tutte le schede

| Campo (art. 30.1) | Valore |
|---|---|
| Titolare | [DA COMPILARE: ragione sociale], [DA COMPILARE: sede legale], P. IVA/C.F. [DA COMPILARE] |
| Rappresentante legale | [DA COMPILARE] |
| Contatto privacy | [DA COMPILARE: email dedicata, es. privacy@dominio-del-centro] — canale unico per diritti e segnalazioni |
| DPO | [DA COMPILARE: "non nominato — vedi valutazione del gg/mm/aaaa (`07-valutazione-dpo.md`)" oppure nominativo e contatti] |
| Contitolari | Nessuno previsto. [DA COMPILARE se esistono accordi con scuole, associazioni o altri centri] |
| Rappresentante UE (art. 27) | Non applicabile (titolare stabilito in Italia) |
| Sistema principale | Gestionale ripetizioni v1.0 (backend Django/PostgreSQL, portali web); modelli citati per tracciabilità tecnica |
| Responsabili art. 28 | Vedi `09-fornitori-checklist.md`, elenco: hosting [DA COMPILARE], DB gestito/backup [DA COMPILARE], email transazionale [DA COMPILARE], error tracking/monitoraggio [DA COMPILARE], fornitore di sviluppo e manutenzione [DA COMPILARE] |
| Misure di sicurezza generali (art. 32) | Vedi `20-politica-sicurezza-informazioni.md`: TLS, cookie `Secure`/`HttpOnly`/`SameSite=Lax`, CSRF, MFA per lo staff (GAP-B04), hasher Argon2id, ruoli e scope per singolo studente ricontrollati a ogni richiesta, ruoli PostgreSQL a privilegio minimo, audit append-only (anche a livello DB, GAP-E08), cifratura a riposo del fornitore, backup PITR con restore provato (GAP-L02), redazione dei log (GAP-I07) |
| Categorie particolari (art. 9) e dati giudiziari (art. 10) | **Escluse per progetto** in tutte le schede. Le note libere hanno avvisi e limiti di lunghezza. Se il centro ha bisogno di gestire BES/DSA, certificazioni o dati sanitari serve un modulo separato con DPIA dedicata |
| Trasferimenti extra-SEE | [DA COMPILARE dopo D08] — di default nessuno; vedi `10-trasferimenti-extra-ue.md` |

## 3. Schede dei trattamenti

Le schede seguono l'elenco proposto dalla guida (anagrafiche; pianificazione e calendario; presenze e recuperi; portali
e account; notifiche; sicurezza e audit; backup; gestione dei diritti), con tre schede aggiuntive emerse dall'analisi del
codice: dati dei tutor, percorsi parentali (se D01 li conferma) e registro delle violazioni.

### TR-01 — Anagrafiche di famiglie e studenti, relazioni di tutela e import iniziale

| Campo | Contenuto |
|---|---|
| Finalità | Gestire il rapporto di servizio con le famiglie e gli studenti; individuare chi esercita la responsabilità genitoriale e con quali diritti nel sistema (visione, gestione disponibilità, richieste, notifiche) |
| Base giuridica (proposta D07) | Art. 6.1.b — contratto con il genitore/tutore legale o con lo studente maggiorenne; per l'import iniziale la stessa base del dato d'origine |
| Interessati | Studenti (anche minorenni); genitori e tutori legali; altri delegati autorizzati dal genitore [DA COMPILARE se previsti] |
| Categorie di dati | Nome visualizzato dello studente, classe/livello, famiglia di appartenenza (riferimento interno), stato attivo; dati di contatto del genitore (email, eventuale telefono [DA COMPILARE se raccolto]); relazione genitore–studente con validità, diritti e stato di verifica (`GuardianLink`, `GuardianLinkDetail`); data di nascita **solo** se necessaria per il passaggio alla maggiore età (`StudentProfile.birth_date`, D07) |
| Dati esclusi | Valutazioni scolastiche, pagelle, diagnosi, BES/DSA, dati sanitari, documenti d'identità (la verifica della relazione registra solo metodo, data e verificatore) |
| Fonte | Raccolti presso il genitore o lo studente maggiorenne (art. 13); per l'import iniziale da archivi esistenti del centro (template CSV versionato `famiglie-v1`, dry-run obbligatorio, GAP-H06) |
| Obbligatorietà | Necessari per erogare il servizio; il rifiuto impedisce la pianificazione |
| Destinatari | Persone autorizzate del centro (coordinatori, segreteria) secondo designazione; tutor solo per i dati minimi degli studenti assegnati; responsabili: hosting, DB gestito, fornitore di manutenzione |
| Trasferimenti | Vedi §2 |
| Conservazione | Matrice D09: durata del rapporto + periodo da approvare (categoria `calendar_attendance`/anagrafiche); account revocati minimizzati a 30–90 giorni (`revoked_accounts`); report di import 90 giorni con soli hash e conteggi (`import_reports`) |
| Misure specifiche | Famiglia ≠ diritto di accesso (invariante I1); delega verificata prima dell'invito; revoca immediata; audit unificato (`governance.AuditEvent`) di creazione, verifica e revoca |

### TR-02 — Dati dei tutor e del personale

| Campo | Contenuto |
|---|---|
| Finalità | Assegnare lezioni compatibili con competenze, disponibilità, modalità consentite e limiti operativi |
| Base giuridica (proposta) | Art. 6.1.b (contratto di lavoro o di collaborazione); art. 88 GDPR e art. 4 L. 300/1970 per i dipendenti (vedi `15-informativa-lavoratori-art4.md`) |
| Interessati | Tutor dipendenti, collaboratori autonomi, staff del centro |
| Categorie di dati | Nome visualizzato, account e ruolo; materie e livelli abilitati con validità e approvazione (`TutorSkill`); disponibilità ricorrenti ed eccezioni con stato e autore; limiti giornalieri/settimanali in minuti, pause e tempi di transizione (`TutorOperatingPolicy`); localizzazione (sede/remoto) della lezione; carichi pianificati |
| Dati esclusi | Metriche di produttività individuale, valutazioni delle prestazioni, geolocalizzazione, dati retributivi (fuori dal sistema) |
| Fonte | Interessato; responsabile didattico per le abilitazioni |
| Destinatari | Coordinatori; il tutor vede i propri dati; responsabili tecnici |
| Conservazione | Durata del rapporto + periodo da approvare [DA COMPILARE con consulente lavoro]; disponibilità storiche secondo D09 |
| Misure specifiche | Nessun cruscotto di produttività; l'audit non è usato per valutare il personale (policy in doc. 15) |

### TR-03 — Pianificazione delle lezioni

| Campo | Contenuto |
|---|---|
| Finalità | Costruire proposte di calendario rispettando aperture, disponibilità, competenze, capienze e vincoli familiari; diagnosticare le richieste non collocabili |
| Base giuridica (proposta) | Art. 6.1.b |
| Interessati | Studenti, tutor; indirettamente i genitori (vincoli familiari) |
| Categorie di dati | Richieste didattiche (materia, durata, frequenza, periodo, priorità, obbligatorietà); disponibilità ed eccezioni; aperture e chiusure; snapshot immutabile dell'input con hash SHA-256 (`PlanningSnapshot`); esiti e diagnostica del solver |
| Logica del trattamento | Ottimizzazione a vincoli (CP-SAT) su regole scritte dalle persone, senza apprendimento automatico. Il risultato è **una proposta**: la pubblicazione è sempre decisa da un coordinatore (FR14/FR15). Non è una decisione basata unicamente su trattamento automatizzato ai sensi dell'art. 22 (vedi `18-nota-ai-act-art22-nis2-accessibilita.md`) |
| Minimizzazione | Lo snapshot non contiene contatti, note libere o link video |
| Destinatari | Coordinatori; responsabili tecnici |
| Conservazione | Snapshot e input: 90 giorni dopo pubblicazione o scarto (proposta `solver_snapshots`), poi si conservano hash e statistiche |

### TR-04 — Calendario operativo e modifiche

| Campo | Contenuto |
|---|---|
| Finalità | Pubblicare e gestire lezioni (serie, spostamenti, cancellazioni, conflitti successivi) e prenotazioni di spazi e risorse |
| Base giuridica (proposta) | Art. 6.1.b |
| Interessati | Studenti, tutor; genitori come destinatari delle informazioni |
| Categorie di dati | Lezioni con materia, tutor, partecipanti, modalità, spazio, orari, versione e stato; prenotazioni; motivi delle modifiche; storico (`CalendarAudit`); pratiche di conflitto e richieste di cambio |
| Destinatari | Centro; tutor per le lezioni assegnate; genitori e studenti per le proprie lezioni (mai i nomi degli altri partecipanti, GAP-F05) |
| Conservazione | Anno didattico + periodo da approvare (D09 `calendar_attendance`) |
| Misure specifiche | Constraint DB contro collisioni; pubblicazione atomica e idempotente; storico non cancellabile dal ruolo applicativo |

### TR-05 — Presenze, assenze e recuperi

| Campo | Contenuto |
|---|---|
| Finalità | Registrare presenze per partecipante, gestire assenze e obblighi di recupero; rendicontare al genitore il servizio erogato |
| Base giuridica (proposta) | Art. 6.1.b |
| Interessati | Studenti, tutor |
| Categorie di dati | Esito di presenza per lezione e partecipante; motivo sintetico di assenza **senza dettagli sanitari**; correzioni amministrative con autore e motivo |
| Divieti | Nessun uso per profilazione o valutazione; il motivo dell'assenza non deve contenere diagnosi (avviso nell'interfaccia) |
| Conservazione | Come TR-04; per eventuali contestazioni sul corrispettivo valutare con il consulente anche l'art. 2955 n. 1 c.c. (prescrizione di un anno per la retribuzione delle lezioni) e l'art. 2946 c.c. (ordinaria decennale) [DA VALUTARE] |

### TR-06 — Percorsi parentali (solo se confermati in D01)

| Campo | Contenuto |
|---|---|
| Finalità | Organizzare percorsi di programma completo per studenti in istruzione parentale: curriculum interno, coorti, sottogruppi, monte minuti |
| Base giuridica (proposta) | Art. 6.1.b. Gli eventuali adempimenti verso la scuola o l'amministrazione restano a carico della famiglia: il sistema non produce certificazioni |
| Categorie di dati | Iscrizione al percorso con periodo, sottogruppi, blocchi curricolari e obiettivi didattici sintetici; audit del percorso (`PathAuditEvent`) |
| Avvertenza | Gli obiettivi didattici non devono contenere valutazioni individuali o informazioni su bisogni educativi speciali |
| Conservazione | Durata del percorso + periodo da approvare |

### TR-07 — Account, autenticazione e portali

| Campo | Contenuto |
|---|---|
| Finalità | Consentire l'accesso individuale a centro, tutor, genitori e studenti con ambito limitato; inviti monouso; reset password; MFA; riconferma delle deleghe alla maggiore età |
| Base giuridica (proposta) | Art. 6.1.b; per l'account dello studente minorenne art. 6.1.b con l'accordo del genitore (D07): non è un trattamento basato sul consenso del minore (art. 8 GDPR e art. 2-quinquies Codice non applicabili in quanto tali) |
| Interessati | Tutti gli utenti |
| Categorie di dati | Email normalizzata, hash della password (Argon2id), fattori MFA (segreto TOTP, hash dei codici di recupero), ruoli con validità, sessioni, hash dei token di invito e reset, data di presa visione delle informative [DA IMPLEMENTARE: versione accettata] |
| Conservazione | Account attivo per la durata del rapporto; revoca immediata; minimizzazione a 30–90 giorni; inviti/token fino a scadenza o uso (`invitations`, default TTL 72 h) |
| Misure specifiche | Risposte non enumeranti, rate limit per IP e identità, sessioni revocabili lato server |

### TR-08 — Notifiche transazionali

| Campo | Contenuto |
|---|---|
| Finalità | Comunicare pubblicazioni, variazioni, cancellazioni, recuperi, inviti e reset |
| Base giuridica (proposta) | Art. 6.1.b. **Nessuna comunicazione promozionale**: richiederebbe consenso (art. 130 Codice) e resta fuori perimetro |
| Interessati | Genitori, studenti con account, tutor, staff |
| Categorie di dati | Indirizzo email, tipo di evento, data/ora e materia della lezione; esito della consegna; nessun elenco dei membri del gruppo; link video solo tramite endpoint autorizzato a scadenza |
| Destinatari | Provider email transazionale (responsabile art. 28) |
| Conservazione | Delivery 90 giorni con contatori aggregati (`notification_deliveries`); log del provider secondo contratto [DA COMPILARE] |

### TR-09 — Sicurezza, audit e log

| Campo | Contenuto |
|---|---|
| Finalità | Proteggere il sistema, ricostruire chi ha fatto cosa, prevenire abusi, rispondere a incidenti |
| Base giuridica (proposta) | Art. 6.1.f (legittimo interesse alla sicurezza) e art. 32; bilanciamento documentato nella DPIA (§3.4) |
| Interessati | Tutti gli utenti |
| Categorie di dati | Attore (ID/pseudonimo), azione, oggetto, motivo, versione, esito, correlation ID, IP e user agent per gli eventi di sicurezza [DA CONFERMARE], tentativi di login |
| Dati vietati nei log | Password, token, cookie, URL video, corpo delle richieste, note sensibili (redazione automatica, GAP-I07) |
| Destinatari | Amministratori designati (accesso tracciato a sua volta); error tracking/monitoraggio (responsabile art. 28, hosting UE) |
| Conservazione | Log diagnostici 30 giorni (`diagnostic_logs`); audit 12–24 mesi da approvare, poi minimizzazione (`audit_events`) |
| Divieti | Uso dell'audit per valutare il personale (doc. 15) |

### TR-10 — Backup e ripristino

| Campo | Contenuto |
|---|---|
| Finalità | Continuità operativa e integrità dei dati |
| Base giuridica | Stessa base del dato d'origine, con art. 32 |
| Categorie di dati | Copia integrale del database; export logici di controllo cifrati |
| Destinatari | Fornitore del DB gestito; operations |
| Conservazione | PITR 7–35 giorni (D09 `backups_pitr`); export logici 30–90 giorni su storage separato con versioning e blocco della cancellazione (`logical_exports`) |
| Misure specifiche | Dopo ogni restore: riconciliazione di revoche, cancellazioni e outbox tramite ledger esterno (`privacy_reconcile`), nessun vecchio invio automatico (T32) |

### TR-11 — Gestione dei diritti degli interessati ed export

| Campo | Contenuto |
|---|---|
| Finalità | Dare seguito alle richieste ex artt. 15–22 e documentarne l'esito |
| Base giuridica | Art. 6.1.c (obbligo legale: artt. 12–22 GDPR) |
| Categorie di dati | Registro delle richieste senza FK verso l'interessato, con pseudonimo, tipo, scadenze, esito e motivazione (`PrivacyRequest`); export protetti con audience nominativa e scadenza (`ProtectedExport`) |
| Conservazione | Registro: durata da approvare (`privacy_requests`); file export cancellato al download o alla scadenza (default 24 h) |
| Procedura | `13-procedura-diritti-interessati.md` |

### TR-12 — Gestione delle violazioni di dati

| Campo | Contenuto |
|---|---|
| Finalità | Documentare e gestire le violazioni (art. 33.5) e le notifiche |
| Base giuridica | Art. 6.1.c (artt. 33–34) |
| Categorie di dati | Descrizione dell'evento, categorie e numero di interessati coinvolti, valutazione, notifiche |
| Conservazione | [DA COMPILARE] — suggerito: almeno 5 anni per responsabilizzazione, da approvare |
| Procedura | `14-procedura-data-breach.md` |

## 4. Registro del responsabile (art. 30.2)

Il fornitore di sviluppo e manutenzione, se accede a dati reali (pilota, assistenza, restore), è responsabile del
trattamento e tiene un proprio registro ex art. 30.2. Il contratto art. 28 (`08-accordo-art28-modello.md`) ne richiede
l'esistenza. [DA COMPILARE: estremi del registro del fornitore].

## 5. Storico delle versioni

| Versione | Data | Autore | Modifica |
|---|---|---|---|
| 0.1 | 2026-10-02 | Team di progetto | Prima bozza tecnica da revisionare |
| [DA COMPILARE] | | Titolare | Approvazione |

Firma del titolare: ______________________  Data: ____________
