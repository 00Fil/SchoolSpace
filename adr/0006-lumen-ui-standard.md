# ADR06 — standard UI Lumen v5.2
Stato: accettato dal committente come riferimento obbligatorio per tutta la UI.

Il file `docs/design/reference/lumen-dashboard-v5.2.html` definisce grafica, struttura, comportamenti e livello di dettaglio. Token, componenti, font (Bricolage Grotesque, OFL, self-hosted) e icone sono estratti in `frontend/src/lumen/` come copia fedele, verificata al pixel (0 differenze, chiaro e scuro). Le regole operative e la Definition of Done sono in `docs/design/ui-standard.md`.

Conseguenze: nessuna nuova schermata con lo stile generico v0.5; niente dialog nativi; stato in URL; temi chiaro/scuro; accessibilità e movimento ridotto obbligatori. Annulla solo per operazioni realmente reversibili lato backend; le operazioni irreversibili restano confermate in modal con motivo. Le deroghe richiedono un ADR. La UI v0.5 va migrata prima di estendere le funzioni.
