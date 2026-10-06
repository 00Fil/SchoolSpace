# 08 · Videolezioni automatiche (Jitsi Meet self-hosted)

Dalla v0.10 ogni lezione **ONLINE** pubblicata ha già la sua stanza video: il centro non crea,
copia o incolla più link. Base: [Jitsi Meet](https://jitsi.org/) (open source, Apache-2.0),
installato sulla stessa VPS o su una dedicata.

## Come funziona
| Passo | Prima (≤ v0.9) | Ora (v0.10) |
|---|---|---|
| Creare la stanza | link a mano per lezione o canale (admin Django) | automatica: `HMAC(segreto, id lezione)` |
| Inviare il link | — (mai via email) | nessun invio: si entra dal portale |
| Entrare | nuova scheda, nome da digitare, pagina di attesa | un clic su «Entra nella lezione», stanza integrata nel gestionale, nome già impostato |
| Chi entra | chiunque abbia il link | solo con token firmato per quella stanza e quell'orario (15 min prima → fine + 10 min) |
| Ruoli | — | tutor e centro moderatori, studenti con microfono spento all'ingresso |
| Presenze | tutte a mano | proposta automatica: chi non è mai entrato risulta «Assente», il tutor conferma |

- Spostare la lezione o cambiare tutor **non** cambia la stanza.
- I `MeetingLink` manuali restano validi e hanno la precedenza (per esempio un'altra piattaforma).
- Nel token: solo nome visualizzato (quello dello studente/tutor) e un identificativo pseudonimo.
  Nessuna email. Registrazione, dirette, trascrizioni e inviti esterni disattivati.
- La presenza misura solo il tempo con la stanza aperta nel gestionale (segnale al minuto):
  nessun audio/video/contenuto viene registrato. Il dato serve a precompilare, non sostituisce
  la conferma del tutor.

## Installazione (Dokploy)
1. DNS: `meet.tuodominio.it` → IP della VPS. Firewall: aprire **UDP 10000**.
2. Nuovo progetto Compose in Dokploy con `compose.jitsi.yaml`; variabili da
   `infra/env/jitsi.env.example` (`openssl rand -hex 32` per `JITSI_JWT_APP_SECRET`).
3. Domains → servizio `jitsi-web`, porta 80, HTTPS. Non rinominare i servizi: un servizio `web` sulla rete condivisa di Dokploy rompe il gestionale.
4. Nello stack del gestionale (Environment):
   ```
   VIDEO_PROVIDER=jitsi
   VIDEO_JITSI_URL=https://meet.tuodominio.it
   JITSI_JWT_APP_ID=ripetizioni
   JITSI_JWT_APP_SECRET=<stesso valore dello stack Jitsi>
   ```
   Il proxy usa `VIDEO_JITSI_URL` per consentire l'iframe (`frame-src`) e delegare camera,
   microfono e condivisione schermo **solo** a quell'origine (`Permissions-Policy`).
5. Ridistribuire il gestionale (`migrate` applica `communications.0003_meeting_presence`).

## Tema grafico (Lumen)
La stanza usa il tema scuro Lumen del gestionale, applicato nell'immagine `web` costruita da
`infra/jitsi/web.Dockerfile` (nessuna modifica al codice di Jitsi):

| File | Cosa fa |
|---|---|
| `static/branding.json` | *dynamic branding* di Jitsi: sfondo, logo e palette (`customTheme`) con i token Lumen scuri |
| `static/lumen.css` + `plugin.head.html` | carattere Bricolage Grotesque self-hosted, barra strumenti a pillola di vetro, riquadri video arrotondati, oratore attivo in blu |
| `static/logo.svg` | il logo a tre barre del gestionale al posto del marchio Jitsi |
| `custom-config.js` | italiano, nome non modificabile (arriva dal gestionale), barra con soli comandi utili alla lezione, niente inviti/registrazioni |
| `custom-interface_config.js` | nome «Centro ripetizioni», niente watermark, promozioni e banner di Jitsi |

Se cambiano i colori in `frontend/src/lumen/tokens.css`, aggiornare `branding.json`: il test
`tests/test_jitsi_theme.py` fallisce finché non sono allineati. Il CSS usa solo selettori
stabili di Jitsi; dopo un aggiornamento importante di Jitsi controllare a vista la stanza
(i colori, che passano da `branding.json`, non dipendono dal CSS).

## Verifica
- Da Configurazione → Calendario, aprire una lezione online → «Entra nella videolezione».
- Da portale famiglia/studente, 15 minuti prima: «Entra nella lezione».
- Un link copiato fuori orario deve dare errore di autenticazione su Jitsi.

## Opzioni
- `VIDEO_EMBED=0`: apre la stanza in una nuova scheda invece che integrata.
- `VIDEO_GRACE_MINUTES` (default 10): minuti dopo la fine per rientrare.
- Moderazione solo per il tutor: il token contiene già `context.user.moderator` e `affiliation`.
  Con `ENABLE_AUTO_OWNER=1` (predefinito) diventa moderatore il primo che entra; per imporre il
  ruolo dal token installare in Prosody un modulo di affiliazione da token (es.
  `token_affiliation` di jitsi-contrib) e impostare `ENABLE_AUTO_OWNER=0`.
- Capacità: Jitsi su 4 vCPU / 8 GB regge decine di lezioni piccole in parallelo. I canali video
  in Configurazione → Aule restano il limite di lezioni online contemporanee per il pianificatore.

## Problemi frequenti

- **`migrate` o `web` riportano `communications.W010 Videolezioni automatiche disattivate: …`**: `VIDEO_PROVIDER=jitsi` è impostato ma manca qualcosa. L'app parte comunque, senza stanze automatiche. Correggere nell'ambiente del gestionale `VIDEO_JITSI_URL=https://meet.<dominio>` e `JITSI_JWT_APP_SECRET` (`openssl rand -hex 32`, 64 caratteri, **identico** a quello dello stack Jitsi), poi ridistribuire. Finché Jitsi non è pronto si può lasciare `VIDEO_PROVIDER` vuoto.
| Sintomo | Causa probabile |
|---|---|
| «Videolezioni non attive» | `VIDEO_PROVIDER` vuoto e nessun link manuale |
| Iframe bianco / bloccato | `VIDEO_JITSI_URL` del proxy diverso dall'origine reale di Jitsi |
| Si entra ma senza audio/video tra i partecipanti | UDP 10000 chiusa o `JVB_ADVERTISE_IPS` errato |
| «Authentication failed» su Jitsi | segreto JWT diverso tra i due stack, orologio VPS non sincronizzato, o link fuori orario |
