# Standard UI Lumen — vincolante

Riferimento unico: `docs/design/reference/lumen-dashboard-v5.2.html` (Lumen v5.2).
Base di codice: `frontend/src/lumen/` (`fonts.css`, `tokens.css`, `lumen.css`, `icons.svg`, font self-hosted).
La copia estratta è stata verificata al pixel contro il riferimento: 0 pixel diversi a 1440×1000, tema chiaro e scuro (`docs/design/reference/specimen-from-extracted.html`).

**Regola.** Ogni schermata nuova, o toccata da un incremento, segue questo standard in grafica, struttura, comportamento e cura del dettaglio. Una deroga va scritta in un ADR prima di implementarla. Non si consegna UI “provvisoria” con stile generico, `window.prompt/alert/confirm`, tabelle grezze o messaggi tecnici in primo piano.

## 1. Principi

1. **Superfici a strati, mai piatte.** `page` → `frame` (guscio arrotondato 36) → `module` (vetro, 28) → elementi `raised` (`surface-2` + luce interna + ombra morbida). Ogni livello ha un raggio più piccolo del contenitore.
2. **Il colore è significato, non decorazione.** Blu = azione primaria, selezione, “ora”. Viola = gruppo / nuovo. Verde = verifica, presente, completato. Ambra = da confermare, in evidenza. Rosso = conflitto, errore, distruttivo. Tutto il resto è neutro.
3. **Una sola azione primaria per vista** (`pill-btn primary` o `cta`). Le secondarie sono `sm`/`ghost`, le distruttive `danger` e stanno a destra, separate da `.grow`.
4. **Prevenire, non punire.** I conflitti si mostrano mentre si compila (`.conflict` con `role="alert"`) e propongono la correzione cliccabile: “Usa le 15:00 oppure assegna a Sara Bianchi”. Gli orari occupati sono marcati prima della scelta.
5. **Reversibile invece di “sei sicuro?”.** Le azioni annullabili danno un toast con **Annulla**. La conferma modale resta solo per ciò che è davvero irreversibile.
6. **Lo stato vive nell’URL.** Vista in `#/nome`, filtri e giorno in query (`?d=…&f=…`) con `history.replaceState`; ricaricare non perde il contesto.
7. **Parlare come una persona.** Frasi complete in italiano, soggetto concreto, prossimo passo esplicito (“Scegli un altro giorno con le frecce qui sopra.”). Codici, hash, UUID e nomi di stato interni vanno in “Dettagli tecnici”, mai nel titolo o nel messaggio principale.
8. **Movimento con massa.** Molle e decelerazioni, mai lineari; ogni animazione spiega un cambiamento (da dove viene, dove va). Un solo momento coreografato all’avvio.
9. **Ogni gesto ha l’equivalente da tastiera**, ogni hover ha l’equivalente touch.

## 2. Token (`tokens.css`)

Usare sempre le variabili; nessun colore, raggio, ombra o durata letterale nei componenti, salvo i bianchi traslucidi su superfici colorate già presenti nel riferimento.

