import { useEffect, useState } from "react";
import { api, list } from "../api";
import { dayLabel, hm, plural, rome } from "../format";
import { human, MODE } from "../messages";
import { Btn, Empty, Notice, PageHead, Skeleton, Tag } from "../ui/core";
import { Check, Field, SegCtl, TextArea } from "../ui/controls";
import { Modal, useToast } from "../ui/layers";

export type AckLesson = { id: string; start_at: string; end_at: string; subject: string; mode: string };
export type Ack = {
  id: string; publication: string; published_at: string; tutor: string; tutor_name: string;
  state: "PENDING" | "ACKNOWLEDGED" | "COUNTER" | "RESOLVED"; note: string;
  items: { lesson_id: string; proposal: string }[]; decision: string; decision_note: string; version: number; lessons: AckLesson[];
};

export const ACK_STATE: Record<Ack["state"], [string, "amber" | "green" | "plain"]> = {
  PENDING: ["Da confermare", "amber"], ACKNOWLEDGED: ["Presa visione confermata", "green"],
  COUNTER: ["Modifiche proposte, in attesa del centro", "plain"], RESOLVED: ["Chiusa dal centro", "plain"],
};
const DECISION: Record<string, string> = { ACCEPTED: "Il centro ha accolto le modifiche", REJECTED: "Il centro non ha accolto le modifiche: controlla di nuovo gli orari", ASK_GUARDIANS: "Il centro ha chiesto conferma alle famiglie" };

export function lessonLine(l: AckLesson) {
  const s = rome(l.start_at), e = rome(l.end_at);
  return `${dayLabel(s.date)} · ${hm(s.min)}–${hm(e.min)} · ${l.subject || "Lezione"} · ${MODE[l.mode] || l.mode}`;
}

export function LessonList({ ack, highlight }: { ack: Ack; highlight?: boolean }) {
  const asked = new Map(ack.items.map((i) => [i.lesson_id, i.proposal]));
  return <ul style={{ margin: "8px 0", paddingLeft: 18 }}>{ack.lessons.map((l) => <li key={l.id}>{lessonLine(l)}{highlight && asked.has(l.id) && <><br /><small>Modifica proposta: {asked.get(l.id)}</small></>}</li>)}</ul>;
}

/** Portale tutor: presa visione degli orari pubblicati e controproposta al centro. */
export default function PresaVisione() {
  const [rows, setRows] = useState<Ack[] | null>(null), [err, setErr] = useState(""), [counter, setCounter] = useState<Ack | null>(null), [busy, setBusy] = useState("");
  const toast = useToast();
  const load = () => list<Ack>("/schedule-acks").then((r) => { setRows(r); setErr(""); }).catch((e) => setErr(human(e).text));
  useEffect(() => { load(); }, []);
  async function confirm(a: Ack) {
    setBusy(a.id);
    try { await api(`/schedule-acks/${a.id}/acknowledge`, { method: "POST", body: JSON.stringify({ expected_version: a.version }) }); toast("Presa visione registrata."); await load(); }
    catch (e) { setErr(human(e).text); await load(); } finally { setBusy(""); }
  }
  const open = (rows || []).filter((a) => a.state === "PENDING");
  return <>
    <FamilyConfirmations />
    <PageHead id="h-ack" title="Orari da confermare" />
    {err && <Notice kind="bad" action={<Btn kind="sm" onClick={load}>Riprova</Btn>}>{err}</Notice>}
    {!rows ? <Skeleton rows={3} /> : !rows.length ? <Empty title="Nessun orario da confermare" /> : <>
      {open.length > 0 && <Notice kind="warn">{plural(open.length, "pubblicazione attende", "pubblicazioni attendono")} la tua presa visione.</Notice>}
      {rows.map((a) => <section key={a.id} className="module" aria-labelledby={`ack-${a.id}`} style={{ marginTop: 14 }}>
        <div className="m-head"><div><h2 className="m-title" id={`ack-${a.id}`}>Pubblicazione del {dayLabel(rome(a.published_at).date).toLowerCase()}</h2>
          <p className="sub-line">{plural(a.lessons.length, "lezione", "lezioni")} con te</p></div>
          <Tag tone={ACK_STATE[a.state][1]}>{ACK_STATE[a.state][0]}</Tag></div>
        <LessonList ack={a} highlight={a.state === "COUNTER"} />
        {a.decision && <Notice kind={a.decision === "REJECTED" ? "warn" : "info"} title={DECISION[a.decision]}>{a.decision_note}</Notice>}
        {(a.state === "PENDING" || a.state === "ACKNOWLEDGED") && <div className="controls" style={{ marginTop: 10 }}>
          {a.state === "PENDING" && <Btn kind="primary" isle="check" disabled={busy === a.id} onClick={() => confirm(a)}>{busy === a.id ? "Registro…" : "Confermo la presa visione"}</Btn>}
          <Btn onClick={() => setCounter(a)}>Proponi modifiche</Btn></div>}
      </section>)}
    </>}
    <CounterModal ack={counter} onClose={() => setCounter(null)} onDone={async () => { setCounter(null); toast("Proposta inviata al centro."); await load(); }} />
  </>;
}

