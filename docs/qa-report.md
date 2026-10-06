# Verifica v0.7 — motivi di rifiuto, portali, moduli e accessibilità

## Prove realmente eseguite
- **Backend: 253 test superati su PostgreSQL 17.10 UTF8 reale** (244 della v0.5 + 9 nuovi: motivi puntuali del rifiuto, opzioni di spostamento in sola lettura, seed multi-giorno idempotente, perimetro di `/my/lessons` per tutor/tutore legale/studente, delega revocata, account senza ruoli, flag e intervalli). Su SQLite (default CI): 245 superati, 8 PostgreSQL-only saltati. Ruff E9/F63/F7/F82 e formattazione, `manage.py check`, nessuna migrazione mancante: `evidence/v0.7-backend-tests.txt`.
- TypeScript strict e build Vite riusciti: `evidence/v0.7-frontend-build.txt`. Contratto `contracts/openapi.yaml` 0.7.0 con i due nuovi endpoint, YAML validato.
- **Collaudo E2E Playwright/Chromium** su database ricreato da zero, `seed_planning_demo` (lun/mer/gio) e `seed_portal_demo`, worker Celery separato, Django e Vite reali, it-IT/Europe/Rome — 20 passi, 0 errori JS, 0 HTTP ≥ 400 non attese, 0 dialoghi nativi (`evidence/v0.7-e2e.json`, script `evidence/v0.7-e2e.cjs`):
  - proposta generata e 6 lezioni pubblicate su due giorni (5 e 8 ottobre) senza creare disponibilità via API;
  - spostamento rifiutato dal server con `violations` (TUTOR_AVAILABILITY, STUDENT_AVAILABILITY, SERVICE_CLOSED, RESOURCE_AVAILABILITY); opzioni server per il giorno; nella modale martedì marcato «pieno», motivo in italiano e pulsante disattivato; spostamento a mercoledì salvato e annullato;
  - **trascinamento col mouse** lungo la riga: rilascio su un orario libero → modale precompilata con lo stesso orario → salvataggio e annullamento;
  - cancellazione; apertura del venerdì creata dal **modulo strutturato** con JSON avanzato sincronizzato; elenco competenze con nomi (nessun UUID visibile) e riferimento tutor risolto;
  - Laboratorio: riepilogo dello scenario, esclusione di una richiesta, 5 lezioni collocate su 5;
  - **portali**: tutor (6 lezioni proprie), tutore legale (2 studenti delegati, 6 partecipanti altrui solo conteggiati) e studente (3 lezioni, 3 partecipanti altrui conteggiati); agenda e `/calendar/` del centro negati (403); nessun nome di studenti non visibili nella pagina.
- **Accessibilità automatica**: axe-core 4.13.0, regole WCAG 2.0/2.1/2.2 livello A e AA, su 54 pagine/stati (10 schermate del centro × chiaro/scuro × 1440/390, modale di spostamento, modulo di configurazione, Panoramica e «La mia settimana» dei tre ruoli in chiaro/scuro): **0 violazioni** finali (`evidence/v0.7-axe.json`). Corretti: contrasto del testo terziario, dei riempimenti blu/viola con testo bianco (anche in scuro), del testo nelle lezioni di gruppo, delle card cancellate e degli orari occupati della ruota.
- Nessun overflow orizzontale su 60 combinazioni (10 schermate × 3 larghezze × 2 temi) né sui portali a 1440/390. Screenshot `evidence/v0.7-*`.
- Credenziali del collaudo generate a runtime fuori dal repository e rimosse alla chiusura; i comandi seed lasciano tutte le password inutilizzabili.

## Non provato / limiti
- L'audit axe copre solo le regole automatizzabili: nessuna prova con lettori di schermo o utenti reali; tastiera verificata su ruota, Esc, palette, modali e moduli, non su ogni controllo.
- Le opzioni di spostamento sono un'anteprima: il comando rivalida comunque sotto lock. Lo spostamento mantiene tutor, spazio, durata e partecipanti.
- Portali in sola lettura: nessuna richiesta di spostamento/assenza, notifica o disponibilità del tutor dal portale; nessun UAT multi-ruolo con utenti reali.
- Test di componenti UI non ancora nel repository (collaudo e audit con script in `docs/evidence/`).
- Dati esclusivamente sintetici: l'uso con dati reali dipende dalle decisioni G1 (D01–D09), privacy/retention e messa in produzione, non da una modifica tecnica.

# Verifica v0.6 — interfaccia Lumen