| Gruppo | Token |
|---|---|
| Fondi | `--page` `--frame` `--solid` `--surface` `--surface-2` `--cell` `--cell-off` `--hatch` `--shell` `--scrim` `--scrim-soft` `--pop-shell` `--glass` `--glass-edge` |
| Testo | `--text` (primario), `--text-2` (secondario), `--text-3` (terziario, placeholder, etichette di colonna) |
| Linee | `--line` (bordo a riposo, 7%), `--line-2` (hover / campo, 12–13%) |
| Ombre | `--raise-hi` (luce interna 1px), `--raise` (elemento sollevato), `--float` (livelli) |
| Semantici | `--blue/-soft/-ink`, `--violet…`, `--green…`, `--amber…`, `--red…` — pieno per riempimenti, `-soft` per sfondi, `-ink` per testo su `-soft` |
| Avatar | `--t1…--t5` (tinte pastello; assegnazione stabile per persona) |
| Raggi | `--r-xl` 36 · `--r-lg` 28 · `--r-md` 18 · `--r-sm` 12 · `--pill` 999; locali: 14 campi, 7 tag, 20 box interni |
| Spazio | `--gap` 16 tra moduli; padding modulo 28 (16–20 su mobile); passo interno 8/10/12/14/18/22/24/28 |
| Tipografia | `--fs-xs` 12 · `--fs-s` 14 · `--fs-m` 16 · `--fs-l` 18 · `--fs-xl` 24 · `--fs-2xl` 36 · `--fs-3xl` 48 · `--fs-4xl` 72; valori ammessi fuori scala: 11, 13, 15, 17, 20, 22 |
| Movimento | `--spring` (.32,.72,0,1) spostamenti/ingressi · `--out` (.16,1,.3,1) colori/opacità · `--snap` (.34,1.4,.64,1) micro-rimbalzi di icone e spunte · `--press` (.2,.8,.2,1) pressione · `--d1` 180 · `--d2` 360 · `--d3` 640 · `--d4` 900 ms |

Tema chiaro e scuro sono entrambi di prima classe: `data-theme` su `<html>`, impostato da uno script inline **prima** del CSS (niente flash), preferenza `system | light | dark`, `meta theme-color` aggiornato, `color-scheme` coerente.

## 3. Tipografia

- Font unico **Bricolage Grotesque** variabile, self-hosted (OFL 1.1), `font-display:swap`, `font-optical-sizing:auto`.
- Titoli display: peso 420, `font-stretch` 84–86%, tracking −0.03/−0.035em, interlinea 1.02–1.1. Titoli di modulo: 24/450/92%/−0.015em.
- Pesi ammessi: 420 · 450 · 500 (nomi, voci) · 550 · 600 (tag, avatar) · 650 (oggi nel calendario). Niente bold 700 generico.
- Numeri, orari, importi, contatori: sempre `tabular-nums` (`.num`).
- `text-wrap: balance` sui titoli, `pretty` sui paragrafi; paragrafi a 48–60ch.
- Ellissi su una riga con `min-width:0` sul contenitore flex: nessun testo deve mai sfondare un layout.

## 4. Struttura

- **Guscio**: `.frame` (margine 16, griglia `80px | 1fr`) → `.rail` sticky (logo, nav con `.puck` animato, impostazioni in fondo, tooltip `.tip`) → `.content` con `.topbar` (ricerca con `kbd` Ctrl/⌘ K, persone, CTA “Nuova …” con isola “+”, tema, notifiche con punto, avatar) → `main` con una `.view` per rotta.
- **Vista principale**: `.module.planner` con `.m-head` (titolo `h-display` + `.sub-line` riassuntiva a sinistra, `.controls` a destra), contenuto, legenda/aiuto in fondo. Sotto, moduli secondari in `.trio`/`.two`.
- **Pagine elenco**: `.page-head` (titolo, frase che spiega la pagina, toolbar), `.stats` (3 numeri chiave), `.toolbar` con `field-search` + `seg-ctl`, `table.list` a righe-carta cliccabili e accessibili da tastiera, `.empty` che spiega e suggerisce.
- **Impostazioni**: `.setting` = titolo + spiegazione a sinistra, controllo a destra.
- **Breakpoint**: ≤1280 il trio diventa 2+1 e `.two` una colonna; ≤767 niente rail, `tabbar` vetro fissa in basso con puck, topbar compatta (solo icone, CTA circolare), sheet e modal diventano fogli dal basso, griglie a una colonna, colonne `hide-m` nascoste, `safe-area-inset` rispettate.
- Scorrimento orizzontale solo dentro `.scroller` / `.list-wrap`, con colonna nomi `sticky`; la pagina non scorre mai di lato.

## 5. Componenti (classi in `lumen.css`)

