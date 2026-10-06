/** Utilità condivise dalle schermate P1 (Anagrafica, Tutor, Utenti e ruoli). */
import { useCallback, useEffect, useState } from "react";
import { api, list } from "../api";
import { ApiError } from "../api/client";

export type Load<T> = { data: T | null; error: unknown; loading: boolean; reload: () => void };

/** Carica un elenco paginato; gestisce caricamento ed errore in modo uniforme. */
export function useList<T>(path: string | null): Load<T[]> {
  const [data, setData] = useState<T[] | null>(null), [error, setError] = useState<unknown>(null), [loading, setLoading] = useState(false);
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (!path) { setData(null); return; }
    let alive = true; setLoading(true); setError(null);
    list<T>(path).then((x) => { if (alive) setData(x); }).catch((e) => { if (alive) setError(e); }).finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [path, tick]);
  return { data, error, loading, reload: useCallback(() => setTick((t) => t + 1), []) };
}

export const send = <T,>(method: string, path: string, body?: unknown) => api<T>(path, { method, body: body === undefined ? undefined : JSON.stringify(body) });

/** Messaggio leggibile per gli errori di scrittura; il conflitto di versione ha un testo dedicato. */
export function writeError(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.code === "VERSION_CONFLICT") return "Qualcun altro ha modificato questo dato nel frattempo. Ricarica e riprova.";
    if (e.code === "REASON_REQUIRED") return "Indica il motivo della modifica.";
    if (e.code === "INVITATION_EXISTS") return "Esiste già un invito aperto per questa email.";
    if (e.status === 403) return "Il tuo ruolo non permette questa operazione.";
    return e.message;
  }
  return "Operazione non riuscita.";
}

export const isConflict = (e: unknown) => e instanceof ApiError && e.code === "VERSION_CONFLICT";

export const RELATIONSHIPS: [string, string][] = [["PARENT", "Genitore"], ["LEGAL_GUARDIAN", "Tutore legale"], ["DELEGATE", "Delegato autorizzato"]];
export const INVITE_STATUS: Record<string, string> = { PENDING_VERIFICATION: "Relazione da verificare", SENT: "Inviato", ACCEPTED: "Accettato", REVOKED: "Revocato" };
