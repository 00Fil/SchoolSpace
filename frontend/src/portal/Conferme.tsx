/** v0.9.7 «Da confermare»: lezioni proposte dal centro che sforano di poco un impegno
 *  (al massimo la tolleranza). Famiglia, studente o tutor accettano o rifiutano. */
import { useEffect, useState } from "react";
import { api } from "../api";
import { dateLong, rangeOf, rome } from "../format";
import { human } from "../messages";
import { Btn, Empty, Icon, Notice, PageHead, Skeleton, Tag } from "../ui/core";
import { Field, Input } from "../ui/controls";
import { Modal, useToast } from "../ui/layers";
import { ErrorState } from "../ui/states";

export type Confirmation = { id: string; party: "STUDENT" | "TUTOR"; who: string; minutes: number; labels: string[]; status: "PENDING" | "ACCEPTED" | "REJECTED"; note: string; decided_at: string | null;
  lesson: { id: string; subject: string; tutor: string; students: string[]; start_at: string; end_at: string; mode: string; state: string } };

export function useConfirmations() {
  const [rows, setRows] = useState<Confirmation[] | null>(null), [err, setErr] = useState<unknown>(null);
  const load = () => { setErr(null); api<Confirmation[]>("/planner/confirmations").then(setRows).catch(setErr); };
  useEffect(load, []);
  return { rows, err, load };
}

type Change = { id: string; state: string; start_at: string; end_at: string; previous_start_at: string; previous_end_at: string; resolution: string;
  lesson: { subject: string; tutor: string; mode: string; students: string[] }; answers: { id: string; party: "TUTOR" | "STUDENT"; who: string; status: string; mine: boolean }[] };

/** Modifiche di orario o durata proposte dal centro (drag & drop in Agenda): servono le risposte dei diretti interessati. */
function LessonChanges() {
  const toast = useToast();
  const [rows, setRows] = useState<Change[] | null>(null), [busy, setBusy] = useState(""), [err, setErr] = useState("");
  const load = () => api<Change[]>("/lesson-changes/").then(setRows).catch(() => setRows([]));
  useEffect(() => { load(); }, []);
  async function answer(x: Change, accept: boolean) {
    setBusy(x.id); setErr("");
    try {
      const r = await api<Change>(`/lesson-changes/${x.id}/answer/`, { method: "POST", body: JSON.stringify({ accept }) });
      toast(!accept ? "Rifiutata: la lezione resta all’orario attuale" : r.state === "APPLIED" ? "Confermata: la lezione ha il nuovo orario" : "Confermata: aspettiamo le altre risposte");
      load();
    } catch (e) { setErr(human(e).text); } finally { setBusy(""); }
  }
  const todo = (rows || []).filter((x) => x.state === "PENDING" && x.answers.some((a) => a.mine && a.status === "PENDING"));
  if (!todo.length && !err) return null;
  return <>
    <h2 className="cf-h">Cambi di orario proposti dal centro</h2>
    {err && <Notice kind="bad">{err}</Notice>}
    <div className="cf-grid">{todo.map((x) => <article key={x.id} className="cf-card">
      <header><span className="cf-day"><b>{+rome(x.start_at).date.slice(8)}</b><small>{dateLong(rome(x.start_at).date).split(" ")[1]?.slice(0, 3)}</small></span>
        <div><h2>{x.lesson.subject}</h2><small>{x.answers.filter((a) => a.mine).map((a) => a.party === "TUTOR" ? `con ${x.lesson.students.join(", ")}` : `per ${a.who}, con ${x.lesson.tutor}`).join(" · ")}</small></div></header>
      <div className="cf-over"><Icon n="clock" /><span>Da <s>{dateLong(rome(x.previous_start_at).date)}, {rangeOf(x.previous_start_at, x.previous_end_at)}</s> a <b>{dateLong(rome(x.start_at).date)}, {rangeOf(x.start_at, x.end_at)}</b></span></div>
      <footer><Btn kind="ghost" disabled={!!busy} onClick={() => answer(x, false)}>Non va bene</Btn><Btn kind="primary" isle="check" disabled={!!busy} onClick={() => answer(x, true)}>{busy === x.id ? "Invio…" : "Va bene"}</Btn></footer>
    </article>)}</div>
  </>;
}