- **Pulsanti**: `pill-btn` 48 (sm 40, nei footer 44) · `primary` · `ghost` · `danger` · `island` (icona finale nella sua isola che si muove in hover; `cta` ruota il “+” di 90°) · `circle` 48/40 icona · scala .97 alla pressione · `aria-pressed/expanded` disegnano l’anello blu.
- **Identità**: `av` iniziali su tinta `t1–t5`, `stack` sovrapposto con `+N`.
- **Etichette**: `tag` (pallino + testo, 24px, toni semantici, `plain` neutro) per stati; `chip` (36px) per fatti (orario, data, persona) ed eventualmente cliccabile.
- **Selettori**: `seg-ctl` con `thumb` che scivola; `choice` (radio a pillola con avatar); `check` (spunta animata); `pick` + `cal` (calendario personalizzato con oggi, marcatori di carico, tastiera); `wheel` (ruota 3D a scatto per orari e durate, voci occupate con punto rosso, `role="spinbutton"`); `combo` + `suggest` (suggerimenti con frecce/Invio). Niente `<input type="date">` o `<select>` nativi nei flussi principali.
- **Campi**: `fld` > `label` + `inp` (48, raggio 14, focus anello 2px blu) + `err` (visibile con `.fld.bad`); opzionale scritto “(facoltativo)” in `muted`. Validazione al submit, focus sul primo campo errato, errore rimosso appena si corregge.
- **Dati**: `stat`, `chart` a colonne e `hbars` con crescita a molla, `facts` (dl a due colonne) nelle schede.
- **Griglia agenda**: intestazioni slot `c-head` (slot corrente pieno blu con “Ora”), nomi `c-name` sticky con carico in ore, celle `cell` (+ in hover per creare; `off` tratteggiate e unite con “Non disponibile”; `past` attenuate), lezioni `les` colorate per tipo con icona, sottotitolo, pillola di stato se c’è spazio, `wait` in vetro, `done` attenuate, punto pulsante se in corso, maniglia `grip` di durata; `nowline` tratteggiata che scorre; `zone` di anteprima (blu ok, rossa occupato, viola nuova) con orario e durata al centro.

## 6. Livelli

| Livello | Uso | Regole |
|---|---|---|
| `pop` | filtri, notifiche, persone, scelta giorno | ancorato, `scrim soft`, chiusura con clic esterno o Esc, una sola pop aperta, riclic sull’ancora la chiude |
| `sheet` | dettaglio di un oggetto (lezione, studente, tutor) | da destra 460px; dal basso su mobile; header con tag di tipo e stato, titolo 36, `facts`, footer azioni |
| `modal` | creare/modificare, conferme irreversibili | centrato 560px; dal basso su mobile; `lead` che spiega; footer: Chiudi a sinistra delle azioni |
| `cmd` | Ctrl/⌘ K o `/` | gruppi Azioni/Persone/Lezioni, frecce + Invio, `aria-activedescendant` |
| `toast` | esito di ogni mutazione | pillola scura in basso al centro, massimo 3, 5,2 s, pausa in hover, azione “Annulla” quando reversibile, `role="status"` |

Tutti i livelli: `bezel` (anello traslucido 6px) + `core`; scrim sfocato; pila unica con Esc sul livello in cima; trappola di focus (non per pop); autofocus sul primo campo; ritorno del focus all’elemento che ha aperto; `aria-modal`, `aria-labelledby`, `aria-expanded` sull’ancora. Con modifiche non salvate la chiusura non usa `confirm()`: il footer si trasforma in “Hai modifiche non salvate. · Continua a modificare · Chiudi senza salvare”, più `beforeunload`.

## 7. Movimento

