"""Prova di carico M01: 25 utenti concorrenti, p95 < 500 ms sulle API di lettura.

Uso (staging o scripts/e2e_local.py --loadtest):
  LOADTEST_USERS_FILE=users.txt locust -f scripts/loadtest/locustfile.py --headless \
      -u 25 -r 0.16 -t 5m --host https://staging.example.it --csv out/loadtest
- users.txt: una riga "email password" per utente sintetico (MAI account reali);
- spawn rate 0.16/s perché il proxy limita il login a 10/min per IP (+5 di burst): da un
  solo IP il login di 25 utenti richiede circa 2,5 min, come in produzione dietro un NAT;
- exit code != 0 se p95 delle letture >= LOADTEST_P95_MS (default 500) o errori > 1%.
Il personale del centro ha MFA obbligatoria: gli utenti sintetici sono tutor/famiglie.
In produzione le viste di pianificazione/calendario sono disattivate (flag sperimentali vietati):
quando G3 le abilita, aggiungere qui i task corrispondenti (settimana personale, proposte).
"""

import itertools
import os
import random
import threading
import time

from locust import HttpUser, between, events, task

P95_MS = float(os.environ.get("LOADTEST_P95_MS", "500"))
MAX_ERROR_RATIO = float(os.environ.get("LOADTEST_MAX_ERROR_RATIO", "0.01"))
CA = os.environ.get(
    "LOADTEST_CA"
)  # CA privata (staging/e2e), altrimenti store di sistema
READS = ("me", "notifications", "preferences", "mfa-status", "feed-tokens", "index")


def _users():
    path = os.environ.get("LOADTEST_USERS_FILE")
    if not path:
        raise SystemExit("LOADTEST_USERS_FILE non impostata")
    with open(path) as fh:
        rows = [line.split(None, 1) for line in fh if line.strip()]
    return itertools.cycle([(u, p.strip()) for u, p in rows])


_lock = threading.Lock()
_credentials = None


def next_credentials():
    global _credentials
    with _lock:
        if _credentials is None:
            _credentials = _users()
        return next(_credentials)


class PortalUser(HttpUser):
    wait_time = between(
        1, 3
    )  # ~10-15 richieste/s con 25 utenti (limite proxy 20/s per IP)

    def on_start(self):
        if CA:
            self.client.verify = CA
        self.client.headers["Referer"] = self.host + "/"
        email, password = next_credentials()
        self.client.get("/api/v1/auth/csrf", name="csrf")
        for attempt in range(8):
            with self.client.post(
                "/api/v1/auth/login",
                json={"email": email, "password": password},
                headers={"X-CSRFToken": self.client.cookies.get("csrftoken", "")},
                name="login",
                catch_response=True,
            ) as resp:
                if resp.status_code == 200:
                    resp.success()
                    break
                if resp.status_code == 429:  # rate limit atteso: riprova più tardi
                    resp.success()
                    self.wait_seconds = int(resp.headers.get("Retry-After", "6"))
                else:
                    resp.failure(f"login {resp.status_code}")
                    break
            time.sleep(min(getattr(self, "wait_seconds", 6), 30) + random.random())
        self.client.get("/api/v1/auth/csrf", name="csrf")

    @task(5)
    def me(self):
        self.client.get("/api/v1/me", name="me")

    @task(4)
    def notifications(self):
        self.client.get("/api/v1/notifications", name="notifications")

    @task(1)
    def preferences(self):
        self.client.get("/api/v1/notifications/preferences", name="preferences")

    @task(1)
    def mfa_status(self):
        self.client.get("/api/v1/auth/mfa", name="mfa-status")

    @task(1)
    def feed_tokens(self):
        self.client.get("/api/v1/calendar-feed-tokens", name="feed-tokens")

    @task(2)
    def index(self):
        self.client.get("/", name="index")


@events.quitting.add_listener
def enforce_thresholds(environment, **_kw):
    stats = environment.stats
    reads = [stats.get(name, "GET") for name in READS]
    total = sum(s.num_requests for s in reads)
    failures = sum(s.num_failures for s in reads)
    # percentile aggregato sulle sole letture (login escluso: limitato di proposito)
    from locust.stats import StatsEntry

    agg = StatsEntry(stats, "reads", "GET")
    for s in reads:
        agg.extend(s)
    p95 = agg.get_response_time_percentile(0.95) if total else float("inf")
    p50 = agg.get_response_time_percentile(0.50) if total else float("inf")
    ratio = failures / total if total else 1.0
    msg = (
        f"letture={total} errori={failures} ({ratio:.2%}) p50={p50:.0f}ms "
        f"p95={p95:.0f}ms soglia_p95={P95_MS:.0f}ms"
    )
    print(f"LOADTEST {msg}", flush=True)
    if total == 0 or p95 >= P95_MS or ratio > MAX_ERROR_RATIO:
        environment.process_exit_code = 1
