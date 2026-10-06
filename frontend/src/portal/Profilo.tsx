/**
 * Disponibilità ed eccezioni per soggetto (GAP-G01/G02/G03): il genitore sceglie il figlio,
 * tutor e studente vedono solo sé stessi. Settimana tipo (impegni e fasce) sul calendario,
 * disponibilità effettiva della settimana ed eccezioni/assenze a cursore («Mostra altre»).
 */
import { useEffect, useState } from "react";
import { get, nextPath, request } from "../api/client";
import type { S } from "../api/schema.gen";
import { addDays, dayShort, mondayOf, rangeOf, rome, todayRome } from "../format";
import { LOCATION, MODE } from "../messages";
import { Avatar, Btn, Icon, PageHead, Tag } from "../ui/core";
import { Check, SegCtl } from "../ui/controls";
import { Help } from "../ui/help";
import { go, setQuery, useRoute } from "../ui/route";
import { ErrorState, ViewState } from "../ui/states";
import { Rule, useData } from "../app/data";
import { api } from "../api";
import { PlanBlock, Slot, toMin, WeekPlanner } from "../ui/WeekPlanner";
import { Commitment, labelOf } from "../screens/Impegni";
import { EXC_LABEL, useLoad, useOverview } from "./data";

type Subject = { kind: "student" | "tutor"; id: string; name: string; canManage: boolean; readOnly: boolean; child?: S.PortalChild };

export default function Profilo() {
  const d = useData(), r = useRoute(), ov = useOverview();
  const o = ov.data;
  const subjects: Subject[] = o ? [
    ...(o.tutor ? [{ kind: "tutor" as const, id: o.tutor.tutor_id, name: o.tutor.display_name, canManage: true, readOnly: false }] : []),
    ...o.children.map((c) => ({ kind: "student" as const, id: c.student_id, name: c.display_name, canManage: c.permissions.can_manage_availability, readOnly: c.read_only, child: c })),
  ] : [];
  const want = r.q.get("s");
  const cur = subjects.find((s) => s.id === want) || (want ? null : subjects[0]);
  const guardian = d.me.roles.includes("GUARDIAN");
  const title = guardian ? "Figli" : "Disponibilità e assenze";
  return <section className="module planner" aria-labelledby="h-prof">
    <PageHead id="h-prof" title={title} lead={guardian ? "Disponibilità, eccezioni e permessi per ogni studente collegato a te." : "Le tue fasce settimanali, la disponibilità effettiva e le eccezioni registrate dal centro."} />
    <div className="page-help"><Help topic={cur?.kind === "tutor" ? "tutor" : "figlio"} /></div>
    {ov.error ? <ErrorState error={ov.error} onRetry={ov.reload} />
      : !o ? <ViewState kind="loading" />
      : !subjects.length ? <ViewState kind="revoked" title="Nessuno studente visibile">Non ci sono deleghe attive. Se il centro ha revocato una delega, i dati non sono più visibili.</ViewState>
      : !cur ? <ViewState kind="revoked" onAction={() => setQuery((q) => q.delete("s"))} actionLabel="Mostra i dati disponibili">Questo studente non è più collegato al tuo account oppure la delega è stata revocata.</ViewState>
      : <>
        {subjects.length > 1 && <div className="toolbar seg-scroll" style={{ marginBottom: 14 }}>
          <SegCtl label="Persona" value={cur.id} options={subjects.map((s) => [s.id, s.kind === "tutor" ? `${s.name} (tutor)` : s.name])} onChange={(v) => setQuery((q) => q.set("s", v))} />
        </div>}
        <SubjectView key={cur.id} s={cur} />
      </>}
  </section>;
}