function CounterModal({ ack, onClose, onDone }: { ack: Ack | null; onClose: () => void; onDone: () => Promise<void> }) {
  const [pick, setPick] = useState<Record<string, string>>({}), [note, setNote] = useState(""), [tried, setTried] = useState(false), [err, setErr] = useState(""), [busy, setBusy] = useState(false);
  useEffect(() => { setPick({}); setNote(""); setTried(false); setErr(""); }, [ack]);
  if (!ack) return null;
  const chosen = Object.entries(pick), empty = chosen.filter(([, v]) => !v.trim()).map(([k]) => k);
  async function submit(e: React.FormEvent) {
    e.preventDefault(); setTried(true);
    if (!chosen.length || empty.length) return;
    setBusy(true); setErr("");
    try {
      await api(`/schedule-acks/${ack!.id}/counter`, { method: "POST", body: JSON.stringify({ expected_version: ack!.version, note: note.trim(), items: chosen.map(([lesson_id, proposal]) => ({ lesson_id, proposal: proposal.trim() })) }) });
      await onDone();
    } catch (er) { setErr(human(er).text); } finally { setBusy(false); }
  }
  return <Modal open={!!ack} onClose={onClose} labelledBy="ct-title"><form onSubmit={submit} noValidate>
    <div className="modal-body">
      <h2 id="ct-title">Proponi modifiche agli orari</h2>
      
      {tried && !chosen.length && <Notice kind="bad">Scegli almeno una lezione.</Notice>}
      {ack.lessons.map((l) => { const on = l.id in pick; return <div key={l.id} className="fld">
        <Check checked={on} onChange={(v) => setPick((p) => { const n = { ...p }; if (v) n[l.id] = ""; else delete n[l.id]; return n; })}>{lessonLine(l)}</Check>
        {on && <Field label="Modifica proposta" id={`ct-${l.id}`} error={tried && empty.includes(l.id) && "Scrivi la modifica che proponi."}>
          <TextArea id={`ct-${l.id}`} maxLength={200} rows={2} value={pick[l.id]} placeholder="Es. Spostare a mercoledì alla stessa ora" onChange={(e) => setPick((p) => ({ ...p, [l.id]: e.target.value }))} /></Field>}
      </div>; })}
      <Field label="Nota per il centro" id="ct-note" optional hint="Senza dati sanitari o personali non necessari."><TextArea id="ct-note" maxLength={500} rows={2} value={note} onChange={(e) => setNote(e.target.value)} /></Field>
      {err && <Notice kind="bad">{err}</Notice>}
    </div>
    <div className="modal-foot"><button type="button" className="pill-btn ghost" onClick={onClose}>Annulla</button>
      <button className="pill-btn primary" disabled={busy}>{busy ? "Invio…" : "Invia al centro"}</button></div>
  </form></Modal>;
}

