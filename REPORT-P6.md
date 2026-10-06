# REPORT P6 · Privacy e registro — parte 1

| Area guida | Cosa | File |
|---|---|---|
| Richieste degli interessati | Elenco aperte/scadute/tutte, scadenza in evidenza; azioni verifica identità, proroga, evasione con export, cancellazione, chiusura con esito, rifiuto; motivi precompilati | `frontend/src/screens/Privacy.tsx` |
| Export | Elenco con stato e revoca | idem |
| Conservazione con approvazione | Regole con stato, approvazione con riferimento del verbale e versione; simulazione/esecuzione con ricevuta | idem |
| Audit consultabile | Registro filtrabile per categoria e oggetto, paginato, sola lettura | idem |
| Maggiore età | Controllo e avvio delle riconferme | idem |
| Fascicolo | Evidenze da catturare dall'interfaccia per C01–C06, C09, C11, C13, C19, C25 | `docs/compliance/fascicolo-P6.md` |

Backend: nessuna modifica, l'area usa gli endpoint `privacy/*` già esistenti (tutti `center_only`).

## Parte 2 (fatta)

| Area | Cosa | File |
|---|---|---|
| C04 presa visione | Modello `NoticeAcknowledgement` (una per account e versione) + migrazione 0005; `POST me/notice/acknowledge` (409 se versione superata); `notice_pending` in `/me`; finestra bloccante nel portale | `apps/privacy/models.py`, `migrations/0005_*`, `api/my_data.py`, `api/views.py`, `portal/InformativaGate.tsx` |
| Export senza ID a mano | `GET privacy/requests/<id>/audiences` (interessato, account studente, genitori con delega attiva); scelta da elenco | `api/privacy.py`, `screens/Privacy.tsx` |
| Test | presa visione per versione, idempotenza, centro escluso, destinatari solo per il centro | `tests/test_p6_privacy.py` |
| C01 | Già coperto da `test_guardian_sees_children_and_hides_other_names` e `test_group_request_does_not_leak_other_participants`: evidenza dall'interfaccia nel fascicolo | `docs/compliance/fascicolo-P6.md` |

Rinviato a P7 (E2E completi per ruolo): E2E dell'area Privacy; ricerca dell'interessato per nome.
