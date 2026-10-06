# Solo sviluppo (compose.yaml): server Vite con hot reload. Mai in produzione.
# /app appartiene all'utente node: Vite scrive in /app il file temporaneo della
# configurazione (vite.config.ts.timestamp-*.mjs) e la cache in node_modules/.vite.
FROM node:22-bookworm-slim
WORKDIR /app
RUN chown node:node /app
USER node
COPY --chown=node:node frontend/package*.json ./
RUN npm ci
COPY --chown=node:node frontend/ .
EXPOSE 5173
CMD ["npm", "run", "dev"]