## Prove realmente eseguite
- TypeScript strict (`tsc --noEmit`) e build Vite riusciti: `evidence/v0.6-frontend-build.txt`. Nessuna modifica a backend, migrazioni, API o contratti rispetto alla v0.5, quindi la suite backend v0.5 non è stata rieseguita.
- **Collaudo E2E Playwright/Chromium su PostgreSQL 17.10 UTF8** con database ricreato da zero, `seed_planning_demo`, worker Celery separato (trasporto filesystem, pool solo), Django e Vite reali, locale it-IT e fuso Europe/Rome. Tutto tramite UI: login; verifica dati e generazione della proposta; calcolo concluso dal worker; pubblicazione dall'Agenda (6 lezioni verificate via API); ruota oraria da tastiera; spostamento validato dal server; «Annulla» che ripristina l'orario originale; cancellazione con motivo; nuova disponibilità creata e approvata con motivo in modal; materia creata; guardia delle modifiche non salvate con Esc; dettaglio percorso; Laboratorio; palette comandi. Esito: `evidence/v0.6-e2e.json`, script `evidence/v0.6-e2e.cjs`.
- Durante il collaudo: **0 errori JavaScript, 0 risposte HTTP ≥ 400** (esclusa la 403 attesa di `/me` prima dell'accesso), **0 dialoghi nativi** (prompt/confirm/alert).
- **Nessun overflow orizzontale del documento** su 10 schermate × 1440/1280/390 px × chiaro/scuro (60 combinazioni). Screenshot `evidence/v0.6-*-{1440,1280,390}-{light,dark}.png`, modal di spostamento e disponibilità, confronto affiancato con il riferimento `evidence/v0.6-confronto-riferimento.png`.
- Difetti trovati e corretti durante il collaudo: crash all'apertura del modal di spostamento (stato iniziale vuoto), ruota che non accumulava pressioni rapide dei tasti, elemento solo-lettore-schermo che allargava la pagina a 390 px, pulsanti secondari senza superficie.

## Non provato / limiti
- Nessun audit WCAG formale né lettore di schermo reale; tastiera verificata su ruota, Esc, palette e modal, non su ogni controllo.
- Trascinamento con mouse/tocco implementato ma non automatizzato nel collaudo (lo spostamento è provato dal modal).
- Il backend non restituisce il motivo puntuale quando rifiuta uno spostamento: la UI mostra un messaggio generale. Lo spostamento verso un giorno è valido solo se esistono disponibilità approvate e finestre di servizio (nel collaudo create come nella v0.5).
- «Annulla» esiste solo per lo spostamento (riesegue lo spostamento inverso); la cancellazione resta irreversibile per scelta del dominio.
- Il limite API di 120 richieste/minuto per utente può essere raggiunto ricaricando molte pagine in rapida successione (osservato solo nello script di screenshot).
- Dati esclusivamente sintetici; portali famiglia/tutor/studente non migrati perché non esistono ancora.

# Verifica v0.5 — calendario sperimentale su PostgreSQL

## Prove realmente eseguite
- **244 test superati su PostgreSQL 17.10 UTF8 reale**, avviato localmente e isolato su loopback. Suite completa core, parentali, solver, job, dati e calendario; non l'intero catalogo normativo T01–T42 o approvazione dei gate.
- Binari di collaudo scaricati nel workspace con @embedded-postgres/linux-x64 17.10.0-beta.17, server PostgreSQL 17.10 effettivo. Non inclusi nell'archivio né dipendenza del prodotto. Richiesto database UTF8; individuato/corretto setup iniziale SQL_ASCII non adatto a JSON Unicode.
- Migrazioni reali PostgreSQL: btree_gist, GiST sui range semiaperti, trigger differibili, unicità domanda attiva e enum. Test SQL diretti: collisione respinta con 23P01; booking mancante, partecipante cancellato, buffer/fine occupazione alterati e identità risorsa modificata respinti con 23514.
- **Race test con due connessioni e barriere sincronizzate**: due proposte della stessa revisione producono un solo commit e uno STALE_INPUT; due cancellazioni producono una sola modifica, l'altra VERSION_CONFLICT. Nessun doppio effetto osservato nei fixture, non prova universale di concorrenza distribuita.
- Pubblicazione 6 lezioni/12 partecipanti/24 booking nello stesso commit; replay uguale risposta, body diverso conflitto, rollback fault-injected a metà batch senza lezioni/audit/eventi parziali. Stale, hash/validator, conferma sintetica, mandatory non derogabile, partial con elenco esatto e motivo testati.
- Domanda già pubblicata riconciliata come KEEP/locked senza duplicazione. Nuova indisponibilità non rimuove appuntamenti; cancella libera solo le proprie booking e preserva storia; ripianificazione della stessa unità canonica crea una nuova occorrenza soltanto dopo pubblicazione esplicita.
- Spostamento futuro stessa settimana e risorse invarianti, validazione indipendente, versioni, collisione respinta con rollback, lezioni iniziate protette. Account fresco ricontrollato sotto lock; oggetto attore obsoleto dopo revoca non può cancellare.
- API centro-only, closed payload, origine/sessione/CSRF, range obbligatorio e revisione pagine. SQLite normale e produzione disabilitano mutazioni; override solo interno a test_settings.
- Ruff E9/F63/F7/F82/formattazione, Django check e nessuna migrazione mancante; pip check senza incompatibilità. TypeScript strict e build Vite/React riusciti.
- **HTTP + UI headless locale su PostgreSQL**: login, generazione con Celery separato (trasporto filesystem, pool solo), pubblicazione di 6 lezioni, agenda, cancellazione da UI; nuova proposta crea soltanto 1 unità libera e mantiene le altre 5; spostamento HTTP valido dopo dichiarazione e approvazione nuove disponibilità. Esito: 6 lezioni attive, 7 storiche, 24 booking, 9 eventi di dominio, zero email.
- Playwright/Chromium locale: nessun errore JavaScript osservato, layout 390 px senza overflow documento dopo correzione badge; screenshot e report in evidence/. Non audit WCAG o E2E completo dei quattro ruoli.

## Ambito e tracciabilità
Fixture sintetici (demo 4 studenti, 2 tutor, 3 spazi, 6 unità); partial usa un'ulteriore richiesta opzionale con indisponibilità esplicita, non mancante. Demo a 2 materie: non un programma scolastico ufficiale completo né una certificazione. OPTIMAL riguarda soltanto P0/P1/P2 e i domini limitati.

Prove correnti: evidence/postgres-tests.txt, calendar-smoke.json, frontend-build.txt e calendar-*.png. Le prove v0.4 sono mantenute con prefisso v0.4-, non rappresentano il collaudo PostgreSQL corrente. Sorgenti e migrazioni nell'archivio; database/credenziali casuali/cluster/dipendenze installate esclusi.

## Non provato / fuori incremento
- Docker Compose, Redis e deployment gestito end-to-end **non eseguiti**. PostgreSQL standalone collaudato non prova la configurazione del fornitore o del container; CI PostgreSQL configurata ma non eseguita su GitHub.
- Worker solo/filesystem non prova timeout hard/soft prefork, perdita broker reale, rete distribuita, deadlock/retry o restore/failover. Lease/reconciler restano verificati con fault injection controllata.
- SQL amministrativo su snapshot/audit/revisioni e DDL privilegiato non universalmente protetti. Ruoli applicativi a minimo privilegio, append-only/retention/audit completo e procedure operative da definire.
- Non tutti H01–H12 sono espressioni DB: trigger verificano completezza/coerenza e collisioni; disponibilità/carichi/transizioni sono anche controlli applicativi. Nessuna garanzia di conformità legale, ASVS, privacy o WCAG.
- Orizzonte una settimana/40 unità/10 tutor/120 studenti/3000 candidati; vettore completo, 6 settimane/720 unità, 20-run benchmark/NFR/SLO/RPO/RTO non dimostrati.
- Presenze e COMPLETED, recuperi/RecoveryObligation, pratiche automatiche di conflitto, questa-e-successive, sostituzione tutor/risorsa/modalità, portali calendario esterni, inviti/MFA, outbox/delivery/email e produzione non implementati.
- OpenAPI subset manuale con riferimenti/operationId/rotte controllati, non validazione completa del catalogo normativo con validatore dedicato.

## Esito
**Calendario transazionale sperimentale funzionante sul dataset sintetico, non rilascio operativo.** PostgreSQL realmente collaudato, nessun gate G1–G6 dichiarato superato. Readiness/production_enabled restano false. Flag calendario disabilitato per default; email/delivery non attive.

## v0.8 · stream s6-frontend (portali, accesso, stati G04)

- **Test di componente/unitari nel repository**: `cd frontend && npm test` (node:test + esbuild + react-dom/server, nessuna dipendenza nuova) — 34 test: client tipizzato e paginazione a cursore, flusso di accesso, classificazione degli stati G04, permessi multi-figlio, carico tutor, rendering accessibile di login/MFA/codici di recupero/contesto/invito/schede.
- **E2E + axe**: `npm run build && npm run e2e` (Playwright + axe-core, API simulate, `vite preview`): login con MFA, panoramica multi-figlio con «Sola lettura», eccezioni a cursore, richiesta di assenza con Idempotency-Key, ritiro in conflitto, notifiche, link ICS, sessione revocata, scelta del contesto, carico tutor e presenze, invito con pulizia del token; tastiera (focus intrappolato, Esc con ritorno del focus) e reflow. 1440/390 px × chiaro/scuro: **92/92 controlli, 48 pagine axe WCAG 2.2 AA, 0 violazioni**. Prove: `docs/evidence/v0.8-s6/` (screenshot + `e2e-report.json`).
- **Contratto**: `npm run check:api` verifica che `src/api/schema.gen.ts` sia allineato a `contracts/openapi.yaml`.
