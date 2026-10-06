# ADR 0002 — Parentali come programma scolastico completo

Stato: significato funzionale confermato dal committente in chat; schema e policy restano esplorativi.

Il committente specifica che i parentali sono studenti che devono svolgere tutto il programma scolastico e tutte le materie con il centro.
`HOME_EDUCATION` non significa semplicemente accesso di un genitore al calendario. La gestione genitori/tutori resta indipendente.

## Conseguenze v0.2
- Percorso per anno e livello, con materie obbligatoriamente dichiarate dal centro.
- Coorte di iscritti separata dai sottogruppi delle sessioni.
- Blocchi con materia, obiettivo interno, periodo, destinatario, minuti, durata/sessioni, modalità, priorità e obbligatorietà esplicite.
- Richiesta derivata univoca per blocco, con partecipanti materializzati per l'intero periodo valido e fingerprint di origine.
- Un gruppo in presenza può avere solo due partecipanti; un gruppo di tre non viene spezzato automaticamente.
- Nessuna somma di blocchi sovrapposti per studente/materia. Per più insegnamenti concomitanti legittimi della stessa materia servirà un ADR con unità canoniche più dettagliate.
- Cambi membri interni a un blocco richiedono segmentazione; revisione di un curriculum già derivato non implementata e perciò bloccata.
- Riepiloghi: minuti settimanali richiesti per segmento. Ore calendarizzate e presenze sono non disponibili, non false cifre zero.

Il programma completo dipende dall'elenco delle materie dichiarato dal centro: non viene verificata la conformità ai programmi ministeriali.
Nessuna certificazione, obbligo scolastico assolto o credito riconosciuto è inferito. G1 e D02–D09 restano da chiudere.
