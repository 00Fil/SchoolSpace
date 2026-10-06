/**
 * Client HTTP tipizzato dal contratto (GAP-G05). I tipi vengono da `schema.gen.ts`,
 * generato da `contracts/openapi.yaml`: un endpoint o un campo che non esiste nel
 * contratto è un errore di compilazione. Sessione + CSRF come il resto dell'app.
 */
import type { Paths, PathsWith } from "./schema.gen";

export const BASE = "/api/v1";

export class ApiError extends Error {
  constructor(public status: number, message: string, public code = "", public data: unknown = null, public retryAfter = 0) {
    super(message);
  }
}

/* ---------- eventi globali di sessione (GAP-G04: accesso revocato, contesto, MFA) ---------- */
export type SessionEvent = { type: "session-ended" | "context-required" | "mfa-required" | "forbidden"; path: string; data?: unknown };
const listeners = new Set<(e: SessionEvent) => void>();
export const onSessionEvent = (f: (e: SessionEvent) => void) => { listeners.add(f); return () => { listeners.delete(f); }; };
export const emitSessionEvent = (e: SessionEvent) => listeners.forEach((f) => f(e));

/** Endpoint per cui un 401/403 è una risposta attesa del flusso di accesso, non una revoca. */
const AUTH_FLOW = /^\/(auth\/(login|logout|csrf|mfa|password-reset)|invitations\/accept|me$)/;

export function csrfToken() {
  if (typeof document === "undefined") return "";
  return document.cookie.split("; ").find((s) => s.startsWith("csrftoken="))?.slice(10) || "";
}

function messageOf(data: Record<string, unknown>) {
  if (typeof data.message === "string") return data.message;
  if (typeof data.detail === "string") return data.detail;
  const parts = Object.entries(data)
    .filter(([k]) => k !== "code")
    .map(([k, v]) => `${k === "non_field_errors" ? "" : k + ": "}${Array.isArray(v) ? v.join(" ") : typeof v === "string" ? v : JSON.stringify(v)}`);
  return parts.join(" · ");
}

export type RequestOptions = { query?: Record<string, string | number | boolean | undefined | null>; body?: unknown; headers?: Record<string, string>; idempotencyKey?: string; signal?: AbortSignal; quiet?: boolean };

export function withQuery(path: string, query?: RequestOptions["query"]) {
  if (!query) return path;
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(query)) if (v !== undefined && v !== null && v !== "") q.set(k, String(v));
  const s = q.toString();
  return s ? path + (path.includes("?") ? "&" : "?") + s : path;
}

/** Trasporto unico: path relativo a /api/v1, JSON in/out, CSRF, errori con `code` stabile. */
export async function request<T = unknown>(method: string, path: string, opt: RequestOptions = {}): Promise<T> {
  const url = withQuery(path, opt.query);
  const headers: Record<string, string> = { "Content-Type": "application/json", "X-CSRFToken": csrfToken(), ...opt.headers };
  if (opt.idempotencyKey) headers["Idempotency-Key"] = opt.idempotencyKey;
  let response: Response;
  try {
    response = await fetch(BASE + url, { method, credentials: "same-origin", headers, signal: opt.signal, body: opt.body === undefined ? undefined : JSON.stringify(opt.body) });
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") throw e;
    throw new ApiError(0, "Connessione al server non riuscita.", "NETWORK");
  }
  const type = response.headers.get("content-type") || "";
  // Una pagina HTML al posto del JSON significa che la richiesta non è arrivata all'API
  // (proxy instradato sul servizio sbagliato, pagina di un altro stack): errore esplicito,
  // mai dati «vuoti» che fanno cadere l'interfaccia.
  if (response.ok && type.includes("text/html")) {
    throw new ApiError(502, "Il server ha risposto con una pagina invece che con i dati. Riprova tra poco o contatta l'amministratore.", "UNEXPECTED_RESPONSE");
  }
  const data = type.includes("json") ? await response.json().catch(() => ({})) : await response.text().catch(() => "");
  if (!response.ok) {
    const d = (data && typeof data === "object" ? data : {}) as Record<string, unknown>;
    const code = typeof d.code === "string" ? d.code : "";
    const err = new ApiError(response.status, messageOf(d) || `Errore ${response.status}`, code, data, Number(response.headers.get("Retry-After")) || 0);
    if (!opt.quiet && !AUTH_FLOW.test(url)) {
      if (code === "CONTEXT_REQUIRED") emitSessionEvent({ type: "context-required", path: url, data });
      else if (code === "MFA_REQUIRED") emitSessionEvent({ type: "mfa-required", path: url, data });
      else if (response.status === 401 || code === "NOT_AUTHENTICATED" || code === "MFA_SESSION_EXPIRED") emitSessionEvent({ type: "session-ended", path: url, data });
      else if (response.status === 403) emitSessionEvent({ type: "forbidden", path: url, data });
    }
    throw err;
  }
  return data as T;
}

