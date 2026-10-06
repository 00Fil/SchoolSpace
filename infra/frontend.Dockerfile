# syntax=docker/dockerfile:1.7
# Frontend di produzione (GAP-J03): build statica Vite servita da Nginx non privilegiato,
# che fa anche da reverse proxy verso gunicorn con header di sicurezza e CSP.
ARG NODE_IMAGE=node:22-bookworm-slim
ARG NGINX_IMAGE=nginxinc/nginx-unprivileged:1.28-alpine
ARG PYTHON_IMAGE=python:3.13-slim-bookworm

# Static di Django. compose.prod.yaml sostituisce questo stage con l'immagine backend
# (additional_contexts: backend-static); Dokploy e build semplici usano questo.
FROM ${PYTHON_IMAGE} AS backend-static
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --require-hashes --no-deps -r /tmp/requirements.txt
WORKDIR /app
COPY backend/ /app/
RUN DJANGO_SETTINGS_MODULE=config.settings DJANGO_SECRET_KEY=build-only-not-secret \
    USE_SQLITE_FOR_TESTS=1 python manage.py collectstatic --noinput --verbosity 0

FROM ${NODE_IMAGE} AS build
WORKDIR /src
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build
# Hash CSP degli script inline di index.html (es. tema): niente 'unsafe-inline'.
COPY infra/nginx/csp-hashes.mjs /tmp/csp-hashes.mjs
RUN node /tmp/csp-hashes.mjs dist/index.html > /tmp/csp-script-hashes.txt

FROM ${NGINX_IMAGE} AS runtime
ARG BUILD_VERSION=dev
LABEL org.opencontainers.image.title="ripetizioni-proxy" \
      org.opencontainers.image.version="${BUILD_VERSION}"
USER root
RUN apk upgrade --no-cache && rm -f /etc/nginx/conf.d/default.conf \
 && mkdir -p /srv/frontend /srv/maintenance /var/www/acme /etc/nginx/tls \
 && chown -R 101:101 /srv/maintenance /var/www/acme
COPY infra/nginx/nginx.conf /etc/nginx/nginx.conf
COPY infra/nginx/conf.d/ /etc/nginx/templates-src/
COPY infra/nginx/snippets/ /etc/nginx/snippets/
COPY infra/nginx/maintenance.html /srv/maintenance-page/index.html
COPY infra/nginx/40-ripetizioni-config.sh /docker-entrypoint.d/40-ripetizioni-config.sh
COPY --from=build /src/dist/ /srv/frontend/
# Static di Django (admin): dall'immagine backend appena costruita, passata come build context
# nominato "backend-static" (compose: additional_contexts; buildx: --build-context).
COPY --from=backend-static /app/staticfiles/ /srv/static/
COPY --from=build /tmp/csp-script-hashes.txt /etc/nginx/csp-script-hashes.txt
RUN chmod 0755 /docker-entrypoint.d/40-ripetizioni-config.sh \
 && chown -R 101:101 /etc/nginx/conf.d \
 && echo "${BUILD_VERSION}" > /srv/frontend/version.txt
USER 101
EXPOSE 8080 8443
HEALTHCHECK --interval=30s --timeout=3s --retries=3 CMD wget -q -O /dev/null http://127.0.0.1:8080/nginx-health || exit 1
