# 07 — Primo gestore del centro (P1, guida v3.1)

Quando: installazione nuova, nessun account con ruolo CENTER.

1. Sul server, con lo stack di produzione avviato (`DJANGO_DEBUG=0`):
   `docker compose -f compose.prod.yaml exec web python manage.py createsuperuser`
   Usa un'email nominativa (non condivisa) e una password lunga.
2. Accedi all'interfaccia con quelle credenziali. Al primo accesso l'app chiede di configurare
   la MFA (app di autenticazione): scansiona il QR, inserisci il codice, **salva i codici di recupero**
   in un luogo sicuro offline.
3. In «Utenti e ruoli» invita subito un **secondo gestore**: serve per azzerare la MFA di un collega
   (nessuno può azzerare la propria) e per non restare senza amministratori.
4. Da qui in poi l'admin Django resta solo per emergenze; ogni azione lì finisce comunque nell'audit.
5. Prova di uscita P1: crea una famiglia, due figli, un genitore (invito + verifica relazione) e un
   tutor (con invito) dalle schermate «Anagrafica» e «Tutor», senza usare l'admin Django.

Verifica: in «Utenti e ruoli» compaiono due gestori; nel registro audit ci sono gli eventi
`TUTOR_CREATED`, `FAMILY_CREATED`, `STUDENT_CREATED`, `INVITE_CREATED`.
