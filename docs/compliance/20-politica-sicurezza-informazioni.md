# Politica di sicurezza delle informazioni

| Campo | Valore |
|---|---|
| Stato | **BOZZA** — da approvare dal titolare; i controlli tecnici rinviano alle evidenze di G6 |
| Versione | 0.1 — 2026-10-02 |
| Documento del fascicolo | supporto ai n. 2, 4, 15 (art. 32) — gate G6 |
| GAP | GAP-I01–I07, GAP-B04, GAP-E08, GAP-K01–K03 |
| Responsabile | Titolare (A); security lead / architect (R) |
| Riferimenti normativi e standard | GDPR artt. 5.1.f, 24, 25, 32; OWASP ASVS 5.0 livello 2 (NFR06); ISO/IEC 27001:2022 (riferimento metodologico, nessuna certificazione dichiarata); paper §10.2–10.5; guida tec2-sicurezza |

## 1. Scopo e ambito
Proteggere riservatezza, integrità e disponibilità dei dati trattati dal gestionale e dagli strumenti collegati (hosting,
DB, code, email, monitoraggio, repository, postazioni dello staff). Si applica a staff, tutor, fornitori con accesso.

## 2. Principi
Privilegio minimo; difesa in profondità; sicurezza per default; dati sintetici fuori dalla produzione; tracciabilità;
nessuna crittografia "fatta in casa"; ogni controllo ha un'evidenza.

## 3. Ruoli
| Ruolo | Responsabilità |
|---|---|
| Titolare | Approva la politica, accetta i rischi residui, decide sulle violazioni |
| Security lead [DA COMPILARE] | Mantiene checklist ASVS, gestisce vulnerabilità e pentest |
| Operations [DA COMPILARE] | Infrastruttura, backup, monitoraggio, incidenti |
| Coordinatori e staff | Applicano le istruzioni della designazione (doc. 12) |
| Fornitori | Rispettano l'accordo art. 28 (doc. 8) |

## 4. Controlli

| Area | Regola | Evidenza / GAP |
|---|---|---|
| Identità | Account individuali; email normalizzata; inviti e reset monouso con hash e scadenza; risposte non enumeranti | B01–B03; test s1/s4 |
| Autenticazione | Argon2id; MFA TOTP obbligatoria per lo staff con codici di recupero; sessioni revocabili lato server; timeout [DA APPROVARE: inattività staff 30 min, assoluto 12 h; famiglie 14 giorni] | B04 |
| Autorizzazione | Scope per singolo studente a ogni richiesta; serializer per ruolo; nessuna funzione amministrativa abilitata da parametri client | B08, T24, T25 |
| Abusi | Rate limit persistente per IP e identità; code del solver limitate | B05 |
| Web | TLS ovunque; HSTS dopo verifica dei domini; cookie Secure/HttpOnly/SameSite=Lax; CSRF; CSP restrittiva; Referrer-Policy, Permissions-Policy; nessun CORS o allowlist esplicita | I02 |
| Segreti | Secret manager; rotazione [DA DEFINIRE: almeno annuale e a ogni uscita di personale con accesso]; mai in repository, snapshot o log | I03 |
| Dati | Cifratura a riposo del fornitore; rete DB privata; ruoli PostgreSQL owner/migrator/runtime/readonly; audit append-only anche contro SQL diretto | J04, E08 |
| Log | JSON strutturati con correlation_id; vietati email, nomi, token, cookie, URL video, corpi; test CI sui pattern; retention 30 giorni | K01, I07 |
| Admin Django | Disattivato in produzione o dietro MFA e allowlist di rete; azioni auditate | I06 |
| Supply chain | Lockfile con hash; pip-audit/npm audit; scansione immagini; SBOM; una vulnerabilità nota con correzione blocca il merge | I04, I08, J06 |
| Vulnerabilità | Critiche: correzione o mitigazione entro 72 h; alte: 7 giorni; medie: 30 giorni [DA APPROVARE] | piano manutenzione |
| Pentest | Esterno prima del go-live; nessun finding critico o alto aperto a G6; ripetere annualmente o dopo cambi rilevanti | I05 |
| Ambienti | Staging e produzione isolati (DB, code, chiavi, domini, provider); staging senza invii reali e senza dati reali | J02 |
| Accessi dei fornitori | Nominativi, MFA, a tempo, su richiesta tracciata | doc. 8 art. 6 |
| Postazioni dello staff | Disco cifrato, blocco schermo, aggiornamenti automatici, browser aggiornato, nessun salvataggio di export [DA VERIFICARE con il centro] | doc. 12 |
| Backup | PITR + export logici cifrati; restore provato con RPO 15 min / RTO 4 h | L01, L02 |
| Monitoraggio | Alert su accessi anomali, backup, heartbeat, validatore, outbox | K02, K03 |
| Incidenti | Classificazione SEV1–3; procedura violazioni (doc. 14); post-mortem | L04, H08 |

## 5. Gestione delle eccezioni
Ogni deroga è scritta, motivata, con scadenza e approvata dal titolare; registrata nel registro di conformità (doc. 22).

## 6. Formazione e consapevolezza
Formazione iniziale prima dell'accesso a dati reali; aggiornamento annuale; esercitazione di gestione delle violazioni.

## 7. Riesame
Annuale e dopo ogni incidente SEV1/SEV2, insieme a DPIA, ASVS, fornitori e runbook.

Approvazione del titolare: ______________________ Data: __________
