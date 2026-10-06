#!/usr/bin/with-contenv bash
# Prima della generazione di config.js (10-config): copia le personalizzazioni del tema
# in /config, da dove docker-jitsi-meet le accoda a config.js e interface_config.js.
set -e
mkdir -p /config
cp -f /defaults/lumen/custom-config.js /config/custom-config.js
cp -f /defaults/lumen/custom-interface_config.js /config/custom-interface_config.js
