import { useEffect, useState } from "react";
import { api } from "../api";
import { dayLabel, hm, plural, rome } from "../format";
import { human, MODE } from "../messages";
import { Btn, Empty, Notice, PageHead, Skeleton, Tag } from "../ui/core";
import { Check, Field, Input, SegCtl } from "../ui/controls";
import { Modal, useToast } from "../ui/layers";
import { setQuery, useRoute } from "../ui/route";
import { useData } from "../app/data";
import { Slot, SlotPicker, slotKey } from "../ui/SlotPicker";

/** P4 · Operatività quotidiana: code «Richieste», «Recuperi», «Conflitti» e pannello invii. */
type CR = { id: string; lesson_id: string; kind: string; origin: string; student_id: string | null; reason: string; state: string; version: number; awaiting: "CENTER" | "TUTOR" | "GUARDIANS" | null; lesson_start_at: string | null; proposal: { start_at?: string; guardians_confirmation_required?: boolean; note?: string } };
type Ob = { id: string; participants: string[]; minutes_remaining: number; cause: string; state: string; version: number; origin_start_at: string | null; due_by: string | null; recovery_periods: { start_date: string; end_date: string; label: string }[] };
type Case = { id: string; lesson_id: string | null; kind: string; codes: string[]; state: string; version: number; week_start: string; created_at: string };
type Status = { counts: Record<string, Record<string, number>>; dead_letter: number; ambiguous: number; oldest_pending_seconds: number | null };
type Dl = { id: string; channel: string; status: string; attempts: number; error: string; event_type: string; created_at: string };

export const KIND: Record<string, string> = { CANCEL: "Annullare la lezione", RESCHEDULE: "Spostare la lezione", ABSENCE: "Assenza", OTHER: "Altro" };
const ORIGIN: Record<string, string> = { GUARDIAN: "Genitore", STUDENT: "Studente", TUTOR: "Tutor", CENTER: "Centro" };
export const CAUSE: Record<string, string> = { CENTER_CANCELLATION: "Annullata dal centro", FAMILY_REQUEST: "Richiesta della famiglia", TUTOR_ABSENCE: "Assenza del tutor", STUDENT_ABSENCE: "Assenza dello studente", CLOSURE: "Chiusura del centro" };
const CASE: Record<string, string> = { TUTOR_ABSENCE: "Assenza del tutor", STUDENT_ABSENCE: "Assenza dello studente", AVAILABILITY_CHANGED: "Disponibilità cambiata", CLOSURE: "Chiusura", RESOURCE: "Aula o canale non disponibile" };
const when = (iso: string | null) => { if (!iso) return "—"; const r = rome(iso); return `${dayLabel(r.date)} · ${hm(r.min)}`; };
const day = (iso: string) => new Date(iso + "T12:00:00").toLocaleDateString("it-IT", { day: "numeric", month: "long", year: "numeric" });
const post = (path: string, body: object) => api<any>(path, { method: "POST", headers: { "Idempotency-Key": crypto.randomUUID() }, body: JSON.stringify(body) });

function useList<T>(path: string) {
  const [rows, setRows] = useState<T[] | null>(null), [err, setErr] = useState("");
  const load = () => { setErr(""); return api<{ results: T[] }>(path).then((r) => setRows(r.results)).catch((e) => { setRows([]); setErr(human(e).text); }); };
  useEffect(() => { setRows(null); load(); }, [path]);
  return { rows, err, load };
}

/** Dialogo di conferma: il motivo nello storico è il testo precompilato (non si chiede più). */
function ReasonModal({ open, title, initial, confirm, children, onClose, onConfirm }: { open: boolean; title: string; initial: string; confirm: string; children?: React.ReactNode; onClose: () => void; onConfirm: (reason: string) => Promise<void> }) {
  const reason = initial, [busy, setBusy] = useState(false), [err, setErr] = useState("");
  useEffect(() => { if (open) setErr(""); }, [open]);
  return <Modal open={open} onClose={onClose} labelledBy="rm-title"><div className="modal-body">
    <h2 id="rm-title">{title}</h2>
    {children}
    {err && <Notice kind="bad">{err}</Notice>}
  </div><div className="modal-foot"><button type="button" className="pill-btn ghost" onClick={onClose}>Annulla</button>
    <Btn kind="primary" disabled={busy} onClick={async () => { setBusy(true); setErr(""); try { await onConfirm(reason); onClose(); } catch (e) { const h = human(e); setErr(h.code === "VERSION_CONFLICT" ? "Qualcuno l’ha appena modificata: ricarico l’elenco, riprova." : h.text); } finally { setBusy(false); } }}>{busy ? "Invio…" : confirm}</Btn></div></Modal>;
}