- Pressione: scala .97 (`--press`, 180 ms). Hover di carte e lezioni: −2px con ombra più lunga.
- Ingressi livelli: opacità `--out` + trasformazione `--spring` `--d3`; uscita rimossa dopo ~460 ms.
- Cambio rotta: View Transitions (0,5 s, `--spring`), scroll in alto, focus su `main`. Cambio tema: rivelazione circolare dal pulsante.
- Dopo uno spostamento o ridimensionamento: FLIP dalla posizione precedente (260 ms). Conferma: piccolo rimbalzo .96 → 1.03 → 1.
- Titolo che cambia (giorno): esce verso l’alto/basso secondo la direzione, rientra a molla.
- Avvio: lezioni che crescono da sinistra sfalsate per riga e orario, poi testo; la linea “ora” parte dopo 520 ms. Una volta sola.
- `prefers-reduced-motion` e l’impostazione “Animazioni: Ridotte” annullano durate e ritardi; `prefers-reduced-transparency` rimuove le sfocature.

## 8. Interazioni

- Mouse: trascinamento attivo dopo 6 px; fantasma a scala 1.02; originale al 30%; autoscroll ai bordi; rilascio non valido → toast con il motivo e ritorno animato. Trascinare su celle libere crea un intervallo (si ferma sugli occupati) e apre il modulo precompilato.
- Touch: pressione lunga 320 ms con feedback di pressione e vibrazione 8 ms; movimento >10 px prima dell’attivazione = scroll, si annulla; fantasma sollevato di 28 px sopra il dito; maniglia di durata immediata e più larga.
- Tastiera: Alt+frecce sposta, Alt+Shift+←/→ cambia durata, Ctrl/⌘ K e `/` ricerca, `N` nuova lezione, `[` `]` giorno precedente/successivo, ruote con frecce/PagSu/PagGiù/Home/Fine; scorciatoie disattivate mentre si scrive o con un livello aperto.
- Testi d’aiuto diversi per puntatore fine e grossolano (`hover:none`).

## 9. Accessibilità (minimo, non opzionale)

Link “Vai al contenuto”; landmark e `aria-label` sulle nav; `aria-current="page"`; ogni pulsante solo-icona ha etichetta; celle e lezioni hanno etichette parlanti (“Luca Ferri, singola, con Marta Conti, 15:00–16:00, confermata”); `aria-live` per riepiloghi e orari selezionati; focus visibile 2px blu con offset 3; bersagli ≥40px (48 preferito); contrasto AA con i token `-ink`; nessuna informazione affidata al solo colore (legenda e tag testuali).

## 10. Testi

- Date `it-IT`, prima lettera maiuscola a inizio frase (“Giovedì 1 ottobre”), “Oggi, giovedì 1 ottobre”. Intervalli con trattino lungo: 15:00–16:00. Durate: “30 min”, “1 ora”, “1 h 30”, “2 ore”. Importi `Intl.NumberFormat` EUR.
- Apostrofo tipografico ’ e puntini di sospensione … nei placeholder (“Es. Luca Ferri…”).
- Toast: oggetto + esito + contesto (“Lezione creata: Luca Ferri, giovedì 1 ottobre alle 15:00”). Vuoti: frase in grassetto + suggerimento.

## 11. Adattamento al gestionale

Il prodotto resta sperimentale con dati sintetici e comandi versionati/idempotenti; lo standard si applica così:

- Stato sperimentale, database, flag: `tag` (`amber` per “Sperimentale”, `plain` per ambiente) nella `sub-line`, non banner tecnici.
- Errori API: messaggio umano mappato dal `reason_code` + azione suggerita; codice, revisione, chiave di idempotenza e hash in un blocco “Dettagli tecnici” richiudibile. Il conflitto di revisione propone “Ricarica e riprova”.
- **Niente Annulla finto.** L’Annulla compare solo se il backend offre l’operazione inversa. Pubblicazione del calendario, cancellazione con storico e simili usano un modal di conferma con conseguenze esplicite e motivo obbligatorio dentro il modulo (mai `window.prompt`).
- “Riprova la stessa operazione” riusa la stessa chiave di idempotenza ed è detto in chiaro.
- Le viste tecniche (laboratorio CP-SAT, job, configurazione) usano gli stessi componenti: `stats`, `list`, `tag`, `sheet` per il dettaglio, `facts` per i metadati.

## 12. Implementazione

