# Stato v0.8 — consegna per esaurimento del budget

- `main` integra s1–s8 (sicurezza, calendario, comunicazioni, privacy, infra, frontend, conformità, solver).
- Verifiche: SQLite 729 passati / 32 saltati / 0 falliti; PostgreSQL 17 + Redis reali 756 passati / 2 saltati
  (3 difetti residui della prima esecuzione corretti e riverificati singolarmente: rieseguire la suite completa PG).
  check --deploy 0 avvisi; pip-audit e npm audit 0 vulnerabilità; frontend build + 34 test; E2E 92/92, axe 0 violazioni.
- NON integrati (interrotti): rami `s9-dominio` (GAP C01–C06) e `s10-verifica` (B08 completo, I01, M03, E09, M04).
  Riprendere da lì: `git log main..s9-dominio`, verificare, completare, unire.
- Stato di tutte le 99 attività e lavoro residuo: guida v3.0, capitolo "Rendicontazione del completamento v0.8".
