# Informativa sull'uso degli strumenti e sui controlli (art. 4 L. 300/1970) e policy d'uso dell'audit

| Campo | Valore |
|---|---|
| Stato | **BOZZA** — da revisionare con il consulente del lavoro e il consulente privacy |
| Versione | 0.1 — 2026-10-02 |
| Documento del fascicolo | n. 12 — gate G6 |
| GAP | GAP-H10 |
| Responsabile | Titolare (funzione HR): [DA COMPILARE] |
| Riferimenti normativi | L. 300/1970 artt. 4 (come modificato dal D.Lgs. 151/2015) e 8; D.Lgs. 196/2003 artt. 113, 114; GDPR artt. 5, 6, 13, 88 |

> Inquadramento proposto (da verificare): il gestionale è uno **strumento utilizzato per rendere la prestazione**
> (art. 4, c. 2) — il tutor lo usa per consultare le lezioni, dichiarare disponibilità e registrare presenze — e non uno
> strumento con finalità di controllo a distanza (art. 4, c. 1). Non servono quindi accordo sindacale o autorizzazione
> dell'Ispettorato, **a condizione** che non vi siano funzioni di monitoraggio oltre a quelle necessarie. Le informazioni
> raccolte sono utilizzabili ai fini del rapporto di lavoro solo con questa informativa adeguata (art. 4, c. 3). Per i
> collaboratori autonomi l'art. 4 non si applica in quanto tale [DA VERIFICARE per le collaborazioni etero-organizzate,
> art. 2 D.Lgs. 81/2015], ma valgono GDPR e informativa. Non è un parere legale.

## Parte 1 — Informativa ai lavoratori e collaboratori

### 1.1 Strumento
Gestionale web del centro (portale tutor e area del centro), con account personale.

### 1.2 Informazioni registrate
| Informazione | Perché | Chi la vede |
|---|---|---|
| Disponibilità, eccezioni, assenze dichiarate | Pianificare le lezioni | Coordinatori; tu |
| Competenze abilitate | Assegnare lezioni ammissibili | Coordinatori, responsabile didattico; tu |
| Lezioni assegnate e carico pianificato in minuti | Rispettare limiti di carico e pause concordati | Coordinatori; tu |
| Presenze degli studenti che registri | Servizio alle famiglie e recuperi | Coordinatori; famiglie per il proprio figlio |
| Audit delle operazioni (chi, cosa, quando, oggetto, motivo) | Sicurezza e ricostruzione delle modifiche | Solo amministratori designati, con accesso tracciato |
| Log tecnici (errori, tempi, IP per eventi di sicurezza) | Funzionamento e sicurezza | Operations e fornitore tecnico |

### 1.3 Cosa il sistema non fa
Non registra posizione, tempo di connessione, movimenti del mouse o tasti; non registra le videolezioni; non calcola
indici di produttività, classifiche o valutazioni; non confronta i tutor tra loro; non raccoglie informazioni su opinioni
o vita privata (art. 8 dello Statuto).

### 1.4 Controlli possibili e loro modalità
- **Sicurezza**: verifiche automatiche su accessi anomali (es. molti login falliti) e operazioni sensibili; possibile sospensione temporanea dell'account per proteggere i dati.
- **Ricostruzione di un evento**: in caso di errore sul calendario, segnalazione di una famiglia o incidente, un amministratore designato consulta l'audit limitatamente all'evento, documentando il motivo.
- **Corretta registrazione delle presenze**: solo a campione o su segnalazione [DA DECIDERE se previsti].
- Gli esiti possono essere usati nel rapporto di lavoro **solo** nei limiti dell'art. 4, c. 3, con proporzionalità e nel rispetto delle regole sulla contestazione disciplinare.

### 1.5 Conservazione
Audit: [DA COMPILARE: 12–24 mesi], poi minimizzato; log tecnici: 30 giorni; dati operativi: come da informativa tutor/staff.

### 1.6 Diritti
Vedi `05-informativa-tutor-staff.md`, §7.

Per presa visione: Nome ______________________ Firma ______________________ Data __________

## Parte 2 — Policy d'uso dell'audit (interna)

1. **Finalità ammesse**: sicurezza; ricostruzione di modifiche, pubblicazioni, deleghe, inviti, export; risposta a interessati, autorità o giudice; gestione delle violazioni.
2. **Finalità vietate**: valutazione delle prestazioni, indicatori di produttività, confronto tra persone, controllo sistematico degli orari di lavoro tramite i log.
3. **Chi accede**: solo il profilo A (amministratore) designato per iscritto; il fornitore tecnico solo su richiesta tracciata del titolare. L'API `/api/v1/privacy/audit-events` è oggi riservata al ruolo CENTER [DA RESTRINGERE a un permesso specifico con MFA].
4. **Come si accede**: ogni consultazione ha motivo scritto e riferimento (pratica, incidente, richiesta) ed è a sua volta registrata [DA IMPLEMENTARE: audit delle letture dell'audit].
5. **Estrazioni**: solo tramite export protetto con audience nominativa e scadenza; vietate copie su strumenti personali.
6. **Uso disciplinare**: solo per dati raccolti per finalità ammesse e nel rispetto di questa policy; decisione del titolare con il consulente del lavoro.
7. **Cruscotti**: mostrano domanda scoperta, conflitti, recuperi e delivery fallite; mai metriche individuali di produttività (GAP-K04).
8. **Riesame**: annuale, con la DPIA.

Approvazione del titolare: ______________________ Data: __________