function Richieste() {
  const d = useData(), toast = useToast(); const { rows, err, load } = useList<CR>("/change-requests/?state=SUBMITTED");
  const [act, setAct] = useState<{ row: CR; accept: boolean } | null>(null);
  const student = (id: string | null) => d.students.find((s) => s.id === id)?.display_name || "—";
  if (!rows) return <Skeleton rows={3} />;
  return <>
    {err && <Notice kind="bad" action={<Btn kind="sm" onClick={load}>Riprova</Btn>}>{err}</Notice>}
    {!rows.length && !err ? <Empty title="Nessuna richiesta in attesa" /> :
      <div className="list-wrap"><table className="list"><thead><tr><th scope="col">Richiesta</th><th scope="col">Lezione</th><th scope="col" className="hide-m">Da</th><th scope="col">Stato</th><th scope="col"><span className="sr">Azioni</span></th></tr></thead>
        <tbody>{rows.map((r) => <tr key={r.id}>
          <td><b style={{ fontWeight: 500 }}>{KIND[r.kind] || r.kind}</b><div className="muted">{r.reason}{r.proposal?.start_at ? ` · nuovo orario ${when(r.proposal.start_at)}` : ""}</div></td>
          <td>{when(r.lesson_start_at)}<div className="muted">{student(r.student_id)}</div></td>
          <td className="hide-m">{ORIGIN[r.origin] || r.origin}</td>
          <td>{r.awaiting === "GUARDIANS" ? <Tag tone="violet">Attende i genitori</Tag> : r.awaiting === "TUTOR" ? <Tag tone="amber">Attende il tutor</Tag> : r.proposal?.guardians_confirmation_required ? <Tag tone="violet">Da far confermare ai genitori</Tag> : <Tag tone="blue">Da decidere</Tag>}</td>
          <td style={{ whiteSpace: "nowrap" }}>{r.awaiting === "CENTER" && <><Btn kind="sm" onClick={() => setAct({ row: r, accept: true })}>Accetta</Btn> <Btn kind="sm" onClick={() => setAct({ row: r, accept: false })}>Rifiuta</Btn></>}</td>
        </tr>)}</tbody></table></div>}
    <ReasonModal open={!!act} onClose={() => setAct(null)} title={act?.accept ? "Accetta la richiesta" : "Rifiuta la richiesta"} confirm={act?.accept ? "Accetta" : "Rifiuta"}
      initial={act?.accept ? "Richiesta accolta dal centro" : "Non è possibile accogliere la richiesta"}
      onConfirm={async (reason) => { const r = act!.row; const res = await post(`/change-requests/${r.id}/decide/`, { expected_version: r.version, decision: act!.accept ? "ACCEPT" : "REJECT", apply: act!.accept && (r.kind === "CANCEL" || r.kind === "RESCHEDULE"), reason }).catch(async (e) => { await load(); throw e; });
        toast(res.awaiting === "TUTOR" ? "Accettata: ora la conferma il tutor" : act!.accept ? "Richiesta accettata" : "Richiesta rifiutata"); await load(); }}>
      {act?.accept && (act.row.origin === "GUARDIAN" || act.row.origin === "STUDENT") && <Notice kind="info">Le richieste delle famiglie le conferma anche il tutor: la lezione cambia solo dopo la sua conferma.</Notice>}
    </ReasonModal>
  </>;
}

type RecOpts = { options: Slot[]; mode?: string; date_from?: string; date_to?: string; due_by?: string | null; minutes?: number; message?: string };

