import { useEffect, useMemo, useRef, useState } from "react";
import { addDays, dayLabel, hm, plural, rangeOf, rome, todayRome } from "../format";
import { Avatar, Btn, Empty, Icon, Skeleton, Tag } from "../ui/core";
import { go } from "../ui/route";
import { useData } from "../app/data";
import { Cap, Lesson, loadLessons } from "../app/calendarApi";
import { api } from "../api";
import { MODE } from "../messages";
import { Alert, Alerts, fromCenter, LessonAccordion, useJoin, useNow } from "../portal/widgets";

/**
 * Panoramica del centro, pensata per l'uso quotidiano: solo ciò che serve oggi.
 * Avvisi (solo se c'è qualcosa da fare), la giornata di tutti i tutor, le proprie lezioni se il gestore insegna.
 * Le statistiche del centro sono nella pagina «Statistiche».
 */
export const greet = () => { const h = new Date().getHours(); return h < 13 ? "Buongiorno" : h < 18 ? "Buon pomeriggio" : "Buonasera"; };
export type Queues = { requests: number | null; recoveries: number | null; conflicts: number | null; deliveries: number | null };
const count = (path: string) => api<{ results: unknown[] }>(path).then((r) => r.results.length).catch(() => null);
const NONE: Queues = { requests: null, recoveries: null, conflicts: null, deliveries: null };
/** Capacità del calendario e code operative del centro. */
export function useQueues() {
  const [cap, setCap] = useState<Cap | null>(null), [q, setQ] = useState<Queues | null>(null);
  useEffect(() => {
    let live = true;
    api<Cap>("/calendar/capabilities").then(async (c) => {
      if (!live) return; setCap(c);
      if (!c.enabled) { setQ(NONE); return; }
      const [requests, recoveries, conflicts, deliveries] = await Promise.all([
        count("/change-requests/?state=SUBMITTED"), count("/recovery-obligations/?state=OPEN"), count("/conflict-cases/?state=OPEN"),
        api<{ dead_letter: number; ambiguous: number }>("/communications/status").then((s) => s.dead_letter + s.ambiguous).catch(() => null),
      ]);
      if (live) setQ({ requests, recoveries, conflicts, deliveries });
    }).catch(() => { if (live) { setCap({ enabled: false, reason_code: "", database: "", production_enabled: false }); setQ(NONE); } });
    return () => { live = false; };
  }, []);
  return { cap, q };
}

export default function Panoramica() {
  const d = useData(), { cap, q } = useQueues(), today = todayRome();
  const drafts = d.rules.filter((r) => r.status === "DRAFT").length;
  const newReqs = d.requests.filter((x) => x.status === "PENDING").length;
  const blockers = d.readiness && !d.readiness.ready ? new Set((d.readiness.blockers || []).map((b) => b.reason)).size : 0;
  const n = (x: number | null | undefined) => x || 0;
  const alerts: Alert[] = [
    ...(n(q?.conflicts) ? [{ id: "conf", tone: "red", icon: "cal", title: plural(n(q?.conflicts), "conflitto su lezioni pubblicate", "conflitti su lezioni pubblicate"), text: "Da risolvere prima che le lezioni si svolgano.", action: ["Risolvi", () => go("operativita", { tab: "conflitti" })] } as Alert] : []),
    ...(n(q?.requests) ? [{ id: "req", tone: "amber", icon: "send", title: plural(n(q?.requests), "richiesta di cambio", "richieste di cambio"), text: "Inviate da famiglie e tutor, in attesa di una decisione.", action: ["Decidi", () => go("operativita", { tab: "richieste" })] } as Alert] : []),
    ...(n(q?.recoveries) ? [{ id: "rec", tone: "amber", icon: "clock", title: plural(n(q?.recoveries), "recupero da fissare", "recuperi da fissare"), text: "Lezioni perse da riprogrammare.", action: ["Fissa", () => go("operativita", { tab: "recuperi" })] } as Alert] : []),
    ...(newReqs ? [{ id: "lez", tone: "amber", icon: "book", title: plural(newReqs, "richiesta di lezioni da approvare", "richieste di lezioni da approvare"), text: "Inviate dalle famiglie: il motore le considera solo dopo l’approvazione.", action: ["Valuta", () => go("pianificazione")] } as Alert] : []),
    ...(drafts ? [{ id: "disp", tone: "blue", icon: "check", title: plural(drafts, "disponibilità da approvare", "disponibilità da approvare"), text: "Inserite da tutor e famiglie.", action: ["Approva", () => go("disponibilita", { f: "DRAFT" })] } as Alert] : []),
    ...(n(q?.deliveries) ? [{ id: "inv", tone: "blue", icon: "bell", title: plural(n(q?.deliveries), "invio da controllare", "invii da controllare"), text: "Email non consegnate o con esito incerto.", action: ["Controlla", () => go("operativita", { tab: "invii" })] } as Alert] : []),
    ...(blockers ? [{ id: "plan", tone: "blue", icon: "gear", title: "Pianificazione da completare", text: plural(blockers, "requisito mancante per generare l’orario", "requisiti mancanti per generare l’orario"), action: ["Completa", () => go("pianificazione")] } as Alert] : []),
  ];
  const ready = q !== null && d.loaded;
  return <>
    <section className="module planner hero" aria-labelledby="h-home">
      <div className="m-head"><div className="titlebox"><h1 className="h-display" id="h-home">{greet()}, {d.me.name.split(/\s+/)[0]}</h1>
        <p className="sub-line">{dayLabel(today)}{ready ? (alerts.length ? ` · ${plural(alerts.length, "cosa da gestire", "cose da gestire")}` : " · Nulla da gestire") : ""}</p></div>
        <div className="controls">{d.me.own_tutor_id && d.switchContext && <button className="pill-btn sm" onClick={d.switchContext}>Vista tutor</button>}
          <a className="pill-btn sm island" href="#/agenda">Agenda<span className="isle"><Icon n="arrow" /></span></a></div></div>
    </section>
    <Alerts items={alerts} />
    <TutorsDay cap={cap} />
    {d.me.own_tutor_id && <MyDay cap={cap} tutor={d.me.own_tutor_id} />}
  </>;
}

