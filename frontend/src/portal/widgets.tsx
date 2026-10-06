/**
 * Widget condivisi dalle dashboard: lezioni del giorno con tutti i dettagli,
 * accesso diretto alle lezioni online, avvisi che richiedono un'azione.
 */
import { ReactNode, useEffect, useState } from "react";
import { ApiError } from "../api";
import { addDays, dayLabel, dayShort, duration, hm, rangeOf, rome, timeOf, todayRome } from "../format";
import { human, LOCATION, MODE } from "../messages";
import { Btn, Icon, IconName, Tag } from "../ui/core";
import type { MyLesson } from "../app/myApi";
import type { Lesson } from "../app/calendarApi";
import { joinLesson } from "./VideoRoom";

/** Lezione normalizzata per la visualizzazione (portali e centro). */
export type DayLesson = {
  id: string; state: string; start_at: string; end_at: string; subject_name: string; tutor_name: string;
  mode: string; location: string; place: string | null; students: string[]; others: number; asTutor: boolean;
};
export const fromMine = (l: MyLesson): DayLesson => ({
  id: l.id, state: l.state, start_at: l.start_at, end_at: l.end_at, subject_name: l.subject_name, tutor_name: l.tutor_name,
  mode: l.mode, location: l.location, place: l.space_name, students: l.participants.map((p) => p.name), others: l.other_participants, asTutor: l.as_tutor,
});
export const fromCenter = (l: Lesson, places: Map<string, string>, asTutor = false): DayLesson => ({
  id: l.id, state: l.state, start_at: l.start_at, end_at: l.end_at, subject_name: l.subject_name, tutor_name: l.tutor_name,
  mode: l.mode, location: l.location, place: l.space ? places.get(l.space) || null : null, students: l.participants.map((p) => p.name), others: 0, asTutor,
});

export const minutes = (l: Pick<DayLesson, "start_at" | "end_at">) => Math.round((new Date(l.end_at).getTime() - new Date(l.start_at).getTime()) / 60000);
/** "Oggi", "Domani" o il giorno per esteso. */
export function dayName(date: string) {
  const t = todayRome();
  return date === t ? "Oggi" : date === addDays(t, 1) ? "Domani" : dayLabel(date);
}
/** Stato temporale della lezione rispetto a ora. */
export function phase(l: Pick<DayLesson, "start_at" | "end_at" | "state">, now = Date.now()): { label: string; tone: "green" | "amber" | "blue" | "plain" | "red"; live: boolean } {
  if (l.state === "CANCELLED") return { label: "Annullata", tone: "red", live: false };
  const s = new Date(l.start_at).getTime(), e = new Date(l.end_at).getTime();
  if (now >= e) return { label: "Conclusa", tone: "plain", live: false };
  if (now >= s) return { label: "In corso", tone: "green", live: true };
  const m = Math.round((s - now) / 60000);
  if (m <= 60) return { label: `Tra ${m} min`, tone: "amber", live: false };
  if (rome(l.start_at).date === todayRome()) return { label: `Alle ${timeOf(l.start_at)}`, tone: "blue", live: false };
  return { label: dayShort(rome(l.start_at).date), tone: "blue", live: false };
}
/** Si aggiorna ogni minuto: countdown e "in corso" restano corretti senza ricaricare. */
export function useNow(step = 60000) {
  const [n, setN] = useState(Date.now());
  useEffect(() => { const t = setInterval(() => setN(Date.now()), step); return () => clearInterval(t); }, [step]);
  return n;
}

/** Ingresso nelle lezioni online: il link arriva dal server solo nella finestra consentita;
 *  con Jitsi attivo la stanza si apre integrata (v0.10). */
export function useJoin() {
  const [msg, setMsg] = useState<Record<string, string>>({});
  async function join(id: string) {
    try { await joinLesson(id); setMsg((m) => ({ ...m, [id]: "" })); }
    catch (e) {
      const h = human(e), d = ((e instanceof ApiError ? e.data : null) || {}) as { opens_at?: string };
      const text = h.code === "MEETING_NOT_OPEN" && d.opens_at ? `Il link si apre alle ${hm(rome(d.opens_at).min)}, poco prima della lezione.` : h.code === "MEETING_NOT_CONFIGURED" ? "La videolezione non è ancora attiva: contatta il centro." : h.text;
      setMsg((m) => ({ ...m, [id]: text }));
    }
  }
  return { msg, join };
}
export type Join = ReturnType<typeof useJoin>;

const where = (l: DayLesson) => l.mode === "ONLINE" ? (l.location === "ON_SITE" ? `Online dal centro${l.place ? ` · ${l.place}` : ""}` : "Online, da remoto") : `${l.place || "Aula da definire"} · ${LOCATION[l.location] || "In sede"}`;
const people = (l: DayLesson) => l.students.length ? l.students.join(", ") + (l.others === 1 ? " e un altro studente" : l.others ? ` e altri ${l.others} studenti` : "") : l.others ? `${l.others} studenti` : "Nessuno studente";

