# Procedura per la gestione dei diritti degli interessati (artt. 12–22 GDPR)

| Campo | Valore |
|---|---|
| Stato | **BOZZA** — da approvare dal titolare; tempi interni proposti |
| Versione | 0.1 — 2026-10-02 |
| Documento del fascicolo | n. 10 — gate G6 |
| GAP | GAP-H05, FR24 |
| Responsabile | Titolare (A) e operations (R); referente privacy: [DA COMPILARE] |
| Riferimenti normativi | GDPR artt. 11, 12, 15–22, 19, 77; D.Lgs. 196/2003 artt. 2-undecies, 2-terdecies; Linee guida EDPB 01/2022 sul diritto di accesso |

> Strumenti del software (stream s4, `apps/privacy`): registro `PrivacyRequest` (tipi ACCESS, RECTIFICATION, ERASURE,
> RESTRICTION, PORTABILITY, OBJECTION; stati RECEIVED → VERIFIED → [EXTENDED] → COMPLETED/REJECTED), export protetti
> (`ProtectedExport`), anonimizzazione governata, ledger esterno e riconciliazione. Non è un parere legale.

## 1. Principi
- Risposta **senza ingiustificato ritardo e comunque entro un mese** dalla ricezione; proroga di **due mesi** solo per complessità o numero, comunicata entro il primo mese con motivazione (art. 12.3).
- Gratuità; contributo spese o rifiuto solo per richieste manifestamente infondate o eccessive, motivati (art. 12.5).
- Nessun obbligo di forma: una richiesta a voce o per email ordinaria è valida. Il centro la registra comunque.
- Si chiedono solo le informazioni necessarie a verificare l'identità (art. 12.6); non si chiedono copie di documenti se la verifica è possibile altrimenti.

## 2. Ruoli
| Ruolo | Compito |
|---|---|
| Chi riceve (qualsiasi persona autorizzata) | Inoltra al referente privacy entro 1 giorno lavorativo |
| Referente privacy [DA COMPILARE] | Registra, verifica, coordina, risponde |
| Coordinatore | Fornisce contesto, esegue rettifiche operative |
| Operations / fornitore | Esegue export, anonimizzazione, verifiche sui backup |
| Titolare | Decide su rifiuti, limitazioni, conflitti con obblighi di conservazione |

## 3. Verifica dell'identità e della legittimazione
| Richiedente | Verifica proposta |
|---|---|
| Utente con account | Richiesta inviata dall'account autenticato (con MFA per lo staff) o conferma tramite email registrata |
| Genitore/tutore per un minore | Delega attiva e **verificata** nel sistema; se la richiesta riguarda un'altra persona o la delega è dubbia (separazioni, affidamento, tutela), verifica documentale a vista (provvedimento, nomina del tutore) **senza conservarne copia**: si registra metodo, data e operatore |
| Studente maggiorenne | Account o verifica in presenza; i genitori non agiscono più per suo conto senza delega riconfermata |
| Studente minorenne | La richiesta è accolta e gestita con il coinvolgimento di chi esercita la responsabilità genitoriale, salvo diversa indicazione del consulente [DA VALUTARE: minori ≥ 14 anni] |
| Terzo (avvocato, delegato) | Delega scritta firmata dall'interessato e verifica del delegante |
| Richiesta di più genitori in disaccordo | Sospendere l'esecuzione delle cancellazioni; decisione del titolare con il consulente |

## 4. Flusso operativo

| Passo | Azione | Strumento | Tempo interno proposto |
|---|---|---|---|
| 1 | Registrazione della richiesta (tipo, interessato, canale, ruolo del richiedente) | `POST /api/v1/privacy/requests` → stato RECEIVED; scadenza calcolata a 1 mese | Giorno 0–1 |
| 2 | Conferma di ricezione all'interessato (modello A) | Email del centro | Entro 2 giorni lavorativi |
| 3 | Verifica dell'identità e della legittimazione | `verify_identity` (metodo obbligatorio) → VERIFIED | Entro 5 giorni lavorativi |
| 4 | Ricerca dei dati: DB applicativo, fornitori (log email, error tracking), archivi esterni del centro [DA COMPILARE] | Checklist §6 | Entro 10 giorni |
| 5 | Esecuzione secondo il tipo (§5) | Funzioni FR24 | Entro 20 giorni |
| 6 | Notifica ai destinatari delle rettifiche/cancellazioni/limitazioni (art. 19) | Email ai responsabili interessati | Con il passo 5 |
| 7 | Risposta all'interessato (modello B/C/D) | Email + export protetto | Entro 25 giorni (margine sulla scadenza) |
| 8 | Chiusura con esito e motivazione; audit | `_close` → COMPLETED/REJECTED; ledger esterno | Entro la scadenza |
| — | Proroga, se necessaria (modello E) | `extend` (una sola volta) → EXTENDED | Entro il giorno 30 |

