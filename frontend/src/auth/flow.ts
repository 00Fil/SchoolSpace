/**
 * Logica pura del flusso di accesso (testabile senza DOM): quale passo mostrare dopo
 * ogni risposta del server, lettura dei token dal frammento URL, invito in sospeso.
 */
import type { S } from "../api/schema.gen";

export type Step =
  | { kind: "login" }
  | { kind: "mfa-verify" }
  | { kind: "mfa-setup" }
  | { kind: "recovery-codes"; codes: string[]; then: Step }
  | { kind: "context"; contexts: S.Role[]; current: string | null }
  | { kind: "done" };

/** Passo successivo dopo login, conferma o verifica MFA. */
export function nextStep(r: S.LoginResult): Step {
  if (r.mfa_required) return r.mfa_enrolled ? { kind: "mfa-verify" } : { kind: "mfa-setup" };
  const after: Step = r.context_required && (r.contexts?.length || 0) > 1
    ? { kind: "context", contexts: r.contexts || [], current: r.context ?? null }
    : { kind: "done" };
  if (r.recovery_codes?.length) return { kind: "recovery-codes", codes: r.recovery_codes, then: after };
  return after;
}

/** Pagine pubbliche raggiunte dai link email: il token sta nel frammento (#token=…), mai nella query. */
export type PublicPage = "invite" | "reset" | null;
export function publicPage(pathname: string): PublicPage {
  const p = pathname.replace(/\/+$/, "");
  if (p === "/invito") return "invite";
  if (p === "/reimposta-password") return "reset";
  return null;
}
export function tokenFromHash(hash: string): string {
  const h = hash.replace(/^#/, "");
  const v = new URLSearchParams(h).get("token") || "";
  return /^[A-Za-z0-9_\-.~]{8,128}$/.test(v) ? v : "";
}

/** Un invito per un account già esistente si accetta dopo l'accesso (409 LOGIN_REQUIRED). */
const PENDING = "ripetizioni-pending-invite";
type Store = Pick<Storage, "getItem" | "setItem" | "removeItem">;
const store = (): Store | null => { try { return typeof sessionStorage !== "undefined" ? sessionStorage : null; } catch { return null; } };
export function savePendingInvite(token: string, s: Store | null = store()) { s?.setItem(PENDING, token); }
export function takePendingInvite(s: Store | null = store()): string {
  const t = s?.getItem(PENDING) || ""; s?.removeItem(PENDING); return t;
}

/** Suggerimenti locali sulla password: il controllo vero resta sul server (WEAK_PASSWORD). */
export function passwordHints(pw: string, email = ""): string[] {
  const out: string[] = [];
  if (pw.length < 12) out.push("Usa almeno 12 caratteri.");
  if (/^\d+$/.test(pw)) out.push("Non usare solo numeri.");
  const local = email.split("@")[0].toLowerCase();
  if (local.length >= 3 && pw.toLowerCase().includes(local)) out.push("Non includere il tuo indirizzo email.");
  return out;
}

/** Codici TOTP: 6 cifre, spazi ammessi durante la digitazione. */
export const cleanCode = (s: string) => s.replace(/\s+/g, "");
export const isTotp = (s: string) => /^\d{6}$/.test(cleanCode(s));

export const CONTEXT_LABEL: Record<string, { label: string; sub: string }> = {
  CENTER: { label: "Centro", sub: "Agenda, proposte, studenti e configurazione" },
  TUTOR: { label: "Tutor", sub: "Le tue lezioni, disponibilità e presenze" },
  GUARDIAN: { label: "Famiglia", sub: "Lezioni e disponibilità dei figli" },
  STUDENT: { label: "Studente", sub: "Le tue lezioni e disponibilità" },
};