/** Tutti i dettagli di una lezione: orario, luogo o link, persone. */
export function LessonDetail({ l, join, extra, noTime }: { l: DayLesson; join: Join; extra?: ReactNode; noTime?: boolean }) {
  const online = l.mode === "ONLINE", off = l.state === "CANCELLED", ended = new Date(l.end_at).getTime() <= Date.now();
  return <div className="ld">
    <dl className="ld-facts">
      {!noTime && <div><dt><Icon n="clock" />Orario</dt><dd>{dayName(rome(l.start_at).date)}, {rangeOf(l.start_at, l.end_at)} <span className="muted">· {duration(minutes(l))}</span></dd></div>}
      <div><dt><Icon n={online ? "mic" : "home"} />{online ? "Modalità" : "Dove"}</dt><dd>{where(l)}</dd></div>
      <div><dt><Icon n="users" />{l.asTutor || !l.students.length ? "Studenti" : "Partecipanti"}</dt><dd>{people(l)}{l.students.length + l.others > 1 ? <span className="muted"> · lezione di gruppo</span> : null}</dd></div>
      {!l.asTutor && <div><dt><Icon n="user" />Tutor</dt><dd>{l.tutor_name}</dd></div>}
    </dl>
    {off ? <p className="ld-off">Questa lezione è stata annullata.</p> : <div className="ld-acts">
      {online && !ended && <Btn kind="sm join" isle="arrow" onClick={() => join.join(l.id)}>Entra nella lezione</Btn>}
      {extra}
    </div>}
    {join.msg[l.id] && <p className="fine" role="status">{join.msg[l.id]}</p>}
  </div>;
}

/** Riga di lezione espandibile: compatta, al clic mostra tutti i dettagli. */
export function LessonRow({ l, join, open, onToggle, now, showDay, extra }: { l: DayLesson; join: Join; open: boolean; onToggle: () => void; now: number; showDay?: boolean; extra?: ReactNode }) {
  const p = phase(l, now), id = "ld-" + l.id;
  return <li className={"lr" + (open ? " open" : "") + (p.live ? " live" : "") + (l.state === "CANCELLED" ? " off" : "") + (p.label === "Conclusa" ? " done" : "")}>
    <button type="button" className="lr-head" aria-expanded={open} aria-controls={id} onClick={onToggle}>
      <span className="lr-time"><b>{timeOf(l.start_at)}</b><small>{showDay ? dayShort(rome(l.start_at).date) : timeOf(l.end_at)}</small></span>
      <span className="lr-main"><b>{l.subject_name}</b><small>{l.asTutor ? people(l) : `con ${l.tutor_name}`} · {MODE[l.mode] || l.mode}</small></span>
      {!(showDay && l.state !== "CANCELLED" && rome(l.start_at).date !== todayRome()) && <Tag tone={p.tone}>{p.label}</Tag>}
      <span className="lr-chev"><Icon n="chev" size={16} /></span>
    </button>
    {open && <div id={id} className="lr-body reveal"><LessonDetail l={l} join={join} extra={extra} /></div>}
  </li>;
}

/** Elenco di lezioni: la prima ancora da svolgere è aperta, le altre si aprono al clic. */
export function LessonAccordion({ rows, join, showDay, extra, closed }: { rows: DayLesson[]; join: Join; showDay?: boolean; extra?: (l: DayLesson) => ReactNode; closed?: boolean }) {
  const now = useNow(), first = closed ? undefined : rows.find((l) => l.state !== "CANCELLED" && new Date(l.end_at).getTime() > now)?.id;
  const [open, setOpen] = useState<Set<string>>(() => new Set(first ? [first] : []));
  const toggle = (id: string) => setOpen((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  return <ul className="lr-list">{rows.map((l) => <LessonRow key={l.id} l={l} join={join} now={now} showDay={showDay} open={open.has(l.id)} onToggle={() => toggle(l.id)} extra={extra?.(l)} />)}</ul>;
}

/** Avvisi che richiedono un'azione: il widget compare solo se c'è qualcosa da fare. */
export type Alert = { id: string; tone: "red" | "amber" | "blue"; icon: IconName; title: string; text?: string; action?: [string, () => void]; dismiss?: () => void };
export function Alerts({ items, title = "Da fare adesso" }: { items: Alert[]; title?: string }) {
  if (!items.length) return null;
  return <section className="module alerts" aria-labelledby="h-alerts">
    <div className="m-head"><h2 className="m-title" id="h-alerts">{title}</h2><span className="count-pill" aria-label={`${items.length} avvisi`}>{items.length}</span></div>
    <ul className="alert-list">{items.map((a) => <li key={a.id} className={"alert " + a.tone} role={a.tone === "red" ? "alert" : undefined}>
      <span className="alert-ic"><Icon n={a.icon} /></span>
      <div className="alert-tx"><b>{a.title}</b>{a.text && <small>{a.text}</small>}</div>
      <div className="alert-acts">{a.action && <Btn kind="sm" onClick={a.action[1]}>{a.action[0]}</Btn>}
        {a.dismiss && <button type="button" className="circle sm-x" aria-label={`Nascondi: ${a.title}`} onClick={a.dismiss}><Icon n="x" size={16} /></button>}</div>
    </li>)}</ul>
  </section>;
}

/** Avvisi già nascosti dall'utente (per dispositivo). */
const HIDDEN = "ripetizioni-avvisi-nascosti";
export function useHidden() {
  const [h, setH] = useState<Set<string>>(() => { try { return new Set(JSON.parse(localStorage.getItem(HIDDEN) || "[]")); } catch { return new Set(); } });
  const hide = (id: string) => setH((s) => { const n = new Set(s).add(id); try { localStorage.setItem(HIDDEN, JSON.stringify([...n].slice(-200))); } catch { /* spazio pieno */ } return n; });
  return { hidden: h, hide };
}
/** Notifiche che chiedono attenzione immediata (lezione annullata, spostata, recupero…). */
export const URGENT_KINDS = ["lesson.cancelled", "lesson.rescheduled", "lesson.makeup_scheduled", "recovery.created", "change_request.awaiting_tutor", "change_request.decided"];
