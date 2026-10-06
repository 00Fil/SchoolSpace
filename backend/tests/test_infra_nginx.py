"""Prova reale della configurazione nginx di produzione (GAP-J03, GAP-J08, GAP-I02).

Ricrea il layout dell'immagine in una directory temporanea, esegue lo script di
entrypoint, valida con ``nginx -t`` e avvia nginx davanti a un upstream finto per
verificare header di sicurezza, CSP, HSTS solo con TLS, endpoint interni chiusi,
limite del corpo, allowlist admin, pagina di manutenzione e correlation_id.
Saltato se il binario nginx non è disponibile (in CI è presente su ubuntu-latest).
"""

import http.client
import importlib.util
import http.server
import json
import os
import re
import shutil
import socket
import ssl
import subprocess
import threading
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
NGINX_SRC = ROOT / "infra" / "nginx"
_spec = importlib.util.spec_from_file_location(
    "local_layout", NGINX_SRC / "local_layout.py"
)
local_layout = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(local_layout)
build_layout = local_layout.build_layout
NGINX = shutil.which("nginx") or (
    "/usr/sbin/nginx" if Path("/usr/sbin/nginx").exists() else None
)
OPENSSL = shutil.which("openssl")

pytestmark = pytest.mark.skipif(NGINX is None, reason="nginx non installato")


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Upstream(http.server.BaseHTTPRequestHandler):
    seen = []

    def _reply(self):
        Upstream.seen.append(
            {
                "path": self.path,
                "rid": self.headers.get("X-Request-ID"),
                "proto": self.headers.get("X-Forwarded-Proto"),
            }
        )
        body = json.dumps({"ok": True, "path": self.path}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Server", "gunicorn")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._reply()

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)
        self._reply()

    def log_message(self, *args):
        pass