function Recuperi() {
  const d = useData(), toast = useToast(); const { rows, err, load } = useList<Ob>("/recovery-obligations/?state=OPEN");
  const [waive, setWaive] = useState<Ob | null>(null), [fix, setFix] = useState<Ob | null>(null);
  const [mode, setMode] = useState(""), [tutor, setTutor] = useState(""), [from, setFrom] = useState("");
  const [opts, setOpts] = useState<RecOpts | null>(null), [pick, setPick] = useState<Slot | null>(null);
  const [manual, setManual] = useState(false), [at, setAt] = useState(""), [mTutor, setMTutor] = useState("");
  const [busy, setBusy] = useState(false), [ferr, setFerr] = useState("");
  const names = (ids: string[]) => ids.map((id) => d.students.find((s) => s.id === id)?.display_name || "Studente").join(", ");
  const today = new Date().toISOString().slice(0, 10);
  useEffect(() => { // orari suggeriti dal motore: tutti i vincoli di tutor e studenti
    if (!fix) return;
    setOpts(null); setPick(null);
    const q = new URLSearchParams(); if (mode) q.set("mode", mode); if (tutor) q.set("tutor_id", tutor); if (from) q.set("from", from);
    api<RecOpts>(`/recovery-obligations/${fix.id}/options/?${q}`).then((r) => { setOpts(r); if (!mode && r.mode) setMode(r.mode); }).catch((e) => { setOpts({ options: [] }); setFerr(human(e).text); });
  }, [fix?.id, mode, tutor, from]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!rows) return <Skeleton rows={3} />;
  const open = (o: Ob) => { setFix(o); setMode(""); setTutor(""); setFrom(""); setManual(false); setAt(o.recovery_periods[0] ? o.recovery_periods[0].start_date + "T15:00" : ""); setMTutor(""); setFerr(""); };
  async function schedule() {
    if (!fix) return;
    let start = pick?.start_at || "", tid = pick?.tutor_id || "", space = pick?.space_id || null;
    if (manual) {
      if (!at || !mTutor) { setFerr("Scegli giorno, ora e tutor."); return; }
      const local = new Date(at); const off = -local.getTimezoneOffset(), sign = off >= 0 ? "+" : "-", pad = (n: number) => String(Math.abs(n)).padStart(2, "0");
      start = `${at}:00${sign}${pad(Math.trunc(off / 60))}:${pad(off % 60)}`; tid = mTutor; space = null;
    } else if (!pick) { setFerr("Scegli uno degli orari proposti."); return; }
    setBusy(true); setFerr("");
    const m = mode || "IN_PERSON";
    try {
      await post(`/recovery-obligations/${fix.id}/makeup/`, { expected_version: fix.version, start_at: start, tutor_id: tid, mode: m, location: m === "ONLINE" ? "REMOTE" : "ON_SITE", space_id: m === "ONLINE" ? null : space, video_id: null, reason: "Recupero fissato dal centro" });
      toast("Recupero fissato: famiglia e tutor ricevono la notifica"); setFix(null); await load();
    } catch (e) { const h = human(e); setFerr(h.code === "RECOVERY_PAST_DUE" ? "Il recupero va fatto entro la fine dell’anno scolastico." : h.text); } finally { setBusy(false); }
  }
  return <>
    {err && <Notice kind="bad" action={<Btn kind="sm" onClick={load}>Riprova</Btn>}>{err}</Notice>}
    
    {!rows.length && !err ? <Empty title="Nessun recupero da fissare" /> :
      <div className="list-wrap"><table className="list"><thead><tr><th scope="col">Per chi</th><th scope="col">Lezione persa</th><th scope="col" className="hide-m">Motivo</th><th scope="col">Entro</th><th scope="col"><span className="sr">Azioni</span></th></tr></thead>
        <tbody>{rows.map((o) => { const soon = o.due_by && o.due_by <= new Date(Date.now() + 21 * 864e5).toISOString().slice(0, 10); return <tr key={o.id}>
          <td>{names(o.participants)}<div className="muted">{o.minutes_remaining} min</div></td>
          <td>{when(o.origin_start_at)}</td>
          <td className="hide-m">{CAUSE[o.cause] || o.cause}</td>
          <td>{o.due_by ? <Tag tone={soon ? "amber" : "plain"}>{day(o.due_by)}</Tag> : <span className="muted">Anno non configurato</span>}{o.recovery_periods[0] && <div className="muted">Periodo recuperi: {day(o.recovery_periods[0].start_date)}</div>}</td>
          <td style={{ whiteSpace: "nowrap" }}><Btn kind="sm" onClick={() => open(o)}>Fissa</Btn> <Btn kind="sm" onClick={() => setWaive(o)}>Rinuncia</Btn></td>
        </tr>; })}</tbody></table></div>}
    <Modal open={!!fix} onClose={() => setFix(null)} labelledBy="fx-title" width={680}><div className="modal-body">
      <h2 id="fx-title">Fissa il recupero</h2>
      {fix && <p className="lead">{names(fix.participants)} · {fix.minutes_remaining} min · lezione persa {when(fix.origin_start_at)}{fix.due_by ? ` · entro il ${day(fix.due_by)}` : ""}</p>}
      <div className="grid2">
        <Field label="Modalità"><SegCtl label="Modalità" value={mode || "IN_PERSON"} options={[["IN_PERSON", MODE.IN_PERSON], ["ONLINE", MODE.ONLINE]]} onChange={setMode} /></Field>
        <Field label="Tutor" id="fx-tf"><select id="fx-tf" className="inp" value={tutor} onChange={(e) => setTutor(e.target.value)}><option value="">Il tutor della lezione o un altro competente</option>{d.tutors.map((t) => <option key={t.id} value={t.id}>Solo {t.display_name}</option>)}</select></Field>
      </div>
      {fix?.recovery_periods.length ? <div className="toolbar sp-periods"><span className="lbl">Cerca da</span>
        <button type="button" className={"pill-btn sm" + (!from ? " on" : "")} aria-pressed={!from} onClick={() => setFrom("")}>Oggi</button>
        {fix.recovery_periods.slice(0, 3).map((p) => <button key={p.start_date} type="button" className={"pill-btn sm" + (from === p.start_date ? " on" : "")} aria-pressed={from === p.start_date} onClick={() => setFrom(p.start_date)}>{p.label || "Periodo recuperi"} ({day(p.start_date)})</button>)}
      </div> : null}
      {!manual && <>
        <span className="lbl sp-lbl">Orari proposti dal motore{opts?.date_from ? ` · dal ${day(opts.date_from)} al ${day(opts.date_to || opts.date_from)}` : ""}</span>
        
        <SlotPicker slots={opts ? opts.options : null} value={pick ? slotKey(pick) : ""} onPick={setPick} empty={opts?.message || "Nessun orario libero per tutti nel periodo: prova l’altra modalità, un altro tutor o un periodo successivo."} />
      </>}
      <p className="fine"><button type="button" className="linklike" onClick={() => setManual(!manual)}>{manual ? "Torna agli orari proposti" : "Scegli un orario a mano"}</button></p>
      {manual && <div className="grid2">
        <Field label="Giorno e ora" id="fx-at"><Input id="fx-at" type="datetime-local" min={today + "T00:00"} max={fix?.due_by ? fix.due_by + "T23:59" : undefined} value={at} onChange={(e) => setAt(e.target.value)} /></Field>
        <Field label="Tutor" id="fx-tutor"><select id="fx-tutor" className="inp" value={mTutor} onChange={(e) => setMTutor(e.target.value)}><option value="">Scegli…</option>{d.tutors.map((t) => <option key={t.id} value={t.id}>{t.display_name}</option>)}</select></Field>
      </div>}
      {ferr && <Notice kind="bad">{ferr}</Notice>}
    </div><div className="modal-foot"><button type="button" className="pill-btn ghost" onClick={() => setFix(null)}>Annulla</button><Btn kind="primary" disabled={busy || (!manual && !pick)} onClick={schedule}>{busy ? "Controllo…" : "Fissa il recupero"}</Btn></div></Modal>
    <ReasonModal open={!!waive} onClose={() => setWaive(null)} title="Rinuncia al recupero" confirm="Conferma la rinuncia" initial="La famiglia rinuncia al recupero"
      onConfirm={async (reason) => { await post(`/recovery-obligations/${waive!.id}/waive/`, { expected_version: waive!.version, reason }).catch(async (e) => { await load(); throw e; }); toast("Recupero chiuso"); await load(); }} />
  </>;
}