function SubjectView({ s }: { s: Subject }) {
  const d = useData();
  const rules = d.rules.filter((x) => (s.kind === "student" ? x.student === s.id : x.tutor === s.id)).sort((a, b) => a.weekday - b.weekday || a.start_time.localeCompare(b.start_time));
  const p = s.child?.permissions;
  return <>
    <div className="kid-head" style={{ marginBottom: 14 }}><Avatar name={s.name} k={s.id} size={44} />
      <div><b>{s.name}</b><small>{s.kind === "tutor" ? "Tutor" : s.child?.relation === "SELF" ? "Il tuo profilo di studente" : "Studente collegato"}</small></div>
      {s.readOnly ? <Tag tone="plain">Sola lettura</Tag> : s.canManage ? <Tag tone="green">Puoi proporre disponibilità</Tag> : null}
    </div>
    {p && s.child?.relation === "GUARDIAN" && <ul className="list-rows" aria-label="Permessi della delega" style={{ marginBottom: 18, listStyle: "none", padding: 0 }}>
      <Perm on={p.can_manage_availability} label="Proporre disponibilità" />
      <Perm on={p.can_request_changes} label="Chiedere cambi e segnalare assenze" />
      <Perm on={p.can_receive_notifications} label="Ricevere le notifiche" />
    </ul>}
    <TypicalWeek s={s} rules={rules} />
    <Effective s={s} />
    <Exceptions s={s} />
  </>;
}
/** Settimana tipo in sola lettura: impegni e fasce dichiarate sopra gli orari di apertura. */
function TypicalWeek({ s, rules }: { s: Subject; rules: Rule[] }) {
  const [hours, setHours] = useState<Slot[]>([]), [items, setItems] = useState<Commitment[] | null>(null), [err, setErr] = useState<unknown>(null), [n, setN] = useState(0);
  useEffect(() => { api<{ opening_hours: { weekday: number; start: string; end: string }[] }>("/planner/opening-hours").then((x) => setHours(x.opening_hours.map((h) => ({ weekday: h.weekday, start: toMin(h.start), end: toMin(h.end) })))).catch(() => undefined); }, []);
  useEffect(() => { setErr(null); api<Commitment[]>(`/commitments?${s.kind}=${s.id}`).then(setItems).catch(setErr); }, [s.kind, s.id, n]);
  const today = todayRome();
  const blocks: PlanBlock[] = [
    ...(items || []).filter((c) => c.kind === "WEEKLY" && c.weekday != null && (!c.valid_until || c.valid_until >= today)).map((c): PlanBlock => ({ id: "c" + c.id, weekday: c.weekday!, start: toMin(c.start_time), end: toMin(c.end_time), label: labelOf(c), tone: "violet", locked: true })),
    ...rules.filter((x) => x.status !== "REVOKED").map((x): PlanBlock => ({ id: "r" + x.id, weekday: x.weekday, start: toMin(x.start_time), end: toMin(x.end_time), label: x.status === "DRAFT" ? "Fascia in bozza" : "Disponibile", sub: MODE[x.mode || ""], tone: x.status === "DRAFT" ? "amber" : "green", draft: x.status === "DRAFT", locked: true })),
  ];
  return <div className="card" aria-labelledby="h-week">
    <div className="oc-head"><span className="oc-ic violet"><Icon n="cal" /></span><div><h2 id="h-week">Settimana tipo</h2><p className="muted">Gli impegni che si ripetono ogni settimana: fuori da questi, quando il centro è aperto, si può fare lezione.</p></div>
      {s.canManage && !s.readOnly && <Btn kind="sm" isle="right" onClick={() => go("impegni", { chi: `${s.kind}:${s.id}` })}>Modifica impegni</Btn>}</div>
    {err ? <ErrorState error={err} onRetry={() => setN((k) => k + 1)} /> : !items ? <ViewState kind="loading" compact /> : <>
      <WeekPlanner label={`Settimana tipo di ${s.name}`} blocks={blocks} bands={hours} emptyText="Nessun impegno settimanale: libero quando il centro è aperto." />
      <div className="imp-legend"><span><i className="lg" />Centro aperto</span><span><i className="lg hatch" />Centro chiuso</span><span><i className="lg block" />Impegno</span>{rules.length > 0 && <span><i className="lg green" />Fascia dichiarata</span>}</div>
    </>}
  </div>;
}

const Perm = ({ on, label }: { on: boolean; label: string }) => <li className="list-row"><div><b>{label}</b></div><Tag tone={on ? "green" : "plain"}>{on ? "Sì" : "No"}</Tag></li>;

