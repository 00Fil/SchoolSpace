"""v0.10 · Il tema Jitsi (infra/jitsi) resta allineato ai token Lumen del gestionale."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JITSI = ROOT / "infra" / "jitsi"


def dark_tokens():
    css = (ROOT / "frontend/src/lumen/tokens.css").read_text()
    block = css[css.index('[data-theme="dark"]{') :]
    block = block[: block.index("}")]
    return dict(re.findall(r"--([a-z0-9-]+):([^;]+);", block))


def test_branding_palette_uses_lumen_dark_tokens():
    tokens = dark_tokens()
    app = (ROOT / "frontend/src/app.css").read_text()
    fill_blue = re.search(
        r'\[data-theme="dark"\]\{[^}]*--fill-blue:(#[0-9A-Fa-f]{6})', app
    )
    palette = json.loads((JITSI / "static/branding.json").read_text())["customTheme"][
        "palette"
    ]
    assert (
        json.loads((JITSI / "static/branding.json").read_text())["backgroundColor"]
        == tokens["page"]
    )
    assert palette["uiBackground"] == tokens["page"]
    assert palette["ui02"] == tokens["frame"] and palette["ui03"] == tokens["solid"]
    assert palette["text01"] == tokens["text"] and palette["focus01"] == tokens["blue"]
    assert palette["action01"] == fill_blue.group(1)
    assert (
        palette["success01"] == tokens["green"] and palette["error01"] == tokens["red"]
    )


def test_theme_files_are_wired_into_the_image():
    docker = (JITSI / "web.Dockerfile").read_text()
    for path in (
        "infra/jitsi/static/",
        "frontend/src/lumen/fonts/BricolageGrotesque-Variable.woff2",
        "infra/jitsi/plugin.head.html",
        "infra/jitsi/custom-config.js",
        "infra/jitsi/05-lumen-theme.sh",
    ):
        assert path in docker, path
        assert (ROOT / path.split(" ")[0]).exists(), path
    head = (JITSI / "plugin.head.html").read_text()
    assert "/static/lumen/lumen.css" in head
    config = (JITSI / "custom-config.js").read_text()
    assert "config.dynamicBrandingUrl = '/static/lumen/branding.json'" in config
    assert "config.readOnlyName = true" in config
    css = (JITSI / "static/lumen.css").read_text()
    assert "Bricolage Grotesque" in css
    assert not re.search(r"\.css-[a-z0-9]+", css)  # niente classi generate


def test_no_service_name_collision_on_shared_network():
    """Un servizio "web" di Jitsi sulla rete di Dokploy veniva risolto dal proxy del
    gestionale al posto di Django: le API rispondevano HTML e l'app restava bianca."""
    import yaml

    jitsi = yaml.safe_load((ROOT / "compose.jitsi.yaml").read_text())["services"]
    app = yaml.safe_load((ROOT / "compose.dokploy.yaml").read_text())["services"]
    assert all(name.startswith("jitsi-") for name in jitsi)
    assert not set(jitsi) & set(app)
    shared = [
        n for n, s in jitsi.items() if "dokploy-network" in (s.get("networks") or {})
    ]
    assert shared == ["jitsi-web"]
    nginx = (ROOT / "infra/nginx/nginx.conf").read_text()
    assert "server ripetizioni-web:8000" in nginx and "server web:8000" not in nginx
    # Nome risolto a ogni ricreazione del container web, non solo all'avvio del proxy.
    assert "server ripetizioni-web:8000 resolve" in nginx
    assert "resolver 127.0.0.11" in nginx and "zone web_upstream" in nginx
    for compose in ("compose.dokploy.yaml", "compose.prod.yaml"):
        web = yaml.safe_load((ROOT / compose).read_text())["services"]["web"]
        assert "ripetizioni-web" in web["networks"]["backend"]["aliases"], compose


def test_jitsi_components_reach_prosody_by_service_name():
    """jicofo/jvb/web non dipendono dagli alias di rete (persi con alcuni deploy Dokploy)."""
    import yaml

    stack = yaml.safe_load((ROOT / "compose.jitsi.yaml").read_text())
    services = stack["services"]
    for name in ("jitsi-web", "jitsi-prosody", "jitsi-jicofo", "jitsi-jvb"):
        env = services[name]["environment"]
        assert env["XMPP_SERVER"] == "jitsi-prosody", name
        assert env["XMPP_BOSH_URL_BASE"] == "http://jitsi-prosody:5280", name
    assert services["jitsi-web"]["environment"]["COLIBRI_WEBSOCKET_JVB_LOOKUP_NAME"] == "jitsi-jvb"


def test_welcome_page_replaces_empty_jitsi_root():
    """https://meet.<dominio>/ senza stanza: pagina del centro, non l'app Jitsi."""
    import yaml

    head = (JITSI / "plugin.head.html").read_text()
    assert 'location.replace("/static/lumen/welcome.html")' in head
    page = (JITSI / "static/welcome.html").read_text()
    for needle in ("welcome.css", "welcome.js", "welcome-config.js", "data-site-link",
                   "Torna al sito del centro", 'class="veil"', "noindex"):
        assert needle in page, needle
    script = (JITSI / "static/welcome.js").read_text()
    assert '"#3B82F6"' in script and '"#000000"' in script and 'fade: "edges"' in script
    assert "cursorSize: 50" in script and "cursorStrength: 0.6" in script
    assert "prefers-reduced-motion" in script and "^https?:" in script
    assert "https://" not in script.replace("^https?:\\/\\/", "")  # nessuna risorsa esterna
    init = (JITSI / "05-lumen-theme.sh").read_text()
    assert "welcome-config.js" in init and "clean_url" in init
    env = yaml.safe_load((ROOT / "compose.jitsi.yaml").read_text())["services"]["jitsi-web"]["environment"]
    assert {"CENTER_NAME", "CENTER_SITE_URL", "CENTER_APP_URL"} <= set(env)


def test_dokploy_builds_backend_image_once():
    """Una sola build del backend: gli altri servizi riusano l'immagine locale."""
    import yaml

    services = yaml.safe_load((ROOT / "compose.dokploy.yaml").read_text())["services"]
    backend = {k: v for k, v in services.items() if v.get("image") == "ripetizioni-backend:dokploy"}
    built = [k for k, v in backend.items() if "build" in v]
    assert built == ["migrate"]
    assert all(v["pull_policy"] == "never" for k, v in backend.items() if k != "migrate")