@pytest.fixture
def proxy(tmp_path, request):
    params = getattr(request, "param", {})
    upstream_port, http_port, https_port = free_port(), free_port(), free_port()
    server = http.server.ThreadingHTTPServer(("127.0.0.1", upstream_port), Upstream)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    Upstream.seen = []
    etc = build_layout(tmp_path, upstream_port, http_port, https_port)
    env = {
        **os.environ,
        "SERVER_NAME": "app.example.test",
        "CSP_MODE": params.get("csp", "enforce"),
        "ADMIN_ALLOW_CIDRS": params.get("admin", ""),
        "TLS_CERT": str(tmp_path / "tls/fullchain.pem"),
        "TLS_KEY": str(tmp_path / "tls/privkey.pem"),
        "HSTS_SECONDS": "31536000",
        "TLS_RELOAD_INTERVAL": "0",
    }
    if params.get("tls"):
        if not OPENSSL:
            pytest.skip("openssl assente")
        (tmp_path / "tls").mkdir()
        subprocess.run(
            [
                OPENSSL,
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-days",
                "1",
                "-subj",
                "/CN=app.example.test",
                "-keyout",
                env["TLS_KEY"],
                "-out",
                env["TLS_CERT"],
            ],
            check=True,
            capture_output=True,
        )
    subprocess.run(
        ["sh", str(tmp_path / "entry.sh")], env=env, check=True, capture_output=True
    )
    conf = str(etc / "nginx.conf")
    test = subprocess.run(
        [NGINX, "-t", "-p", str(tmp_path), "-c", conf], capture_output=True, text=True
    )
    assert test.returncode == 0, test.stderr
    proc = subprocess.Popen(
        [NGINX, "-p", str(tmp_path), "-c", conf, "-g", "daemon off;"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    for _ in range(50):
        try:
            socket.create_connection(("127.0.0.1", http_port), timeout=0.2).close()
            break
        except OSError:
            time.sleep(0.1)
    yield {"http": http_port, "https": https_port, "tmp": tmp_path}
    proc.terminate()
    proc.wait(5)
    server.shutdown()


def get(port, path, method="GET", body=None, headers=None, tls=False):
    if tls:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        conn = http.client.HTTPSConnection("127.0.0.1", port, timeout=5, context=ctx)
    else:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    conn.request(method, path, body=body, headers=headers or {})
    resp = conn.getresponse()
    data = resp.read()
    conn.close()
    return resp, data


def test_security_headers_and_csp_on_spa(proxy):
    resp, body = get(proxy["http"], "/qualunque/rotta")
    assert resp.status == 200 and b'id="root"' in body  # fallback SPA
    csp = resp.getheader("Content-Security-Policy")
    assert csp and "default-src 'self'" in csp and "frame-ancestors 'none'" in csp
    assert "'unsafe-inline'" not in csp and "'unsafe-eval'" not in csp
    assert re.search(r"script-src 'self' 'sha256-[A-Za-z0-9+/=]+'", csp)
    assert resp.getheader("X-Content-Type-Options") == "nosniff"
    assert resp.getheader("X-Frame-Options") == "DENY"
    assert resp.getheader("Referrer-Policy") == "same-origin"
    assert "camera=()" in resp.getheader("Permissions-Policy")
    assert resp.getheader("Strict-Transport-Security") is None  # mai HSTS senza TLS
    assert "nginx/" not in (resp.getheader("Server") or "")
    asset, _ = get(proxy["http"], "/assets/app.js")
    assert "immutable" in asset.getheader("Cache-Control") and asset.getheader(
        "Content-Security-Policy"
    )


def test_api_proxy_headers_and_request_id(proxy):
    resp, body = get(
        proxy["http"], "/api/v1/me", headers={"X-Request-ID": "edge-trace-0001"}
    )
    assert resp.status == 200 and json.loads(body)["path"] == "/api/v1/me"
    assert resp.getheader("X-Request-ID") == "edge-trace-0001"
    assert resp.getheader("Content-Security-Policy")
    assert resp.getheader("Server") != "gunicorn"
    assert (
        Upstream.seen[-1]["rid"] == "edge-trace-0001"
        and Upstream.seen[-1]["proto"] == "http"
    )
    get(proxy["http"], "/api/v1/me", headers={"X-Request-ID": "bad id with spaces"})
    assert re.fullmatch(r"[0-9a-f]{32}", Upstream.seen[-1]["rid"])


def test_internal_endpoints_and_admin_closed(proxy):
    for path in ("/metrics", "/healthz", "/readyz"):
        assert get(proxy["http"], path)[0].status == 404
    assert get(proxy["http"], "/admin/")[0].status == 403
    assert get(proxy["http"], "/api/v1/ready")[0].status == 200


@pytest.mark.parametrize("proxy", [{"admin": "127.0.0.1/32"}], indirect=True)
def test_admin_allowlist(proxy):
    assert get(proxy["http"], "/admin/")[0].status == 200


def test_body_limit(proxy):
    resp, _ = get(
        proxy["http"],
        "/api/v1/teaching-requests/",
        method="POST",
        body=b"x" * (1024 * 1024 + 10),
        headers={"Content-Type": "application/json"},
    )
    assert resp.status == 413


def test_maintenance_page(proxy):
    (proxy["tmp"] / "srv/maintenance/on").write_text("1")
    resp, body = get(proxy["http"], "/")
    assert resp.status == 503 and "Manutenzione in corso".encode() in body
    assert resp.getheader("Retry-After") == "600" and resp.getheader(
        "Content-Security-Policy"
    )
    assert get(proxy["http"], "/api/v1/me")[0].status == 503
    assert get(proxy["http"], "/nginx-health")[0].status == 200
    (proxy["tmp"] / "srv/maintenance/on").unlink()
    assert get(proxy["http"], "/")[0].status == 200


def test_login_rate_limited(proxy):
    statuses = [
        get(proxy["http"], "/api/v1/auth/login", method="POST", body=b"{}")[0].status
        for _ in range(10)
    ]
    assert 429 in statuses


def test_acme_challenge_served(proxy):
    acme = proxy["tmp"] / "var/www/acme/.well-known/acme-challenge"
    acme.mkdir(parents=True)
    (acme / "tok123").write_text("tok123.key")
    resp, body = get(proxy["http"], "/.well-known/acme-challenge/tok123")
    assert resp.status == 200 and body == b"tok123.key"


@pytest.mark.parametrize("proxy", [{"csp": "report-only"}], indirect=True)
def test_csp_report_only_mode(proxy):
    resp, _ = get(proxy["http"], "/")
    assert resp.getheader("Content-Security-Policy") is None
    assert resp.getheader("Content-Security-Policy-Report-Only")


@pytest.mark.parametrize("proxy", [{"tls": True}], indirect=True)
def test_tls_mode_redirects_and_hsts(proxy):
    resp, _ = get(proxy["http"], "/api/v1/me")
    assert resp.status == 308 and resp.getheader("Location").startswith("https://")
    assert get(proxy["http"], "/nginx-health")[0].status == 200
    resp, _ = get(proxy["https"], "/", tls=True)
    assert resp.status == 200
    assert (
        resp.getheader("Strict-Transport-Security")
        == "max-age=31536000; includeSubDomains"
    )
    resp, _ = get(proxy["https"], "/api/v1/me", tls=True)
    assert resp.status == 200 and Upstream.seen[-1]["proto"] == "https"