/** Giornata di tutti i tutor: una riga per tutor, le lezioni sulla linea del tempo. La gestione completa è nell’Agenda. */
function TutorsDay({ cap }: { cap: Cap | null }) {
  const d = useData(), today = todayRome(), now = useNow();
  const [day, setDay] = useState(today), [rows, setRows] = useState<Lesson[] | null>(null), [all, setAll] = useState(false);
  useEffect(() => {
    if (!cap?.enabled) return;
    let live = true; setRows(null);
    loadLessons(day, addDays(day, 1)).then((r) => live && setRows(r.lessons.filter((l) => rome(l.start_at).date === day))).catch(() => live && setRows([]));
    return () => { live = false; };
  }, [day, cap?.enabled]);
  const me = d.me.own_tutor_id;
  const tutors = useMemo(() => {
    const m = new Map<string, string>(); d.tutors.forEach((t) => m.set(t.id, t.display_name)); (rows || []).forEach((l) => m.set(l.tutor, l.tutor_name));
    const busy = new Set((rows || []).map((l) => l.tutor));
    return [...m].map(([id, name]) => ({ id, name, busy: busy.has(id) }))
      .sort((a, b) => Number(b.id === me) - Number(a.id === me) || Number(b.busy) - Number(a.busy) || a.name.localeCompare(b.name, "it"));
  }, [d.tutors, rows, me]);
  const shown = all ? tutors : tutors.filter((t) => t.busy || t.id === me);
  const live = (rows || []).filter((l) => l.state === "PUBLISHED");
  const mins = (rows || []).flatMap((l) => [rome(l.start_at).min, rome(l.end_at).min]);
  const open = Math.min(9 * 60, ...(mins.length ? [Math.floor(Math.min(...mins) / 60) * 60] : [])), close = Math.max(20 * 60, ...(mins.length ? [Math.ceil(Math.max(...mins) / 60) * 60] : []));
  const span = close - open, pos = (m: number) => ((m - open) / span) * 100;
  const hours = Array.from({ length: span / 60 + 1 }, (_, i) => open + i * 60);
  const nowMin = rome(new Date(now)).min, showNow = day === today && nowMin >= open && nowMin <= close;
  const box = useRef<HTMLDivElement>(null);
  // Su schermi stretti la linea del tempo scorre: si apre già sull'ora attuale.
  useEffect(() => { const el = box.current; if (!el || rows === null || el.scrollWidth <= el.clientWidth) return; const line = el.querySelector<HTMLElement>(".tday-line"); if (!line) return;
    const target = day === today ? nowMin : Math.min(...(rows.length ? rows.map((l) => rome(l.start_at).min) : [open]));
    el.scrollLeft = Math.max(0, line.offsetLeft + (pos(target) / 100) * line.clientWidth - 60); }, [rows, day]); // eslint-disable-line react-hooks/exhaustive-deps
  const sub = !cap ? "Carico il calendario…" : !cap.enabled ? "Calendario non attivo." : rows === null ? "Carico le lezioni…"
    : live.length ? `${plural(live.length, "lezione", "lezioni")} con ${plural(new Set(live.map((l) => l.tutor)).size, "tutor", "tutor")}` : "Nessuna lezione in programma";
  return <section className="module" aria-labelledby="h-tday">
    <div className="m-head"><div><h2 className="m-title" id="h-tday">{day === today ? "Oggi" : dayLabel(day)} in calendario</h2><p className="sub-line">{sub}</p></div>
      <div className="controls">
        <div className="datenav">
          <button className="circle" aria-label="Giorno precedente" onClick={() => setDay(addDays(day, -1))}><Icon n="left" /></button>
          <span className="datebtn" aria-live="polite">{day === today ? "Oggi" : day.split("-").reverse().slice(0, 2).join("/")}</span>
          <button className="circle" aria-label="Giorno successivo" onClick={() => setDay(addDays(day, 1))}><Icon n="right" /></button>
        </div>
        {day !== today && <button className="pill-btn sm" onClick={() => setDay(today)}>Oggi</button>}
        <button className="pill-btn sm island" onClick={() => go("agenda", day === today ? {} : { d: day })}>Gestisci nell’agenda<span className="isle"><Icon n="arrow" /></span></button>
      </div></div>
    {cap && !cap.enabled ? <Empty title="Calendario non disponibile" />
      : rows === null ? <Skeleton rows={3} />
      : !tutors.length ? <Empty title="Nessun tutor" />
      : <div className="tday-scroll" ref={box}><div className="tday" role="table" aria-label={`Lezioni dei tutor, ${dayLabel(day)}`}>
        <div className="tday-row tday-hours" role="row" aria-hidden="true"><span className="tday-name" /><div className="tday-line">{hours.map((h) => <span key={h} style={{ left: pos(h) + "%" }}>{hm(h)}</span>)}</div></div>
        {shown.map((t) => { const ls = (rows || []).filter((l) => l.tutor === t.id); return <div className="tday-row" role="row" key={t.id}>
          <span className="tday-name" role="rowheader"><Avatar name={t.name} k={t.id} size={28} /><b>{t.name}</b>{t.id === me && <Tag tone="amber">Tu</Tag>}</span>
          <div className="tday-line" role="cell" style={{ backgroundSize: `${(60 / span) * 100}% 100%`, backgroundPosition: `${pos(open)}% 0` }}>
            {showNow && <i className="tday-now" style={{ left: pos(nowMin) + "%" }} aria-hidden="true" />}
            {ls.length ? ls.map((l) => { const s = rome(l.start_at).min, e = rome(l.end_at).min, off = l.state === "CANCELLED";
              return <button key={l.id} className={"tday-ev" + (off ? " off" : "") + (l.mode === "ONLINE" ? " online" : "") + (new Date(l.end_at).getTime() < now ? " past" : "")} style={{ left: pos(s) + "%", width: Math.max(2, pos(e) - pos(s)) + "%" }}
                onClick={() => go("agenda", { d: day, l: l.id })} title={`${l.subject_name} · ${rangeOf(l.start_at, l.end_at)} · ${l.participants.map((p) => p.name).join(", ")}${off ? " · annullata" : ""}`}
                aria-label={`${l.subject_name}, ${rangeOf(l.start_at, l.end_at)}, ${l.participants.map((p) => p.name).join(", ")}, ${MODE[l.mode] || l.mode}${off ? ", annullata" : ""}`}>
                <b>{l.subject_name}</b><small>{rangeOf(l.start_at, l.end_at)} · {l.participants.map((p) => p.name.split(/\s+/)[0]).join(", ")}</small></button>; })
              : <span className="tday-free">Libero</span>}
          </div></div>; })}
      </div></div>}
    {rows !== null && tutors.length > shown.length && <button className="link-btn" style={{ marginTop: 12 }} onClick={() => setAll(true)}>Mostra anche i tutor liberi ({tutors.length - shown.length})</button>}
    {all && tutors.some((t) => !t.busy) && <button className="link-btn" style={{ marginTop: 12 }} onClick={() => setAll(false)}>Mostra solo i tutor con lezioni</button>}
  </section>;
}

