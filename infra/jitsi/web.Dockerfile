# Jitsi Meet web con il tema Lumen del gestionale (v0.10).
# Contesto di build: radice del repository (serve il font in frontend/src/lumen/fonts).
ARG JITSI_IMAGE_VERSION=stable
FROM jitsi/web:${JITSI_IMAGE_VERSION}
COPY infra/jitsi/static/ /usr/share/jitsi-meet/static/lumen/
COPY frontend/src/lumen/fonts/BricolageGrotesque-Variable.woff2 /usr/share/jitsi-meet/static/lumen/
COPY infra/jitsi/plugin.head.html /usr/share/jitsi-meet/plugin.head.html
# Accodati a config.js e interface_config.js dall'avvio del container (meccanismo ufficiale
# di docker-jitsi-meet: /config/custom-*.js). /config è un volume: si copiano in /defaults
# e lo script di avvio li mette al loro posto a ogni partenza.
COPY infra/jitsi/custom-config.js infra/jitsi/custom-interface_config.js /defaults/lumen/
COPY infra/jitsi/05-lumen-theme.sh /etc/cont-init.d/05-lumen-theme
RUN chmod 0755 /etc/cont-init.d/05-lumen-theme
