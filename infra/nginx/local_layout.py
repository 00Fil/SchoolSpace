"""Layout locale dell'immagine proxy (infra/frontend.Dockerfile) per eseguire la stessa
configurazione nginx fuori da Docker: usato da backend/tests/test_infra_nginx.py e da
scripts/e2e_local.py (GAP-J03, J07). Riscrive i percorsi assoluti verso una directory
temporanea e porte/upstream verso localhost.
"""

import re
import shutil
import subprocess
from pathlib import Path

NGINX_SRC = Path(__file__).resolve().parent

_FAKE_INDEX = (
    "<!doctype html><html><head><script>document.documentElement.dataset.x=1</script></head>"
    '<body><div id="root"></div><script type="module" src="/assets/app.js"></script></body></html>'
)


def build_layout(
    tmp: Path,
    upstream_port: int,
    http_port: int,
    https_port: int,
    frontend_dist: Path | None = None,
    static_root: Path | None = None,
) -> Path:
    """Crea ``tmp/etc/nginx`` e ``tmp/srv``; ``frontend_dist``/``static_root`` reali opzionali."""
    etc = tmp / "etc" / "nginx"
    (etc / "conf.d").mkdir(parents=True)
    for sub in (
        "srv/frontend/assets",
        "srv/maintenance",
        "srv/maintenance-page",
        "srv/static",
        "var/www/acme",
        "tmp",
    ):
        (tmp / sub).mkdir(parents=True, exist_ok=True)
    shutil.copy(
        "/etc/nginx/mime.types"
        if Path("/etc/nginx/mime.types").exists()
        else NGINX_SRC / "nginx.conf",
        etc / "mime.types",
    )
    shutil.copytree(NGINX_SRC / "conf.d", etc / "templates-src")
    shutil.copytree(NGINX_SRC / "snippets", etc / "snippets")
    shutil.copy(NGINX_SRC / "nginx.conf", etc / "nginx.conf")
    shutil.copy(NGINX_SRC / "maintenance.html", tmp / "srv/maintenance-page/index.html")
    shutil.copy(NGINX_SRC / "40-ripetizioni-config.sh", tmp / "entry.sh")
    if frontend_dist:
        shutil.copytree(frontend_dist, tmp / "srv/frontend", dirs_exist_ok=True)
    else:
        (tmp / "srv/frontend/index.html").write_text(_FAKE_INDEX)
        (tmp / "srv/frontend/assets/app.js").write_text("console.log(1)")
    if static_root:
        shutil.copytree(static_root, tmp / "srv/static", dirs_exist_ok=True)
    hashes = (
        subprocess.run(
            [
                "node",
                str(NGINX_SRC / "csp-hashes.mjs"),
                str(tmp / "srv/frontend/index.html"),
            ],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        if shutil.which("node")
        else "'sha256-test'"
    )
    (etc / "csp-script-hashes.txt").write_text(hashes)

    mapping = {
        "/etc/nginx": str(etc),
        "/srv/": f"{tmp}/srv/",
        "/var/www/acme": str(tmp / "var/www/acme"),
        "/tmp/": f"{tmp}/tmp/",
    }
    pattern = re.compile("|".join(re.escape(k) for k in mapping))

    def rewrite(path: Path):
        text = pattern.sub(lambda m: mapping[m.group(0)], path.read_text())
        text = text.replace("server ripetizioni-web:8000", f"server 127.0.0.1:{upstream_port}")
        text = text.replace("listen 8080", f"listen 127.0.0.1:{http_port}").replace(
            "listen 8443", f"listen 127.0.0.1:{https_port}"
        )
        text = text.replace("ssl_stapling on;", "ssl_stapling off;").replace(
            "ssl_stapling_verify on;", ""
        )
        path.write_text(text)

    for path in [
        etc / "nginx.conf",
        tmp / "entry.sh",
        *etc.joinpath("templates-src").iterdir(),
        *etc.joinpath("snippets").iterdir(),
    ]:
        rewrite(path)
    return etc
