import { useEffect, useState } from "react";
import { addMonths, duration, monthYear, plural, todayRome } from "../format";
import { Empty, Icon, PageHead, Skeleton, Stat, Tag } from "../ui/core";
import { go } from "../ui/route";
import { useData } from "../app/data";
import { Lesson, loadLessons } from "../app/calendarApi";
import { useQueues } from "./Panoramica";

const mins = (l: Lesson) => Math.round((new Date(l.end_at).getTime() - new Date(l.start_at).getTime()) / 60000);
const shown = (n: number | null) => (n === null ? "—" : n >= 200 ? "200+" : String(n));

/** Statistiche del centro: numeri d'insieme e andamento del mese, fuori dalla panoramica quotidiana. */
export default function Statistiche() {
  const d = useData(), { cap, q } = useQueues(), cur = todayRome().slice(0, 7);
  const [ym, setYm] = useState(cur), [rows, setRows] = useState<Lesson[] | null>(null);
  useEffect(() => {
    if (!cap?.enabled) return;
    let live = true; setRows(null);
    loadLessons(ym + "-01", addMonths(ym, 1) + "-01").then((r) => live && setRows(r.lessons)).catch(() => live && setRows([]));
    return () => { live = false; };
  }, [ym, cap?.enabled]);
  const pub = (rows || []).filter((l) => l.state === "PUBLISHED"), off = (rows || []).filter((l) => l.state === "CANCELLED");
  const done = pub.filter((l) => new Date(l.end_at).getTime() <= Date.now());
  const sum = (xs: Lesson[]) => xs.reduce((a, l) => a + mins(l), 0);
  const byTutor = [...pub.reduce((m, l) => m.set(l.tutor_name, (m.get(l.tutor_name) || 0) + mins(l)), new Map<string, number>())].sort((a, b) => b[1] - a[1]);
  const max = byTutor[0]?.[1] || 1;
  const drafts = d.rules.filter((r) => r.status === "DRAFT").length, approved = d.rules.filter((r) => r.status === "APPROVED").length;
  const queue = [
    { k: "richieste", label: "Richieste di cambio", n: q?.requests ?? null, run: () => go("operativita", { tab: "richieste" }) },
    { k: "recuperi", label: "Recuperi da fissare", n: q?.recoveries ?? null, run: () => go("operativita", { tab: "recuperi" }) },
    { k: "conflitti", label: "Conflitti aperti", n: q?.conflicts ?? null, run: () => go("operativita", { tab: "conflitti" }) },
    { k: "invii", label: "Invii da controllare", n: q?.deliveries ?? null, run: () => go("operativita", { tab: "invii" }) },
  ];
  return <>
    <PageHead id="h-stats" title="Statistiche" lead="I numeri del centro e l’andamento del mese." />
    <section className="module" aria-labelledby="h-st-month">
      <div className="m-head"><h2 className="m-title" id="h-st-month">Lezioni del mese</h2>
        <div className="datenav">
          <button className="circle" aria-label="Mese precedente" onClick={() => setYm(addMonths(ym, -1))}><Icon n="left" /></button>
          <span className="datebtn" aria-live="polite">{monthYear(ym)}</span>
          <button className="circle" aria-label="Mese successivo" onClick={() => setYm(addMonths(ym, 1))}><Icon n="right" /></button>
        </div></div>
      {cap && !cap.enabled ? <Empty title="Calendario non disponibile" /> : rows === null ? <Skeleton rows={3} /> : <>
        <div className="stats four">
          <Stat label="Lezioni in programma" value={pub.length} note={duration(sum(pub))} />
          <Stat label="Svolte" value={done.length} note={duration(sum(done))} />
          <Stat label="Annullate" value={off.length} note={off.length ? duration(sum(off)) : "Nessuna"} />
          <Stat label="Tutor impegnati" value={byTutor.length} note={`su ${d.tutors.length}`} />
        </div>
        {byTutor.length > 0 && <div className="tbars" role="list" aria-label="Ore per tutor">{byTutor.map(([name, m]) => <div className="tbar" role="listitem" key={name}>
          <span>{name}</span><span className="track"><span className="fill" style={{ width: (m / max) * 100 + "%" }} /></span><em>{duration(m)}</em></div>)}</div>}
      </>}
    </section>
    <div className="two">
      <section className="module" aria-labelledby="h-st-center">
        <div className="m-head"><h2 className="m-title" id="h-st-center">Il centro</h2></div>
        {!d.loaded ? <Skeleton rows={2} /> : <div className="stats two-col">
          <Stat label="Studenti" value={d.students.length} note={plural(d.requests.length, "richiesta didattica", "richieste didattiche")} />
          <Stat label="Tutor" value={d.tutors.length} />
          <Stat label="Disponibilità approvate" value={approved} note={drafts ? `${drafts} in bozza` : "Nessuna in bozza"} />
          <Stat label="Aule e canali" value={d.resources.length} note={d.resources.slice(0, 3).map((r) => r.name).join(", ") || "Nessuno configurato"} />
        </div>}
      </section>
      <section className="module" aria-labelledby="h-st-queue">
        <div className="m-head"><h2 className="m-title" id="h-st-queue">Code operative</h2>{d.readiness && <Tag tone={d.readiness.ready ? "green" : "amber"}>{d.readiness.ready ? "Pianificazione pronta" : "Pianificazione da completare"}</Tag>}</div>
        {q === null ? <Skeleton rows={3} /> : <div className="todo">{queue.map((t) => <button key={t.k} className="todo-it" onClick={t.run}><div><b>{t.label}</b></div><Tag tone={t.n ? "amber" : "plain"}>{shown(t.n)}</Tag><Icon n="right" /></button>)}</div>}
      </section>
    </div>
  </>;
}