export default function Conferme() {
  const c = useConfirmations(), toast = useToast();
  const [no, setNo] = useState<Confirmation | null>(null), [note, setNote] = useState(""), [busy, setBusy] = useState(""), [err, setErr] = useState("");
  async function answer(x: Confirmation, accept: boolean, text = "") {
    setBusy(x.id); setErr("");
    try {
      const r = await api<{ lesson_state: string; message?: string }>(`/planner/confirmations/${x.id}/answer`, { method: "POST", body: JSON.stringify({ accept, ...(text ? { note: text } : {}) }) });
      toast(accept ? (r.lesson_state === "PUBLISHED" ? "Confermata: la lezione è nel calendario" : r.message || "Confermata: aspettiamo le altre conferme") : "Rifiutata: il centro cercherà un altro orario");
      setNo(null); setNote(""); c.load();
    } catch (e) { setErr(human(e).text); } finally { setBusy(""); }
  }
  const pending = (c.rows || []).filter((x) => x.status === "PENDING"), done = (c.rows || []).filter((x) => x.status !== "PENDING");
  return <section className="module" aria-labelledby="h-cf">
    <PageHead id="h-cf" title="Da confermare" />
    <LessonChanges />
    {err && <Notice kind="bad">{err}</Notice>}
    {c.err ? <ErrorState error={c.err} onRetry={c.load} /> : !c.rows ? <Skeleton /> : <>
      {pending.length ? <div className="cf-grid">{pending.map((x) => <article key={x.id} className="cf-card">
        <header><span className="cf-day"><b>{+rome(x.lesson.start_at).date.slice(8)}</b><small>{dateLong(rome(x.lesson.start_at).date).split(" ")[1]?.slice(0, 3)}</small></span>
          <div><h2>{x.lesson.subject}</h2><small>{rangeOf(x.lesson.start_at, x.lesson.end_at)} · {x.lesson.mode === "ONLINE" ? "Online" : "In sede"} · {x.party === "TUTOR" ? `con ${x.lesson.students.join(", ")}` : `per ${x.who}, con ${x.lesson.tutor}`}</small></div></header>
        <div className="cf-over"><Icon n="clock" /><span>Sfora di <b>{x.minutes} minuti</b> {x.labels.length ? <>l’impegno «{x.labels.join(", ")}»</> : "un impegno"}</span></div>
        <footer><Btn kind="ghost" disabled={!!busy} onClick={() => setNo(x)}>Non va bene</Btn><Btn kind="primary" isle="check" disabled={!!busy} onClick={() => answer(x, true)}>{busy === x.id ? "Invio…" : "Va bene"}</Btn></footer>
      </article>)}</div> : <Empty title="Nessuna lezione da confermare" />}
      {done.length > 0 && <><h2 className="cf-h">Già gestite</h2><ul className="pm-un">{done.map((x) => <li key={x.id}>
        <div><b>{x.lesson.subject} · {x.who}</b><small>{dateLong(rome(x.lesson.start_at).date)}, {rangeOf(x.lesson.start_at, x.lesson.end_at)}{x.note ? ` · “${x.note}”` : ""}</small></div>
        <Tag tone={x.status === "ACCEPTED" ? "green" : "red"}>{x.status === "ACCEPTED" ? "Accettata" : "Rifiutata"}</Tag></li>)}</ul></>}
    </>}
    <Modal open={!!no} onClose={() => setNo(null)} labelledBy="cf-no"><div className="modal-body">
      <h2 id="cf-no">Rifiutare questo orario?</h2>
      <p className="lead">Lo slot viene liberato e il centro proporrà un’alternativa.</p>
      <Field label="Vuoi aggiungere un messaggio?" id="cf-note" optional><Input id="cf-note" value={note} maxLength={300} placeholder="Es. Il martedì finiamo alle 17:30" onChange={(e) => setNote(e.target.value)} /></Field>
    </div><div className="modal-foot"><Btn kind="ghost" onClick={() => setNo(null)}>Annulla</Btn><Btn kind="danger" disabled={!!busy} onClick={() => no && answer(no, false, note.trim())}>Rifiuta</Btn></div></Modal>
  </section>;
}