function Effective({ s }: { s: Subject }) {
  const r = useRoute(), today = todayRome(), week = mondayOf(r.q.get("w") || today);
  const eff = useLoad((signal) => get("/availability/effective", { query: { [s.kind]: s.id, from: week, until: addDays(week, 7) } as never, signal }), [s.kind, s.id, week]);
  const e = eff.data;
  const days = Array.from({ length: 7 }, (_, i) => addDays(week, i));
  const eb: PlanBlock[] = (e?.windows || []).filter((x) => x.start_at && x.end_at).flatMap((x, i): PlanBlock[] => {
    const a = rome(x.start_at!), b = rome(x.end_at!), wd = days.indexOf(a.date);
    if (wd < 0) return [];
    const end = b.date === a.date ? b.min : 1440;
    return [{ id: String(i), weekday: wd, start: a.min, end, label: MODE[x.mode || ""] || "Disponibile", sub: x.location ? (LOCATION[x.location] || x.location) : undefined, tone: "green", locked: true }];
  });
  return <div className="card" style={{ marginTop: 18 }} aria-labelledby="h-eff">
    <div className="m-head"><h2 className="m-title" id="h-eff">Disponibilità effettiva</h2>
      <div className="datenav">
        <button className="circle" aria-label="Settimana precedente" onClick={() => setQuery((q) => q.set("w", addDays(week, -7)))}><Icon n="left" /></button>
        <span className="datebtn num" aria-live="polite">{`Dal ${Number(week.slice(8))}/${Number(week.slice(5, 7))}`}</span>
        <button className="circle" aria-label="Settimana successiva" onClick={() => setQuery((q) => q.set("w", addDays(week, 7)))}><Icon n="right" /></button>
      </div></div>
    {eff.error ? <ErrorState error={eff.error} onRetry={eff.reload} />
      : !e ? <ViewState kind="loading" compact />
      : <>
        {!e.ready && <ViewState kind="partial" title="Disponibilità incompleta">{(e.problems || []).map((p) => p.message).filter(Boolean).join(" ") || "Alcune fasce sono ancora in bozza o mancano: il centro non le considera finché non sono approvate."}</ViewState>}
        <WeekPlanner label="Disponibilità effettiva della settimana" blocks={eb} emptyText="Nessuna fascia disponibile in questa settimana." />
      </>}
  </div>;
}

function Exceptions({ s }: { s: Subject }) {
  const [past, setPast] = useState(false), [n, setN] = useState(0);
  const [rows, setRows] = useState<S.PortalException[]>([]), [next, setNext] = useState<string | null>(null), [err, setErr] = useState<unknown>(null), [busy, setBusy] = useState(true);
  const first = () => get("/portal/availability-exceptions", { query: { [s.kind]: s.id, past: past ? "1" : "0", page_size: 20 } as never });
  useEffect(() => {
    let live = true; setBusy(true); setErr(null); setRows([]); setNext(null);
    first().then((p) => { if (live) { setRows(p.results); setNext(nextPath(p.next, location.origin)); } }).catch((x) => live && setErr(x)).finally(() => live && setBusy(false));
    return () => { live = false; };
  }, [s.id, past, n]); // eslint-disable-line react-hooks/exhaustive-deps
  async function more() {
    if (!next) return;
    setBusy(true);
    try { const p = await request<S.PortalExceptionPage>("GET", next); setRows((x) => [...x, ...p.results]); setNext(nextPath(p.next, location.origin)); }
    catch (x) { setErr(x); } finally { setBusy(false); }
  }
  return <div style={{ marginTop: 22 }} aria-labelledby="h-exc">
    <div className="m-head"><h2 className="m-title" id="h-exc">{s.kind === "tutor" ? "Assenze ed eccezioni" : "Eccezioni"}</h2><Check checked={past} onChange={setPast}>Mostra anche le passate</Check></div>
    {err ? <ErrorState error={err} onRetry={() => setN((k) => k + 1)} />
      : busy && !rows.length ? <ViewState kind="loading" compact />
      : rows.length ? <>
        <div className="list-rows" aria-live="polite">{rows.map((x) => <div className="list-row" key={x.id}>
          <div><b>{dayShort(rome(x.start_at).date)} {rangeOf(x.start_at, x.end_at)}</b><small>{MODE[x.mode]}{x.location ? `, ${(LOCATION[x.location] || x.location).toLowerCase()}` : ""}</small></div>
          <Tag tone={x.kind === "REMOVE_AVAILABLE" ? "amber" : "green"}>{EXC_LABEL[x.kind]}</Tag></div>)}</div>
        {next && <div style={{ marginTop: 12 }}><Btn kind="sm" disabled={busy} onClick={more}>{busy ? "Carico…" : "Mostra altre"}</Btn></div>}
      </>
      : <ViewState kind="empty" title={past ? "Nessuna eccezione registrata" : "Nessuna eccezione in arrivo"}>{s.kind === "tutor" ? "Per un’assenza su una lezione già pubblicata usa «Segnala assenza» dalla tua settimana; per periodi lunghi contatta il centro." : "Le eccezioni (giorni in più o in meno) le registra il centro su richiesta."}</ViewState>}
  </div>;
}
