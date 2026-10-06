# Backlog di implementazione

Questo è un avvio esplorativo v0.3; non è il completamento di Fase 1 o Fase 2.

## UI — standard Lumen (vincolante)
- [x] Studiare il riferimento Lumen v5.2 e codificare lo standard (ADR06, ui-standard.md).
- [x] Estrarre token, componenti, font e icone in `frontend/src/lumen/` con verifica al pixel.
- [x] Primitive React: LayerStack, Toasts, SegCtl, Wheel, CalendarPicker, Combo, Field, Icon, CommandPalette, useHashRoute, useTheme.
- [x] Ricostruire guscio (rail, topbar, tabbar) e tutte le schermate v0.5 sullo standard; eliminare `window.prompt`, date/ISO digitati e codici in primo piano.
- [x] Agenda del centro come griglia Lumen (tutor × slot) collegata al calendario transazionale, con spostamento validato dal backend.
- [x] Prove visive 1440/1280/390, chiaro/scuro, tastiera e movimento ridotto in `docs/evidence/`.
- [x] Mostrare il motivo puntuale quando il validatore del calendario rifiuta uno spostamento (v0.7: `violations` + opzioni di spostamento lato server).
- [x] Audit di accessibilità automatico axe-core e correzione contrasti (v0.7); resta la verifica WCAG manuale con tecnologie assistive.
- [x] Moduli strutturati per la configurazione di prova e riepilogo leggibile del Laboratorio (v0.7).
- [x] Prima versione dei portali tutor/famiglia/studente in sola lettura («La mia settimana», v0.7).
- [ ] Test automatici dei componenti UI nel repository (oggi collaudo E2E Playwright e audit axe fuori dal repository, prove in `docs/evidence/`).
- [ ] Portali: richieste di spostamento/assenza da famiglia e tutor, notifiche, disponibilità del tutor dal portale, UAT con utenti reali.
- [ ] Spostamento con cambio tutor o spazio (oggi tutor, durata e partecipanti restano invariati).

## Subito — G1
- [x] Chiarire il significato di parentali: programma scolastico completo presso il centro.
- [ ] Dettagliare D01 e chiudere D02–D06 con committente e referente didattico.
- [ ] Assegnare owner/scadenze e valori di prova D07–D09.
- [ ] Congelare entità/stati e unità canoniche; approvare H01–H12 e politica obiettivi.
- [ ] Definire fixture T01–T42 ed expected; firmare contratto del dominio.

## Dopo G1 — Fase 2
- [x] Prototipo curriculum, coorti/iscrizioni, sottogruppi, copertura materie e derivazione idempotente richieste.
- [ ] Approvare schema definitivo; completare skill, catalogo durate e revisione curriculum/partecipazioni datate.
- [ ] Email normalizzata con unicità robusta DB, inviti e reset monouso, MFA staff, policy per-operazione e per-oggetto (FR01–03; T01/T24/T25).
- [ ] Audit append-only per mutazioni di dominio e admin; revisioni monotone e comandi versionati (FR23; T39/T42).
- [ ] ServiceWindow, Closure, AvailabilityException, stati readiness, conflitti tutori (FR05–06; T09–T11).
- [ ] Compiler integrato, serie/eccezioni, snapshot consistente, DemandUnit e import idempotente (FR07–11/24; T12–T17/T37–T39).
- [ ] OpenAPI completo generato dai serializer; client tipizzato generato; filtri e paginazione cursor definitivi.

## Fase 3
- [x] Esplorazione isolata CP-SAT, DTO chiuso, vincoli principali, copertura P0/P1/P2 e validatore indipendente su casi sintetici.
- [ ] Integrare il solver con snapshot approvati; completare H01–H12, equità, preferenze, ricorrenza, sequenze e vettore obiettivi completo.
- [ ] Validatore indipendente, ledger esclusioni, diagnostica esiti, benchmark e G3.
- [ ] Celery/Redis con job persistenti, cancellazione/heartbeat e concorrenza uno.

## Fase 4
- [ ] CalendarOccurrence, ResourceBooking con GiST e trigger differibile.
- [ ] Lock/revisioni, idempotenza, validate/publish e race test PostgreSQL.
- [ ] Outbox, riconciliazione, recuperi, presenze individuali e conflitti.

## Fase 5–6
- [ ] Portali completi e UAT multi-ruolo; WCAG manuale e E2E.
- [ ] Sicurezza ASVS, retention, provisioning, backup/PITR/restore e pilota.

Nessun FR della baseline è dichiarato completamente soddisfatto da v0.3.

## Incremento v0.4 e residuo
Completati per esplorazione: dati→snapshot, configurazioni/competenze, disponibilità approvate, revisioni, unità, job e monitoraggio. Prossimo blocco: approvazioni dominio residue e verifica PostgreSQL/Redis reale; poi booking e pubblicazione transazionale, presenze/recuperi/outbox. Il bridge non autorizza a saltare G1/G2/G3.

## Aggiornamento v0.5
Pubblicazione/prenotazioni e comandi manuali completati solo per calendario sintetico del centro; PostgreSQL collaudato realmente. Prossimi blocchi: decisioni/gate residui, presenze e COMPLETED, pratiche di conflitto/recuperi, outbox-delivery, portali calendario con scope e sicurezza. Nessun go-live automatico.

## Aggiornamento v0.7
Risolti i limiti UI della v0.6 (motivi del rifiuto, seed su più giorni, trascinamento collaudato, moduli al posto del JSON, audit accessibilità) e avviati i portali in sola lettura. Restano aperti: decisioni G1 D01–D09, dati reali/privacy/produzione, test UI nel repository, azioni dai portali.
