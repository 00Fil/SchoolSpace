# Comunicazioni: outbox, email, notifiche, ICS e link video (v0.8, stream s3)

Contratto HTTP: `contracts/openapi.yaml` (tag `communications`, verificato da `tests/test_communications_contract.py`).

Chiude in codice e test GAP-F01…F05 (paper §7.4, FR20, T22, T23). Modulo:
`backend/apps/communications`, API in `backend/api/communications.py`.

## API pubblica per gli altri moduli

```python
from django.db import transaction
from apps.communications.services import emit, Recipient

with transaction.atomic():
    ...  # scritture di dominio
    emit(
        "absence.recorded",                       # tipo: parole minuscole separate da punti
        {"absence_id": str(a.id), "start_at": a.start_at.isoformat()},  # payload minimo
        [Recipient(account, {"student_names": [student.display_name]})],
        idempotency_key=f"absence:{a.id}:v{a.version}",
    )
```

- `emit` **deve** essere chiamato dentro la transazione di dominio (altrimenti
  `RuntimeError`): `OutboxEvent` e `Delivery` sono scritti nello stesso commit.
- Stessa chiave + stesso evento = replay senza effetti; chiave con evento diverso =
  `OutboxConflict`.
- Il payload è condiviso fra destinatari: `PayloadNotMinimal` se contiene elenchi di
  persone (`participants`, `members`, …), recapiti, link (`https://…`) o oggetti annidati
  in liste. Il contesto per destinatario ammette solo `student_names` (i *propri*
  studenti, ≤ 6) e `role`.
- Canali: `IN_APP` (sempre attivo per il servizio) ed `EMAIL` (preferenza). Categoria
  `MARKETING` separata e disabilitata (`COMMUNICATIONS_MARKETING_ENABLED=False`).
- Template: `templates/communications/email/<tipo_con_underscore>.{subject,body,notification}.txt`;
  in mancanza si usa `generic.*`. Orari sempre in Europe/Rome.

## Integrazione con il calendario

`apps/calendar/services.py` (3 righe): `notify_lesson(lesson, kind, before)` dopo ogni
`CalendarEvent` di pubblicazione, spostamento e cancellazione. Chiave
`calendar:lesson:<id>:v<version>`; tipi `lesson.published|rescheduled|cancelled`.
Destinatari calcolati come nei portali: tutor assegnato, account studente con ruolo
STUDENT attivo, tutori legali con delega verificata/`can_view`/valida e ruolo GUARDIAN.
Il replay di un comando (ricevuta idempotente) non crea né eventi né notifiche.

## Ricontrollo dell'autorizzazione all'invio

`emit(..., audience="<nome>")` lega l'evento a un autorizzatore registrato
(`apps/communications/authorization.py`; gli altri stream usano
`register_authorizer(nome, fn)`). Il worker lo richiama subito prima di consegnare
(in-app ed email): se il destinatario non ha più diritto al contenuto la consegna passa
a **`REVOKED`** (`RECIPIENT_NOT_AUTHORIZED`, tentativo tracciato), senza notifica né
email. Autorizzatore sconosciuto = negato (fail closed); eccezione = errore temporaneo.

- `calendar.lesson`: destinatario ancora nel perimetro della lezione (tutor assegnato,
  studente con ruolo attivo, tutore con delega verificata e valida). Una delega revocata
  dopo l'emissione annulla le consegne non ancora fatte.
- `identity.invitation`: invito ancora `SENT`, stessa versione, non scaduto, stesso
  indirizzo (reinvio o revoca annullano l'email precedente).
- `identity.password_reset`: record non usato né superato da una nuova richiesta, non
  scaduto, account attivo con lo stesso indirizzo.

## Inviti e reset password (s1) via outbox

`IDENTITY_MESSAGE_SENDER = "apps.communications.identity_hooks.send"` (blocco s3 in
settings). Hook minimo in identity: `delivery.deliver(kind, to, token, ref)` esegue i
sender `transactional` dentro la transazione che emette il token (gli altri restano
`on_commit`); `services.py` passa invito o record di reset come `ref`.

**Scelta sul token in chiaro: segreto effimero cifrato.** s1 salva solo l'hash, quindi il
token non è ricostruibile dopo l'emissione; il chiaro esiste solo in memoria in quel
momento e nel corpo dell'email:

1. il payload dell'`OutboxEvent` contiene solo riferimenti (`invitation_id`+`version` o
   `reset_id`, scadenza); la guardia dei payload rifiuta chiavi `token`/`password` e link;
