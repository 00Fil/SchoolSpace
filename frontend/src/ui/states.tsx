/**
 * Stati obbligatori delle viste (GAP-G04): ogni schermata mostra in modo esplicito
 * accesso revocato, dati obsoleti, ricerca non conclusiva, risultato parziale e conflitto,
 * oltre a caricamento, vuoto, errore, rete assente e funzione non attiva.
 */
import { ReactNode } from "react";
import { ApiError } from "../api/client";
import { human } from "../messages";
import { Btn, Notice, Skeleton, Tech } from "./core";

export type StateKind = "loading" | "empty" | "error" | "offline" | "revoked" | "forbidden" | "stale" | "inconclusive" | "partial" | "conflict" | "disabled";

type Copy = { title: string; text: string; tone: "info" | "ok" | "warn" | "bad"; action?: string };
export const STATE_COPY: Record<Exclude<StateKind, "loading">, Copy> = {
  empty: { title: "Ancora niente da mostrare", text: "Quando ci saranno dati li troverai qui.", tone: "info" },
  error: { title: "Qualcosa non ha funzionato", text: "Non siamo riusciti a completare l’operazione. Nulla è stato salvato a metà.", tone: "bad", action: "Riprova" },
  offline: { title: "Connessione assente", text: "Il server non risponde. Controlla la rete e riprova: la stessa operazione non verrà duplicata.", tone: "bad", action: "Riprova" },
  revoked: { title: "Accesso non più disponibile", text: "Il centro ha revocato o modificato l’autorizzazione per questi dati, oppure la sessione è terminata. Se pensi sia un errore, contatta il centro.", tone: "warn", action: "Torna alla panoramica" },
  forbidden: { title: "Non è una funzione del tuo ruolo", text: "Questi dati sono visibili solo a chi ha l’autorizzazione del centro.", tone: "warn" },
  stale: { title: "Dati non aggiornati", text: "Nel frattempo qualcuno ha modificato questi dati. Ricarica per vedere la versione attuale prima di continuare.", tone: "warn", action: "Ricarica" },
  inconclusive: { title: "Ricerca non conclusiva", text: "Non è stato possibile stabilire una risposta certa entro il tempo disponibile. Nessun risultato è stato inventato: riprova o restringi la ricerca.", tone: "warn", action: "Riprova" },
  partial: { title: "Elenco parziale", text: "Vedi solo una parte dei risultati. Restringi il periodo o i filtri per vedere tutto.", tone: "info" },
  conflict: { title: "C’è un conflitto da risolvere", text: "L’operazione si sovrappone a qualcosa che esiste già. Non è stato salvato nulla.", tone: "bad", action: "Ricarica e riprova" },
  disabled: { title: "Funzione non attiva", text: "In questo ambiente la funzione non è abilitata.", tone: "info" },
};

/** Classifica un errore API in uno stato di vista. */
export function classify(e: unknown): Exclude<StateKind, "loading" | "empty" | "partial"> {
  if (!(e instanceof ApiError)) return "error";
  const c = e.code;
  if (e.status === 0) return "offline";
  if (["VERSION_CONFLICT", "STALE_INPUT", "SNAPSHOT_CHANGED", "DATA_CONFLICT", "REVISION_CHANGED"].includes(c)) return "stale";
  if (["BOOKING_CONFLICT", "IDEMPOTENCY_CONFLICT", "TRANSITION_CONFLICT", "CALENDAR_VALIDATION_FAILED"].includes(c)) return "conflict";
  if (["UNKNOWN", "TIMEOUT", "INCONCLUSIVE", "SOFT_TIME_LIMIT"].includes(c)) return "inconclusive";
  if (["FEATURE_DISABLED", "DEVELOPMENT_ONLY", "POSTGRES_REQUIRED", "IMPLEMENTATION_PENDING"].includes(c) || e.status === 503) return "disabled";
  if (e.status === 401 || ["NOT_AUTHENTICATED", "MFA_SESSION_EXPIRED", "CONTEXT_NOT_GRANTED", "NOT_FOUND"].includes(c) || e.status === 404) return "revoked";
  if (e.status === 403) return "forbidden";
  if (e.status === 409) return "stale";
  return "error";
}

type Props = { kind: StateKind; title?: string; children?: ReactNode; onAction?: () => void; actionLabel?: string; error?: unknown; compact?: boolean };
/** Riquadro di stato con titolo umano, prossimo passo e dettagli tecnici richiudibili. */
export function ViewState({ kind, title, children, onAction, actionLabel, error, compact }: Props) {
  if (kind === "loading") return <Skeleton rows={compact ? 2 : 3} />;
  const copy = STATE_COPY[kind];
  const h = error !== undefined ? human(error) : null;
  const body = children ?? (kind === "error" && h ? h.text : copy.text);
  const label = actionLabel || copy.action;
  if (kind === "empty") return <div className="empty" data-state={kind}><b>{title || copy.title}</b>{body}{onAction && label && <div style={{ marginTop: 12 }}><Btn kind="sm" onClick={onAction}>{label}</Btn></div>}</div>;
  return <div data-state={kind}>
    <Notice kind={copy.tone} title={title || copy.title} action={onAction && label ? <Btn kind="sm" onClick={onAction}>{label}</Btn> : undefined}>
      {body}
      {h?.detail && <Tech>{h.detail}</Tech>}
    </Notice>
  </div>;
}

/** Stato di un errore: classifica e mostra il riquadro giusto. */
export function ErrorState({ error, onRetry, title }: { error: unknown; onRetry?: () => void; title?: string }) {
  const kind = classify(error);
  const retry = kind === "revoked" ? () => { location.hash = "#/panoramica"; } : onRetry;
  return <ViewState kind={kind} error={kind === "error" ? error : undefined} onAction={retry} title={title}>{kind === "error" ? undefined : extra(kind, error)}</ViewState>;
}
function extra(kind: StateKind, error: unknown) {
  const base = STATE_COPY[kind as Exclude<StateKind, "loading">].text;
  const h = human(error);
  return kind === "conflict" && h.text && !h.text.startsWith("Operazione") ? h.text : base;
}
