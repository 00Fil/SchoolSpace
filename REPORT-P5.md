# REPORT P5 · Portali famiglie, studente e tutor (parti 1 e 2)

Decisioni del committente applicate (3 ottobre 2026):

| Decisione | Attuazione | File |
|---|---|---|
| D07 · account studente da 14 anni | Invito STUDENT rifiutato senza attestazione dell'età (`age_confirmed`), registrata nell'audit | `apps/identity/services.py`, `api/auth.py`, `config/settings.py` |
| D07 · minorenne in sola visione | `PORTAL_STUDENT_CAN_REQUEST_CHANGES=False`, `PORTAL_STUDENT_CAN_EDIT_AVAILABILITY=False` | `config/settings.py` |
| DC-CONFERMA-GENITORI · sempre | Le modifiche del tutor accolte dal centro attendono i genitori (`awaiting=GUARDIANS`); il centro non può accettarle prima; nuovo comando `POST /change-requests/<id>/guardian-confirm/` | `apps/calendar/acknowledgements.py`, `apps/calendar/conflicts.py`, `api/calendar_ops.py` |
| Portale famiglie | Riquadro «Modifiche proposte dal tutor» in *Cambi* con conferma/rifiuto e motivo precompilato | `portal/ConfermeGenitori.tsx`, `portal/Cambi.tsx` |

Test: `tests/test_p5_decisioni.py` (logica pura). Da aggiungere con il database: BOLA del nuovo comando (genitore di altro studente → 404, studente → 404).

Da verificare in locale: che l'elenco `/change-requests/` mostri ai genitori anche le richieste nate dal tutor sulle lezioni dei figli.

## Parte 2

| Area guida | Cosa | File |
|---|---|---|
| «I miei dati», informativa | Pagina del portale con informativa breve e versione | `portal/MieiDati.tsx`, `api/my_data.py` (`GET /me/data`) |
| Export personale | Copia JSON monouso con scadenza (stesse protezioni degli export del centro), apre una richiesta di accesso; limite 1 export non scaricato per 24 h e 5/ora | `POST /me/data/export` |
| Richieste degli interessati | Rettifica, cancellazione, limitazione, opposizione dal portale → registro privacy (canale PORTALE, scadenza 1 mese, ledger); niente doppioni aperti | `POST /me/data/requests`, `apps/privacy/requests.py` |
| Consenso e maggiore età | Studente maggiorenne: consenso/revoca dell'accesso dei genitori; minorenne: spiegazione della sola visione | `portal/MieiDati.tsx` (usa `auth/student-consent`) |
| Link lezione online | «Lezioni online in arrivo» nella home del portale con apertura a finestra temporale | `portal/LezioniOnline.tsx` |
| Carico del tutor | Già presente (pannello «Il tuo carico») | `portal/PortalHome.tsx` |
| Griglia disponibilità / eccezioni | Già presenti da P2 (pagina Figli / Disponibilità e assenze) | `portal/Profilo.tsx` |

Test: `tests/test_p5_miei_dati.py` (centro escluso, export di studente altrui → 403, richiesta doppia → 409).

## Parte 3

| Area | Cosa | File |
|---|---|---|
| Riconferma deleghe alla maggiore età | Lo studente maggiorenne conferma o chiude ogni delega dal portale (chiusura con conferma); usa gli endpoint esistenti `registry/guardian-links/<id>/reconfirm|decline`, che già autorizzano lo studente titolare | `api/my_data.py` (`consent.reconfirmations`), `portal/MieiDati.tsx` |
| E2E portali P5 | Genitore (export del figlio, download monouso, secondo export bloccato, richiesta di cancellazione), studente maggiorenne (consenso, riconferma, chiusura), studente minorenne (sola visione); 1440/360 px, chiaro/scuro, axe WCAG 2.2 AA | `frontend/e2e/miei-dati.e2e.mjs` (`npm run e2e:dati`, porta 4183) |
| Copione UAT | 12 compiti per 3 famiglie e 2 tutor, soglie d'uscita | `docs/uat/p5-portali.md` |

## Stato di P5

Software completo per quanto indicato nella guida. Resta al centro: eseguire `pytest`, `npm run e2e:dati` e gli altri E2E in locale, condurre l'UAT con il copione e firmarne l'esito.