2. il token passa a `emit(secrets={"token": …}, secrets_expire_at=…)` ed è salvato in
   `SealedSecret` cifrato con Fernet (AES-128-CBC + HMAC-SHA256, libreria
   `cryptography`), una riga per consegna, scadenza pari a quella del token;
3. il worker ricontrolla l'autorizzazione, decifra in memoria, compone il link
   (`apps.identity.delivery.build_link`, frammento `#token=`) e invia; il segreto è
   cancellato appena la consegna è finale; il reconciler elimina i segreti scaduti;
4. segreto assente, scaduto o illeggibile → **`EXPIRED`** (nessun invio): serve un nuovo
   invito/reset;
5. nessun log contiene corpo, link o token (solo id di consegna); l'audit di s1 non lo
   riceve; `DeliveryAttempt` registra solo esiti e codici. Un test scansiona tutte le
   tabelle del DB prima e dopo l'invio.

Chiavi: `COMMUNICATIONS_SEAL_KEYS` (o `_FILE`), chiavi Fernet separate da virgola; la
prima cifra, le altre decifrano (rotazione). Se vuoto, chiave derivata con HKDF da
`SECRET_KEY` e fallback; in produzione il check `communications.W002` chiede una chiave
dedicata. Alternative scartate: token in cache/Redis (chiaro su un altro archivio, perso
con Redis), token derivato via HMAC dall'id (rifare la generazione dei token di s1),
invio sincrono (nessun retry, differenza di tempi nel reset). I messaggi `essential` non
dipendono da preferenze né da email verificata; il destinatario può essere solo un
indirizzo (invito senza account).

## Consegna

Stati `Delivery`: `PENDING → SENDING → SENT`; `REVOKED` (destinatario non più autorizzato) ed `EXPIRED` (segreto scaduto) sono finali; errore temporaneo → `PENDING` con backoff
esponenziale ed equal jitter (30 s … 1 h, `MAX_ATTEMPTS`=6); errore permanente o tentativi
esauriti → `DEAD` (dead-letter "da verificare"); risposta persa o worker morto durante
l'invio email → `AMBIGUOUS`; preferenze/recapito assenti → `SKIPPED`; decisione del
centro → `CANCELLED`. Ogni tentativo è in `DeliveryAttempt` (append-only).

- Dispatcher: `transaction.on_commit` accoda `apps.communications.tasks.deliver` sulla coda
  `notifications`. Se il broker manca, la consegna resta `PENDING`.
- Reconciler (`apps.communications.tasks.reconcile`, beat ogni 30 s; manuale:
  `manage.py dispatch_communications [--inline]`): lease scaduti, esiti ambigui, consegne
  non accodate o accodate da > 5 minuti (job perso). T22 coperto da test.
- In-app: `Notification` unica per `event+recipient` (vincolo DB): nessun duplicato.
- Email ambigua (T23): `lookup` presso il provider → `SENT` se trovata, nuovo tentativo se
  sicuramente non ricevuta; se ignota: provider idempotente → reinvio con la stessa chiave;
  altrimenti `COMMUNICATIONS_AMBIGUOUS_POLICY=verify` (default) → `DEAD` da verificare,
  `retry` → at-least-once (possibile duplicato, da approvare). Nessuna promessa
  exactly-once.
- Centro: `GET /api/v1/communications/status` (conteggi, nessun destinatario) e
  `POST /api/v1/communications/deliveries/{id}/resolve` (`MARK_SENT|RETRY|ABANDON` + motivo).

## Provider email (D08 da approvare)