/** Il gestore che insegna: le sue lezioni di oggi con tutti i dettagli e il link per quelle online. */
function MyDay({ cap, tutor }: { cap: Cap | null; tutor: string }) {
  const d = useData(), today = todayRome(), join = useJoin();
  const [rows, setRows] = useState<Lesson[] | null>(null);
  useEffect(() => {
    if (!cap?.enabled) return;
    let live = true;
    loadLessons(today, addDays(today, 1)).then((r) => live && setRows(r.lessons.filter((l) => l.tutor === tutor && rome(l.start_at).date === today))).catch(() => live && setRows([]));
    return () => { live = false; };
  }, [cap?.enabled, tutor, today]);
  const places = useMemo(() => new Map(d.resources.map((r) => [r.id, r.name])), [d.resources]);
  return <section className="module" aria-labelledby="h-myday">
    <div className="m-head"><div><h2 className="m-title" id="h-myday">Le tue lezioni di oggi</h2><p className="sub-line">Come tutor</p></div></div>
    {cap && !cap.enabled ? <Empty title="Calendario non disponibile" /> : rows === null ? <Skeleton rows={2} />
      : rows.length ? <LessonAccordion rows={rows.map((l) => fromCenter(l, places, true))} join={join} extra={(l) => <Btn kind="sm ghost" onClick={() => go("agenda", { l: l.id })}>Apri nell’agenda</Btn>} />
      : <Empty title="Oggi non insegni" />}
  </section>;
}
