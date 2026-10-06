#!/usr/bin/with-contenv bash
# Prima della generazione di config.js (10-config): copia le personalizzazioni del tema
# in /config, da dove docker-jitsi-meet le accoda a config.js e interface_config.js.
set -e
mkdir -p /config
cp -f /defaults/lumen/custom-config.js /config/custom-config.js
cp -f /defaults/lumen/custom-interface_config.js /config/custom-interface_config.js

# Pagina di benvenuto (https://meet.<dominio>/): nome del centro e collegamenti di ritorno.
# Valori ripuliti: URL solo http(s) con caratteri sicuri, nome senza virgolette/markup.
clean_url() {
  local value="$1"
  if [[ "$value" =~ ^https?://[A-Za-z0-9._~:/?#@!\$\&()*+,\;=%-]+$ ]]; then printf '%s' "$value"; fi
}
clean_text() { printf '%s' "$1" | tr -d '"\\<>`\r\n' | cut -c1-80; }
cat > /usr/share/jitsi-meet/static/lumen/welcome-config.js <<JS
window.LUMEN_WELCOME = {
  centerName: "$(clean_text "${CENTER_NAME:-}")",
  siteUrl: "$(clean_url "${CENTER_SITE_URL:-}")",
  appUrl: "$(clean_url "${CENTER_APP_URL:-}")"
};
JS
