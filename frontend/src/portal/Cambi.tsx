import ConfermeGenitori from "./ConfermeGenitori";
/**
 * Richieste di cambio e assenza (GAP-G01/G02): invio da una lezione futura con chiave di
 * idempotenza (un «Riprova» non duplica), elenco delle proprie richieste, ritiro con
 * versione attesa (conflitto → stato «dati non aggiornati»).
 */
import { FormEvent, useEffect, useMemo, useState } from "react";
import { ApiError, get, newIdempotencyKey, post } from "../api/client";
import type { S } from "../api/schema.gen";
import { addDays, dayShort, hm, rangeOf, rome, romeISO, todayRome } from "../format";
import { human } from "../messages";
import { Btn, Icon, Notice, PageHead, Tag, Tech } from "../ui/core";
import { Choices, DateField, Field, SegCtl, TextArea, Wheel } from "../ui/controls";
import { GuardFoot, Modal, useDirtyGuard, useToast } from "../ui/layers";
import { Help } from "../ui/help";
import { setQuery, useRoute } from "../ui/route";
import { classify, ErrorState, ViewState } from "../ui/states";
import { loadMine, MyLesson } from "../app/myApi";
import { CR_STATE, KIND_LABEL, useLoad } from "./data";

export type CrTarget = { lesson: MyLesson; students: { id: string; name: string }[]; asTutor: boolean; kind?: S.ChangeRequest["kind"] };
const STEPS = Array.from({ length: 57 }, (_, i) => 8 * 60 + i * 15); // 08:00–22:00
const MAX = 200;

/** Elenco delle richieste dell'utente, con il contesto della lezione quando è visibile. */
export default function Cambi() {
  const r = useRoute(), toast = useToast(), f = r.q.get("f") || "aperte";
  const crs = useLoad((signal) => get("/change-requests/", { signal }), []);
  const lessons = useLoad(async () => { const t = todayRome(); return loadMine(addDays(t, -30), addDays(t, 31)).catch(() => [] as MyLesson[]); }, []);
  const byId = useMemo(() => new Map((lessons.data || []).map((l) => [l.id, l])), [lessons.data]);
  const [withdraw, setWithdraw] = useState<S.ChangeRequest | null>(null);
  const all = crs.data?.results || [];
  const rows = all.filter((x) => (f === "aperte" ? x.state === "SUBMITTED" : f === "chiuse" ? x.state !== "SUBMITTED" : true));
  return <section className="module planner" aria-labelledby="h-cambi">
    <ConfermeGenitori />
    <PageHead id="h-cambi" title="Richieste di cambio" lead="Cambi, cancellazioni e assenze che hai chiesto al centro. Una richiesta non modifica il calendario finché il centro non la accoglie." />
    <div className="page-help"><Help topic="cambi" /></div>
    <div className="toolbar" style={{ marginBottom: 12 }}>
      <SegCtl label="Stato" value={f} options={[["aperte", "In attesa"], ["chiuse", "Chiuse"], ["tutte", "Tutte"]]} onChange={(v) => setQuery((q) => (v === "aperte" ? q.delete("f") : q.set("f", v)))} />
    </div>
    {crs.error ? (classify(crs.error) === "disabled" ? <ViewState kind="disabled" title="Calendario non attivo">Le richieste di cambio non sono disponibili finché il calendario non è attivo.</ViewState> : <ErrorState error={crs.error} onRetry={crs.reload} />)
      : !crs.data ? <ViewState kind="loading" />
      : rows.length ? <div className="list-rows">{rows.map((x) => { const l = byId.get(x.lesson_id); const [label, tone] = CR_STATE[x.state]; return <div className="list-row" key={x.id}>
        <div><b>{KIND_LABEL[x.kind]}{l ? ` · ${l.subject_name}` : ""}</b>
          <small>{l ? `${dayShort(rome(l.start_at).date)} ${rangeOf(l.start_at, l.end_at)}` : "Lezione fuori dal periodo visibile"}{x.kind === "RESCHEDULE" && typeof x.proposal?.start_at === "string" ? ` → proposta ${dayShort(rome(x.proposal.start_at).date)} ${hm(rome(x.proposal.start_at).min)}` : ""}{x.reason ? ` · «${x.reason}»` : ""}</small>
          {x.resolution_note && x.state !== "SUBMITTED" && <small>Nota del centro: {x.resolution_note}</small>}
        </div>
        <Tag tone={tone}>{label}</Tag>
        {x.state === "SUBMITTED" && <Btn kind="sm ghost" onClick={() => setWithdraw(x)}>Ritira</Btn>}
      </div>; })}</div>
      : <ViewState kind="empty" title={all.length ? "Nessuna richiesta in questo filtro" : "Nessuna richiesta"}>Per chiedere un cambio o segnalare un’assenza apri la lezione da <a href="#/settimana">La mia settimana</a>.</ViewState>}
    <WithdrawModal cr={withdraw} onClose={() => setWithdraw(null)} onDone={(m) => { toast(m); crs.reload(); }} onStale={crs.reload} />
  </section>;
}

