# Modello di accordo sul trattamento dei dati (art. 28 GDPR)

| Campo | Valore |
|---|---|
| Stato | **BOZZA / MODELLO** — da adattare a ciascun fornitore e revisionare con il legale |
| Versione | 0.1 — 2026-10-02 |
| Documento del fascicolo | n. 6 — gate G6 (firmato **prima del primo import di dati reali** per il fornitore di sviluppo, GAP-H06) |
| GAP | GAP-H03 |
| Responsabile | Titolare del trattamento: [DA COMPILARE] |
| Riferimenti normativi | GDPR artt. 28, 29, 32–36, 44–49; Decisione di esecuzione (UE) 2021/915 (clausole contrattuali tipo tra titolari e responsabili); Linee guida EDPB 07/2020 sui concetti di titolare e responsabile |

> Uso del modello: per i grandi fornitori cloud (hosting, DB, email) di norma si accetta il DPA standard del fornitore;
> in quel caso questo modello serve come **lista di confronto** (colonna "Verifica" dell'allegato C) e non va firmato.
> Per il fornitore di sviluppo e manutenzione e per i fornitori minori si propone di firmarlo. Non è un parere legale.

---

## ACCORDO PER IL TRATTAMENTO DI DATI PERSONALI

tra **[DA COMPILARE: ragione sociale del centro]**, con sede in [DA COMPILARE], in persona di [DA COMPILARE]
("**Titolare**")
e **[DA COMPILARE: ragione sociale del fornitore]**, con sede in [DA COMPILARE], in persona di [DA COMPILARE]
("**Responsabile**"),
collegato al contratto principale [DA COMPILARE: titolo, data] ("**Contratto**").

### Art. 1 — Oggetto
1.1 Il Responsabile tratta dati personali per conto del Titolare esclusivamente per eseguire il Contratto, secondo
l'Allegato A (descrizione del trattamento) e le istruzioni documentate del Titolare, comprese quelle relative ai
trasferimenti verso paesi terzi (art. 28.3.a).
1.2 Se il Responsabile ritiene che un'istruzione violi il GDPR o altre norme, ne informa immediatamente il Titolare (art. 28.3, ultimo comma).

### Art. 2 — Obblighi del Responsabile
Il Responsabile:
a) tratta i dati solo su istruzione documentata del Titolare, salvo obblighi di legge da comunicare preventivamente;
b) garantisce che le persone autorizzate al trattamento si siano impegnate alla riservatezza o abbiano un obbligo legale di riservatezza (art. 28.3.b) e siano formate;
c) adotta le misure tecniche e organizzative dell'Allegato B (art. 32);
d) non ricorre a sub-responsabili senza autorizzazione scritta, secondo l'art. 3;
e) assiste il Titolare, con misure adeguate, nel dare seguito alle richieste degli interessati (artt. 12–22) entro [DA COMPILARE: 5] giorni lavorativi dalla richiesta;
f) assiste il Titolare negli obblighi degli artt. 32–36 (sicurezza, violazioni, DPIA, consultazione preventiva);
g) alla cessazione, a scelta del Titolare, cancella o restituisce tutti i dati e le copie entro [DA COMPILARE: 30] giorni, rilasciando attestazione scritta, salvo obblighi di conservazione di legge (art. 28.3.g); i backup cifrati del Responsabile scadono secondo il loro ciclo naturale, entro [DA COMPILARE] giorni;
h) mette a disposizione tutte le informazioni necessarie a dimostrare il rispetto dell'art. 28 e consente attività di revisione, comprese le ispezioni, del Titolare o di un auditor incaricato, con preavviso di [DA COMPILARE: 15] giorni; certificazioni di terza parte (ISO/IEC 27001, SOC 2 Tipo II) possono sostituire l'ispezione in loco salvo violazioni;
i) tiene il registro ex art. 30.2;
j) non usa i dati per finalità proprie (inclusi addestramento di modelli, statistiche commerciali, profilazione).

### Art. 3 — Sub-responsabili
3.1 Il Titolare concede un'autorizzazione [DA COMPILARE: specifica / generale] ai sub-responsabili dell'Allegato D.
3.2 In caso di autorizzazione generale, il Responsabile informa il Titolare almeno [DA COMPILARE: 30] giorni prima di aggiungere o sostituire un sub-responsabile; il Titolare può opporsi per motivi ragionevoli e, se il disaccordo persiste, recedere senza penali.
3.3 Il Responsabile impone ai sub-responsabili gli stessi obblighi del presente accordo e resta pienamente responsabile del loro operato (art. 28.4).

