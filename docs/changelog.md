# v0.10 — videolezioni automatiche (Jitsi Meet) e aule creabili
- **Corretto: gestionale bianco dopo l'installazione di Jitsi.** Lo stack Jitsi aveva un servizio `web` sulla rete condivisa `dokploy-network`; il proxy del gestionale risolveva `web` anche su quel container, le API rispondevano con la pagina HTML di Jitsi e l'app cadeva (`roles` undefined) restando sullo skeleton. Ora i servizi Jitsi hanno il prefisso `jitsi-` (solo `jitsi-web` sulla rete condivisa) e nginx usa l'alias privato `ripetizioni-web`. Il client segnala una risposta HTML dell'API come errore («Server non raggiungibile» con «Riprova») invece di cadere. Tolti `interest-cohort` dalla Permissions-Policy (non più riconosciuto dai browser) e lo stile inline dello sprite delle icone (bloccato dalla CSP). Test `test_no_service_name_collision_on_shared_network`.
- **Corretto «Nuova aula o canale» (405 Method Not Allowed)**: `/api/v1/resources/` era in sola lettura. Ora il centro crea (`POST`) e modifica/disattiva (`PATCH`, `expected_version` facoltativa) aule e canali; nessuna eliminazione. Validazione leggibile: aula con capienza ≥ 1, canale senza capienza; nome duplicato → errore chiaro. In Configurazione → Aule: «Modifica» e «Disattiva/Riattiva».
- **Stanza video automatica per ogni lezione online** su Jitsi Meet self-hosted (`VIDEO_PROVIDER=jitsi`): nome stanza non indovinabile e stabile (HMAC dell'id lezione), ingresso con JWT firmato valido solo per quella stanza e dalla finestra di apertura a fine lezione + `VIDEO_GRACE_MINUTES`. Tutor e centro moderatori; nessuna email nel token; registrazione, dirette e trascrizioni disattivate. I `MeetingLink` manuali hanno la precedenza.
- **Videolezione integrata nel gestionale**: «Entra nella lezione» apre la stanza a schermo intero senza pagina intermedia e con il nome già impostato (o in una nuova scheda con `VIDEO_EMBED=0`).
- **Presenze precompilate**: mentre la stanza è aperta il client invia un segnale al minuto (`POST /occurrences/<id>/meeting/presence`); in «Presenze e conclusione» chi non è mai entrato è proposto «Assente», con i minuti per studente. Il tutor conferma sempre. Migrazione `communications.0003_meeting_presence`.
- Infrastruttura: `compose.jitsi.yaml`, `infra/env/jitsi.env.example`, runbook `docs/runbooks/08-videolezioni.md`. Il proxy consente `frame-src` e delega camera/microfono/schermo solo a `VIDEO_ORIGIN`; senza, restano bloccati come prima.
- **Tema Lumen per Jitsi** (`infra/jitsi`): palette scura Lumen tramite dynamic branding, carattere Bricolage Grotesque, logo del gestionale, barra strumenti a pillola, comandi ridotti, nome non modificabile, interfaccia in italiano. La cornice della videolezione nel gestionale usa gli stessi token (tema scuro forzato). Test `tests/test_jitsi_theme.py`.
- **Cornice della videolezione ridisegnata**: una sola intestazione (logo, materia, stato «Termina tra N min» che diventa ambra negli ultimi 5 minuti, nome, ruolo, barra di avanzamento della lezione); Jitsi integrato riceve `embed_url` e non ripete materia, timer e logo. Uscita con conferma in un riquadro Lumen (Esc la apre e la chiude) al posto della finestra del browser. Icone del set Lumen, nessuna emoji. Animazioni a molla in ingresso e uscita, video in dissolvenza al collegamento, attesa animata con suggerimento se il collegamento è lento; tutto disattivato con «riduci movimento».
- Contratto OpenAPI e tipi aggiornati. Test `tests/test_video_lessons.py`.

# v0.9.11 — un solo calendario pubblico per mese, rettifiche in bozza
- **Calendario pubblico unico per mese**: alla pubblicazione le lezioni di una bozza (mensile o di una richiesta) confluiscono nel calendario pubblico del mese (`merge_public`, piano di origine → `MERGED`). La migrazione `scheduling.0007_month_corrections` unisce i calendari già pubblicati dello stesso mese. Famiglie e tutor vedono sempre e solo il calendario pubblicato.
- **Ogni modifica va in bozza** (`CalendarCorrection`): spostamento (trascinamento, Alt+frecce, «Sposta»), cambio durata, cancellazione, scambio, sostituto e cambio modalità di una singola lezione diventano rettifiche del mese, validate subito contro il calendario e le altre rettifiche in bozza (una sola rettifica aperta per lezione). Anche «Conferma e completa» di una richiesta mette le lezioni nella bozza del mese, salvo «Pubblica subito nel calendario del mese».
- **Pubblica subito / Pubblica le rettifiche** (solo gestore del centro): in ogni finestra c'è «Pubblica subito la rettifica»; la barra del mese in Agenda pubblica tutte le rettifiche del mese in ordine (quelle non più valide restano «Non applicate» con il motivo), oppure una alla volta, o le scarta.
- **Agenda separata per mesi**: barra del mese con mese precedente/successivo, stato (Pubblicato / Bozza), elenco delle rettifiche e della bozza mensile; i giorni della settimana fuori dal mese sono attenuati. Nella griglia le rettifiche in bozza si vedono con bordo tratteggiato ambra al nuovo orario, la lezione d'origine attenuata, le cancellazioni barrate; un clic apre la rettifica (Scarta / Pubblica subito). Il pannello «Proposte» mostra solo le proposte settimanali del motore.
- **Correzioni visive**: indicatore della barra laterale ora sempre sulla sezione attiva; intestazione «Tutor» della griglia allineata; linea dei passi in Pianificazione non più sovrapposta ai testi; niente spazio spurio prima della virgola nel suggerimento «vai a …», che ora indica anche il giorno precedente quando non ci sono lezioni dopo.
- API: `GET /planner/calendar-months/<AAAA-MM>`, `POST …/<AAAA-MM>/publish`, `POST /planner/corrections` (`op`: reschedule, cancel, modify, swap; `publish_now`), `POST /planner/corrections/<id>/publish|discard`; `publish_now` su `…/planning/complete`. Contratto OpenAPI e tipi aggiornati. Test `tests/test_month_corrections_v0911.py`.
- **Sostituto, modalità e durata sulle lezioni mensili**: prima davano errore 500 («Sostituisci il tutor») o venivano rifiutati dal database; ora usano i vincoli del pianificatore mensile e la lezione viene ri-agganciata al suo snapshot (`ensure_anchor`). In Agenda si vedono anche le lezioni delle richieste ancora «in verifica» (bordo puntinato), che occupano già l'orario.
- Restano immediati (non passano dalla bozza): modifiche «da questa in poi» sulle serie, annullamento con recupero, presenze e conclusione.

# v0.9.10 — il motore lavora sul mese; nessun errore 500 alla conferma
- **Un mese alla volta**: il ricalcolo automatico di una richiesta colloca solo le lezioni del primo mese utile (mai l'intero anno). Nella verifica si vede il «Mese in verifica» e, per le ricorrenti, si può scegliere un altro mese del periodo (`POST …/planning/rerun` con `month`: `AAAA-MM`). «Aggiungi a mano» e «Sposta» restano dentro il mese (`OUT_OF_MONTH`); i mesi successivi li pianifica il calendario mensile.
- **Errore 500 su «Conferma e completa»**: le lezioni in presenza potevano ricevere un'aula con meno posti dei partecipanti (o nessuna aula), che il database rifiuta alla pubblicazione (`Space capacity exceeded`). Ora motore e ricerca orari assegnano solo aule libere con posti sufficienti; le lezioni senza aula adatta restano «non collocate»; la verifica segnala come conflitto le lezioni senza aula valida; un rifiuto del database alla pubblicazione diventa `409 PLAN_INVALID` con messaggio, mai 500.
- Test aggiunti in `tests/test_request_review_v099.py`, verificati anche su PostgreSQL reale (trigger del calendario).
- **Agenda**: tolto il pannello sfocato «Nessuna lezione in questo giorno» che copriva la griglia; ora c'è solo una riga di suggerimento sopra il calendario e la griglia resta visibile per creare lezioni trascinando.
- **Niente lezioni a centro chiuso**: trascinando sull'agenda la zona «Centro chiuso» (fuori orario, chiusure) o un impegno del tutor si colora di rosso e la lezione non si crea; il server rifiuta anche una lezione singola a orario fisso fuori dall'apertura o durante una chiusura (`fixed_time`: «Il centro è chiuso in quell'orario»).

# v0.9.9 — verifica delle lezioni calcolate e lezioni di gruppo
- **Finestra unica per le lezioni**: rimossa la finestra duplicata «Nuova lezione»; «Nuova lezione», tasto N e trascinamento in agenda aprono il modulo originale delle richieste, precompilato (singola, giorno, ora, durata, tutor obbligatorio).
- **Calcolo automatico**: alla creazione di una richiesta del centro, all'approvazione e alla modifica di una richiesta approvata il motore calcola subito le lezioni della sola richiesta (`autoplan.plan_request`, bozza legata alla richiesta, migrazioni `education.0009`, `scheduling.0006`). Le lezioni in verifica occupano già gli orari per gli altri calcoli.
- **Fase di verifica prima del completamento**: la richiesta passa a «Da verificare»; la finestra di verifica elenca le lezioni per mese e le incongruenze (conflitti, lezioni mancanti con motivo, sforamenti da confermare) con Sposta, Togli, Aggiungi a mano, Ricalcola. «Conferma e completa» pubblica le lezioni; bloccata se restano conflitti, le mancanti si accettano esplicitamente.
- **Lezioni di gruppo** (centro): 2–8 studenti, nome del gruppo, partecipanti in `RequestParticipant`; elenco e motore considerano tutti i partecipanti.
- **Correzioni**: motivo di non collocazione calcolato per settimana (non più «chiuso» fuorviante); le bozze mensili non toccano quelle delle richieste.
- API: `GET /teaching-requests/<id>/planning`, `POST …/planning/rerun|options|lessons|complete`, `POST /planner/request-lessons/<id>/move|remove`. Test `tests/test_request_review_v099.py`.

# v0.9.7 — pianificatore mensile semplificato
- **Tre ingressi soltanto**: impegni dello studente (inseriti dal genitore o dal centro), orari di apertura e ferie/chiusure (gestore) e impegni dei tutor. Nuovi modelli `OpeningHours`, `Commitment`, `AutoPlan`, `AutoPlanLesson`, `AutoPlanConfirmation` (migrazione `scheduling.0005`).
- **Motore mensile** (`apps/scheduling/autoplan.py`, CP-SAT): orari del centro e chiusure sempre rigidi; impegni di studenti e tutor rispettati, con sforamento massimo di 30 minuti (`AUTOPLAN_TOLERANCE_MINUTES`) penalizzato e solo con conferma; stesso tutor per tutta la richiesta, stesso giorno/ora ogni settimana quando possibile, al massimo una lezione al giorno per richiesta, aule in presenza, giornate compatte (meno buchi). Le lezioni non collocabili riportano il motivo (chiuso, studente/tutor occupato, aule piene, tutor mancante…).
- **Pianificazione in tre passi** (Calendario › Pianificazione): verifica dei dati con checklist, genera il mese, rivedi la bozza (calendario mensile, filtro per persona, dettaglio lezione, «Togli dalla bozza») e pubblica. Dopo la pubblicazione si vede il calendario pubblicato e lo stato delle conferme; rigenerare un mese pubblicato aggiunge solo le lezioni mancanti.
- **Conferme degli sforamenti**: alla pubblicazione le lezioni che sforano un impegno restano «in attesa»; genitore/tutor ricevono email e notifica (`autoplan.confirmation_requested`) e rispondono da Lezioni › Da confermare («Va bene» / «Non va bene»). Con tutte le conferme la lezione entra in calendario; un rifiuto libera l'orario.
- **Nuove schermate**: Centro › Orari e chiusure, Persone › Impegni (centro) e Disponibilità › Impegni (portale, giorni multipli in un colpo, impegni occasionali), avviso in home per le lezioni da confermare, azione rapida «Nuovo impegno».
- **Configurazioni nascoste**: il motore settimanale, le disponibilità dettagliate, finestre, regole, eccezioni, dichiarazioni e le impostazioni avanzate restano solo per l'amministrazione tecnica; per il gestore Configurazione diventa «Anno e aule».
- API: `/planner/setup`, `/planner/opening-hours`, `/planner/closures`, `/commitments`, `/planner/plans` (+ `publish`, `discard`), `/planner/lessons/<id>/remove`, `/planner/confirmations` (+ `answer`); contratto OpenAPI e tipi aggiornati. Test `tests/test_autoplan_v097.py`.

# v0.9.6 — richieste singole o ricorrenti e pagina Materie
- **Due tipi di richiesta** (migrazioni `education.0007`–`0008`): *singola* — in un giorno (con orario preciso la lezione si piazza lì, senza orario il calcolo cerca l'ora in quel giorno) oppure da collocare in una settimana — e *ricorrente* — solo il numero di lezioni a settimana (1–5) dal giorno di inizio alla data di fine (di norma la fine dell'anno scolastico), sempre con lo stesso tutor (vincolo rigido). Le richieste esistenti e quelle derivate dai percorsi parentali compaiono come ricorrenti.
- **Modulo guidato** in passi numerati (tipo, studente e materia, quando, lezione e tutor, pianificazione) con riepilogo in linguaggio naturale prima dell'invio; stesso modulo per centro e famiglie. Le richieste del centro sono già approvate, quelle dal portale famiglie restano da approvare.
- **Approvazione con tutor**: una richiesta ricorrente inviata dalla famiglia senza tutor si approva solo scegliendolo («Scegli tutor e approva»); `POST /teaching-requests/<id>/approve/` accetta `tutor_id` (errore `TUTOR_REQUIRED` altrimenti).
- **Elenco richieste**: colonna «Quando e con chi», filtri per stato (da approvare, in corso, chiuse) e per tipo (singole, ricorrenti); il centro può modificare anche le richieste in attesa. La home dei genitori ha «Chiedi delle lezioni».
- **Motore**: una richiesta singola genera una sola unità (finestra pari alla durata se a orario fisso); la regola delle settimane parziali vale solo per le richieste settimanali storiche.
- **Pagina Materie** (Didattica › Materie): tutor competenti con livelli e modalità, richieste in corso e da approvare, percorsi; creazione, rinomina, descrizione, archiviazione/riattivazione (le archiviate non si propongono per nuove richieste) ed eliminazione delle sole materie mai usate (`PATCH`/`DELETE /subjects/<id>/`, `GET /subjects/overview/`).

# v0.9.1 — frontend di produzione: pulizia debug e nuova navigazione
- Navigazione per aree: il centro passa da 15 voci di menu a 6 (Panoramica, Calendario, Da gestire, Persone, Didattica, Centro); le schermate affini sono schede in cima alla pagina. I portali passano a 5 aree (Panoramica, Lezioni, Disponibilità, Studio, I miei dati). Gli indirizzi `#/…` esistenti restano validi.
- Panoramica del centro riorganizzata: statistiche, contatori «Da gestire» (richieste di cambio, recuperi, conflitti, disponibilità in bozza, invii), prossime lezioni e stato della pianificazione con collegamento diretto a Configurazione.
- Rimossi i dettagli di debug in produzione: badge «Sperimentale / dati sintetici / v0.8», riferimenti a PostgreSQL/SQLite, README, decisioni D0x e G1, hash, ID, revisioni, codici HTTP e JSON grezzi. I «Dettagli tecnici» compaiono solo in sviluppo o con `VITE_TECH_ADMIN=1`; etichetta d'ambiente facoltativa con `VITE_ENV_LABEL`.
- «Configurazione di prova» tolta da Genera orario: le categorie non coperte altrove sono in Configurazione › Avanzate; la modifica JSON è riservata all'amministrazione tecnica.
- Agenda: il riquadro «nessuna lezione» non copre più l'intestazione degli orari.
- Dashboard diverse per ruolo: gestore (code del centro e pianificazione), tutor (lezioni di oggi, presenze, orari da confermare, carico), genitore (schede dei figli, conferme e deleghe, lezioni dei figli), studente (prossima lezione, settimana, disponibilità, cambi). Corrette le barre del carico tutor, che non si riempivano.

# v0.8 — solver: contratto 0.5, sei settimane e vettore completo
- Contratto `0.5` (0.4 accettato e archiviato): orizzonte fino a 6 settimane, limiti 720 unità / 150.000 candidati configurabili, budget fino a 30 s che parte dopo la costruzione del modello.
- Vettore lessicografico P0, P1, P2, F, C, R, P, G con valutazione indipendente degli obiettivi; ordine ed equità marcati da approvare.
- Serie ricorrenti, vincoli familiari, sequenze curricolari, iscrizioni, preferenze, buffer studente, mezzanotte locale e studente online dalla sede.
- Ripianificazione locale autorizzata con audit, proposta di estensione del perimetro, diagnostica con ipotesi non prenotabili e analisi dei conflitti.
- Modello CP-SAT ottimizzato (pool di spazi, clique, simmetrie, warm start), comando `benchmark_solver` e fixture da 720 unità; `LessonSeries` e nuovi campi PlanningPolicy.
- Test: contratto 0.5, Celery (lease, tentativi, soft limit) e proprietà con hypothesis; test demo non più dipendente dal tempo macchina.

# v0.7 — limiti v0.6 risolti e primi portali
- Spostamento lezioni: il rifiuto del validatore riporta i motivi puntuali (`violations`: disponibilità tutor/studenti, centro chiuso, risorse, sovrapposizioni, pause, carichi…), solo quelli introdotti dallo spostamento.
- Nuovo `GET /api/v1/occurrences/<id>/reschedule-options/?date=` (centro, sola lettura): esito del validatore per ogni inizio a 15'. La modale «Sposta» marca gli orari non validi sulla ruota, segnala i giorni pieni e spiega il motivo in italiano prima del salvataggio.
- Seed dimostrativo più realistico: disponibilità e aperture lunedì, mercoledì e giovedì 10–16 (`--days`, default `0,2,3`; i test usano `--days 0`). Il collaudo non crea più disponibilità via API.
- Portali sperimentali per tutor, tutori legali e studenti: `GET /api/v1/my/lessons` con perimetro per ruolo e nomi degli altri partecipanti nascosti; sezione «La mia settimana» e prossime lezioni in Panoramica; comando `seed_portal_demo` con account sintetici senza credenziali.
- Configurazione di prova con moduli strutturati per le 9 categorie (nomi al posto degli UUID, giorni, orari, date, scelte); JSON solo come modalità avanzata e sincronizzato. Elenco con riepiloghi leggibili.
- Laboratorio: riepilogo dello scenario (studenti, tutor, spazi, richieste) con inclusione/esclusione delle richieste prima del calcolo.
- Accessibilità: audit axe-core automatico (WCAG 2.0/2.1/2.2 A–AA) su tutte le schermate, modali e portali, chiaro/scuro, 1440 e 390; corretti i contrasti dei token (testo terziario, riempimenti blu/viola).
- Collaudo E2E esteso: rifiuto con motivi, opzioni server, trascinamento col mouse fino al salvataggio, moduli, laboratorio, tre ruoli non centro.

# v0.6 — interfaccia Lumen
- Guscio ricostruito sullo standard Lumen v5.2: rail con indicatore, barra superiore, barra a schede su mobile, palette comandi (Ctrl/⌘ K, «/»), tema chiaro/scuro con transizione, notifiche, menu account, stato di navigazione nell'URL.
- Tutte le schermate migrate: Panoramica, Agenda, Studenti, Disponibilità, Richieste, Percorsi, Proposte (ex Dati → proposta), Laboratorio (ex Simulazione), Decisioni, Impostazioni.
- Agenda del centro come griglia tutor × orari a quarti d'ora con striscia dei giorni, celle non disponibili, trascinamento (mouse, tocco prolungato, Alt + frecce), scheda lezione, sposta con ruota oraria e controllo conflitti, «Annulla» dello spostamento, cancellazione irreversibile con motivo.
- Pubblicazione delle proposte dall'Agenda in un modal con riepilogo, accettazione esplicita delle richieste non collocate, motivo e conferma dati sintetici; stessa chiave idempotente su «Riprova».
- Eliminati `window.prompt`, `<select>`, `<input type="date">` e orari ISO digitati: motivi in modal, calendario e ruote personalizzati, scelte a pillola e controlli segmentati.
- Codici interni (stati, reason code, ID, hash, revisioni) tradotti in italiano; i valori tecnici restano in «Dettagli tecnici» richiudibili.
- Livelli unici (pop, sheet, modal) con Esc, trappola del focus e protezione delle modifiche non salvate; toast con pausa al passaggio e azione.
- Nessuna modifica al backend, alle API o ai contratti. Collaudo E2E su PostgreSQL 17 con worker separato; prove visive in `docs/evidence/v0.6-*`.

# v0.5 — calendario sperimentale del centro
- Publication, lezioni, partecipanti e prenotazioni; eventi/audit minimali nello stesso commit.
- PostgreSQL GiST anti-overlap e trigger differibili di completezza, coerenza e occupazioni; enum DB e unicità della domanda attiva.
- Pubblicazione idempotente con revisione/versione, accettazione partial esatta e validatore indipendente su dati correnti.
- Generazione che mantiene lezioni già pubblicate; cancellazione con domanda canonica ancora da gestire, nessun recupero automatico.
- Spostamento futuro stessa settimana, risorse/tutor invariati, rollback e versioni attese.
- Agenda/revisione proposte del solo centro; flag esplicito e PostgreSQL reale richiesti, produzione/email disabilitate.
- Verifiche PostgreSQL 17 UTF8, connessioni concorrenti, trigger/corruzioni e smoke UI; nessun gate o programma scolastico certificato.

# v0.4 — database e job sperimentali
- Configurazioni persistenti di competenze, limiti tutor, aperture/chiusure, disponibilità approvate ed eccezioni.
- Revisione applicativa, unità settimanali canoniche, snapshot minimizzato immutabile con hash/metadati, proposte readonly.
- Run Celery separati, dispatcher post-commit, replay, cancellazione, lease/reconciler e protezione dagli input obsoleti.
- UI Dati → proposta e console di configurazione con versione attesa; approvazione/revoca regole.
- Contratti DTO 0.4: settimana locale e horizon_minutes (DST 167/169 ore).
- Nessuna pubblicazione, booking, email, attestazione scolastica o gate dichiarato superato.

# Changelog

## v0.9.5 — Famiglie rifatte: si parte dal genitore, accesso con QR

- **Una sola sezione: Persone › Famiglie.** La scheda «Studenti» del centro non c’è più: i figli si aggiungono e si gestiscono dentro la loro famiglia. I vecchi link (Agenda, Percorsi, ricerca rapida) aprono la scheda del figlio in Famiglie. I portali di genitori e tutor non cambiano.
- **Elenco a schede:** ogni famiglia mostra a colpo d’occhio genitori/tutori (con lo stato dell’accesso) e figli (con la classe), un bollino con la cosa più urgente (manca un genitore, da verificare, invito scaduto, nessun figlio, tutto attivo), ricerca per famiglia, figlio o genitore e filtri «Accesso da completare» / «Senza figli». Si apre la pagina della famiglia oppure direttamente la scheda del figlio o del genitore.
- **Iscrizione guidata in tre passi:** 1) genitore o tutore (nome, email, telefono, relazione, permessi, verifica della relazione); 2) nome della famiglia (proposto dal cognome) e figli, facoltativi; 3) accesso: l’invito parte via email e, se il genitore è presente, il pulsante **«Mostra QR code»** apre un codice da inquadrare con il telefono per scegliere la password ed entrare subito.
- **Pagina della famiglia:** «Prossimo passo» in evidenza (verifica, nuovo invito, QR, aggiungi figli), colonne «Genitori e tutori» (stato, contatti, figli visibili, permessi, Mostra QR / Invia di nuovo / Modifica / Rimuovi) e «Figli» (disponibilità, richieste, chi lo segue; scheda con disponibilità, richieste di lezioni e scorciatoie).
- **Backend:** invito di famiglia (`Invitation.family`) e nuovo modello `FamilyGuardian`: accettando l’invito il genitore riceve una delega verificata su tutti i figli attivi, e su quelli aggiunti dopo; la rimozione revoca subito invito e deleghe; i permessi modificati valgono per tutte le deleghe della famiglia. Nuove API `POST registry/families/onboard` (famiglia + genitore + figli in un’unica transazione), `POST registry/families/<id>/guardians`, `PATCH/POST registry/family-guardians/<id>[/remove|/reinvite]`, `GET registry/families?expand=1` con figli e genitori.
- **QR sicuro:** `POST registry/invitations/<id>/qr` emette un token separato e breve (15 minuti, `IDENTITY_INVITATION_QR_TTL_SECONDS`), solo per inviti già verificati, senza toccare né invalidare l’email; mai salvato in chiaro né nell’audit; risposta `no-store`. Accettato l’invito, entrambi i token smettono di valere.
- **Accesso immediato:** chi accetta un invito scegliendo la password entra subito nella sua pagina (gli account del centro passano comunque dalla verifica in due passaggi).
- Migrazioni `identity/0004_family_guardians`, `privacy/0006_family_guardians`. Nuova dipendenza frontend `qrcode-generator` (MIT, senza dipendenze). Test: `tests/test_family_onboarding_v095.py` (6) e `frontend/tests/families.test.tsx` (4).

