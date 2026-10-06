/**
 * Presenze del tutor (GAP-G02): lezioni concluse negli ultimi 14 giorni senza presenze
 * complete (cursore), registrazione per partecipante con versione attesa della lezione.
 */
import { FormEvent, useEffect, useState } from "react";
import { get, newIdempotencyKey, nextPath, post, request } from "../api/client";
import type { S } from "../api/schema.gen";
import { dayShort, rangeOf, rome } from "../format";
import { Btn, Icon, PageHead } from "../ui/core";
import { Field, Input, SegCtl } from "../ui/controls";
import { Modal, useToast } from "../ui/layers";
import { Help } from "../ui/help";
import { classify, ErrorState, ViewState } from "../ui/states";
import { ATT_LABEL } from "./data";

export default function Presenze() {
  const toast = useToast();
  const [rows, setRows] = useState<S.PortalAttendanceItem[] | null>(null), [next, setNext] = useState<string | null>(null), [err, setErr] = useState<unknown>(null), [busy, setBusy] = useState(false), [n, setN] = useState(0);
  const [open, setOpen] = useState<S.PortalAttendanceItem | null>(null);
  useEffect(() => {
    let live = true; setErr(null); setRows(null);
    get("/portal/attendance-pending").then((p) => { if (live) { setRows(p.results); setNext(nextPath(p.next, location.origin)); } }).catch((x) => live && setErr(x));
    return () => { live = false; };
  }, [n]);
  async function more() {
    if (!next) return; setBusy(true);
    try { const p = await request<S.PortalAttendancePage>("GET", next); setRows((x) => [...(x || []), ...p.results]); setNext(nextPath(p.next, location.origin)); } catch (x) { setErr(x); } finally { setBusy(false); }
  }
  return <section className="module planner" aria-labelledby="h-pres">
    <PageHead id="h-pres" title="Presenze" lead="Lezioni concluse negli ultimi 14 giorni in cui manca la presenza di almeno un partecipante." />
    <div className="page-help"><Help topic="tutor" /></div>
    {err ? (classify(err) === "disabled" ? <ViewState kind="disabled" title="Calendario non attivo">Le presenze si registrano sulle lezioni del calendario, che non è ancora attivo.</ViewState> : <ErrorState error={err} onRetry={() => setN((k) => k + 1)} />)
      : rows === null ? <ViewState kind="loading" />
      : rows.length ? <>
        <div className="list-rows">{rows.map((l) => <div className="list-row" key={l.lesson_id}>
          <div><b>{l.subject_name}</b><small>{dayShort(rome(l.start_at).date)} {rangeOf(l.start_at, l.end_at)} · {l.participants.map((p) => p.name).join(", ")}</small></div>
          <Btn kind="sm" isle="check" onClick={() => setOpen(l)}>Registra</Btn></div>)}</div>
        {next && <div style={{ marginTop: 12 }}><Btn kind="sm" disabled={busy} onClick={more}>{busy ? "Carico…" : "Mostra altre"}</Btn></div>}
      </>
      : <ViewState kind="empty" title="Tutto registrato">Non ci sono presenze da registrare per le lezioni recenti.</ViewState>}
    <AttendanceModal lesson={open} onClose={() => setOpen(null)} onDone={(m) => { toast(m); setN((k) => k + 1); }} />
  </section>;
}

type Entry = { student_id: string; status: S.AttendanceStatus; minutes: string };
export function AttendanceModal({ lesson, onClose, onDone }: { lesson: S.PortalAttendanceItem | null; onClose: () => void; onDone: (m: string) => void }) {
  const [sum, setSum] = useState<S.AttendanceSummary | null>(null), [entries, setEntries] = useState<Entry[]>([]), [err, setErr] = useState<unknown>(null), [loadErr, setLoadErr] = useState<unknown>(null), [busy, setBusy] = useState(false), [n, setN] = useState(0);
  const [last, setLast] = useState(lesson), [key, setKey] = useState("");
  useEffect(() => {
    if (!lesson) return;
    setLast(lesson); setSum(null); setErr(null); setLoadErr(null); setKey(newIdempotencyKey());
    get("/occurrences/{pk}/attendance/", { params: { pk: lesson.lesson_id } }).then((s) => {
      setSum(s);
      setEntries(s.entries.map((e) => ({ student_id: e.student_id, status: e.recorded ? e.status : "PRESENT", minutes: e.minutes != null ? String(e.minutes) : "" })));
    }).catch(setLoadErr);
  }, [lesson, n]);
  const l = lesson || last; if (!l) return null;
  const name = (id: string) => l.participants.find((p) => p.student_id === id)?.name || "Partecipante";
  const full = Math.round((new Date(l.end_at).getTime() - new Date(l.start_at).getTime()) / 60000);
  async function submit(e: FormEvent) {
    e.preventDefault(); if (!sum) return;
    setBusy(true); setErr(null);
    try {
      await post("/occurrences/{pk}/attendance/", { expected_version: sum.lesson_version, entries: entries.map((x) => ({ student_id: x.student_id, status: x.status, ...(x.status === "PRESENT" && x.minutes ? { minutes: Math.max(0, Math.min(full, Number(x.minutes))) } : {}) })) }, { params: { pk: l!.lesson_id }, idempotencyKey: key });
      onClose(); onDone(`Presenze registrate: ${l!.subject_name}.`);
    } catch (x) { setErr(x); } finally { setBusy(false); }
  }
  const upd = (i: number, p: Partial<Entry>) => { setKey(newIdempotencyKey()); setEntries((xs) => xs.map((x, k) => (k === i ? { ...x, ...p } : x))); };
  return <Modal open={!!lesson} onClose={onClose} labelledBy="att-title" width={620}><form onSubmit={submit} noValidate>
    <div className="modal-body">
      <h2 id="att-title">Registra le presenze</h2>
      <p className="lead">{l.subject_name}, {dayShort(rome(l.start_at).date)} {rangeOf(l.start_at, l.end_at)}.</p>
      {loadErr ? <ErrorState error={loadErr} onRetry={() => setN((k) => k + 1)} /> : !sum ? <ViewState kind="loading" compact /> : entries.map((x, i) => <div className="att-row" key={x.student_id} role="group" aria-label={name(x.student_id)}>
        <b>{name(x.student_id)}</b>
        <div className="seg-scroll"><SegCtl label={`Presenza di ${name(x.student_id)}`} value={x.status} options={(["PRESENT", "ABSENT", "JUSTIFIED"] as S.AttendanceStatus[]).map((s) => [s, ATT_LABEL[s]])} onChange={(s) => upd(i, { status: s })} /></div>
        <Field label="Minuti" id={"att-m-" + i} optional><Input id={"att-m-" + i} type="number" inputMode="numeric" min={0} max={full} placeholder={String(full)} disabled={x.status !== "PRESENT"} value={x.minutes} onChange={(e) => upd(i, { minutes: e.target.value })} /></Field>
      </div>)}
      <p className="fine">Minuti vuoti = lezione intera ({full} min). Una presenza già registrata si può correggere: resta lo storico.</p>
      {err !== null && <ErrorState error={err} onRetry={classify(err) === "stale" ? () => setN((k) => k + 1) : undefined} />}
    </div>
    <div className="modal-foot"><button type="button" className="pill-btn ghost" onClick={onClose}>Chiudi</button>
      <button className="pill-btn primary island" disabled={busy || !sum}>{busy ? "Salvataggio…" : "Salva presenze"}<span className="isle"><Icon n="check" /></span></button></div>
  </form></Modal>;
}
