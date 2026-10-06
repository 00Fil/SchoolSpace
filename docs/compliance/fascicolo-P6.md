# Fascicolo di conformità · evidenze dall'interfaccia (P6)

Criterio d'uscita della guida (P6): fascicolo di conformità **con evidenze prese dall'interfaccia**.
Ogni riga indica la schermata da cui catturare l'evidenza (screenshot + export JSON dove previsto), da salvare in
`docs/evidence/v0.9-p6/` con il nome indicato. Le evidenze vanno prese in staging con dati sintetici (C24).

| Controllo | Obbligo | Dove nell'interfaccia | Evidenza da salvare | Stato |
|---|---|---|---|---|
| C01 | Minimizzazione (art. 5.1.c, 25) | Portale genitore → La mia settimana: nessun nome di altri partecipanti | `c01-portale-gruppo.png` | da catturare |
| C02 | Riservatezza, minori (art. 32, 8) | Utenti e ruoli → revoca delega; portale genitore subito dopo: accesso negato | `c02-revoca.png`, `c02-negato.png` | da catturare |
| C03 | Registro dei trattamenti (art. 30) | Documento 01 firmato (fuori software) | `c03-registro.pdf` | documentale |
| C04 | Informative (artt. 12–14) | Primo accesso al portale: finestra «Informativa» bloccante; poi I miei dati: versione | `c04-presa-visione.png`, `c04-informativa.png` | da catturare |
| C05 | DPIA (art. 35) | Documento 06 firmato | `c05-dpia.pdf` | documentale |
| C06 | Valutazione DPO (art. 37) | Documento 07 | `c06-dpo.pdf` | documentale |
| C09 | Limitazione della conservazione (art. 5.1.e) | Privacy → Conservazione: regole approvate + ricevuta di simulazione ed esecuzione | `c09-regole.png`, `c09-ricevuta.json` | da catturare |
| C11 | Diritti degli interessati (artt. 15–22) | Portale → I miei dati (richiesta) → Privacy → Richieste (verifica, evasione) → Export (scaricato) | `c11-richiesta.png`, `c11-evasa.png`, `c11-export.png` | da catturare |
| C13 | Controllo a distanza (L. 300/1970 art. 4) | Privacy → Registro: avviso «non misura la produttività»; nessun cruscotto per persona | `c13-registro.png` | da catturare |
| C19 | Integrità (art. 32) | Privacy → Registro: voce di ogni scrittura con motivo | `c19-audit.png` | da catturare |
| C25 | Riconferma alla maggiore età (D07) | Privacy → Maggiore età (controllo, avvio) → portale studente (riconferma) → Registro (LINK_RECONFIRMED) | `c25-avvio.png`, `c25-portale.png`, `c25-audit.png` | da catturare |

C01–C06 sono i controlli richiesti dalla voce T6 della guida: C01, C02 e C04 ora hanno un'evidenza
nell'interfaccia; C03, C05 e C06 restano documenti da firmare a cura del titolare.

Firma del titolare: ____________________  Data: __________
