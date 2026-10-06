/**
 * Impostazioni di build dell'interfaccia.
 * - TECH_ADMIN: strumenti tecnici (laboratorio, registro decisioni, identificativi e codici di errore)
 *   visibili solo in sviluppo o con VITE_TECH_ADMIN=1. In produzione restano nascosti.
 * - ENV_LABEL: etichetta d'ambiente facoltativa (es. «Collaudo»), mostrata in testata solo se impostata.
 */
const env: Partial<ImportMetaEnv> = import.meta.env || {};
export const TECH_ADMIN = !!env.DEV || env.VITE_TECH_ADMIN === "1";
export const ENV_LABEL: string = String(env.VITE_ENV_LABEL || "").trim();
