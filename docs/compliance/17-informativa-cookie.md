# Informativa sui cookie e sugli strumenti di archiviazione locale

| Campo | Valore |
|---|---|
| Stato | **BOZZA** — verificata sul codice v0.7 (backend `config/settings.py`, frontend `src/api.ts`, `src/ui/prefs.ts`, `src/app/Shell.tsx`) |
| Versione | cookie-v0.1 — 2026-10-02 |
| Documento del fascicolo | n. 13 — gate G6 |
| GAP | GAP-H09 |
| Responsabile | Titolare; verifica tecnica: tech lead |
| Riferimenti normativi | D.Lgs. 196/2003 art. 122; Linee guida del Garante su cookie e altri strumenti di tracciamento, provv. 10 giugno 2021, n. 231; GDPR art. 13 |

> Esito della verifica tecnica: il portale usa **solo strumenti tecnici**, che non richiedono consenso né banner, ma vanno
> descritti. Nessuno script di analytics, pixel, font o CDN di terze parti (standard Lumen con font e icone locali; la CSP
> impedisce risorse esterne non dichiarate). **Ogni nuovo strumento non tecnico richiede banner e consenso preventivo**
> e l'aggiornamento di questo documento. Non è un parere legale.

---

## Cookie e archiviazione locale nel portale di [DA COMPILARE: nome del centro]

Il portale usa solo strumenti **tecnici**, necessari per farlo funzionare in modo sicuro o per ricordare le preferenze
che hai scelto. Non usiamo cookie di profilazione, pubblicità o statistiche, né strumenti di terze parti. Per questo non
ti chiediamo il consenso e non vedi alcun banner.

| Nome | Tipo | Finalità | Durata | Prima/terza parte |
|---|---|---|---|---|
| `sessionid` | Cookie tecnico di sessione (HttpOnly, Secure, SameSite=Lax) | Mantenere l'accesso dopo il login | Fino al logout o alla scadenza della sessione ([DA COMPILARE: timeout approvato, GAP-B04]) | Prima parte |
| `csrftoken` | Cookie tecnico di sicurezza (Secure, SameSite=Lax) | Proteggere da richieste falsificate (CSRF) | [DA COMPILARE: durata configurata, default Django 1 anno] | Prima parte |
| `ripetizioni-ui` | Archiviazione locale del browser (localStorage) | Ricordare tema chiaro/scuro e riduzione delle animazioni | Finché non la cancelli | Prima parte; non inviata al server |
| `ripetizioni-read` | Archiviazione locale del browser (localStorage) | Ricordare quali avvisi hai già letto su questo dispositivo | Finché non la cancelli | Prima parte; non inviata al server |

**Come gestirli.** Puoi cancellare cookie e archiviazione locale dalle impostazioni del browser. Senza `sessionid` e
`csrftoken` non è possibile accedere al portale; senza le preferenze locali il portale usa le impostazioni predefinite.

**Link esterni.** I link alle lezioni online aprono il servizio di videoconferenza scelto dal centro, che applica una
propria informativa sui cookie.

Titolare: [DA COMPILARE]. Contatti: [DA COMPILARE]. Versione [DA COMPILARE] del [DA COMPILARE].

---

## Checklist di verifica prima di ogni release (per il tech lead)
- [ ] Nessun nuovo `Set-Cookie` o chiave di storage oltre a quelli della tabella (verifica con DevTools/E2E).
- [ ] CSP senza domini di terze parti per script, stili, font e immagini.
- [ ] Nessun tag di analytics o pixel nel bundle (`grep` su build).
- [ ] Durate dei cookie coerenti con i settings di produzione (`SESSION_COOKIE_AGE`, `CSRF_COOKIE_AGE`).
- [ ] Se servono statistiche d'uso: solo analytics di prima parte, IP minimizzato, senza incroci, nelle condizioni del Garante per l'equiparazione ai tecnici; altrimenti banner con consenso preventivo, senza cookie wall.