/* ---------- funzioni tipizzate sui path del contratto ---------- */
type Op<P extends keyof Paths, M extends string> = M extends keyof Paths[P] ? Paths[P][M] : never;
type Field<O, K extends string> = O extends Record<K, infer V> ? V : never;
export type ResponseOf<P extends keyof Paths, M extends string = "get"> = Field<Op<P, M>, "response">;
export type BodyOf<P extends keyof Paths, M extends string = "post"> = Field<Op<P, M>, "body">;
export type QueryOf<P extends keyof Paths, M extends string = "get"> = Field<Op<P, M>, "query">;
type Opts<P extends keyof Paths, M extends string> = Omit<RequestOptions, "query" | "body"> & { params?: Record<string, string>; query?: QueryOf<P, M> };

/** Sostituisce `{pk}`/`{id}` con valori codificati; un parametro mancante è un errore. */
export function fillPath(path: string, params: Record<string, string> = {}) {
  return path.replace(/\{(\w+)\}/g, (_, k: string) => {
    if (!(k in params)) throw new Error(`Parametro di percorso mancante: ${k}`);
    return encodeURIComponent(params[k]);
  });
}
export function get<P extends PathsWith<"get">>(path: P, opt: Opts<P, "get"> = {}) {
  return request<ResponseOf<P, "get">>("GET", fillPath(path, opt.params), opt as RequestOptions);
}
export function post<P extends PathsWith<"post">>(path: P, body: BodyOf<P, "post">, opt: Opts<P, "post"> = {}) {
  return request<ResponseOf<P, "post">>("POST", fillPath(path, opt.params), { ...(opt as RequestOptions), body });
}
export function put<P extends PathsWith<"put">>(path: P, body: BodyOf<P, "put">, opt: Opts<P, "put"> = {}) {
  return request<ResponseOf<P, "put">>("PUT", fillPath(path, opt.params), { ...(opt as RequestOptions), body });
}

/* ---------- paginazione (cursore opaco o `next` DRF) ---------- */
export type Page<T> = { results: T[]; next?: string | null; previous?: string | null };
/** Converte il link `next` del server in un path /api/v1 relativo, rifiutando altre origini. */
export function nextPath(next: string | null | undefined, origin: string): string | null {
  if (!next) return null;
  const url = new URL(next, origin);
  if (url.origin !== origin || !url.pathname.startsWith(BASE + "/")) throw new ApiError(0, "Paginazione fuori origine", "PAGINATION_ORIGIN");
  return url.pathname.slice(BASE.length) + url.search;
}
const here = () => (typeof location !== "undefined" ? location.origin : "http://localhost");
/**
 * Scorre le pagine seguendo `next` (cursore opaco: il client non costruisce mai offset).
 * Si ferma a `maxPages` segnalando `truncated`, e rifiuta un cursore ripetuto (ciclo).
 */
export async function* pages<T>(path: string, opt: { maxPages?: number; signal?: AbortSignal } = {}): AsyncGenerator<{ items: T[]; truncated: boolean }> {
  const max = opt.maxPages ?? 50, seen = new Set<string>();
  let cur: string | null = path, n = 0;
  while (cur) {
    if (seen.has(cur)) throw new ApiError(0, "Il server ha restituito due volte lo stesso cursore.", "PAGINATION_LOOP");
    seen.add(cur);
    const page: Page<T> = await request<Page<T>>("GET", cur, { signal: opt.signal });
    n += 1;
    cur = nextPath(page.next, here());
    const truncated = !!cur && n >= max;
    yield { items: page.results, truncated };
    if (truncated) return;
  }
}
/** Tutte le righe (fino a `maxPages`); `truncated` dice se l'elenco è parziale. */
export async function collect<T>(path: string, opt: { maxPages?: number; signal?: AbortSignal } = {}) {
  const rows: T[] = []; let truncated = false;
  for await (const p of pages<T>(path, opt)) { rows.push(...p.items); truncated = p.truncated; }
  return { rows, truncated };
}

/** Chiave di idempotenza: «Riprova» riusa la stessa chiave, quindi nessun doppio effetto. */
export function newIdempotencyKey() {
  const c = (globalThis as { crypto?: Crypto }).crypto;
  if (c?.randomUUID) return c.randomUUID();
  return "k-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2);
}
