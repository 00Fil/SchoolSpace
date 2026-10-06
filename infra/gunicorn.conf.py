"""Configurazione gunicorn di produzione (GAP-J03). Valori sovrascrivibili da env."""

import os
import shutil

bind = os.environ.get("GUNICORN_BIND", "0.0.0.0:8000")
workers = int(os.environ.get("GUNICORN_WORKERS", "3"))  # 2-4 per vCPU (sync)
worker_class = "sync"
timeout = int(os.environ.get("GUNICORN_TIMEOUT", "30"))
graceful_timeout = 25
keepalive = 5
max_requests = int(os.environ.get("GUNICORN_MAX_REQUESTS", "1000"))
max_requests_jitter = int(os.environ.get("GUNICORN_MAX_REQUESTS_JITTER", "100"))
limit_request_line = 4094
limit_request_fields = 100
forwarded_allow_ips = os.environ.get(
    "GUNICORN_FORWARDED_ALLOW_IPS", "*"
)  # solo rete interna
worker_tmp_dir = "/dev/shm"
# Access log disattivato: lo emette apps.ops.middleware in JSON redatto (senza query string).
accesslog = None
errorlog = "-"
loglevel = os.environ.get("LOG_LEVEL", "info").lower()
logconfig_dict = {}  # usa la configurazione LOGGING di Django per i logger applicativi


def on_starting(server):
    path = os.environ.get("PROMETHEUS_MULTIPROC_DIR")
    if path:
        shutil.rmtree(path, ignore_errors=True)
        os.makedirs(path, exist_ok=True)


def child_exit(server, worker):
    if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        from prometheus_client import multiprocess

        multiprocess.mark_process_dead(worker.pid)
