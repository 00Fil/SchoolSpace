# ADR 0003 — Prototipo isolato del pianificatore

Stato: esplorazione tecnica non vincolante prima dei gate, non approvazione G1/G2/G3.

Si introduce OR-Tools CP-SAT con un contratto sintetico chiuso, una ricerca bounded e un validatore indipendente, per verificare i vincoli principali senza impegnare lezioni reali.
L'API di simulazione è sincrona e riservata allo sviluppo; non viene spacciata per il worker asincrono normativo.
I candidati hanno inizi enumerati integralmente entro un limite rigido. Superamento del limite blocca l'esecuzione; nessuna impossibilità viene dedotta da tagli euristici.
Il solo vettore implementato è copertura P0/P1/P2 in minuti per beneficiario. Gli altri livelli del paper rimangono espliciti gap; non sono ignorati da un'esecuzione operativa perché quella non esiste ancora.
Appuntamenti già pubblicati non sono letti dal database: eventuali blocchi sono parte del DTO sintetico. La validità di una proposta non garantisce alcuna prenotazione.
Tutti gli esiti sono non pubblicabili. Snapshot persistenti, revisioni globali, job, benchmark baseline e calendario anti-collisione restano futuri deliverable dei rispettivi gate.
