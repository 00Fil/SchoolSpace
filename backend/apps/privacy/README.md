# apps.privacy — protezione dei dati (stream s4)

Stato: v1.0-candidate per la parte tecnica; **tutte le durate e le azioni D07/D09 sono "da approvare"**.

## Campi del paper assenti nei modelli v0.7 (nessuna modifica a identity/education)

| Modello paper | Campo | Dove vive ora | Nota per l'integrazione |
|---|---|---|---|
| Family | contatto autorizzato | `FamilyProfile` (1:1) | migrare in `education.Family` quando il proprietario lo decide |
| Student | data di nascita (solo se necessaria) | `StudentProfile.birth_date` | usata solo dal job maggiore età |
| Student | chiave di import | `StudentImportKey` | idempotenza T17 |
| GuardianLink | relazione dichiarata, `can_receive_notifications`, `can_request_changes` | `GuardianLinkDetail` | letti da `identity.policies` (`notification_guardian_links`, `can_request_student_changes`) |
| GuardianLink | verificatore, metodo, data; attore e motivo della revoca | `GuardianLinkDetail` | |
| GuardianLink | stato di riconferma alla maggiore età | `GuardianLinkDetail.reconfirmation*` | |
| GuardianLink | UQ relazione attiva per coppia | servizio `registry.create_guardian_link` (lock + verifica) | un vincolo DB parziale richiede modifica di `education` |

## Servizi
- `registry.py` — famiglie, studenti, deleghe (creazione non verificata → verifica → permessi → revoca). Inviti: **un solo sistema, quello di identity** (`identity.Invitation` + `identity.services`); qui solo `InvitationTerms` (relazione, notifiche, richieste di modifica, batch di import) applicate alla delega quando identity accetta l'invito (`signals.py`). Accettazione: `/api/v1/invitations/accept` (s1).
- `retention.py` — matrice D09 (`RetentionPolicy`), job con dry-run e ricevuta firmata (`RetentionRun`).
- `requests.py` — registro richieste artt. 15-22 con scadenze art. 12.3; `subjects.py` raccolta/export/rettifica/anonimizzazione.
- `exports.py` — export protetti: audience, scadenza (`PRIVACY_EXPORT_TTL_HOURS`), token monouso, audit di ogni tentativo.
- `importer.py` — template CSV `import_templates/famiglie-v1.csv`, dry-run senza inviti, idempotenza; tutori senza account → inviti identity `PENDING_VERIFICATION` (token inviato solo con `--verify-links --create-invites`).
- `majority.py` — riconferma deleghe ai 18 anni (`PRIVACY_MAJORITY_GRACE_DAYS`, `PRIVACY_MAJORITY_OVERDUE_ACTION`).
- `ledger.py` / `reconcile.py` — ledger esterno con catena di hash; riconciliazione dopo restore.

## Comandi
`privacy_import`, `privacy_retention`, `privacy_majority_review`, `privacy_reconcile`, `privacy_ledger_verify`
(tutti in dry-run/piano per default dove modificano dati).

## API
`/api/v1/registry/...` (api/families.py) e `/api/v1/privacy/...` (api/privacy.py); vedi REPORT-s4-privacy.md.