/** Centro: controproposte dei tutor da decidere (accogli, chiedi alle famiglie, respingi). */
export function AckQueue() {
  const [rows, setRows] = useState<Ack[] | null>(null), [err, setErr] = useState(""), [cur, setCur] = useState<Ack | null>(null);
  const toast = useToast();
  const load = () => list<Ack>("/schedule-acks").then(setRows).catch((e) => setErr(human(e).text));
  useEffect(() => { load(); }, []);
  const counters = (rows || []).filter((a) => a.state === "COUNTER"), pending = (rows || []).filter((a) => a.state === "PENDING");
  return <section className="module" aria-labelledby="h-acks" style={{ marginTop: 18 }}>
    <div className="m-head"><div><h2 className="m-title" id="h-acks">Prese visione dei tutor</h2>
      <p className="sub-line">{rows ? `${plural(counters.length, "controproposta da decidere", "controproposte da decidere")} · ${plural(pending.length, "tutor deve ancora confermare", "tutor devono ancora confermare")}` : "Carico…"}</p></div></div>
    {err && <Notice kind="bad" action={<Btn kind="sm" onClick={() => { setErr(""); load(); }}>Riprova</Btn>}>{err}</Notice>}
    {!rows ? <Skeleton rows={2} /> : !rows.length ? <Empty title="Nessuna pubblicazione" />
      : <div className="mini-list">{[...counters, ...pending].slice(0, 12).map((a) => <button key={a.id} type="button" className="mini" onClick={() => a.state === "COUNTER" && setCur(a)} aria-disabled={a.state !== "COUNTER"}>
        <span className="grow"><b>{a.tutor_name}</b><small>{plural(a.lessons.length, "lezione", "lezioni")}{a.state === "COUNTER" ? ` · ${plural(a.items.length, "modifica proposta", "modifiche proposte")}` : ""}</small></span>
        <Tag tone={ACK_STATE[a.state][1]}>{ACK_STATE[a.state][0]}</Tag></button>)}
        {!counters.length && !pending.length && <p className="muted">Tutti i tutor hanno confermato.</p>}</div>}
    <DecideModal ack={cur} onClose={() => setCur(null)} onDone={async (m) => { setCur(null); toast(m); await load(); }} />
  </section>;
}

type Decision = "ACCEPTED" | "ASK_GUARDIANS" | "REJECTED";
const PREFILL: Record<Decision, string> = { ACCEPTED: "Modifiche accolte dal centro", ASK_GUARDIANS: "Modifiche plausibili: chiediamo conferma alla famiglia", REJECTED: "Modifiche non compatibili con il calendario del centro" };

function DecideModal({ ack, onClose, onDone }: { ack: Ack | null; onClose: () => void; onDone: (m: string) => Promise<void> }) {
  const [d, setD] = useState<Decision>("ASK_GUARDIANS"), [reason, setReason] = useState(PREFILL.ASK_GUARDIANS), [err, setErr] = useState(""), [busy, setBusy] = useState(false);
  useEffect(() => { setD("ASK_GUARDIANS"); setReason(PREFILL.ASK_GUARDIANS); setErr(""); }, [ack]);
  if (!ack) return null;
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setErr("");
    try {
      await api(`/schedule-acks/${ack!.id}/decide`, { method: "POST", body: JSON.stringify({ expected_version: ack!.version, decision: d, reason: reason.trim() || PREFILL[d] }) });
      await onDone(d === "REJECTED" ? "Controproposta respinta: il tutor rivedrà gli orari." : d === "ASK_GUARDIANS" ? "Richieste create: servono le conferme delle famiglie." : "Richieste di modifica create nella coda.");
    } catch (er) { setErr(human(er).text); } finally { setBusy(false); }
  }
  return <Modal open={!!ack} onClose={onClose} labelledBy="dc-title"><form onSubmit={submit} noValidate>
    <div className="modal-body">
      <h2 id="dc-title">Controproposta di {ack.tutor_name}</h2>
      {ack.note && <p className="lead">{ack.note}</p>}
      <LessonList ack={{ ...ack, lessons: ack.lessons.filter((l) => ack.items.some((i) => i.lesson_id === l.id)) }} highlight />
      <SegCtl<Decision> label="Decisione" value={d} onChange={(v) => { setD(v); setReason(PREFILL[v]); }} options={[["ASK_GUARDIANS", "Chiedi alle famiglie"], ["ACCEPTED", "Accogli"], ["REJECTED", "Respingi"]]} />
      
      {err && <Notice kind="bad">{err}</Notice>}
    </div>
    <div className="modal-foot"><button type="button" className="pill-btn ghost" onClick={onClose}>Annulla</button>
      <button className="pill-btn primary" disabled={busy}>{busy ? "Salvo…" : "Conferma la decisione"}</button></div>
  </form></Modal>;
}