Promemoria: report `due_soon` (7 giorni) e `overdue` controllati settimanalmente dal referente [DA IMPLEMENTARE: alert automatico].

## 5. Esecuzione per tipo di diritto

| Diritto | Esecuzione | Limiti e note |
|---|---|---|
| Accesso (15) | Export JSON o CSV dei dati dell'interessato + informazioni dell'art. 15.1 (finalità, categorie, destinatari, durata, diritti, fonte, assenza di decisioni automatizzate) | Non includere dati di terzi (es. altri partecipanti di un gruppo); export con audience nominativa, token monouso, scadenza 24 h |
| Rettifica (16) | Correzione auditata con motivo | Presenze: la correzione non modifica orario o durata della lezione (I8) |
| Cancellazione (17) | Anonimizzazione di studente/account/famiglia vuota, revoca di deleghe e inviti, motivazione registrata | Se esistono obblighi di conservazione o la difesa di un diritto (art. 17.3), si minimizza e si spiega; i backup scadono naturalmente e la cancellazione è riapplicata al restore tramite ledger |
| Limitazione (18) | Chiusura manuale con misura applicata [DA IMPLEMENTARE: flag di limitazione per soggetto] | Durante la limitazione i dati sono solo conservati |
| Portabilità (20) | Export JSON dei dati forniti dall'interessato e trattati su base contrattuale | Solo formato JSON strutturato |
| Opposizione (21) | Valutazione sul legittimo interesse (audit, log di sicurezza) | Di norma prevalgono motivi legittimi cogenti di sicurezza; motivazione scritta |
| Art. 22 | Non applicabile (nessuna decisione unicamente automatizzata); su richiesta il coordinatore spiega e rivede l'orario | Doc. 18 |

## 6. Checklist di ricerca dei dati
- [ ] DB applicativo (anagrafiche, deleghe, calendario, presenze, percorsi, audit) — export automatico
- [ ] Snapshot del solver non ancora scaduti (contengono riferimenti allo studente)
- [ ] Log del provider email (≤ 30 giorni) — richiesta al fornitore se necessario
- [ ] Error tracking (≤ 30 giorni)
- [ ] Archivi fuori dal sistema: email del centro, fogli di calcolo pre-esistenti, documenti cartacei [DA COMPILARE]
- [ ] Backup: non estratti per l'accesso; menzionati nella risposta con la loro scadenza

## 7. Modelli di risposta

**A — Conferma di ricezione.**
"Gentile [nome], abbiamo ricevuto il [data] la Sua richiesta di [tipo di diritto] relativa a [interessato]. Il numero
della pratica è [ID]. Risponderemo entro il [scadenza]. Per proteggere i dati, potremmo chiederLe di confermare la Sua
identità [modalità]. [Firma, contatto privacy]"

**B — Accesso / portabilità evasa.**
"… in allegato trova le informazioni richieste. I dati sono disponibili tramite un collegamento protetto valido fino al
[data e ora]; il codice di download Le viene comunicato [canale separato]. Il file sarà eliminato dopo il download o alla
scadenza. Le ricordiamo le informazioni dell'art. 15: [finalità, destinatari, conservazione, diritti, reclamo al Garante]."

**C — Cancellazione evasa (anche parziale).**
"… abbiamo cancellato o reso anonimi i dati di [interessato] il [data]. [Se parziale:] Conserviamo in forma ridotta [dati]
fino al [data] perché [motivo: obbligo di legge / difesa di un diritto]. Le copie di sicurezza scadono entro [N] giorni
e la cancellazione verrà riapplicata in caso di ripristino. Abbiamo informato [destinatari] (art. 19)."

**D — Rifiuto motivato.**
"… non possiamo dare seguito alla richiesta perché [motivo]. Può proporre reclamo al Garante per la protezione dei dati
personali (www.garanteprivacy.it) o ricorso all'autorità giudiziaria (art. 12.4)."

**E — Proroga.**
"… a causa di [complessità / numero di richieste] la risposta richiederà più tempo. Risponderemo entro il [nuova scadenza,
massimo +2 mesi]."

## 8. Evidenze e controlli
- Registro delle richieste (`PrivacyRequest`) e ledger esterno verificato (`privacy_ledger_verify`).
- Test: `test_privacy_rights.py` (scadenze e proroga, export JSON/CSV, portabilità, rettifica, anonimizzazione, riconciliazione dopo restore, ledger manomesso).
- Riesame annuale: numero di richieste, tempi medi, ritardi, motivi di rifiuto.