function Conflitti() {
  const toast = useToast(); const { rows, err, load } = useList<Case>("/conflict-cases/?state=OPEN");
  const [act, setAct] = useState<Case | null>(null), [res, setRes] = useState("CANCEL"), [recover, setRecover] = useState(true), [late, setLate] = useState(false), [busy, setBusy] = useState(false);
  if (!rows) return <Skeleton rows={3} />;
  const cause = (c: Case) => c.kind === "TUTOR_ABSENCE" ? "TUTOR_ABSENCE" : c.kind === "STUDENT_ABSENCE" ? "STUDENT_ABSENCE" : c.kind === "CLOSURE" ? "CLOSURE" : "CENTER_CANCELLATION";
  return <>
    <div className="controls" style={{ marginBottom: 10 }}><Btn kind="sm" disabled={busy} onClick={async () => { setBusy(true); try { const r = await post("/conflict-cases/detect/", {}); toast(r?.opened ? plural(r.opened, "conflitto trovato", "conflitti trovati") : "Controllo completato"); await load(); } catch (e) { toast(human(e).text); } finally { setBusy(false); } }}>{busy ? "Controllo…" : "Cerca conflitti"}</Btn></div>
    {err && <Notice kind="bad" action={<Btn kind="sm" onClick={load}>Riprova</Btn>}>{err}</Notice>}
    {!rows.length && !err ? <Empty title="Nessun conflitto aperto" /> :
      <div className="list-wrap"><table className="list"><thead><tr><th scope="col">Conflitto</th><th scope="col">Settimana</th><th scope="col"><span className="sr">Azioni</span></th></tr></thead>
        <tbody>{rows.map((c) => <tr key={c.id}><td><b style={{ fontWeight: 500 }}>{CASE[c.kind] || c.kind}</b>{c.kind === "TUTOR_ABSENCE" && <div className="muted">Cerca un sostituto abilitato dall’Agenda; se non c’è, annulla con recupero.</div>}</td>
          <td>{day(c.week_start)}</td>
          <td>{c.lesson_id && <Btn kind="sm" onClick={() => { setAct(c); setRes("CANCEL"); setRecover(true); setLate(false); }}>Risolvi</Btn>}</td></tr>)}</tbody></table></div>}
    <ReasonModal open={!!act} onClose={() => setAct(null)} title="Risolvi il conflitto" confirm="Applica" initial={act ? `${CASE[act.kind] || "Conflitto"}: deciso dal centro` : ""}
      onConfirm={async (reason) => { const c = act!; await post(`/conflict-cases/${c.id}/resolve/`, { expected_version: c.version, resolution: res, reason, ...(res === "CANCEL" && recover ? { recovery_cause: cause(c), grant_late_notice: late } : {}) }).catch(async (e) => { await load(); if (human(e).code === "LATE_NOTICE") throw new Error("Avviso arrivato con meno di 24 ore: spunta «Concedi comunque il recupero» per concederlo."); throw e; }); toast("Conflitto risolto"); await load(); }}>
      <SegCtl label="Decisione" value={res} options={[["CANCEL", "Annulla la lezione"], ["CONFIRM", "Conferma com’è"]]} onChange={setRes} />
      {res === "CANCEL" && <div style={{ margin: "10px 0" }}><Check checked={recover} onChange={setRecover}>Crea il recupero</Check>{recover && act?.kind === "STUDENT_ABSENCE" && <Check checked={late} onChange={setLate}>Concedi comunque il recupero se l’avviso è arrivato con meno di 24 ore</Check>}</div>}
    </ReasonModal>
  </>;
}

