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
    for compose in ("compose.dokploy.yaml", "compose.prod.yaml"):
        web = yaml.safe_load((ROOT / compose).read_text())["services"]["web"]
        assert "ripetizioni-web" in web["networks"]["backend"]["aliases"], compose
