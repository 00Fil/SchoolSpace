# Runbook operativi (GAP-L04)

Stato: **bozza operativa da approvare** (D08: team, reperibilità e fornitori non ancora decisi).
I nomi dei ruoli sono funzioni, non persone: vanno assegnati prima di G4.

## Ruoli e contatti

| Funzione | Responsabilità | Titolare (da assegnare) | Sostituto |
|---|---|---|---|
| Responsabile tecnico (RT) | decisioni tecniche durante l'incidente, rilascio, rollback, restore | _TBD_ | _TBD_ |
| Reperibile operativo (OPS) | primo intervento sugli alert, esecuzione runbook | _TBD_ | _TBD_ |
| Referente del centro (CEN) | comunicazione a famiglie e tutor, decisioni sul calendario | _TBD_ | _TBD_ |
| Titolare / DPO | violazioni di dati personali (art. 33-34 GDPR), autorità | _TBD_ | _TBD_ |
| Fornitori | DB gestito, hosting, provider email, DNS | contratti D08 | — |

Canale incidenti: _TBD_ (un solo canale, con registro scritto). Alertmanager instrada `team: operations`
a OPS e `team: security` a OPS + RT (infra/monitoring/alertmanager.yml).

## Severità

| SEV | Definizione | Esempi | Risposta | Aggiornamenti |
|---|---|---|---|---|
| SEV1 | dati personali esposti o persi, servizio fermo per tutti | violazione, DB corrotto, restore necessario | immediata, RT + DPO | ogni 30 min |
| SEV2 | funzione critica degradata | solver fermo, heartbeat assente, Redis giù, 5xx > 5 % | entro 30 min (orario di servizio) | ogni ora |
| SEV3 | degrado parziale con aggiramento | email in ritardo, backlog outbox, errori provider | entro 4 h lavorative | a risoluzione |
| SEV4 | anomalia senza impatto | dead-letter da verificare, certificato a 14 giorni | giorno lavorativo successivo | — |

Ogni SEV1/SEV2 chiude con un post-mortem senza colpe entro 5 giorni lavorativi (cronologia,
impatto, causa, azioni con responsabile e data) archiviato in `docs/evidence/`.

## Indice

| Runbook | Alert collegati |
|---|---|
| [01 Solver bloccato o fallito](01-solver-bloccato.md) | HeartbeatWorkerAssente, RunOltreLimiteHard, ValidatoreRespingeSolver, CodaSolverFerma |
| [02 Redis indisponibile](02-redis-indisponibile.md) | RedisGiu, RedisMemoriaAlta |
| [03 Collisioni e conflitti stale](03-collisione-stale.md) | ConflittiCommitAnomali |
| [04 Email indisponibile](04-email-indisponibile.md) | BacklogOutbox, ErroriProviderEmail, ConsegneInDeadLetter |
| [05 Incidente di sicurezza](05-incidente-sicurezza.md) | LoginFallitiAnomali, AccessiNegatiAnomali |
| [06 Restore e PITR](06-restore.md) | BackupAssente, ArchiviazioneWALFallita, StorageDatabaseQuasiPieno, WALQuasiPieno |
| [DNS, TLS e manutenzione](../infra/dns-tls-manutenzione.md) | CertificatoTLSInScadenza |
| [Indisponibilità](#indisponibilita) (sotto) | ServizioNonRaggiungibile, ScrapeMetricheAssente, ErroriServer5xx, LatenzaP95Alta, ProviderMetricheInErrore |

## Indisponibilità

Alert `ServizioNonRaggiungibile` (probe esterno, docs/infra/uptime-monitor.md) o 5xx elevati.

1. Confermare da rete esterna: `curl -sS -o /dev/null -w '%{http_code}\n' https://<host>/api/v1/ready`.
2. Sull'host: `docker compose -f compose.prod.yaml ps` (servizi `unhealthy`?) e
   `docker compose -f compose.prod.yaml exec web python manage.py ops_check` (quale dipendenza è giù).
3. Database giù → fornitore DB gestito + [06](06-restore.md); Redis giù → [02](02-redis-indisponibile.md);
   certificato → [DNS/TLS](../infra/dns-tls-manutenzione.md).
4. Dopo un rilascio recente: rollback (sotto). Se serve tempo: `scripts/maintenance.sh on` (pagina 503
   dedicata) e comunicazione CEN.

## Rilascio

Automatico da `.github/workflows/cd.yml` (staging, poi produzione con approvazione) o manuale:

```bash
BASE_URL=https://<host> scripts/deploy.sh <tag>
```

`deploy.sh` blocca il rilascio senza un backup riuscito nelle ultime 24 h, esegue il job `migrate`
(ruolo `app_migrator`), `scripts/pg-privileges.sh` (privilegi + trigger append-only + `04_verify.sql`),
il rollout con attesa dei healthcheck, `scripts/smoke.sh` e, se qualcosa fallisce, il rollback
automatico all'immagine precedente (`/var/lib/ripetizioni/current-tag`).

Regole per le migrazioni (expand/contract): una release aggiunge colonne/tabelle compatibili con la
versione precedente; la rimozione avviene in una release successiva. Il rollback **non** annulla le
migrazioni: se una migrazione è incompatibile, il rollback richiede il restore ([06](06-restore.md)).

Rollback manuale: `BASE_URL=https://<host> scripts/deploy.sh $(cat /var/lib/ripetizioni/previous-tag)`.

## Controlli periodici

| Frequenza | Attività | Evidenza |
|---|---|---|
| giornaliera | backup cifrato (`scripts/backup.sh`, cron/timer 02:30) | `backup-status.json`, metrica |
| settimanale | revisione alert silenziati, dead-letter comunicazioni, PR Dependabot | — |
| mensile | restore drill (`scripts/restore-drill.sh`) su DB isolato | `docs/evidence/restore-drill-*.json` |
| trimestrale | PITR di prova presso il fornitore, revisione accessi e ruoli, test dei contatti | verbale |
| annuale | esercitazione incidente di sicurezza (05), revisione runbook | verbale |