### Art. 4 — Violazioni di dati personali
4.1 Il Responsabile notifica al Titolare ogni violazione **senza ingiustificato ritardo e comunque entro [DA COMPILARE: 24] ore** dalla scoperta, all'indirizzo [DA COMPILARE] e al numero di reperibilità [DA COMPILARE].
4.2 La notifica contiene almeno: natura della violazione, categorie e numero approssimativo di interessati e registrazioni (indicando se riguarda minori), probabili conseguenze, misure adottate o proposte, punto di contatto. Le informazioni non disponibili subito sono fornite in fasi successive.
4.3 Il Responsabile conserva le evidenze (log, audit) e non comunica la violazione a interessati o autorità senza accordo del Titolare, salvo obbligo di legge.

### Art. 5 — Trasferimenti verso paesi terzi
5.1 Nessun trasferimento fuori dallo SEE senza autorizzazione scritta del Titolare e senza uno strumento del Capo V (decisione di adeguatezza, inclusa l'adesione certificata al EU–US Data Privacy Framework; clausole contrattuali tipo, Decisione (UE) 2021/914; altre garanzie dell'art. 46).
5.2 L'accesso remoto da un paese terzo (incluso il supporto tecnico) è un trasferimento ai fini del presente articolo.
5.3 In caso di richiesta di accesso da parte di autorità di un paese terzo il Responsabile informa il Titolare, se consentito, e contesta le richieste non conformi.

### Art. 6 — Obblighi specifici per il fornitore di sviluppo e manutenzione
6.1 Accesso ai dati reali solo quando necessario (pilota, assistenza, restore), su richiesta tracciata del Titolare, con account **nominativi**, MFA, privilegio minimo e durata limitata; ogni accesso è registrato e il registro è consegnato su richiesta.
6.2 Nessuna copia di dati reali su postazioni locali, ambienti di sviluppo, test o demo; per i test si usano solo dati sintetici.
6.3 Repository, contratti (OpenAPI, schemi del solver) e account cloud sono intestati al Titolare o a lui consegnati; restano a carico del fornitore gli obblighi di manutenzione di sicurezza previsti dal Contratto (GAP-N05).
6.4 Le persone del fornitore che accedono ai dati sono elencate nell'Allegato E e designate per iscritto.

### Art. 7 — Durata, responsabilità, legge applicabile
7.1 L'accordo segue la durata del Contratto e sopravvive per gli obblighi di cancellazione e riservatezza.
7.2 Responsabilità secondo l'art. 82 GDPR e il Contratto [DA COMPILARE: eventuali limitazioni, da valutare con il legale].
7.3 Legge italiana; foro [DA COMPILARE].

Luogo e data: __________ Il Titolare: ______________ Il Responsabile: ______________

---

### Allegato A — Descrizione del trattamento

| Voce | Contenuto [DA ADATTARE per fornitore] |
|---|---|
| Servizio | [es. hosting dell'applicazione e del database; invio email transazionali; error tracking; sviluppo e manutenzione] |
| Natura e finalità | [es. conservazione, elaborazione, backup; invio; raccolta errori; assistenza e restore] |
| Categorie di interessati | Studenti (anche minorenni), genitori e tutori legali, tutor, staff |
| Categorie di dati | Vedi registro TR-01…TR-11; per l'email solo indirizzo, tipo di evento, data/ora e materia; per l'error tracking ID pseudonimi e metadati tecnici con scrubbing |
| Categorie particolari | Nessuna |
| Durata | Durata del Contratto |
| Luoghi del trattamento | [DA COMPILARE: region UE] |
| Retention presso il fornitore | [DA COMPILARE coerente con D09: es. log email ≤ 30 giorni; eventi di error tracking ≤ 30 giorni; backup 7–35 giorni] |

### Allegato B — Misure tecniche e organizzative minime
Cifratura in transito (TLS 1.2+) e a riposo; controllo degli accessi con MFA e privilegio minimo; segregazione dei
clienti; registrazione degli accessi amministrativi; gestione delle vulnerabilità e patch; backup e test di ripristino;
continuità operativa; formazione e riservatezza del personale; cancellazione sicura; gestione degli incidenti con
notifica entro i termini dell'art. 4; certificazioni [DA COMPILARE].

### Allegato C — Lista di confronto con il DPA standard del fornitore
Per ogni voce: ☐ presente ☐ assente ☐ insufficiente — nota.
Istruzioni documentate · riservatezza del personale · misure art. 32 · sub-responsabili e preavviso · assistenza diritti ·
assistenza artt. 32–36 · termine di notifica delle violazioni · cancellazione/restituzione · audit · registro 30.2 ·
trasferimenti e strumento Capo V · divieto di uso per finalità proprie · region dei dati e dei backup.

### Allegato D — Sub-responsabili autorizzati
| Nome | Servizio | Sede / luogo del trattamento | Strumento Capo V se extra-SEE |
|---|---|---|---|
| [DA COMPILARE] | | | |

### Allegato E — Persone del Responsabile con accesso ai dati reali (solo fornitore di sviluppo)
| Nome | Ruolo | Ambito | Data designazione | Data cessazione |
|---|---|---|---|---|
| [DA COMPILARE] | | | | |
