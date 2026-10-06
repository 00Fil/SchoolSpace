# Deploy in produzione con GitHub + Dokploy su VPS

File coinvolti: `compose.dokploy.yaml`, `infra/env/dokploy.env.example`,
`scripts/dokploy-secrets.py`.

## 0. Prerequisiti
- VPS Ubuntu 24.04, consigliati 4 vCPU / 8 GB RAM / 80 GB disco (build + solver fino a 2 GB).
- Un dominio, es. `gestionale.tuodominio.it`.
- Account GitHub e account Resend.

## 1. Repository GitHub (sul tuo PC)
```
unzip progettov1-dokploy.zip -d ripetizioni && cd ripetizioni
git init && git add . && git status   # controlla: NESSUN .env, secrets/, *.dump
git commit -m "Prima versione"
git branch -M main
git remote add origin git@github.com:<utente>/ripetizioni.git   # repo PRIVATA
git push -u origin main
```
Su GitHub: Settings -> Branches -> proteggi `main` richiedendo il workflow `ci` verde.

## 2. VPS
```
ssh root@IP_VPS
apt update && apt upgrade -y
curl -sSL https://dokploy.com/install.sh | sh
```
Firewall del provider (non ufw: Docker lo aggira): aperte 22, 80, 443; 3000 solo
temporaneamente dal tuo IP.

## 3. DNS
- Record A `gestionale.tuodominio.it` -> IP della VPS.
- (Opzionale) record A `dokploy.tuodominio.it` -> IP della VPS, per il pannello.

## 4. Dokploy
1. Apri `http://IP_VPS:3000` e crea l'account amministratore (password forte + 2FA).
2. Settings -> Web Server: imposta il dominio del pannello con HTTPS, poi chiudi la 3000.
3. Settings -> Git -> GitHub: crea la GitHub App e installala SOLO sulla repo.
4. Projects -> Create Project `ripetizioni` -> Create Service -> Compose:
   - Provider GitHub, repository, branch `main`
   - Compose Path: `./compose.dokploy.yaml`
5. Scheda Environment: incolla `infra/env/dokploy.env.example` compilato (vedi §5). Save.
6. Scheda Domains -> Add Domain: Service `proxy`, Host `gestionale.tuodominio.it`,
   Path `/`, Container Port `8080`, HTTPS attivo, Certificate `Let's Encrypt`.
7. Deploy. Segui i log: db -> db-init -> migrate -> db-privileges -> web -> proxy.
8. General -> Autodeploy attivo: ogni push su `main` rilascia.

## 5. Variabili
Sul PC: `python3 scripts/dokploy-secrets.py` e copia le 8 righe generate.
Da compilare a mano:

| Variabile | Valore |
|---|---|
| APP_DOMAIN | `gestionale.tuodominio.it` (senza https://) |
| EMAIL_FROM | `Centro ripetizioni <no-reply@tuodominio.it>` (dominio verificato su Resend) |
| EMAIL_DOMAIN | `tuodominio.it` |
| RESEND_API_KEY | chiave Resend con permesso solo invio |
| CENTER_ADMIN_USERNAME | vuoto al primo deploy; poi lo username del superuser |

Conserva tutti i valori in un password manager. NON cambiare `PG_ADMIN_PASSWORD` dopo
il primo avvio (Postgres la usa solo all'inizializzazione del volume).

## 6. Resend
1. Domains -> Add Domain `tuodominio.it`, regione UE.
2. Inserisci nel DNS i record mostrati (SPF/DKIM, MX di ritorno) e attendi "Verified".
3. API Keys -> Create, permesso "Sending access", limitata al dominio -> `RESEND_API_KEY`.
4. Accetta il DPA (trattamento dati) dal pannello Resend.

## 7. Primo avvio applicativo (una volta)
Dalla VPS:
```
WEB=$(docker ps --filter name=web --format '{{.Names}}' | head -1)
docker exec -it $WEB python manage.py createsuperuser
docker exec -it $WEB python manage.py bootstrap_center
docker exec -it $WEB python manage.py approve_decisions --by <username-superuser>
```
Poi in Dokploy imposta `CENTER_ADMIN_USERNAME=<username-superuser>` e rifai Deploy.
Al primo login il superuser configura l'MFA (obbligatoria).

## 8. Verifiche
- `https://gestionale.tuodominio.it/api/v1/health` -> `production_ready: true`.
- Login, invio di una email di prova, generazione del calendario del mese.
- Log `db-privileges`: le verifiche non devono stampare righe "problem".

## 9. Backup
Il servizio `db-backup` crea un dump al giorno (14 giorni) nel volume `pgbackups`.
Copialo fuori dalla VPS (Dokploy -> Volume Backups verso S3, oppure rclone/cron).
Ripristino di prova:
```
DB=$(docker ps --filter name=db-backup --format '{{.Names}}' | head -1)
docker exec $DB ls /backups
docker exec $DB pg_restore -l /backups/<file>.dump | head
```

## 10. Aggiornamenti
`git push` su `main` -> Dokploy ricostruisce, migra e riavvia. Se un rilascio fallisce,
Deployments -> Rollback o `git revert` + push.
