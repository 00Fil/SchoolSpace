import { useEffect, useState } from "react";
import { addDays, dayLabel, plural, rangeOf, rome, todayRome, mondayOf } from "../format";
import { Empty, Icon, Notice, Skeleton, Stack, Tag } from "../ui/core";
import { setQuery, useRoute } from "../ui/route";
import { useData } from "../app/data";
import { loadMine, MyLesson } from "../app/myApi";
import { human, LOCATION, MODE } from "../messages";
import { DayStrip } from "./Agenda";
import { Btn } from "../ui/core";
import { useToast } from "../ui/layers";
import { requestersFor, useOverview } from "../portal/data";
import { ChangeRequestModal, CrTarget } from "../portal/Cambi";
import { AttendanceModal } from "../portal/Presenze";
import type { S } from "../api/schema.gen";
import { ViewState } from "../ui/states";
import { Help } from "../ui/help";

export const who = (l: MyLesson) => {
  const names = l.participants.map((p) => p.name);
  const others = l.other_participants ? (names.length ? ` e ${plural(l.other_participants, "altro studente", "altri studenti")}` : plural(l.other_participants, "studente", "studenti")) : "";
  return names.join(", ") + others;
};
export function LessonCard({ l, hl, actions }: { l: MyLesson; hl?: boolean; actions?: React.ReactNode }) {
  const off = l.state === "CANCELLED";
  return <article className={"event" + (hl ? " hl" : "") + (off ? " off" : "")} aria-label={`${l.subject_name}, ${rangeOf(l.start_at, l.end_at)}${off ? ", cancellata" : ""}`}>
    <div className="e-top"><div><b>{l.subject_name}</b><p>{l.as_tutor ? `Con ${who(l) || "nessuno studente"}` : `Con ${l.tutor_name}${l.participants.length + l.other_participants > 1 ? " · lezione di gruppo" : ""}`}</p></div>
      {off ? <Tag tone="plain">Cancellata</Tag> : <Tag tone={hl ? "plain" : "blue"}>{MODE[l.mode] || l.mode}</Tag>}</div>
    <div className="e-bot"><span className="chip"><Icon n="clock" />{rangeOf(l.start_at, l.end_at)}</span><span className="chip"><Icon n="home" />{l.space_name || LOCATION[l.location] || l.location}</span>{l.participants.length > 0 && <Stack names={l.participants.map((p) => p.name)} />}</div>
    {actions && <div className="kid-actions" style={{ marginTop: 10 }}>{actions}</div>}
  </article>;
}

export default function Settimana() {
  const d = useData(), r = useRoute(), today = todayRome(), toast = useToast();
  const ov = useOverview(undefined, !d.center);
  const [cr, setCr] = useState<CrTarget | null>(null), [att, setAtt] = useState<S.PortalAttendanceItem | null>(null);
  const actionsFor = (l: MyLesson) => {
    const who = requestersFor(l, ov.data);
    const can = who.asTutor || who.students.length > 0;
    const ended = l.state === "PUBLISHED" && new Date(l.end_at) <= new Date() && l.as_tutor;
    if (!can && !ended) return undefined;
    return <>
      {can && <Btn kind="sm" onClick={() => setCr({ lesson: l, ...who, kind: "ABSENCE" })}>Segnala assenza</Btn>}
      {can && <Btn kind="sm ghost" onClick={() => setCr({ lesson: l, ...who, kind: "RESCHEDULE" })}>Chiedi un cambio</Btn>}
      {ended && <Btn kind="sm" isle="check" onClick={() => setAtt({ lesson_id: l.id, version: 0, start_at: l.start_at, end_at: l.end_at, subject_name: l.subject_name, participants: l.participants })}>Presenze</Btn>}
    </>;
  };
  const day = r.q.get("d") || today, week = mondayOf(day);
  const [rows, setRows] = useState<{ week: string; list: MyLesson[] } | null>(null), [err, setErr] = useState("");
  useEffect(() => {
    let live = true; setErr("");
    loadMine(week, addDays(week, 7)).then((list) => live && setRows({ week, list })).catch((e) => live && setErr(human(e).text));
    return () => { live = false; };
  }, [week]);
  const list = rows && rows.week === week ? rows.list : null;
  const of = (x: string) => (list || []).filter((l) => rome(l.start_at).date === x);
  const dayRows = of(day), active = dayRows.filter((l) => l.state !== "CANCELLED");
  const tutor = d.me.roles.includes("TUTOR"), setDay = (x: string) => setQuery((q) => q.set("d", x));
  const sub = list === null ? "Carico le lezioni…" : active.length ? `${plural(active.length, "lezione", "lezioni")} ${day === today ? "oggi" : "in questo giorno"}.` : "Nessuna lezione in questo giorno.";
  return <section className="module planner" aria-labelledby="h-week">
    <div className="m-head">
      <div className="titlebox"><h1 className="h-display" id="h-week">{day === today ? "La mia giornata" : dayLabel(day)}</h1><p className="sub-line">{sub}</p></div>
      <div className="controls"><div className="datenav">
        <button className="circle" aria-label="Settimana precedente" onClick={() => setDay(addDays(day, -7))}><Icon n="left" /></button>
        <span className="datebtn num" aria-live="polite">{`Settimana del ${Number(week.slice(8))}/${Number(week.slice(5, 7))}`}</span>
        <button className="circle" aria-label="Settimana successiva" onClick={() => setDay(addDays(day, 7))}><Icon n="right" /></button>
      </div>{day !== today && <button className="pill-btn sm" onClick={() => setDay(today)}>Oggi</button>}</div>
    </div>
    <div className="page-help"><Help topic={tutor ? "tutor" : "cambi"} /></div>
    <DayStrip week={week} day={day} today={today} counts={(x) => of(x).filter((l) => l.state !== "CANCELLED").length} onPick={setDay} />
    {err ? <Notice kind="bad" title="Non riesco a caricare le lezioni">{err}</Notice>
      : list === null ? <Skeleton rows={3} />
      : dayRows.length ? <div className="events">{list.length >= 300 && <ViewState kind="partial">Questa settimana ha più lezioni di quante se ne possano mostrare insieme: alcune potrebbero mancare.</ViewState>}{dayRows.map((l, i) => <LessonCard key={l.id} l={l} hl={i === 0 && l.state !== "CANCELLED"} actions={actionsFor(l)} />)}</div>
      : <Empty title="Nessuna lezione">{tutor ? "Quando il centro pubblica le lezioni assegnate a te, le trovi qui." : "Quando il centro pubblica le lezioni dei tuoi studenti, le trovi qui."}</Empty>}
    <p className="mv-hint" style={{ marginTop: 14 }}>Vedi solo le lezioni tue o degli studenti a cui sei collegato. Cambi e assenze sono richieste al centro: il calendario cambia solo se le accoglie. Se i pulsanti non compaiono, la delega è in sola lettura.</p>
    <ChangeRequestModal target={cr} onClose={() => setCr(null)} onDone={(m) => { toast(m); ov.reload(); }} />
    <AttendanceModal lesson={att} onClose={() => setAtt(null)} onDone={(m) => toast(m)} />
  </section>;
}
