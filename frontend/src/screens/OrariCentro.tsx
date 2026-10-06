/** v0.9.7 «Orari e chiusure»: l'unica configurazione che il centro deve mantenere per il
 *  pianificatore. Orari di apertura settimanali (vincolo rigido) e ferie/chiusure. */
import { FormEvent, useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { dateLong, todayRome, WD_LONG } from "../format";
import { human } from "../messages";
import { Btn, Empty, Icon, Notice, PageHead, Skeleton, Tag } from "../ui/core";
import { Check, DateField, Field, Input } from "../ui/controls";
import { Modal, useToast } from "../ui/layers";
import { ErrorState } from "../ui/states";
import { fmt, Slot, SlotPlanner, TimeSelect, toMin } from "../ui/WeekPlanner";

export type ClosureRow = { id: string; start_date: string; end_date: string; start_time: string | null; end_time: string | null; all_day: boolean; reason: string; source: "MANUAL" | "SCHOOL_YEAR"; mode: string };
export type Setup = { opening_hours: { weekday: number; start: string; end: string }[]; closures: ClosureRow[]; tolerance_minutes: number };

export const slotsOf = (s: Setup | null): Slot[] => (s?.opening_hours || []).map((o) => ({ weekday: o.weekday, start: toMin(o.start), end: toMin(o.end) }));
export function useSetup() {
  const [s, set] = useState<Setup | null>(null), [err, setErr] = useState<unknown>(null);
  const load = () => { setErr(null); api<Setup>("/planner/setup").then(set).catch(setErr); };
  useEffect(load, []);
  return { data: s, error: err, reload: load, set };
}

export default function OrariCentro() {
  const st = useSetup();
  return <section className="module planner" aria-labelledby="h-oc">
    <PageHead id="h-oc" title="Orari e chiusure" lead="Il pianificatore colloca le lezioni solo quando il centro è aperto: questi orari e le chiusure non vengono mai superati." />
    {st.error ? <ErrorState error={st.error} onRetry={st.reload} /> : !st.data ? <Skeleton /> : <div className="oc-grid">
      <Apertura setup={st.data} onSaved={st.set} />
      <Chiusure setup={st.data} reload={st.reload} />
    </div>}
  </section>;
}

function Apertura({ setup, onSaved }: { setup: Setup; onSaved: (s: Setup) => void }) {
  const toast = useToast();
  const saved = useMemo(() => slotsOf(setup), [setup]);
  const [edit, setEdit] = useState<Slot[] | null>(null), [busy, setBusy] = useState(false), [err, setErr] = useState("");
  const value = edit || saved;
  const days = WD_LONG.map((w, i) => ({ w, list: value.filter((s) => s.weekday === i).sort((a, b) => a.start - b.start) }));
  const total = value.reduce((a, s) => a + s.end - s.start, 0);
  const copyMonday = () => { const mon = value.filter((s) => s.weekday === 0); setEdit([...value.filter((s) => s.weekday === 0 || s.weekday > 4), ...[1, 2, 3, 4].flatMap((wd) => mon.map((s) => ({ ...s, weekday: wd })))]); };
  async function save() {
    setBusy(true); setErr("");
    try { const s = await api<Setup>("/planner/opening-hours", { method: "PUT", body: JSON.stringify({ slots: value }) }); onSaved(s); setEdit(null); toast("Orari di apertura salvati"); }
    catch (x) { setErr(human(x).text); } finally { setBusy(false); }
  }
  return <div className="card oc-card">
    <div className="oc-head"><span className="oc-ic green"><Icon n="clock" /></span><div><h2>Orari di apertura</h2><p className="muted">Trascina sul calendario le fasce in cui il centro è aperto; sposta o allunga una fascia trascinandola. Valgono ogni settimana, per tutte le lezioni.</p></div></div>
    <div className="oc-days" aria-label="Riepilogo orari">
      {days.map((d) => <div key={d.w} className={"oc-day" + (d.list.length ? "" : " off")}><b>{d.w.slice(0, 3)}</b><span>{d.list.length ? d.list.map((s) => `${fmt(s.start)}–${fmt(s.end)}`).join(", ") : "Chiuso"}</span></div>)}
    </div>
    <SlotPlanner label="Orari di apertura del centro" value={value} onChange={setEdit} from={7 * 60} to={22 * 60} />
    <div className="toolbar" style={{ marginTop: 12 }}>
      <Btn kind="sm ghost" onClick={copyMonday} disabled={!value.some((s) => s.weekday === 0)}>Copia il lunedì su mar–ven</Btn>
      <span className="muted" style={{ fontSize: 13 }}>{Math.floor(total / 60)} ore di apertura a settimana</span>
    </div>
    {err && <Notice kind="bad">{err}</Notice>}
    {edit && <div className="toolbar" style={{ marginTop: 12 }}><Btn onClick={() => setEdit(null)}>Annulla</Btn><Btn kind="primary" isle="check" disabled={busy} onClick={save}>{busy ? "Salvataggio…" : "Salva orari"}</Btn></div>}
  </div>;
}

function Chiusure({ setup, reload }: { setup: Setup; reload: () => void }) {
  const toast = useToast(), today = todayRome();
  const [open, setOpen] = useState(false), [del, setDel] = useState<ClosureRow | null>(null), [err, setErr] = useState("");
  const rows = setup.closures.filter((c) => c.end_date >= today);
  const past = setup.closures.length - rows.length;
  async function remove() {
    if (!del) return;
    try { await api(`/planner/closures/${del.id}`, { method: "DELETE" }); toast("Chiusura eliminata"); setDel(null); reload(); } catch (x) { setErr(human(x).text); }
  }
  return <div className="card oc-card">
    <div className="oc-head"><span className="oc-ic red"><Icon n="cal" /></span><div><h2>Ferie e chiusure</h2><p className="muted">Nei giorni chiusi non si programma nulla. Le pause dell’anno scolastico compaiono qui da sole.</p></div>
      <Btn kind="primary" isle="plus" onClick={() => setOpen(true)}>Aggiungi</Btn></div>
    {rows.length ? <ul className="oc-list">{rows.map((c) => <li key={c.id}>
      <div className="oc-date"><b>{+c.start_date.slice(8)}</b><small>{dateLong(c.start_date).split(" ")[1]?.slice(0, 3)}</small></div>
      <div className="oc-what"><b>{c.reason}</b><small>{c.start_date === c.end_date ? dateLong(c.start_date) : `${dateLong(c.start_date)} – ${dateLong(c.end_date)}`}{c.all_day ? ", tutto il giorno" : `, ${c.start_time}–${c.end_time}`}</small></div>
      {c.source === "SCHOOL_YEAR" ? <Tag tone="blue">Anno scolastico</Tag> : <button type="button" className="pill-btn sm ghost" onClick={() => setDel(c)} aria-label={`Elimina ${c.reason}`}><Icon n="x" />Elimina</button>}
    </li>)}</ul> : <Empty title="Nessuna chiusura in programma">Aggiungi ferie, ponti o chiusure straordinarie.</Empty>}
    {past > 0 && <p className="fine">{past} chiusure passate non mostrate.</p>}
    {err && <Notice kind="bad">{err}</Notice>}
    {open && <ClosureForm onClose={() => setOpen(false)} onDone={() => { setOpen(false); reload(); toast("Chiusura aggiunta: il pianificatore la rispetterà"); }} />}
    <Modal open={!!del} onClose={() => setDel(null)} labelledBy="cl-del"><div className="modal-body"><h2 id="cl-del">Eliminare la chiusura?</h2><p className="lead">{del?.reason}: il centro tornerà disponibile in quei giorni per i prossimi calendari. Le lezioni già pubblicate non cambiano.</p></div>
      <div className="modal-foot"><Btn kind="ghost" onClick={() => setDel(null)}>Annulla</Btn><Btn kind="danger" onClick={remove}>Elimina</Btn></div></Modal>
  </div>;
}

function ClosureForm({ onClose, onDone }: { onClose: () => void; onDone: () => void }) {
  const today = todayRome();
  const [v, setV] = useState({ from: today, to: today, allDay: true, a: 9 * 60, b: 13 * 60, reason: "" }), [err, setErr] = useState(""), [busy, setBusy] = useState(false);
  const presets = ["Ferie estive", "Vacanze di Natale", "Ponte", "Festività", "Chiusura straordinaria"];
  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!v.allDay && v.b <= v.a && v.from === v.to) { setErr("L’ora di fine deve essere dopo l’inizio."); return; }
    setBusy(true); setErr("");
    try {
      await api("/planner/closures", { method: "POST", body: JSON.stringify({ start_date: v.from, end_date: v.to, reason: v.reason.trim() || "Chiusura", ...(v.allDay ? {} : { start_time: fmt(v.a), end_time: fmt(v.b) }) }) });
      onDone();
    } catch (x) { setErr(human(x).text); } finally { setBusy(false); }
  }
  return <Modal open onClose={onClose} labelledBy="cl-new"><form onSubmit={submit} noValidate>
    <div className="modal-body">
      <h2 id="cl-new">Nuova chiusura</h2>
      <p className="lead">Il centro resta chiuso dal primo all’ultimo giorno compresi.</p>
      <div className="grid2">
        <Field label="Dal" id="cl-from"><DateField id="cl-from" label="Dal" value={v.from} onChange={(x) => setV({ ...v, from: x, to: v.to < x ? x : v.to })} /></Field>
        <Field label="Al" id="cl-to"><DateField id="cl-to" label="Al" value={v.to} min={v.from} onChange={(x) => setV({ ...v, to: x })} /></Field>
      </div>
      <Check checked={v.allDay} onChange={(x) => setV({ ...v, allDay: x })}>Tutto il giorno</Check>
      {!v.allDay && <div className="grid2" style={{ marginTop: 10 }}>
        <Field label="Dalle" id="cl-a"><TimeSelect id="cl-a" label="Dalle" value={v.a} onChange={(a) => setV({ ...v, a })} /></Field>
        <Field label="Alle" id="cl-b"><TimeSelect id="cl-b" label="Alle" value={v.b} onChange={(b) => setV({ ...v, b })} /></Field>
      </div>}
      <Field label="Descrizione (facoltativa)" id="cl-r" hint="Visibile solo al centro."><Input id="cl-r" value={v.reason} maxLength={160} placeholder="Es. Ferie estive" onChange={(e) => setV({ ...v, reason: e.target.value })} /></Field>
      <div className="chips" role="group" aria-label="Descrizioni frequenti">{presets.map((p) => <button key={p} type="button" className={"chip" + (v.reason === p ? " on" : "")} onClick={() => setV({ ...v, reason: p })}>{p}</button>)}</div>
      {err && <Notice kind="bad">{err}</Notice>}
    </div>
    <div className="modal-foot"><Btn kind="ghost" type="button" onClick={onClose}>Annulla</Btn><Btn kind="primary" isle="check" type="submit" disabled={busy}>{busy ? "Salvataggio…" : "Aggiungi chiusura"}</Btn></div>
  </form></Modal>;
}