function WithdrawModal({ cr, onClose, onDone, onStale }: { cr: S.ChangeRequest | null; onClose: () => void; onDone: (m: string) => void; onStale: () => void }) {
  const [reason, setReason] = useState(""), [busy, setBusy] = useState(false), [err, setErr] = useState<unknown>(null), [last, setLast] = useState(cr), [key, setKey] = useState("");
  useEffect(() => { if (cr) { setLast(cr); setReason(""); setErr(null); setKey(newIdempotencyKey()); } }, [cr]);
  const v = cr || last; if (!v) return null;
  async function submit(e: FormEvent) {
    e.preventDefault(); setBusy(true); setErr(null);
    try { await post("/change-requests/{pk}/withdraw/", { expected_version: v!.version, reason: reason.trim() || "Ritirata dal richiedente" }, { params: { pk: v!.id }, idempotencyKey: key }); onClose(); onDone("Richiesta ritirata."); }
    catch (x) { setErr(x); if (classify(x) === "stale") onStale(); } finally { setBusy(false); }
  }
  return <Modal open={!!cr} onClose={onClose} labelledBy="wd-title"><form onSubmit={submit} noValidate>
    <div className="modal-body">
      <h2 id="wd-title">Ritirare la richiesta?</h2>
      <p className="lead">{KIND_LABEL[v.kind]}: il centro non la valuterà più. Potrai inviarne una nuova se serve.</p>
      {err !== null && (classify(err) === "stale" ? <ViewState kind="stale">La richiesta è cambiata nel frattempo (forse il centro l’ha già valutata). L’elenco è stato ricaricato.</ViewState> : <ErrorState error={err} />)}
    </div>
    <div className="modal-foot"><button type="button" className="pill-btn ghost" onClick={onClose}>Annulla</button>
      <button className="pill-btn danger island" disabled={busy}>{busy ? "Ritiro…" : "Ritira"}<span className="isle"><Icon n="x" /></span></button></div>
  </form></Modal>;
}

