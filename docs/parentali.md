# Percorsi parentali — guida v0.2

## Significato recepito
Studenti che svolgono con il centro tutto il programma scolastico, in tutte le materie. La gestione degli account dei genitori resta separata dal percorso didattico.

## Primo percorso nell'interfaccia
1. Accedere come operatore del centro e aprire **Percorsi parentali**.
2. Aggiungere le materie e creare un percorso con anno didattico, livello, date e **tutte** le materie previste.
3. Iscrivere studenti di prova già creati nell'admin, con periodi compresi nel percorso.
4. Per lezioni di gruppo, creare sottogruppi per materia, approvare esplicitamente la compatibilità e aggiungere i membri.
5. Aggiungere un blocco per ogni materia/iscritto o sottogruppo: obiettivo, periodo, modalità, durata, sessioni, minuti, priorità e domanda obbligatoria.
6. Controllare **Copertura del programma dichiarato**: ogni materia deve coprire tutto il periodo dell'iscritto.
7. Premere **Deriva le richieste didattiche**. Il comando è versionato, idempotente e atomico; crea domanda, **non** lezioni.

I minuti settimanali sono per studente. Un gruppo di due con 60 minuti produce una richiesta di una sessione da 60 minuti, non due lezioni indipendenti. Il beneficio didattico riguarda entrambi gli studenti.
Blocchi di periodi successivi non vengono sommati come se fossero simultanei. Un buco di copertura blocca la derivazione.

## Esempio sintetico opzionale
Dopo l'avvio locale e la creazione del proprio superuser:

```bash
docker compose exec backend python manage.py record_parentali_scope
docker compose exec backend python manage.py seed_parentali_demo --actor NOME_UTENTE_CENTRO
```

Non crea account o password. Crea 4 studenti sintetici, 2 materie **illustrative**, 4 sottogruppi di 2 e 4 richieste. Nessun tutor viene assegnato, nessuno spazio prenotato e nessuna lezione pubblicata.
Le 2 materie del demo **non** rappresentano un programma scolastico reale o sufficiente. Il centro deve configurare l'elenco reale per ciascuna classe.
Il seed usa identificatori stabili e la ripetizione non duplica gli studenti o le richieste.

## Accessi e privacy
Solo il centro crea percorsi, iscrizioni, sottogruppi e blocchi o deriva richieste. Tutori/studenti con diritto valido vedono percorsi e riepiloghi riferiti esclusivamente agli studenti autorizzati.
I nomi degli altri membri del gruppo non compaiono nelle richieste o nel riepilogo familiare. La revoca della delega viene ricontrollata a ogni richiesta.
Il dettaglio completo dei blocchi e dei gruppi rimane centro-only; un portale tutor didattico completo è ancora da implementare.

## Revisioni e limiti
Dopo derivazione, il percorso è congelato per le nuove scritture di curriculum/iscrizioni/membri. Le revisioni future richiedono un flusso dedicato non ancora implementato; non usare il database o l'admin per aggirare il blocco.
Gruppi online richiedono capienza esplicita. La capienza due vale per le lezioni in presenza, non per la coorte e non automaticamente per l'online.
I servizi salvano un audit limitato delle mutazioni del percorso e ricevute di idempotenza; audit append-only a livello DB e retention sono ancora da implementare.
Non sono implementati gli appuntamenti, le presenze, le verifiche didattiche, la contabilità né la certificazione di un programma completato.
