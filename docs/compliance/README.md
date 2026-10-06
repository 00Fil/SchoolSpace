# Fascicolo di conformità per il go-live — indice

| Campo | Valore |
|---|---|
| Stato | **BOZZE** pronte per la revisione del titolare e del consulente — **nessun documento è approvato** |
| Versione | 0.1 — 2026-10-02 |
| Riferimenti | Guida Parte II (reg1-quadro, reg2-gdpr, reg3-altre, reg4-fascicolo), gov-gate |

> **Avvertenza.** Questi documenti sono bozze tecniche preparate dal team di progetto. **Non sono un parere legale.**
> Le scelte giuridiche (basi giuridiche, durate, inquadramenti) sono proposte da validare con un consulente qualificato e
> approvare dal titolare. I campi `[DA COMPILARE]` richiedono dati che solo il titolare conosce; i campi `[DA DECIDERE]` /
> `[DA VALUTARE]` richiedono una scelta; `[DA IMPLEMENTARE]` segnala un controllo software ancora mancante.

## Convenzioni
Ogni documento ha un'intestazione con stato, versione, numero nel fascicolo, GAP, responsabile e riferimenti normativi.
Le versioni approvate vanno esportate in PDF firmato in `docs/evidence/G6/` (GAP-M04); i testi destinati agli utenti
(informative, termini, cookie, dichiarazione) vanno pubblicati con versione e data di efficacia.

## I 22 documenti del fascicolo (reg4-fascicolo)

| # | Documento | Responsabile | Gate | File | Stato |
|---|---|---|---|---|---|
| 1 | Verbale decisioni D01–D09 e contratto del dominio | Committente | G1 | `../governance/verbale-D01.md`…`verbale-D09.md`, `../governance/g1-contratto-dominio.md` | Bozza |
| 2 | Registro dei trattamenti | Titolare | G6 | [01-registro-trattamenti.md](01-registro-trattamenti.md) | Bozza |
| 3 | Informative (famiglie, minori, maggiorenni, tutor e staff) | Titolare | G5/G6 | [02](02-informativa-famiglie.md), [03](03-informativa-studenti-minorenni.md), [04](04-informativa-studenti-maggiorenni.md), [05](05-informativa-tutor-staff.md) | Bozza |
| 4 | DPIA (prevalutazione e bozza strutturata) | Titolare + consulente | G6 | [06-dpia.md](06-dpia.md) | Bozza |
| 5 | Valutazione DPO | Titolare | G6 | [07-valutazione-dpo.md](07-valutazione-dpo.md) | Bozza |
| 6 | Contratti art. 28 ed elenco sub-responsabili | Titolare | G6 | [08-accordo-art28-modello.md](08-accordo-art28-modello.md), [09-fornitori-checklist.md](09-fornitori-checklist.md) | Modello |
| 7 | Valutazione dei trasferimenti extra-UE | Titolare | G6 | [10-trasferimenti-extra-ue.md](10-trasferimenti-extra-ue.md) | Modello |
| 8 | Matrice di retention (D09) | Titolare | G6 | [11-matrice-retention-d09.md](11-matrice-retention-d09.md) | Proposta |
| 9 | Designazioni degli autorizzati con istruzioni | Titolare | G2/G6 | [12-designazione-autorizzati.md](12-designazione-autorizzati.md) | Modello |
| 10 | Procedura diritti degli interessati | Titolare + operations | G6 | [13-procedura-diritti-interessati.md](13-procedura-diritti-interessati.md) | Bozza |
| 11 | Procedura e registro violazioni, modelli di notifica | Titolare + operations | G6 | [14-procedura-data-breach.md](14-procedura-data-breach.md) | Bozza |
| 12 | Informativa art. 4 Statuto e policy d'uso dell'audit | Titolare (HR) | G6 | [15-informativa-lavoratori-art4.md](15-informativa-lavoratori-art4.md) | Bozza |
| 13 | Termini d'uso e informativa cookie | Titolare + legale | G6 | [16-termini-di-servizio.md](16-termini-di-servizio.md), [17-informativa-cookie.md](17-informativa-cookie.md) | Bozza |
| 14 | Nota AI Act, art. 22, NIS2, accessibilità (+ dichiarazione modello) | Architect + consulente | G3/G6 | [18-nota-ai-act-art22-nis2-accessibilita.md](18-nota-ai-act-art22-nis2-accessibilita.md), [19-dichiarazione-accessibilita.md](19-dichiarazione-accessibilita.md) | Bozza |
| 15 | Checklist ASVS 5.0 L2 | Security lead | G6 | [23-schede-evidenze-tecniche.md](23-schede-evidenze-tecniche.md) §15 (struttura) | Da produrre (s1) |
| 16 | Report pentest e piano di rientro | Security lead | G6 | doc. 23 §16 | Da produrre |
| 17 | Report di restore con RPO/RTO | Operations | G6 | doc. 23 §17; [21-piano-continuita.md](21-piano-continuita.md) | Da produrre (s5) |
| 18 | Runbook (sei) | Operations | G6 | doc. 23 §18; doc. 21 | Da produrre (s5) |
| 19 | Audit di accessibilità | QA | G5 | doc. 23 §19 | Da produrre (s6) |
| 20 | SBOM e licenze | Tech lead | G6 | doc. 23 §20 | Da produrre |
| 21 | Esito UAT e pilota | Committente | G5/G6 | `../governance/piano-pilota-golive.md` | Piano in bozza |
| 22 | Verbale di go/no-go | Committente | G6 | `../governance/verbale-go-no-go.md` | Modello |

## Documenti di supporto
| File | Contenuto |
|---|---|
| [20-politica-sicurezza-informazioni.md](20-politica-sicurezza-informazioni.md) | Politica di sicurezza (art. 32) |
| [21-piano-continuita.md](21-piano-continuita.md) | BIA, scenari, backup, comunicazione |
| [22-registro-conformita.md](22-registro-conformita.md) | Catene obbligo → requisito → controllo → evidenza |
| [23-schede-evidenze-tecniche.md](23-schede-evidenze-tecniche.md) | Struttura e criteri dei documenti 15–22 |

## Controlli software ancora necessari emersi dalla redazione
1. Registrazione della **presa visione** delle informative (versione, data, account) — richiesta da reg2-gdpr "Informative" e G5.
2. Flag di **limitazione** del trattamento per soggetto (art. 18) e **legal hold** per categoria di retention.
3. **Audit delle letture** dell'audit e permesso dedicato con MFA per `/api/v1/privacy/audit-events`.
4. Policy di identità collegate a `can_receive_notifications` / `can_request_changes` e allo stato di riconferma alla maggiore età.
5. Alert automatico sulle richieste privacy in scadenza (`due_soon`, `overdue`).
6. Profili distinti all'interno del ruolo CENTER (amministratore, coordinatore, segreteria, didattica), oggi unico.
