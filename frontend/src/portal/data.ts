/**
 * Dati dei portali (GAP-G01/G02/G03) dal client tipizzato: panoramica multi-figlio/tutor,
 * eccezioni e presenze a cursore, richieste di cambio. Logica pura separata dalla vista.
 */
import { useCallback, useEffect, useState } from "react";
import { get } from "../api/client";
import { api, list } from "../api";
import type { S } from "../api/schema.gen";
import type { MyLesson } from "../app/myApi";

export type Overview = S.PortalOverview;
export type Child = S.PortalChild;

export type Load<T> = { data: T | null; error: unknown; loading: boolean; reload: () => void };
/** Caricamento con annullamento: una risposta arrivata tardi non sovrascrive quella nuova. */
export function useLoad<T>(fn: (signal: AbortSignal) => Promise<T>, deps: unknown[]): Load<T> {
  const [s, set] = useState<{ data: T | null; error: unknown; loading: boolean }>({ data: null, error: null, loading: true });
  const [n, setN] = useState(0);
  useEffect(() => {
    const ctl = new AbortController();
    set((x) => ({ ...x, loading: true, error: null }));
    fn(ctl.signal).then((data) => { if (!ctl.signal.aborted) set({ data, error: null, loading: false }); })
      .catch((error) => { if (!ctl.signal.aborted) set({ data: null, error, loading: false }); });
    return () => ctl.abort();
  }, [...deps, n]); // eslint-disable-line react-hooks/exhaustive-deps
  const reload = useCallback(() => setN((k) => k + 1), []);
  return { ...s, reload };
}

export const useOverview = (week?: string, enabled = true) =>
  useLoad((signal) => (enabled ? get("/portal/overview", { query: week ? { week } : {}, signal }) : Promise.resolve(null)), [week, enabled]);

/** Chi può chiedere un cambio per questa lezione: figli/sé con permesso, o il tutor della lezione. */
export function requestersFor(l: Pick<MyLesson, "as_tutor" | "participants" | "state" | "start_at">, ov: Overview | null, now = new Date()): { students: { id: string; name: string }[]; asTutor: boolean } {
  if (!ov || l.state !== "PUBLISHED" || new Date(l.start_at) <= now) return { students: [], asTutor: false };
  if (l.as_tutor) return { students: [], asTutor: !!ov.tutor };
  const ok = new Map(ov.children.filter((c) => c.permissions.can_request_changes && !c.read_only).map((c) => [c.student_id, c]));
  return { students: l.participants.filter((p) => ok.has(p.student_id)).map((p) => ({ id: p.student_id, name: p.name })), asTutor: false };
}

/** Carico del tutor rispetto ai limiti: percentuale e superamento per giorno e settimana. */
export function loadOf(t: S.PortalTutor) {
  const daily = t.limits?.daily_limit_minutes || 0, weekly = t.limits?.weekly_limit_minutes || 0;
  const week = t.week;
  const days = (week?.by_day || []).map((d) => ({ ...d, pct: daily ? Math.min(100, Math.round((d.minutes / daily) * 100)) : 0, over: !!daily && d.minutes > daily }));
  const total = week?.scheduled_minutes || 0;
  return { days, daily, weekly, total, weeklyPct: weekly ? Math.min(100, Math.round((total / weekly) * 100)) : 0, weeklyOver: !!weekly && total > weekly };
}

export const KIND_LABEL: Record<S.ChangeRequest["kind"], string> = { ABSENCE: "Assenza", CANCEL: "Cancellazione", RESCHEDULE: "Spostamento", OTHER: "Altro" };
export const CR_STATE: Record<S.ChangeRequest["state"], [string, "blue" | "green" | "red" | "plain"]> = {
  SUBMITTED: ["In attesa del centro", "blue"], ACCEPTED: ["Accolta", "green"], REJECTED: ["Respinta", "red"], WITHDRAWN: ["Ritirata", "plain"],
};
export const ATT_LABEL: Record<S.AttendanceStatus, string> = { PRESENT: "Presente", ABSENT: "Assente", JUSTIFIED: "Giustificato", NOT_RECORDED: "Non registrato" };
export const EXC_LABEL: Record<S.PortalException["kind"], string> = { ADD_AVAILABLE: "Disponibilità in più", REMOVE_AVAILABLE: "Assenza / non disponibile" };

/** Riepilogo mensile del tutor: ore previste, svolte, annullate e ripartizione per settimana. */
export function monthStats(rows: Pick<MyLesson, "state" | "start_at" | "end_at" | "as_tutor">[], now = Date.now()) {
  const mins = (l: Pick<MyLesson, "start_at" | "end_at">) => Math.round((new Date(l.end_at).getTime() - new Date(l.start_at).getTime()) / 60000);
  const mine = rows.filter((l) => l.as_tutor);
  const live = mine.filter((l) => l.state === "PUBLISHED"), off = mine.filter((l) => l.state === "CANCELLED");
  const done = live.filter((l) => new Date(l.end_at).getTime() <= now);
  const sum = (xs: typeof mine) => xs.reduce((a, l) => a + mins(l), 0);
  return { lessons: live.length, planned: sum(live), done: sum(done), doneCount: done.length, cancelled: off.length, cancelledMin: sum(off), left: sum(live) - sum(done) };
}
/** Stima del compenso: ore previste per tariffa oraria (in euro). */
export const earnings = (minutes: number, rate: number | null) => (rate && rate > 0 ? Math.round((minutes / 60) * rate * 100) / 100 : null);

/** Azioni in sospeso per i portali, condivise da campanella e panoramica (cache breve). */
export type Pending = { confirm: number | null; acks: number | null };
let pendingCache: { at: number; key: string; p: Promise<Pending> } | null = null;
export function loadPending(roles: string[]): Promise<Pending> {
  const key = roles.join(",");
  if (pendingCache && pendingCache.key === key && Date.now() - pendingCache.at < 20000) return pendingCache.p;
  const confirm = roles.includes("GUARDIAN")
    ? api<{ results: { awaiting?: string | null }[] }>("/change-requests/?state=SUBMITTED").then((r) => r.results.filter((x) => x.awaiting === "GUARDIANS").length).catch(() => null)
    : Promise.resolve(0);
  const acks = roles.includes("TUTOR")
    ? list<{ state: string }>("/schedule-acks").then((r) => r.filter((a) => a.state === "PENDING").length).catch(() => null)
    : Promise.resolve(0);
  const p = Promise.all([confirm, acks]).then(([c, a]) => ({ confirm: c, acks: a }));
  pendingCache = { at: Date.now(), key, p };
  return p;
}
