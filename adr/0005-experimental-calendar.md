# ADR05 — calendario transazionale sperimentale
Stato: incremento di prototipo, nessun gate approvato.

PG reale richiesto per mutazioni, default EXPERIMENTAL_CALENDAR=0. Distinguere publishable (produzione=false) ed experimental_publish_available. Unico centro, lock globale breve, versioni e idempotenza; snapshot immutabile più Publication separata, nessuna riscrittura della proposta storica. Partecipanti materializzati e prenotazioni FK concrete, GiST ed esatta completezza al commit.

Nuove proposte riconciliano domanda e KEEP. Nessuno sblocco globale/REPLACE/CANCEL implicito. Cancellata non elimina unità canonica; nuova assegnazione richiede proposta e approvazione, non recupero autonomo. Spostamento di un solo evento futuro, stessa settimana e risorse invarianti. Eventi persistenti senza delivery/email: non presentare come outbox completa.

Ruoli/deleghe nelle revisioni conservative, account fresco autorizzato sotto lock. PG UTF8 verificato. Raw SQL/DDL amministrativo non universale né produzione protetta: ruoli operativi, governance/retention e gate restano obbligatori. Alternative rinviate: series edits, completezza degli obiettivi, multi-ruolo calendario e produzione.
