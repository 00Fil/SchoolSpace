# Uptime e probe esterno (GAP-K04)

Il monitoraggio interno (Prometheus sull'host) non vede un host spento o un problema DNS/TLS: serve un probe
**esterno** su infrastruttura diversa.

| Controllo | URL | Atteso | Frequenza | Alert |
|---|---|---|---|---|
| Disponibilità | `https://app.<dominio>/api/v1/ready` | 200, corpo `{"status": "ok"}` (nessun dettaglio interno) | 60 s da ≥ 2 regioni UE | 2 errori consecutivi → `ServizioNonRaggiungibile` (SEV2) |
| Pagina | `https://app.<dominio>/` | 200, header `Content-Security-Policy` | 5 min | SEV3 |
| Certificato | stesso host | scadenza > 14 giorni | 6 h | `CertificatoTLSInScadenza` (SEV4) |
| Redirect | `http://app.<dominio>/` | 301 verso https | 1 h | SEV4 |

Implementazioni equivalenti:

- **blackbox_exporter** su un secondo host/VM (configurazione pronta: `infra/monitoring/blackbox.yml`, job
  `uptime` in `prometheus.yml`, regole in `alerts.yml`);
- **servizio SaaS** con sede/dati nell'UE (scelta D08): stessi controlli, notifiche verso lo stesso canale di
  Alertmanager. Nessun dato personale nel probe: l'endpoint è anonimo.

`/api/v1/ready` controlla database, migrazioni, cache e broker; i nomi dei controlli sono visibili solo su
`/readyz` (rete interna). Stato dei worker: heartbeat (`ripetizioni_worker_heartbeat_age_seconds`), non nel
probe pubblico, per non rendere "giù" il portale quando è fermo solo il solver.
