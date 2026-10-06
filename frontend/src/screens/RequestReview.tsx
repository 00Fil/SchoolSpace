/** Verifica delle lezioni di una richiesta (v0.9.9).
 *  Dopo l'inserimento o l'approvazione il motore viene ricalcolato per la richiesta e
 *  colloca le lezioni in una bozza. Qui il centro vede l'elenco, gestisce le incongruenze
 *  (lezioni non collocate, conflitti nati nel frattempo, sforamenti da confermare) e solo
 *  alla conferma le lezioni vanno in calendario e la richiesta diventa «completata». */
import { Fragment, useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { addDays, dayLabel, monthYear, plural, rangeOf, rome, todayRome } from "../format";
import { human } from "../messages";
import { Btn, Icon, Notice, Tag } from "../ui/core";
import { Check, DateField, Field } from "../ui/controls";
import { Modal } from "../ui/layers";
import { Slot, SlotPicker, slotKey } from "../ui/SlotPicker";
import { useData } from "../app/data";
import { KindTag, modeText, Req, StatusTag, whenText } from "./requestForms";

type Conf = { id: string; party: string; who: string; minutes: number; labels: string[]; status: string };
export type ReviewLesson = {
  id: string; start_at: string; end_at: string; mode: string; room: string | null; overflow_minutes: number;
  tutor: { id: string; name: string }; students: { id: string; name: string }[];
  confirmations: Conf[]; conflicts: string[]; conflict_codes: string[];
};
type Issue = { kind: "CONFLICT" | "MISSING" | "CONFIRM"; blocking: boolean; message: string; lesson_id?: string; start_at?: string; reason?: string; missing?: number; weeks?: string[] };
export type Review = {
  request_id: string; planning_state: "" | "REVIEW" | "DONE"; completed_at: string | null;
  /** Mese su cui lavora la verifica (AAAA-MM) e mesi del periodo della richiesta. */
  month: string | null; months: string[];
  plan: { id: string; solver_status: string; stats: Record<string, unknown>; created_at: string } | null;
  lessons: ReviewLesson[]; issues: Issue[]; missing: number; conflicts: number; confirmations: number; can_complete: boolean;
  result?: { published: number; awaiting: number; confirmations_sent: number; missing: number; draft?: boolean; correction_id?: string | null };
};
type Opts = { options: Slot[]; message?: string; date_from: string; date_to: string };

const base = (id: string) => `/teaching-requests/${id}/planning`;

/** Primo e ultimo giorno del mese AAAA-MM. */
function monthBounds(m: string): [string, string] {
  const [y, mo] = m.split("-").map(Number);
  const last = new Date(Date.UTC(y, mo, 0)).getUTCDate();
  return [`${m}-01`, `${m}-${String(last).padStart(2, "0")}`];
}

/** Orari liberi per aggiungere (lesson assente) o spostare una lezione. */
function Picker({ req, lesson, from0, month, onPick, onCancel, busy }: { req: Req; lesson?: ReviewLesson; from0: string; month: string | null; onPick: (s: Slot) => void; onCancel: () => void; busy: boolean }) {
  const [mFirst, mLast] = month && req.kind !== "SINGLE" ? monthBounds(month) : ["", "9999-12-31"];
  const min = [todayRome(), req.period_start || "", mFirst].sort().pop() || todayRome();
  const max = [req.period_end || "9999-12-31", mLast].sort()[0];
  const [from, setFrom] = useState(from0 < min ? min : from0), [res, setRes] = useState<Opts | null>(null), [pick, setPick] = useState<Slot | null>(null), [err, setErr] = useState("");
  useEffect(() => {
    let live = true; setRes(null); setPick(null); setErr("");
    api<Opts>(`${base(req.id)}/options`, { method: "POST", body: JSON.stringify({ date_from: from, date_to: [addDays(from, 13), max].sort()[0], ...(lesson ? { lesson_id: lesson.id } : {}) }) })
      .then((r) => live && setRes(r)).catch((e) => { if (live) { setErr(human(e).text); setRes({ options: [], date_from: from, date_to: from }); } });
    return () => { live = false; };
  }, [from, lesson?.id, req.id]); // eslint-disable-line react-hooks/exhaustive-deps
  return <div className="rv-pick">
    <div className="rv-pick-head">
      <b>{lesson ? `Sposta la lezione di ${dayLabel(rome(lesson.start_at).date).toLowerCase()} ${rangeOf(lesson.start_at, lesson.end_at)}` : "Aggiungi una lezione a mano"}</b>
      <Field label="A partire dal"><DateField label="A partire dal" value={from} min={min} max={max} onChange={setFrom} /></Field>
    </div>
    <span className="lbl sp-lbl">Orari liberi per tutti nei 14 giorni successivi{month && req.kind !== "SINGLE" ? ` (solo ${monthYear(month).toLowerCase()})` : ""}</span>
    <SlotPicker slots={res ? res.options : null} value={pick ? slotKey(pick) : ""} onPick={setPick}
      empty={res?.message || "Nessun orario libero per studenti, tutor e aule in questi giorni: prova da un’altra data."} />
    {err && <Notice kind="bad">{err}</Notice>}
    <div className="rv-pick-foot">
      <button type="button" className="pill-btn ghost" onClick={onCancel}>Annulla</button>
      <Btn kind="primary" disabled={!pick || busy} onClick={() => pick && onPick(pick)}>{busy ? "Salvo…" : lesson ? "Sposta qui" : "Aggiungi"}</Btn>
    </div>
  </div>;
}

export function ReviewModal({ id, onClose, onDone }: { id: string | null; onClose: () => void; onDone: (msg: string, date?: string) => void }) {
  const d = useData();
  const [rv, setRv] = useState<Review | null>(null), [err, setErr] = useState(""), [busy, setBusy] = useState<string>("");
  const [moving, setMoving] = useState<string | null>(null), [adding, setAdding] = useState<string | null>(null), [accept, setAccept] = useState(false), [pubNow, setPubNow] = useState(false);
  const req = (d.requests as Req[]).find((r) => r.id === id) || null;
  const load = useCallback(() => {
    if (!id) return;
    api<Review>(base(id)).then((r) => { setRv(r); setErr(""); }).catch((e) => setErr(human(e).text));
  }, [id]);
  useEffect(() => { setRv(null); setMoving(null); setAdding(null); setAccept(false); setPubNow(false); setErr(""); load(); }, [load]);

  async function act(key: string, path: string, body: Record<string, unknown> = {}) {
    setBusy(key); setErr("");
    try { const r = await api<Review>(path, { method: "POST", body: JSON.stringify(body) }); setRv(r); setMoving(null); setAdding(null); return r; }
    catch (e) { setErr(human(e).text); return null; } finally { setBusy(""); }
  }
  async function complete() {
    if (!id || !rv) return;
    const r = await act("complete", `${base(id)}/complete`, { ...(rv.missing ? { accept_missing: accept } : {}), publish_now: pubNow });
    if (!r) return;
    const res = r.result;
    const first = rv.lessons[0] ? rome(rv.lessons[0].start_at).date : undefined;
    const lm = monthYear(rome(rv.lessons[0]?.start_at || new Date().toISOString()).date.slice(0, 7)).toLowerCase();
    const parts = [res?.draft ? `${plural(rv.lessons.length, "lezione", "lezioni")} nella bozza di ${lm}, da pubblicare dall’Agenda` : res ? plural(res.published, "lezione in calendario", "lezioni in calendario") : "", res?.awaiting ? plural(res.awaiting, "in attesa di conferma", "in attesa di conferma") : "", res?.missing ? plural(res.missing, "non collocata", "non collocate") : ""].filter(Boolean);
    await d.refresh();
    onDone(`${rv.month && req?.kind !== "SINGLE" ? `Mese di ${monthYear(rv.month).toLowerCase()} verificato` : "Richiesta completata"}: ${parts.join(", ")}.`, first);
  }

  if (!id) return null;
  const title = req ? `${req.subject_name}${req.student_name ? " · " + req.student_name : ""}` : "Richiesta";
  const done = rv?.planning_state === "DONE";
  const months = rv ? [...new Set(rv.lessons.map((l) => rome(l.start_at).date.slice(0, 7)))] : [];
  const firstWeek = (i: Issue) => (i.weeks && i.weeks[0]) || todayRome();
  return <Modal open onClose={onClose} labelledBy="rv-title" width={860}><div className="modal-body rv">
    <h2 id="rv-title">Verifica le lezioni: {title}</h2>
    {req && <p className="rq-kind-now"><KindTag r={req} />{req.target_type === "GROUP" && <Tag tone="violet">Gruppo</Tag>}<StatusTag s={req.status} p={rv?.planning_state ?? req.planning_state} /> <span className="muted">{whenText(req)} · {req.duration_minutes} min · {modeText(req.mode)}</span></p>}
    {req?.participant_names && req.participant_names.length > 0 && <p className="muted rv-who">Partecipanti: {req.participant_names.join(", ")}</p>}
    <p className="lead">{done ? "Richiesta completata: le lezioni del mese sono nel calendario del mese (in bozza finché non pubblichi le rettifiche dall’Agenda, se non le hai pubblicate subito). I mesi successivi li pianifica il calendario mensile." : "Il motore lavora su un mese alla volta: ha calcolato le lezioni di questa richiesta per il mese indicato. Controllale e risolvi le incongruenze: la richiesta diventa «completata» solo dopo la tua conferma. I mesi successivi li pianifica il calendario mensile (Calendario › Pianificazione)."}</p>
    {rv?.month && req?.kind !== "SINGLE" && <div className="rv-monthbar">
      <span className="lbl">Mese in verifica</span>
      {!done && rv.months.length > 1
        ? <select className="inp rv-month-sel" aria-label="Mese in verifica" value={rv.month} disabled={!!busy}
            onChange={(e) => act("rerun", `${base(id)}/rerun`, { month: e.target.value })}>
            {rv.months.map((m) => <option key={m} value={m}>{monthYear(m)}</option>)}
          </select>
        : <b>{monthYear(rv.month)}</b>}
      {busy === "rerun" && <span className="muted">Calcolo…</span>}
    </div>}

    {!rv ? (err ? <Notice kind="bad">{err}</Notice> : <div className="sp-loading" aria-busy="true"><span /><span /><span /></div>) : <>
      <div className="rv-stats" role="list">
        <div role="listitem"><small>Inserite dal motore</small><b>{rv.lessons.length}</b></div>
        <div role="listitem" className={rv.missing ? "warn" : ""}><small>Non collocate</small><b>{rv.missing}</b></div>
        <div role="listitem" className={rv.conflicts ? "bad" : ""}><small>Conflitti</small><b>{rv.conflicts}</b></div>
        <div role="listitem"><small>Da confermare</small><b>{rv.confirmations}</b></div>
      </div>

      {!rv.plan && !done && <Notice kind="warn" title="Nessuna proposta del motore" action={<Btn kind="sm primary" disabled={!!busy} onClick={() => act("rerun", `${base(id)}/rerun`, rv?.month ? { month: rv.month } : {})}>{busy === "rerun" ? "Calcolo…" : "Ricalcola"}</Btn>}>Il calcolo non è stato eseguito o non è riuscito: ricalcola le lezioni.</Notice>}

      {rv.plan && <section className="rv-sec" aria-labelledby="rv-issues"><h3 id="rv-issues">Incongruenze</h3>
        {rv.issues.length ? <ul className="rv-issues">{rv.issues.map((i, k) => <li key={k} className={"rv-issue " + i.kind.toLowerCase()}>
          <span className="rv-ic" aria-hidden="true"><Icon n={i.kind === "CONFIRM" ? "clock" : i.kind === "MISSING" ? "plus" : "x"} /></span>
          <div><b>{i.kind === "CONFLICT" ? `Conflitto · ${dayLabel(rome(i.start_at!).date)}` : i.kind === "MISSING" ? plural(i.missing || 0, "lezione non collocata", "lezioni non collocate") : `Sforamento · ${dayLabel(rome(i.start_at!).date)}`}</b>
            <span>{i.message}{i.kind === "MISSING" && i.weeks && i.weeks.length > 0 ? ` Settimane: ${i.weeks.map((w) => dayLabel(w).toLowerCase()).join(", ")}.` : ""}</span></div>
          {i.kind === "CONFLICT" && i.lesson_id && <Btn kind="sm primary" onClick={() => { setAdding(null); setMoving(i.lesson_id!); }}>Sposta</Btn>}
          {i.kind === "MISSING" && <Btn kind="sm" onClick={() => { setMoving(null); setAdding(firstWeek(i)); }}>Aggiungi a mano</Btn>}
        </li>)}</ul> : <Notice kind="ok">Nessuna incongruenza: tutte le lezioni richieste sono collocate e valide.</Notice>}
      </section>}

      {adding && req && <Picker req={req} from0={adding} month={rv.month} busy={busy === "add"} onCancel={() => setAdding(null)} onPick={(s) => act("add", `${base(id)}/lessons`, { start_at: s.start_at, tutor_id: s.tutor_id })} />}

      {rv.plan && <section className="rv-sec" aria-labelledby="rv-list"><h3 id="rv-list">Lezioni inserite dal motore{rv.month && req?.kind !== "SINGLE" ? ` · ${monthYear(rv.month).toLowerCase()}` : ""}</h3>
        {rv.lessons.length ? months.map((m) => <div key={m} className="rv-month">
          {months.length > 1 && <span className="rv-month-lbl">{monthYear(m)}</span>}
          <table className="list rv-table">
            <thead><tr><th scope="col">Giorno</th><th scope="col">Orario</th><th scope="col">Tutor</th><th scope="col" className="hide-m">Aula</th><th scope="col">Esito</th><th scope="col"><span className="sr">Azioni</span></th></tr></thead>
            <tbody>{rv.lessons.filter((l) => rome(l.start_at).date.startsWith(m)).map((l) => <Fragment key={l.id}>
              <tr className={l.conflicts.length ? "rv-bad" : ""}>
                <td>{dayLabel(rome(l.start_at).date)}</td>
                <td className="num">{rangeOf(l.start_at, l.end_at)}</td>
                <td>{l.tutor.name}</td>
                <td className="hide-m">{l.mode === "ONLINE" ? "Online" : l.room || "—"}</td>
                <td>{l.conflicts.length ? <Tag tone="red">Conflitto</Tag> : l.confirmations.length ? <Tag tone="amber">Da confermare</Tag> : <Tag tone="green">Libero</Tag>}
                  {l.conflicts.length > 0 && <small className="muted block">{l.conflicts.join("; ")}</small>}
                  {!l.conflicts.length && l.confirmations.length > 0 && <small className="muted block">Sfora di {l.overflow_minutes} min: {l.confirmations.map((c) => c.who).join(", ")}</small>}</td>
                <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>{!done && <>
                  <Btn kind="sm ghost" disabled={!!busy} onClick={() => { setAdding(null); setMoving(moving === l.id ? null : l.id); }}>Sposta</Btn>{" "}
                  <Btn kind="sm ghost" disabled={!!busy} onClick={() => act("rm" + l.id, `/planner/request-lessons/${l.id}/remove`)}>{busy === "rm" + l.id ? "Tolgo…" : "Togli"}</Btn></>}</td>
              </tr>
              {moving === l.id && req && <tr className="rv-mv"><td colSpan={6}>
                <Picker req={req} lesson={l} from0={rome(l.start_at).date} month={rv.month} busy={busy === "move"} onCancel={() => setMoving(null)} onPick={(s) => act("move", `/planner/request-lessons/${l.id}/move`, { start_at: s.start_at, tutor_id: s.tutor_id })} />
              </td></tr>}
            </Fragment>)}</tbody>
          </table>
        </div>) : <p className="sp-empty">Nessuna lezione collocata: usa «Aggiungi a mano» o ricalcola dopo aver sistemato impegni e orari.</p>}
      </section>}

      {err && <Notice kind="bad">{err}</Notice>}
      {!done && rv.plan && rv.missing > 0 && <Check checked={accept} onChange={setAccept}>Completa anche senza {plural(rv.missing, "lezione mancante", "lezioni mancanti")} (le cercherà il calendario mensile)</Check>}
      {!done && rv.plan && <><Check checked={pubNow} onChange={setPubNow}>Pubblica subito nel calendario del mese</Check>
        <p className="fine">{pubNow ? "Le lezioni entrano adesso nel calendario pubblico: tutor e famiglie ricevono gli orari." : "Le lezioni entrano nella bozza del calendario del mese: le pubblichi dall’Agenda con «Pubblica le rettifiche», insieme alle altre modifiche."}</p></>}
      {!done && rv.plan && rv.conflicts > 0 && <p className="fine">Risolvi i conflitti (sposta o togli le lezioni) per poter confermare.</p>}
    </>}
  </div>
    <div className="modal-foot rv-foot">
      {!done && rv?.plan && <Btn kind="ghost" disabled={!!busy} onClick={() => act("rerun", `${base(id)}/rerun`, rv?.month ? { month: rv.month } : {})}>{busy === "rerun" ? "Ricalcolo…" : "Ricalcola"}</Btn>}
      <span className="spacer" />
      <button type="button" className="pill-btn ghost" onClick={onClose}>{done ? "Chiudi" : "Verifica dopo"}</button>
      {!done && <Btn kind="primary" isle="check" disabled={!rv?.plan || !!busy || !rv.can_complete || (rv.missing > 0 && !accept)} onClick={complete}>{busy === "complete" ? "Confermo…" : "Conferma e completa"}</Btn>}
    </div>
  </Modal>;
}