## v0.9.4 — Pianificazione orari per il gestore, motore pronto per la produzione

- **Motore attivo in produzione**: le esecuzioni dipendono solo da `FEATURE_PLANNING` (attivo per default in `settings_production`), non più da `DEBUG`. Prima, con `DEBUG=0`, ogni calcolo rispondeva `FEATURE_DISABLED`.
- **Richieste delle famiglie**: i genitori inviano richieste di lezioni per i figli (materia, modalità, durata, lezioni a settimana, periodo, tutor, note). Restano «Da approvare» finché il centro non le approva o rifiuta; il motore usa solo le richieste `APPROVED`. Priorità e obbligatorietà le decide il centro. API: `POST/PATCH /teaching-requests/`, `…/approve/`, `…/reject/`, `…/withdraw/`, `GET /teaching-requests/options/`.
- **Tutor per richiesta**: «Qualsiasi» (tutor competenti), «Preferito» (vincolo morbido: termine P dell'obiettivo, peso 100 per lezione, valutato anche dal valutatore indipendente) o «Obbligatorio» (vincolo duro: solo quel tutor; se non competente la verifica blocca con `REQUIRED_TUTOR_UNAVAILABLE`, nessun rilassamento). Contratto 0.5: campo unità `preferred_tutors` ⊆ `allowed_tutors`.
- **Calcolo accurato (notturno)**: profilo `THOROUGH` con budget `PLANNING_THOROUGH_BUDGET_SECONDS` (default 6 h, max 12 h), più processi CP-SAT (`PLANNING_THOROUGH_WORKERS`), presolve completo, limiti Celery e lease scalati sul budget, battito e annullamento anche durante la ricerca, coda dedicata `solver_long` (servizio `worker-solver-long`). Il calcolo rapido resta ≤ 30 s.
- **Nuova pagina Calendario › Pianificazione**, un percorso guidato: in alto un unico «Prossimo passo» con una sola azione (correggere i blocchi, approvare, attendere il calcolo, rivedere la proposta), poi tre passi numerati **Rivedi → Calcola → Pubblica**. *Rivedi* raggruppa per urgenza («Da correggere», «Da decidere» con Approva/Rifiuta/Modifica, «Da tenere d’occhio») e mostra i vincoli della settimana a schede (Famiglie con disponibilità e margine di ogni richiesta, Tutor con carico possibile e vincoli obbligatorio/preferito, Orari del centro su linea del tempo con chiusure). *Calcola* spiega il problema in una frase, sceglie Rapido/Accurato e la copertura e segue i calcoli della settimana; *Pubblica* mostra le lezioni collocate e quelle senza posto e porta all’Agenda. Colori pieni, avatar con iniziali centrate, layout mobile con azioni a capo.
- Richieste didattiche: stato, tutor, approvazione e «Vincoli» per il centro; «Chiedi delle lezioni» e «Ritira» per i genitori. La panoramica del gestore segnala le richieste da approvare.
- Corretto `month_weeks` (calendario): `ZONE` non definita.

## v0.9.3 — Dashboard quotidiane essenziali

- Panoramiche senza statistiche e senza dati ripetuti: in testata solo saluto e data; «Da fare adesso» compare solo quando c'è un'azione.
- Gestore: nuova pagina **Statistiche** (Panoramica › Statistiche) con lezioni del mese, ore per tutor, numeri del centro e code operative.
- Tutor: «Il tuo mese» con grafico ad anello (svolte, da svolgere, annullate), ricavato finora al centro e statistiche a destra.
- Studente: stessa scheda delle famiglie (prossima lezione con dettagli e impegni successivi).
- Stile uniforme: avvisi in un unico riquadro, calendario dei tutor più leggero, spaziature allineate allo standard Lumen.

## v0.9.2 — Dashboard per ruolo, seconda versione

- **Gestore**: nuovo widget «Oggi in calendario» con una riga per tutor sulla linea del tempo (navigazione per giorno, linea dell'ora attuale, clic sulla lezione → Agenda). La gestione completa resta nell'Agenda. Il gestore che è anche tutor vede «Le tue lezioni di oggi» e il pulsante «Passa alla vista tutor».
- **Backend**: `/me` espone `own_tutor_id` (scheda tutor collegata all'account se ha il ruolo TUTOR concesso), anche nel contesto centro.
- **Tutor**: «La tua giornata» con le lezioni di oggi espandibili (orario, luogo/aula, studenti, link «Entra nella lezione» per le online, «Registra presenze» a fine lezione); «Il tuo mese» al posto del carico settimanale: ore previste, svolte, annullate, guadagno stimato (tariffa oraria salvata sul dispositivo) e accesso a «Modifica disponibilità settimanali». Rimossi i limiti di minuti.
- **Genitore**: tolta la scheda «Da fare» (le azioni sono nella campanella); avvisi in dashboard solo quando serve un'azione (modifiche da confermare, lezioni annullate o spostate, deleghe in scadenza). Una scheda grande per figlio con colore personalizzabile, prossima lezione con tutti i dettagli, impegni successivi apribili e «Gestisci …».
- Campanella dei portali: modifiche da confermare, orari da confermare, presenze da registrare, deleghe da riconfermare, richieste in attesa.

## v0.3 — Motore di simulazione reale
- OR-Tools CP-SAT con DTO JSON chiuso e hash input, esempi sintetici e comando CLI.
- Tutor qualificati, disponibilità, risorse esclusive, capienze, blocchi, carichi, pause e transizioni.
- Strict/coverage e copertura lessicografica P0/P1/P2, senza falsa ottimalità dei livelli non provati.
- Validatore indipendente e distinzione OPTIMAL/FEASIBLE/INFEASIBLE/UNKNOWN/MODEL_INVALID/BLOCKED/VALIDATION_FAILED.
- Schermata Simulazione ed export JSON; endpoint solo centro e sviluppo, risultati mai pubblicabili.
- 139 test superati; build frontend e flusso HTTP con sei assegnazioni validate.
- Nessuna integrazione operativa o calendario transazionale dichiarato completato.

## v0.2 — Parentali come programma scolastico completo
- Chiarimento D01 recepito, senza dichiarare G1 superato.
- Percorsi per anno/livello con materie dichiarate, coorti e iscrizioni datate.
- Sottogruppi approvati per materia, membri e capienza online separata.
- Blocchi del programma con minuti, sessioni, obiettivi, modalità, priorità e obbligatorietà.
- Verifica copertura completa per materie e periodi degli iscritti, senza sovrapposizioni o doppioni gruppo/individuale.
- Derivazione atomica/versionata/idempotente delle richieste; congelamento del curriculum già derivato e rilevamento di alterazioni.
- Riepilogo familiare sul solo studente autorizzato; dati calendario/presenze non disponibili indicati come null.
- UI e API del modulo, demo sintetico opzionale, migrazioni compatibili con v0.1 e contratto subset aggiornato.
- 73 test core superati su SQLite, build frontend riuscita, prova HTTP del flusso.

## v0.1 — Fondazioni esplorative
Account/ruoli/deleghe, anagrafiche, disponibilità, registro decisioni, API/UI iniziali, Docker di sviluppo e 38 test core.
