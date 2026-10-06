# 04 — Email indisponibile o in ritardo

**Alert**: `BacklogOutbox` (SEV3: > 100 consegne in attesa o la più vecchia > 10 min),
`ErroriProviderEmail` (SEV3: > 10 % di errori su 15 min), `ConsegneInDeadLetter` (SEV4).
**Impatto**: avvisi a famiglie e tutor in ritardo. Le notifiche in-app e il calendario non dipendono
dal provider. Nessun duplicato: consegne idempotenti (chiave `delivery-<id>`), esiti ambigui riconciliati
prima di un nuovo invio (s3, `docs/communications.md`).

## Diagnosi

```bash
docker compose -f compose.prod.yaml ps worker-notifications
docker compose -f compose.prod.yaml exec web python manage.py ops_check --checks workers,broker
```

Metriche: `ripetizioni_delivery_backlog{channel,status}`, `ripetizioni_delivery_attempts_total{outcome}`
(TRANSIENT_ERROR = provider giù/limite; PERMANENT_ERROR = indirizzo o contenuto rifiutato),
pagina di stato del provider, `GET /api/v1/communications/status` (staff).

## Intervento

1. Worker fermo → `docker compose -f compose.prod.yaml restart worker-notifications`.
2. Provider giù: nessuna azione sui dati; i tentativi proseguono con backoff fino al limite, poi
   dead-letter. Se il fermo supera 2 h: CEN avvisa per i cambi urgenti con altri canali.
3. Credenziali/dominio (SPF, DKIM, DMARC) rifiutati: correggere nel secret manager/DNS e riavviare.
4. Dopo il ripristino: le consegne in dead-letter si decidono dal pannello comunicazioni
   (`resolve_delivery`: reinvio o chiusura); mai reinvii in massa via SQL.
5. Esiti `AMBIGUOUS` (worker interrotto durante l'invio) restano in riconciliazione: con provider senza
   idempotenza la policy `COMMUNICATIONS_AMBIGUOUS_POLICY` (default prudente, da approvare) li porta
   in dead-letter invece di rischiare un duplicato.