- `import "./lumen/index.css"` una sola volta; gli stili di schermata stanno in file dedicati e usano solo token.
- Primitive React da costruire una volta e riusare: `LayerStack` (pop/sheet/modal, focus, Esc, guard), `Toasts` (con Annulla), `SegCtl`, `Wheel`, `CalendarPicker`, `Combo`, `Choice`, `Field`, `Icon` (sprite `icons.svg`, 24px, tratto 1.4), `Avatar/Stack`, `Tag`, `CommandPalette`, `useHashRoute` (vista + query), `useTheme`, `useMotion`.
- Icone: solo dallo sprite (28 simboli); nuove icone nello stesso stile (viewBox 24, tratto 1.4, estremità arrotondate).

## 13. Definition of Done UI

- [ ] Solo token e componenti Lumen; nessun dialog nativo del browser.
- [ ] Tema chiaro e scuro verificati; nessun flash al caricamento.
- [ ] Schermate a 1440, 1280 e 390 px senza overflow orizzontale della pagina né testi tagliati male.
- [ ] Stati vuoto, caricamento, errore, conflitto e successo progettati e scritti.
- [ ] Percorso completo solo da tastiera; focus che torna al punto giusto; Esc coerente.
- [ ] Touch: bersagli ≥40px, gesti con alternativa, nessun hover indispensabile.
- [ ] Movimento ridotto e trasparenza ridotta rispettati.
- [ ] Ogni mutazione ha un toast; Annulla solo se reale.
- [ ] URL ripristina vista e filtri.
- [ ] Confronto visivo affiancato con il riferimento, prove salvate in `docs/evidence/`.

## 14. Stato della migrazione (v0.6)

Completata in v0.6: guscio e tutte le schermate v0.5 usano le primitive di `frontend/src/ui/` (`core`, `controls`, `layers`, `prefs`, `route`) sopra `frontend/src/lumen/`; estensioni applicative solo a token in `frontend/src/app.css`. Non restano `window.prompt`, `<select>`, `<input type="date">`, orari ISO digitati né codici interni in primo piano. Eccezioni consapevoli: gli editor JSON della configurazione di prova e del Laboratorio restano testuali (chiuse in v0.7, vedi §15) e il nome dell'anno didattico è un campo libero. Prove: `docs/evidence/v0.6-*` (1440/1280/390, chiaro/scuro) e collaudo E2E descritto in `docs/qa-report.md`.

## 15. Aggiornamento v0.7

- **Eccezioni v0.6 chiuse**: la configurazione di prova usa moduli schema-driven (`frontend/src/screens/configForms.tsx`): riferimenti → `Combo` per nome, enum → `SegCtl`, date → `DateField`, orari → `Wheel` a 15', booleani → `Check`. Il JSON resta come modalità «JSON avanzato», sincronizzata in entrambe le direzioni. Il Laboratorio mostra un riepilogo leggibile con inclusione/esclusione delle richieste; il JSON è la vista avanzata.
- **Contrasto WCAG 2.2 AA** (audit axe-core): in `app.css` il testo terziario è `#6D707A` (chiaro) / `rgba(236,238,243,.62)` (scuro); i riempimenti con testo bianco usano `--fill-blue` `#466EDB` e `--fill-violet` `#7A60D7` anche nel tema scuro; il testo delle lezioni è bianco pieno; gli orari non disponibili della ruota usano `--text-2` barrato con il punto rosso. I token originali di `frontend/src/lumen/` non sono modificati: le correzioni sono override documentati.
- **Lezioni cancellate** nelle card: bordo tratteggiato tenue e titolo barrato, senza opacità (che abbassava il contrasto).
- **Portali**: «La mia settimana» riusa `DayStrip` e le card `.event` della Panoramica; nessuna azione distruttiva, solo lettura.
- **Spiegare prima di rifiutare**: dove il server può calcolare l'esito (spostamenti), la UI marca le opzioni non valide e mostra il motivo in italiano prima dell'invio; il server rivalida comunque al salvataggio.
