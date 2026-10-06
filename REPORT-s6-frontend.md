# REPORT — stream s6-frontend

Branch `s6-frontend` · worktree `/data/work/s6-frontend`.

## Nota sull'ambiente (importante per l'integrazione)
Durante il lavoro `/data` è stato ripristinato a uno snapshot precedente: `main` risultava `6bad967` (solo s1+s3), non l'integrazione completa. Il branch è stato ricostruito con `git merge main` → `s2-calendario` (fast-forward) → `s4-privacy` (merge `fd1b5f8`, serve per deleghe/permessi). **s5, s7, s8 non sono mergiati** in questo branch (non necessari al frontend): al merge finale attendersi conflitti solo testuali in `contracts/openapi.yaml` e `backend/config/urls.py` (blocco `# --- s6-frontend ---` in coda).

## GAP chiusi (codice + test)
- **GAP-G01 portale famiglie** — `frontend/src/portal/`: panoramica multi-figlio (una scheda per studente con lezioni/minuti/cancellate/prossima, disponibilità, eccezioni in arrivo, richieste aperte, riconferma delega), tag **«Sola lettura»** e azioni nascoste senza delega di modifica; vista «Figli» con permessi della delega, fasce settimanali, disponibilità effettiva (luogo/modalità) ed eccezioni a cursore («Mostra altre», passate); richieste di cambio/assenza dalla lezione (Idempotency-Key, studente obbligatorio, proposta ISO con offset Europe/Rome), elenco e ritiro con versione attesa; «Nuova disponibilità» limitata ai figli con `can_manage_availability`.
- **GAP-G02 portale tutor** — carico in minuti per giorno/settimana rispetto ai limiti (barre accessibili, superamento evidenziato), disponibilità e localizzazione, assenze/eccezioni, «Segnala assenza» sulle proprie lezioni, presenze da registrare (ultimi 14 gg, cursore) con modal per partecipante e versione attesa.
- **GAP-G03 portale studenti** — stesso portale con scope proprio (relazione SELF, dati altrui non mostrati); richieste dirette dipendenti da D07.
- **GAP-G04 stati** — `ui/states.tsx` (`classify`, `ViewState`, `ErrorState`: revocato, vietato, obsoleto, non conclusivo, parziale, conflitto, offline, non attivo) applicati a portali, impostazioni, caricamento globale, Laboratorio/Proposte (solver UNKNOWN, risultati parziali), Settimana (limite 300 righe). Eventi globali del client: sessione revocata → schermata «Accesso non più disponibile»; `CONTEXT_REQUIRED` → scelta ruolo; `MFA_REQUIRED` → step-up; account senza ruoli → «Nessun ruolo attivo».
- **GAP-G05 client tipizzato** — `frontend/scripts/gen-api.py` genera `src/api/schema.gen.ts` da `contracts/openapi.yaml` (`npm run gen:api`, `npm run check:api` per CI); `src/api/client.ts` con `get/post/put` tipizzati sui path del contratto, errori con `code`/`retryAfter`, cursore opaco (`pages`/`collect`, rifiuto di origini estranee e cicli, `truncated`), chiavi di idempotenza. Contratto portato a **0.8.0**: auth s1 (login email, MFA, reset, sessioni, contesto, invito), change-request/presenze/disponibilità effettiva s2, notifiche/preferenze/feed ICS s3, `portal/*`.
- **Accesso** — login email, «Password dimenticata?», MFA TOTP (autocomplete one-time-code) e codici di recupero, attivazione MFA con QR + chiave + codici mostrati una volta («Li ho salvati»), scelta contesto e «Cambia ruolo», reset password e accettazione invito da `#token=` (token rimosso subito dall'URL; account esistente → invito in sospeso accettato dopo il login).
- **Notifiche interne ed ICS** — campanella con notifiche reali (non lette, lettura singola/totale, polling 60 s, visibile anche su mobile) + «Da fare»; Impostazioni: Sicurezza (password, sessioni, nuovi codici MFA), Notifiche (preferenze, obbligatorie bloccate), Calendario (crea link ICS mostrato una volta, copia, revoca).
- **GAP-G06 test** — `npm test`: 34 test unitari/di componente (node:test + esbuild + react-dom/server, nessuna dipendenza nuova). `npm run e2e`: Playwright + axe-core con API simulate, 1440/390 px × chiaro/scuro: **92/92 controlli, 48 pagine axe WCAG 2.2 AA, 0 violazioni**, tastiera (focus trap, Esc + ritorno focus) e reflow. Prove in `docs/evidence/v0.8-s6/`.
- **GAP-G09** — «Come funziona» su ogni schermata (portali, accesso, centro) e manuali `docs/manuali/{centro,tutor,famiglie,studenti,onboarding-famiglie}.md`.
- Backend sola lettura `backend/api/portals_v2.py`: `GET /portal/overview`, `/portal/availability-exceptions` (cursore), `/portal/attendance-pending` (cursore) + 11 test (`tests/test_portals_v2.py`, contract test incluso).

- **Permesso `can_request_changes` lato server** — `apps/calendar/conflicts.may_request_changes` applicato in `submit_change_request`: tutore legale solo con delega che include il permesso (403 FORBIDDEN altrimenti), studente solo se D07 (`PORTAL_STUDENT_CAN_REQUEST_CHANGES`) lo abilita; test `test_guardian_without_change_permission_is_forbidden` e `test_may_request_changes_follows_delegation_and_d07`.

## GAP parziali
- **Eccezioni dal portale**: il backend le rende scrivibili solo dal centro → il portale le mostra in sola lettura (le assenze su lezioni pubblicate passano dalle richieste di cambio).
- **E2E non in CI**: richiede dev-deps non dichiarate (`playwright`, `axe-core`); eseguito con moduli esterni (`PLAYWRIGHT_MODULE`, `AXE_PATH`). E2E solo su API simulate (nessun backend PG disponibile).

## File fuori proprietà
`contracts/openapi.yaml` (estensione 0.8.0), `backend/apps/calendar/conflicts.py` e `backend/tests/test_calendar_conflicts.py` (proprietà s2: controllo del permesso; `guardian_of` crea ora il dettaglio delega con `can_request_changes=True` di default), `backend/config/urls.py` (blocco s6 in coda), `docs/qa-report.md` (sezione v0.8), `docs/manuali/*`, `docs/evidence/v0.8-s6/*`. Nessun modello/migrazione.

## Settings / urls / requirements / dipendenze
- Settings: nessuna modifica; letto opzionalmente `PORTAL_STUDENT_CAN_REQUEST_CHANGES` (default `False`, **D07 da approvare**).
- urls: `urlpatterns += s6_portals.urlpatterns()`.
- requirements: nessuna. Dev-deps frontend da aggiungere: `playwright`, `axe-core` (E2E); consigliato dichiarare `esbuild` (oggi transitivo di Vite, usato da `npm test`). `frontend/node_modules` non modificato (symlink locale non committato).

## Test
- Backend suite completa: **589 passed, 19 skipped** (5 min 10 s); ruff ok (228 file formattati), `manage.py check` ok, `makemigrations --check` nessuna modifica.
- Frontend: `tsc --noEmit` ok, `npm run build` ok, `npm test` 34/34, `check:api` allineato, E2E 92/92 + axe 0 violazioni.

## Verifica di integrazione (merge simulato, branch non modificato)
- `git merge-tree` HEAD ⟵ `s5-infra`: **pulito**; ⟵ `s7-conformita`: **pulito**; ⟵ `s8-solver`: conflitto solo in `backend/requirements-dev.txt`, **già presente fra `main` e `s8`** (s8 riporta pytest a `>=8,<9` e sposta hypothesis): non dipende da s6, da risolvere in integrazione mantenendo `pytest>=9.0.3,<10`.
- Dev-deps E2E pronte ma **non applicate** (il brief vieta di installarle): `package.json`/`package-lock.json` aggiornati in sola modalità lockfile (`playwright@^1.63.0`, `axe-core@^4.13.0`, `esbuild@^0.28.2`) in `/data/work/s6-tooling/devdeps-{package,lock}.patch`; applicandole, `npm run e2e` funziona senza `PLAYWRIGHT_MODULE`/`AXE_PATH` (servono poi `npx playwright install chromium` in CI).

## Rischi / punti aperti
- D07 (richieste dirette dello studente) resta disattivata e configurabile.
- Merge con s5/s7/s8 e con l'integrazione 60603aa da verificare (contratto e urls).
- Il link ICS assume frontend e API sulla stessa origine (proxy); `/my/lessons` ha finestra ≤62 gg, quindi in «Richieste di cambio» il contesto della lezione è mostrato solo per ±30 gg.
- Notifiche in polling (nessun push); lo schema legacy `Login` (username) resta nei componenti del contratto, non più usato.
