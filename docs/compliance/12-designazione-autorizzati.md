# Atti di designazione delle persone autorizzate e istruzioni operative

| Campo | Valore |
|---|---|
| Stato | **BOZZA / MODELLO** — una designazione per persona o per profilo, firmata per ricevuta |
| Versione | 0.1 — 2026-10-02 |
| Documento del fascicolo | n. 9 — bozza a G2, firmate a G6 |
| GAP | GAP-H10 |
| Responsabile | Titolare del trattamento: [DA COMPILARE] |
| Riferimenti normativi | GDPR artt. 29, 32.4; D.Lgs. 196/2003 art. 2-quaterdecies; paper §10.1 (matrice degli accessi) |

> Le designazioni sono coerenti con i ruoli applicativi (`RoleGrant`): il ruolo nel sistema non va assegnato prima
> della firma della designazione corrispondente. Non è un parere legale.

## 1. Profili di autorizzazione

| Profilo | Ruolo applicativo | Ambito dei dati | Operazioni consentite | MFA |
|---|---|---|---|---|
| A — Amministratore del centro | CENTER (proprietario/operatore) | Configurazione, operatori, deleghe, audit | Gestione operatori, ruoli e deleghe; lettura audit; export governati | Obbligatoria |
| B — Coordinatore | CENTER (coordinatore) | Studenti, famiglie, tutor, calendario | Pianificare, validare, **pubblicare**, spostare, gestire conflitti, presenze con correzione auditata | Obbligatoria |
| C — Segreteria | CENTER (operatore) [DA CONFERMARE se ruolo distinto] | Anagrafiche e contatti | Inserimento e rettifica anagrafiche, inviti dopo verifica della relazione | Obbligatoria |
| D — Responsabile didattico | CENTER (didattica) | Competenze, gruppi, percorsi | Approvare competenze, gruppi e curriculum | Obbligatoria |
| E — Tutor | TUTOR | Propri dati; studenti delle proprie lezioni (dati minimi) | Disponibilità proprie, presenze delle lezioni assegnate, proposte di modifica | Consigliata [DA DECIDERE] |
| F — Operatore tecnico del fornitore | Accesso infrastruttura (non utente applicativo) | Solo su richiesta tracciata | Assistenza, restore — vedi accordo art. 28 art. 6 | Obbligatoria |

## 2. Modello di atto di designazione

**[DA COMPILARE: nome del centro]**, titolare del trattamento,
visto l'art. 29 del Regolamento (UE) 2016/679 e l'art. 2-quaterdecies del D.Lgs. 196/2003,

**designa** [DA COMPILARE: nome e cognome], [DA COMPILARE: qualifica — dipendente / collaboratore], quale **persona
autorizzata al trattamento** dei dati personali nell'ambito del **profilo [A/B/C/D/E]** descritto al §1, per le finalità
del registro dei trattamenti (TR-[DA COMPILARE]), a decorrere dal [DA COMPILARE] e fino alla cessazione dell'incarico o
alla revoca.

La persona autorizzata si impegna a rispettare le istruzioni del §3, che dichiara di aver ricevuto e compreso, e a
mantenere la riservatezza anche dopo la cessazione dell'incarico.

Luogo e data: __________ Il titolare: ______________ Per ricevuta e accettazione: ______________

## 3. Istruzioni operative (allegate a ogni designazione)

1. **Finalità.** Tratta i dati solo per organizzare ed erogare le lezioni e per i compiti del tuo profilo. Non consultare dati di studenti o famiglie che non ti servono.
2. **Accesso personale.** Usa solo il tuo account; non condividere password o codici MFA; blocca lo schermo quando ti allontani; esci dal portale sui dispositivi condivisi.
3. **Dati vietati.** Non inserire mai nel gestionale diagnosi, informazioni sanitarie, certificazioni BES/DSA, voti scolastici, situazioni familiari delicate o documenti d'identità. Se una famiglia te li comunica, rivolgiti al coordinatore.
4. **Note e motivi.** Scrivi motivi brevi e oggettivi ("assenza giustificata", "spostamento richiesto dalla famiglia"), senza giudizi personali.
5. **Gruppi.** Non comunicare a una famiglia i nomi o i contatti degli altri partecipanti.
6. **Deleghe e inviti** (profili A–C). Attiva una delega o invia un invito solo dopo aver verificato la relazione con lo studente secondo la procedura (doc. 13 §3). Registra il metodo di verifica, non conservare copie dei documenti.
7. **Comunicazioni.** Usa i canali del gestionale o l'email del centro; niente gruppi di messaggistica personali con i dati degli studenti; niente esportazioni su dispositivi personali.
8. **Export.** Usa solo gli export protetti del sistema; non salvare copie locali; i file scadono e non vanno inoltrati.
9. **Dati reali e test.** Non usare dati reali per prove, formazione o demo: esistono dati sintetici.
10. **Richieste degli interessati.** Inoltra subito al contatto privacy ogni richiesta di accesso, rettifica, cancellazione o opposizione, anche se arriva a voce.
11. **Incidenti.** Segnala **subito** (entro 1 ora dalla scoperta) al [DA COMPILARE: referente] qualsiasi sospetto: email inviata al destinatario sbagliato, password scoperta, dispositivo perso, accesso strano, dati visibili a chi non dovrebbe. Non cercare di risolvere da solo e non cancellare tracce (doc. 14).
12. **Audit.** Le tue operazioni sono registrate per la sicurezza; i registri non sono usati per valutare il tuo lavoro (doc. 15).
13. **Fine incarico.** Alla cessazione l'account viene revocato; restituisci eventuali materiali e non conservare dati.
14. **Formazione.** Partecipa alla formazione iniziale e agli aggiornamenti annuali (piano `governance/piano-pilota-golive.md` §5).

## 4. Registro delle designazioni

| Nome | Profilo | Ruolo applicativo assegnato il | Designazione firmata il | Formazione | Revoca |
|---|---|---|---|---|---|
| [DA COMPILARE] | | | | | |