/** Nuova richiesta da una lezione. La chiave di idempotenza nasce all'apertura e resta per i «Riprova». */
export function ChangeRequestModal({ target, onClose, onDone }: { target: CrTarget | null; onClose: () => void; onDone: (m: string) => void }) {
  const [last, setLast] = useState(target);
  const init = (t: CrTarget | null) => ({ kind: (t?.kind || (t?.asTutor ? "ABSENCE" : "ABSENCE")) as S.ChangeRequest["kind"], student: t?.students.length === 1 ? t.students[0].id : "", reason: "", date: t ? rome(t.lesson.start_at).date : todayRome(), min: t ? rome(t.lesson.start_at).min : 15 * 60 });
  const [v, setV] = useState(() => init(target)), [key, setKey] = useState(""), [bad, setBad] = useState<Record<string, string>>({}), [err, setErr] = useState<unknown>(null), [busy, setBusy] = useState(false);
  useEffect(() => { if (target) { setLast(target); setV(init(target)); setKey(newIdempotencyKey()); setBad({}); setErr(null); g.reset(); } }, [target]); // eslint-disable-line react-hooks/exhaustive-deps
  const dirty = !!target && !!v.reason.trim();
  const g = useDirtyGuard(dirty);
  const t = target || last; if (!t) return null;
  // Stesso contenuto → stessa chiave (il «Riprova» non duplica); contenuto cambiato → chiave nuova.
  const set = (p: Partial<typeof v>) => { setV((x) => ({ ...x, ...p })); setBad({}); if (err) setKey(newIdempotencyKey()); };
  const l = t.lesson, needStudent = !t.asTutor;
  async function submit(e: FormEvent) {
    e.preventDefault();
    const b: Record<string, string> = {};
    if (needStudent && !v.student) b.student = "Scegli lo studente a cui si riferisce.";
    if (v.kind === "RESCHEDULE" && romeISO(v.date, v.min) === romeISO(rome(l.start_at).date, rome(l.start_at).min)) b.when = "Scegli un orario diverso da quello attuale.";
    setBad(b);
    if (Object.keys(b).length) { document.getElementById(b.student ? "cr-student" : b.when ? "cr-date" : "cr-reason")?.focus(); return; }
    setBusy(true); setErr(null);
    const body: S.ChangeRequestCommand = { lesson_id: l.id, kind: v.kind, reason: v.reason.trim() || KIND_LABEL[v.kind], ...(needStudent ? { student_id: v.student } : {}), ...(v.kind === "RESCHEDULE" ? { proposal: { start_at: romeISO(v.date, v.min) } } : {}) };
    try { await post("/change-requests/", body, { idempotencyKey: key }); g.allow(); onClose(); onDone(`${KIND_LABEL[v.kind]} inviata al centro: riceverai una notifica con l’esito.`); }
    catch (x) { if (x instanceof ApiError && x.code === "IDEMPOTENCY_CONFLICT") setKey(newIdempotencyKey()); setErr(x); } finally { setBusy(false); }
  }
  const kinds: [S.ChangeRequest["kind"], string][] = [["ABSENCE", t.asTutor ? "Mia assenza" : "Assenza"], ["RESCHEDULE", "Spostamento"], ["CANCEL", "Cancellazione"], ["OTHER", "Altro"]];
  return <Modal open={!!target} onClose={onClose} guard={g.guard} labelledBy="cr-title"><form onSubmit={submit} noValidate>
    <div className="modal-body">
      <h2 id="cr-title">{v.kind === "ABSENCE" ? "Segnala un’assenza" : "Chiedi un cambio"}</h2>
      <p className="lead">{l.subject_name}, {dayShort(rome(l.start_at).date)} {rangeOf(l.start_at, l.end_at)}. Il centro valuta la richiesta: finché non risponde la lezione resta com’è.</p>
      <Field label="Tipo di richiesta"><div className="seg-scroll"><SegCtl label="Tipo di richiesta" value={v.kind} options={kinds} onChange={(k) => set({ kind: k })} /></div></Field>
      {needStudent && (t.students.length > 1
        ? <Field label="Per chi" id="cr-student" error={bad.student}><Choices label="Per chi" name="cr-student" value={v.student} onChange={(x) => set({ student: x })} options={t.students.map((s) => ({ v: s.id, label: s.name, av: s.name }))} /></Field>
        : <p className="fine">Per: <b>{t.students[0]?.name}</b></p>)}
      {v.kind === "RESCHEDULE" && <>
        <div className="grid2">
          <Field label="Nuovo giorno" id="cr-date" error={bad.when}><DateField id="cr-date" label="Nuovo giorno" value={v.date} min={todayRome()} onChange={(x) => set({ date: x })} /></Field>
          <Field label={`Nuovo inizio: ${hm(v.min)}`}><Wheel label="Nuovo inizio" items={STEPS.map((m) => ({ v: m, label: hm(m) }))} value={v.min} onChange={(m) => set({ min: m })} onLive={(m) => setV((x) => ({ ...x, min: m }))} /></Field>
        </div>
        <p className="fine">È una proposta: il centro verifica tutor, spazi e altri partecipanti prima di decidere.</p>
      </>}
      <Field label="Note per il centro" id="cr-reason" optional error={bad.reason} hint={`${v.reason.length}/${MAX} · senza dati sanitari o dettagli personali non necessari.`}>
        <TextArea id="cr-reason" value={v.reason} maxLength={MAX} onChange={(e) => set({ reason: e.target.value })} aria-invalid={!!bad.reason || undefined} style={{ minHeight: 80, fontFamily: "inherit" }} placeholder={v.kind === "ABSENCE" ? "Es. impegno scolastico, viaggio…" : "Es. preferiremmo il pomeriggio…"} /></Field>
      {err !== null && (classify(err) === "error" ? <Notice kind="bad">{human(err).text}<Tech>{human(err).detail}</Tech></Notice> : <ErrorState error={err} />)}
    </div>
    {g.asking ? <GuardFoot onKeep={g.keep} onDiscard={() => { g.allow(); onClose(); }} /> :
      <div className="modal-foot"><button type="button" className="pill-btn ghost" onClick={() => { if (g.guard()) onClose(); }}>Chiudi</button>
        <button className="pill-btn primary island" disabled={busy}>{busy ? "Invio…" : err ? "Riprova" : "Invia al centro"}<span className="isle"><Icon n="send" /></span></button></div>}
  </form></Modal>;
}