type FamilyCR = { id: string; kind: string; reason: string; version: number; awaiting: string | null; lesson_start_at: string | null; proposal: { start_at?: string; center_reason?: string } };
/** P4 · DC-APPROVAZIONI: le richieste delle famiglie accolte dal centro le conferma anche il tutor. */
export function FamilyConfirmations() {
  const toast = useToast(); const [rows, setRows] = useState<FamilyCR[] | null>(null), [err, setErr] = useState(""), [act, setAct] = useState<{ row: FamilyCR; ok: boolean } | null>(null), [reason, setReason] = useState(""), [busy, setBusy] = useState(false);
  const load = () => api<{ results: FamilyCR[] }>("/change-requests/?state=SUBMITTED").then((r) => setRows(r.results.filter((x) => x.awaiting === "TUTOR"))).catch((e) => { setRows([]); setErr(human(e).text); });
  useEffect(() => { load(); }, []);
  if (!rows) return <Skeleton rows={2} />;
  if (!rows.length && !err) return null;
  const at = (iso: string | null) => { if (!iso) return ""; const r = rome(iso); return `${dayLabel(r.date)} · ${hm(r.min)}`; };
  return <section aria-labelledby="fc-title" style={{ marginTop: 24 }}>
    <h2 id="fc-title">Richieste delle famiglie da confermare</h2>
    {err && <Notice kind="bad">{err}</Notice>}
    {rows.map((r) => <div className="card" key={r.id} style={{ marginBottom: 10 }}>
      <b>{r.kind === "CANCEL" ? "Annullare la lezione" : "Spostare la lezione"}</b> del {at(r.lesson_start_at)}{r.proposal.start_at ? ` → ${at(r.proposal.start_at)}` : ""}
      <p className="muted">{r.reason ? `Richiesta della famiglia: ${r.reason}. ` : ""}Il centro ha accettato{r.proposal.center_reason ? `: «${r.proposal.center_reason}»` : ""}.</p>
      <div className="controls"><Btn kind="primary" onClick={() => { setAct({ row: r, ok: true }); setReason("Confermo"); }}>Confermo</Btn><Btn onClick={() => { setAct({ row: r, ok: false }); setReason("Non posso in quell’orario"); }}>Non posso</Btn></div>
    </div>)}
    <Modal open={!!act} onClose={() => setAct(null)} labelledBy="fc-m"><div className="modal-body">
      <h2 id="fc-m">{act?.ok ? "Confermi la richiesta?" : "Rifiuti la richiesta?"}</h2>
    </div><div className="modal-foot"><button type="button" className="pill-btn ghost" onClick={() => setAct(null)}>Annulla</button>
      <Btn kind="primary" disabled={busy} onClick={async () => { setBusy(true); try { await api(`/change-requests/${act!.row.id}/tutor-confirm/`, { method: "POST", headers: { "Idempotency-Key": crypto.randomUUID() }, body: JSON.stringify({ expected_version: act!.row.version, decision: act!.ok ? "CONFIRM" : "REJECT", reason: reason.trim() }) }); toast(act!.ok ? "Confermata: il calendario è aggiornato" : "Rifiutata: il centro e la famiglia sono avvisati"); setAct(null); } catch (e) { toast(human(e).text); } finally { setBusy(false); load(); } }}>{busy ? "Invio…" : "Conferma"}</Btn></div></Modal>
  </section>;
}
