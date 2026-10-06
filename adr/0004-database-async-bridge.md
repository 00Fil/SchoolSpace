# ADR04 — bridge DB e job asincroni sperimentali
Stato: scelta di prototipo, non baseline approvata G1/G2/G3.

Una settimana locale e schema DTO chiuso, per esercitare dominio→snapshot→worker prima delle booking. Coda persistente nel DB; Redis trasporta e non decide stato. Worker separato, confronto revisione e hash, validatore indipendente, nessun publish. Lock globale breve per ORM application; raw SQL/through non certificati. Canonicalità richiesta/settimana/progressivo, non ancora riconciliazione con calendario pubblico. Schema 0.4 include horizon_minutes per DST. Metadati ambiente impediscono claim con build/timezone/solver differenti, senza promettere identiche soluzioni.

Alternative rinviate: sei settimane/720 unità, concorrenza distribuita, solver completo e pubblicazione. Non accettabili: callback broker pre-commit, fallback sincrono nascosto, mancanza disponibilità trattata come libera, ottimalità o G3 dichiarati sulla sola UI.
