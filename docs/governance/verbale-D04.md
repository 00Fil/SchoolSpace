# Verbale di decisione D04 — Aperture per modalità e presenza del tutor in sede

| Campo | Valore |
|---|---|
| Stato | **BOZZA DI VERBALE** — da approvare |
| Versione | 0.1 — 2026-10-02 |
| GAP | GAP-A01, GAP-A06; sblocca valori reali di FR05, H07 |
| Gate | G1 |
| Responsabile | Committente (A), coordinatore (R) — [DA COMPILARE] |
| Scadenza | [DA COMPILARE] |
| Riferimenti | Paper §1.3, FR05, T08, T09; `ServiceWindow(mode, location)`, `Closure`, `PlanningPolicy.online_onsite_requires_space`, `video_channels_required` |

## 1. Opzioni

| Punto | Opzioni | Raccomandazione motivata |
|---|---|---|
| Finestre in presenza | [DA COMPILARE: es. lun–ven 14:30–19:30, sab 9:00–13:00] | Valori del centro |
| Finestre online | a) uguali alla presenza; b) più ampie (es. fino alle 21:00) | **b se richiesto**, sempre esplicite: nessuna disponibilità 24/7 implicita |
| Online svolto dal tutor in sede | Occupa uno spazio (T08) | Confermare `online_onsite_requires_space = true` |
| Risorse video | a) nessun limite; b) N canali esclusivi (licenze) | **b** con N = numero di licenze [DA COMPILARE]; H07 |
| Chiusure e festività | Calendario annuale del centro; chiusura prevale (T09) | Caricare con D06 |

## 2. Impatto tecnico
Seed delle `ServiceWindow` reali; catalogo canali video (`video` in `LessonOccurrence`); readiness blocca se mancano
finestre (`test_required_configuration_missing`).

## 3. Valori di prova
Presenza lun–ven 15–19; online lun–ven 15–20; 2 canali video.

## 4. Esito e firme
☐ Approvata ☐ Con modifiche: [DA COMPILARE] ☐ Rinviata
| Ruolo | Nome | Firma | Data |
|---|---|---|---|
| Committente | [DA COMPILARE] | | |
| Coordinatore | [DA COMPILARE] | | |
| Architect | [DA COMPILARE] | | |