const DSTATUS: Record<string, string> = { PENDING: "In coda", SENDING: "In invio", SENT: "Inviati", DELIVERED: "Consegnati", SKIPPED: "Non necessari", DEAD: "Falliti", AMBIGUOUS: "Esito incerto" };
function Invii() {
  const toast = useToast(); const [st, setSt] = useState<Status | null>(null), [err, setErr] = useState(""); const { rows, load } = useList<Dl>("/communications/deliveries");
  const [act, setAct] = useState<{ row: Dl; res: "RETRY" | "ABANDON" | "MARK_SENT" } | null>(null);
  const reload = () => { api<Status>("/communications/status").then(setSt).catch((e) => setErr(human(e).text)); load(); };
  useEffect(reload, []);
  if (!st && !err) return <Skeleton rows={3} />;
  const portal = st?.counts?.IN_APP || {};
  return <>
    {err && <Notice kind="bad">{err}</Notice>}
    
    {st && <div className="stats">
      <div className="stat"><small>Avvisi nel portale</small><b>{Object.values(portal).reduce((a, b) => a + b, 0)}</b></div>
      <div className="stat"><small>Falliti</small><b>{st.dead_letter}</b></div>
      <div className="stat"><small>Esito incerto</small><b>{st.ambiguous}</b></div>
      <div className="stat"><small>In coda da</small><b>{st.oldest_pending_seconds == null ? "—" : `${Math.round(st.oldest_pending_seconds / 60)} min`}</b></div>
    </div>}
    {!rows ? <Skeleton rows={2} /> : !rows.length ? <Empty title="Nessun invio da controllare" /> :
      <div className="list-wrap"><table className="list"><thead><tr><th scope="col">Messaggio</th><th scope="col">Stato</th><th scope="col" className="hide-m">Tentativi</th><th scope="col"><span className="sr">Azioni</span></th></tr></thead>
        <tbody>{rows.map((r) => <tr key={r.id}><td>{r.event_type}<div className="muted">{r.channel === "EMAIL" ? "Email" : "Portale"} · {when(r.created_at)}</div></td><td><Tag tone="amber">{DSTATUS[r.status] || r.status}</Tag>{r.error && <div className="muted">{r.error}</div>}</td><td className="hide-m">{r.attempts}</td>
          <td style={{ whiteSpace: "nowrap" }}><Btn kind="sm" onClick={() => setAct({ row: r, res: "RETRY" })}>Riprova</Btn> {r.status === "AMBIGUOUS" && <Btn kind="sm" onClick={() => setAct({ row: r, res: "MARK_SENT" })}>È arrivato</Btn>} <Btn kind="sm" onClick={() => setAct({ row: r, res: "ABANDON" })}>Abbandona</Btn></td></tr>)}</tbody></table></div>}
    <ReasonModal open={!!act} onClose={() => setAct(null)} title={act?.res === "RETRY" ? "Riprova l’invio" : act?.res === "MARK_SENT" ? "Segna come arrivato" : "Abbandona l’invio"} confirm="Conferma"
      initial={act?.res === "RETRY" ? "Nuovo tentativo dopo verifica" : act?.res === "MARK_SENT" ? "Il destinatario conferma di averlo ricevuto" : "Comunicato per altra via"}
      onConfirm={async (reason) => { await api(`/communications/deliveries/${act!.row.id}/resolve`, { method: "POST", body: JSON.stringify({ resolution: act!.res, reason }) }); toast("Fatto"); reload(); }} />
  </>;
}

const TABS: [string, string][] = [["richieste", "Richieste"], ["recuperi", "Recuperi"], ["conflitti", "Conflitti"], ["invii", "Comunicazioni"]];
export default function Operativita() {
  const r = useRoute(); const tab = TABS.some(([k]) => k === r.q.get("tab")) ? r.q.get("tab")! : "richieste";
  return <section className="module" aria-labelledby="h-op">
    <PageHead id="h-op" title="Da gestire" />
    <div className="seg-scroll"><SegCtl label="Coda" value={tab} options={TABS} onChange={(v) => setQuery((q) => q.set("tab", v))} /></div>
    <div style={{ marginTop: 14 }}>{tab === "richieste" ? <Richieste /> : tab === "recuperi" ? <Recuperi /> : tab === "conflitti" ? <Conflitti /> : <Invii />}</div>
  </section>;
}
