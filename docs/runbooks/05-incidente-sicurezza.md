# 05 — Incidente di sicurezza e violazione di dati personali

**Alert**: `LoginFallitiAnomali` (SEV2, team security), `AccessiNegatiAnomali` (SEV3); oppure
segnalazione da utenti, fornitori, scansioni (Trivy, pip-audit, npm audit), gitleaks.
Dati trattati: anagrafiche di minori e famiglie, calendario, comunicazioni → ogni sospetto è almeno SEV2
finché non escluso.

## 1. Contenimento (prima ora)

- Aprire il registro dell'incidente (ora UTC di **scoperta**: da qui partono le 72 h dell'art. 33 GDPR).
- Preservare le evidenze **prima** di cambiare: `docker compose -f compose.prod.yaml logs --since 72h > incident-<data>.log`
  (log JSON già redatti: niente password, token, email in chiaro), snapshot del DB presso il fornitore.
- Credenziali compromesse: ruotare nel secret manager e ridistribuire
  (`DJANGO_SECRET_KEY` invalida tutte le sessioni e i token firmati; password PG `app_runtime`/`app_migrator`;
  ACL Redis con `scripts/redis-acl.sh`; `OPS_METRICS_TOKEN`; chiavi del provider email; token ICS: revoca dal
  portale). Poi `scripts/deploy.sh <tag corrente>` per riavviare con i nuovi segreti.
- Account compromesso: revoca sessioni (s1, `UserSession`), reset MFA dal centro, disattivazione.
- Attacco in corso: `scripts/maintenance.sh on` (servizio sospeso con pagina 503), allowlist/blocco IP sul
  proxy o sul firewall del fornitore.

## 2. Valutazione (entro 24 h)

| Domanda | Fonte |
|---|---|
| Quali dati, di chi, quanti interessati (minori?) | audit `governance_auditevent`, log di accesso (`actor_id` pseudonimo, `route`) |
| Riservatezza, integrità o disponibilità? | log, verifica catene audit (`privacy_ledger_verify`) |
| Il rischio per gli interessati è improbabile? | RT + DPO, motivazione scritta |

## 3. Notifiche

- **Garante (art. 33)**: entro **72 h** dalla scoperta, salvo che la violazione sia improbabile che presenti un
  rischio; se mancano informazioni, notifica in fasi. Decide il Titolare con il DPO; la motivazione di una
  mancata notifica va registrata.
- **Interessati (art. 34)**: senza ingiustificato ritardo se il rischio è elevato (con i genitori per i minori);
  testo approvato da Titolare/DPO, inviato dal centro (CEN).
- **Fornitori** (art. 28): richiedere le loro evidenze; i fornitori devono avvisare senza ritardo.
- Registro delle violazioni: **sempre**, anche senza notifica (art. 33.5).

## 4. Ripristino e chiusura

Correzione della causa (patch, configurazione), rilascio con la CI completa, verifica (smoke, alert rientrati),
eventuale restore ([06](06-restore.md)) se l'integrità è compromessa. Post-mortem entro 5 giorni lavorativi;
azioni preventive nel backlog con responsabile.