`COMMUNICATIONS_EMAIL_BACKEND`: `sink` (default, nessun invio), `smtp`, `api`.
Fuori da `COMMUNICATIONS_ENV=production` i backend reali sono rifiutati (errore a runtime
e system check `communications.E002`). Variabili: `COMMUNICATIONS_EMAIL_FROM`,
`COMMUNICATIONS_MESSAGE_ID_DOMAIN`, `COMMUNICATIONS_EMAIL_TIMEOUT`,
`COMMUNICATIONS_SMTP_HOST|PORT|USER|PASSWORD|SECURITY(starttls|tls)`,
`COMMUNICATIONS_EMAIL_API_URL|STATUS_URL({key})|TOKEN|IDEMPOTENT(0|1)`. Segreti solo da
secret manager, mai nel repository. Un destinatario per messaggio (nessun CC/BCC),
`Message-ID` derivato dalla chiave di consegna, `Auto-Submitted: auto-generated`.

### Requisiti del dominio mittente (prima del go-live)

1. **Fornitore UE** con contratto ex art. 28 GDPR (GAP-H03), log di consegna e, se
   possibile, API idempotente e lookup per chiave (abilita la riconciliazione T23).
2. **Sottodominio dedicato** per le email transazionali (es. `notifiche.<dominio>`),
   separato da eventuali invii promozionali.
3. **SPF**: record TXT `v=spf1 include:<fornitore> -all` sul dominio di envelope; ≤ 10
   lookup DNS.
4. **DKIM**: chiave ≥ 2048 bit pubblicata dal fornitore (`<selector>._domainkey`),
   firma allineata al dominio del `From`; rotazione almeno annuale.
5. **DMARC**: `_dmarc` con `p=none; rua=mailto:…` per 2–4 settimane di monitoraggio, poi
   `p=quarantine` e infine `p=reject`, `adkim=s; aspf=s` se il fornitore lo consente.
6. Bounce/complaint del fornitore → errore permanente (dead-letter) e verifica del
   recapito; nessuna lista di soppressione condivisa con il marketing.
7. Verifica con strumenti del fornitore e invio a caselle di prova *solo in produzione*.

## Preferenze e notifiche interne (GAP-F03)

`GET /api/v1/notifications[?unread=1&category=SERVICE]` (solo proprie, con
`unread_count` e `pending_email_deliveries`), `POST /api/v1/notifications/{id}/read`,
`POST /api/v1/notifications/read-all`, `GET|PUT /api/v1/notifications/preferences`
(`SERVICE/IN_APP` non disattivabile: il portale è la fonte autorevole). Default
prudenziali: email di servizio attiva solo con email verificata; email agli account
studente spenta (`COMMUNICATIONS_EMAIL_STUDENTS=False`, D07 da approvare).

## Export ICS e link video (GAP-F04)

- `POST /api/v1/calendar-feed-tokens` → token `ics_…` mostrato una sola volta; salvato
  solo l'hash SHA-256; massimo 3 attivi, scadenza 365 giorni (configurabile);
  `POST /api/v1/calendar-feed-tokens/{id}/revoke`.
- `GET /api/v1/calendar.ics?token=…`: perimetro ricalcolato a ogni richiesta (revoche di
  ruolo/delega immediate), finestra −30/+120 giorni, solo materia/orari/stato/modalità;
  nessun nome, nessun link video; `Cache-Control: private, no-store`. Il token è nella
  URL: configurare il proxy per non registrare la query string di questo percorso.
- `GET /api/v1/occurrences/{id}/meeting`: 404 fuori perimetro; solo lezioni online
  pubblicate; link restituito da 15 minuti prima dell'inizio fino alla fine
  (`expires_at`), `no-store`. Il centro lo configura in admin (`MeetingLink` per lezione,
  preferibile, o per canale video). Stanze per lezione o con scadenza lato provider
  video sono raccomandate (D08).

## Esercizio

Il worker Compose consuma solo la coda `solver`: in produzione serve un worker
dedicato `celery -A config worker -Q notifications` (container separato, paper §6).
Retention proposta per le consegne: 90 giorni (D09, da approvare; job non incluso).
