/** v0.9.7 «Impegni»: genitori (per i figli), tutor (per sé) e centro (per chiunque) indicano
 *  quando NON si può fare lezione. Il pianificatore li rispetta; se deve sforare fino alla
 *  tolleranza (30 minuti) chiede conferma all'interessato. */
import { FormEvent, useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { dateLong, todayRome, WD_LONG, WD_SHORT } from "../format";
import { human } from "../messages";
import { Avatar, Btn, Empty, Icon, Notice, PageHead, Skeleton, Tag } from "../ui/core";
import { Check, Combo, ComboItem, DateField, Field, Input, SegCtl } from "../ui/controls";
import { Modal, useToast } from "../ui/layers";
import { setQuery, useRoute } from "../ui/route";
import { ErrorState } from "../ui/states";
import { covered, fmt, fmtEnd, PlanBlock, PlanTone, Slot, TimeSelect, toMin, WeekPlanner } from "../ui/WeekPlanner";
import { useData } from "../app/data";
import { useOverview } from "../portal/data";

export type Commitment = { id: string; student: string | null; tutor: string | null; label: string; kind: "WEEKLY" | "ONE_OFF"; weekday: number | null; date: string | null; start_time: string; end_time: string; valid_from: string | null; valid_until: string | null; version: number };
type Person = { id: string; kind: "student" | "tutor"; name: string; sub: string; canEdit: boolean };
const SUGGEST = ["Scuola", "Sport", "Musica", "Catechismo", "Lingue", "Lavoro", "Università", "Altro corso"];
const TONES: PlanTone[] = ["violet", "blue", "amber", "red"];
const toneOf = (label: string) => (label ? TONES[[...label.toLowerCase()].reduce((a, c) => a + c.charCodeAt(0), 0) % TONES.length] : "violet");
export const labelOf = (c: { label: string }) => c.label.trim() || "Impegno";

export default function Impegni() {
  const d = useData(), r = useRoute(), toast = useToast();
  const ov = useOverview(undefined, !d.center), o = ov.data;
  const people: Person[] = useMemo(() => d.center
    ? [...d.students.map((s) => ({ id: "student:" + s.id, kind: "student" as const, name: s.display_name, sub: "Studente", canEdit: true })),
      ...d.tutors.map((t) => ({ id: "tutor:" + t.id, kind: "tutor" as const, name: t.display_name, sub: "Tutor", canEdit: true }))]
    : [...(o?.tutor ? [{ id: "tutor:" + o.tutor.tutor_id, kind: "tutor" as const, name: o.tutor.display_name, sub: "Io (tutor)", canEdit: true }] : []),
      ...(o?.children || []).map((c) => ({ id: "student:" + c.student_id, kind: "student" as const, name: c.display_name, sub: c.permissions.can_manage_availability && !c.read_only ? "Figlio/a" : "Sola lettura", canEdit: c.permissions.can_manage_availability && !c.read_only }))],
  [d.center, d.students, d.tutors, o]);
  const chi = r.q.get("chi");
  const who = people.find((p) => p.id === chi) || (!d.center && people.length ? people[0] : null);
  const [rows, setRows] = useState<Commitment[] | null>(null), [err, setErr] = useState<unknown>(null);
  const [hours, setHours] = useState<{ weekday: number; start: number; end: number }[]>([]), [tol, setTol] = useState(30);
  const [form, setForm] = useState<{ row?: Commitment } | null>(null);
  useEffect(() => { api<{ opening_hours: { weekday: number; start: string; end: string }[]; tolerance_minutes: number }>("/planner/opening-hours").then((x) => { setHours(x.opening_hours.map((h) => ({ weekday: h.weekday, start: toMin(h.start), end: toMin(h.end) }))); setTol(x.tolerance_minutes); }).catch(() => undefined); }, []);
  const load = () => { if (!who) { setRows(null); return; } setErr(null); setRows(null); const [k, id] = who.id.split(":"); api<Commitment[]>(`/commitments?${k}=${id}`).then(setRows).catch(setErr); };
  useEffect(load, [who?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (r.q.get("nuova") === "1" && who?.canEdit) { setForm({}); setQuery((q) => q.delete("nuova")); } }, [r.q, who?.canEdit]);
  const today = todayRome();
  const weekly = (rows || []).filter((c) => c.kind === "WEEKLY" && (!c.valid_until || c.valid_until >= today));
  const once = (rows || []).filter((c) => c.kind === "ONE_OFF" && c.date! >= today).sort((a, b) => a.date!.localeCompare(b.date!));
  const blocks: PlanBlock[] = weekly.map((c) => ({ id: c.id, weekday: c.weekday!, start: toMin(c.start_time), end: toMin(c.end_time), label: labelOf(c), tone: toneOf(c.label), sub: c.valid_until ? `fino al ${dateLong(c.valid_until)}` : c.valid_from && c.valid_from > today ? `dal ${dateLong(c.valid_from)}` : undefined, locked: c.id.startsWith("tmp-") }));
  const free = hours.reduce((a, h) => a + h.end - h.start, 0), busy = hours.reduce((a, h) => a + covered(h.start, h.end, blocks.filter((b) => b.weekday === h.weekday)), 0);
  const lead = d.center ? "Gli impegni di studenti e tutor: il pianificatore programma le lezioni fuori da questi orari." : "Indica quando tu o i tuoi figli siete già impegnati (scuola, sport, lavoro…): il centro programmerà le lezioni negli altri momenti.";
  const body = (s: Slot) => ({ start_time: fmt(s.start), end_time: fmtEnd(s.end) });
  async function create(s: Slot) {
    if (!who || !rows) return;
    const [k, id] = who.id.split(":"), tmp = { id: "tmp-" + Date.now(), student: null, tutor: null, label: "", kind: "WEEKLY", weekday: s.weekday, date: null, start_time: fmt(s.start), end_time: fmtEnd(s.end), valid_from: null, valid_until: null, version: 0 } as Commitment;
    setRows([...rows, tmp]);
    try {
      const out = await api<Commitment[]>("/commitments", { method: "POST", body: JSON.stringify({ [k]: id, label: "", kind: "WEEKLY", weekdays: [s.weekday], ...body(s) }) });
      setRows((x) => [...(x || []).filter((c) => c.id !== tmp.id), ...out]);
      toast(`Impegno aggiunto: ${WD_LONG[s.weekday].toLowerCase()} ${fmt(s.start)}–${fmtEnd(s.end)}`, out[0] ? { action: "Dai un nome", onAction: () => setForm({ row: out[0] }) } : undefined);
    } catch (x) { toast(human(x).text); load(); }
  }
  async function move(cid: string, s: Slot) {
    if (!rows) return;
    setRows(rows.map((c) => (c.id === cid ? { ...c, weekday: s.weekday, ...body(s) } : c)));
    try { await api(`/commitments/${cid}`, { method: "PATCH", body: JSON.stringify({ weekday: s.weekday, ...body(s) }) }); }
    catch (x) { toast(human(x).text); load(); }
  }
  return <section className="module planner" aria-labelledby="h-imp">
    <PageHead id="h-imp" title="Impegni" lead={lead}>{who?.canEdit && <Btn kind="primary" isle="plus" onClick={() => setForm({})}>Aggiungi impegno</Btn>}</PageHead>
    {d.center ? <div className="card" style={{ marginBottom: 14 }}><Field label="Persona" id="imp-who"><Combo id="imp-who" value={who ? { id: who.id, label: who.name, sub: who.sub } : null} items={people.map((p): ComboItem => ({ id: p.id, label: p.name, sub: p.sub }))} placeholder="Cerca uno studente o un tutor…" onPick={(x) => setQuery((q) => (x ? q.set("chi", x.id) : q.delete("chi")))} /></Field></div>
      : people.length > 1 && <div className="imp-people" role="tablist" aria-label="Persona">{people.map((p) => <button key={p.id} role="tab" aria-selected={p.id === who?.id} className={"imp-person" + (p.id === who?.id ? " on" : "")} onClick={() => setQuery((q) => q.set("chi", p.id))}><Avatar name={p.name} size={28} /><span><b>{p.name}</b><small>{p.sub}</small></span></button>)}</div>}
    {!who ? (d.center ? <Empty title="Scegli una persona">Vedrai la sua settimana tipo con gli impegni e potrai aggiungerne di nuovi trascinando sul calendario.</Empty> : ov.loading ? <Skeleton /> : <Empty title="Nessuna persona da gestire">Il centro non ha ancora collegato figli o profilo tutor al tuo account.</Empty>)
      : err ? <ErrorState error={err} onRetry={load} /> : !rows ? <Skeleton /> : <div className="imp-grid">
        <div className="card">
          <div className="oc-head"><span className="oc-ic violet"><Icon n="cal" /></span><div><h2>Settimana tipo · {who.name}</h2><p className="muted">{who.canEdit ? "Disegna gli impegni direttamente sul calendario: il nome è facoltativo." : "Impegni che si ripetono ogni settimana."}</p></div></div>
          <WeekPlanner label={`Impegni settimanali di ${who.name}`} blocks={blocks} bands={hours} editable={who.canEdit} newLabel="Impegno"
            noOverlap onBlocked={(m) => toast(m.replace("blocco", "impegno"))} onCreate={create} onChange={move} onPick={(b) => { const row = rows.find((c) => c.id === b.id); if (row && who.canEdit) setForm({ row }); }}
            emptyText={!who.canEdit ? "Nessun impegno settimanale: si considera libero quando il centro è aperto." : undefined} />
          <div className="imp-legend"><span><i className="lg" />Centro aperto</span><span><i className="lg hatch" />Centro chiuso</span><span><i className="lg block" />Impegno</span>{free > 0 && <span className="muted">Libero per lezioni: {Math.round((free - busy) / 60)} h su {Math.round(free / 60)} h di apertura</span>}</div>
        </div>
        <div className="imp-side">
          <div className="card">
            <div className="oc-head"><span className="oc-ic amber"><Icon n="clock" /></span><div><h2>Impegni occasionali</h2><p className="muted">Un giorno preciso: gita, visita, esame…</p></div></div>
            {once.length ? <ul className="oc-list">{once.map((c) => <li key={c.id}>
              <div className="oc-date"><b>{+c.date!.slice(8)}</b><small>{WD_SHORT[(new Date(c.date + "T12:00:00Z").getUTCDay() + 6) % 7]}</small></div>
              <div className="oc-what"><b>{labelOf(c)}</b><small>{dateLong(c.date!)}, {c.start_time === "00:00" && c.end_time === "24:00" ? "tutto il giorno" : `${c.start_time}–${c.end_time}`}</small></div>
              {who.canEdit && <button type="button" className="pill-btn sm ghost" onClick={() => setForm({ row: c })}>Modifica</button>}
            </li>)}</ul> : <Empty title="Nessun impegno occasionale" />}
            {who.canEdit && <Btn kind="sm" icon="plus" onClick={() => setForm({ row: { kind: "ONE_OFF" } as Commitment })}>Aggiungi un giorno</Btn>}
          </div>
          <Notice kind="info" title="Come vengono usati">Le lezioni restano fuori dagli impegni. Solo se non c’è altra soluzione il centro può proporre uno sforamento fino a {tol} minuti: in quel caso ricevi un’email e una notifica e decidi tu se accettare.</Notice>
          {!who.canEdit && <Tag>La delega non consente di modificare gli impegni</Tag>}
        </div>
      </div>}
    {form && who && <CommitmentForm who={who} row={form.row} rows={rows || []} onClose={() => setForm(null)} onDone={(m) => { setForm(null); toast(m); load(); }} />}
  </section>;
}

/** Primo impegno (stesso tipo, stessa persona) che si sovrappone a quello indicato. */
export function overlapping(rows: Commitment[], c: { id?: string; kind: Commitment["kind"]; weekday?: number; date?: string; a: number; b: number; from?: string | null; until?: string | null }) {
  return rows.find((x) => x.id !== c.id && !x.id.startsWith("tmp-") && x.kind === c.kind && toMin(x.start_time) < c.b && c.a < toMin(x.end_time)
    && (c.kind === "WEEKLY" ? x.weekday === c.weekday && (!c.until || !x.valid_from || x.valid_from <= c.until) && (!c.from || !x.valid_until || x.valid_until >= c.from) : x.date === c.date));
}

function CommitmentForm({ who, row, rows, onClose, onDone }: { who: Person; row?: Commitment; rows: Commitment[]; onClose: () => void; onDone: (m: string) => void }) {
  const editing = !!row?.id, today = todayRome();
  const [v, setV] = useState(() => ({
    label: row?.label || "", kind: (row?.kind || "WEEKLY") as "WEEKLY" | "ONE_OFF",
    days: row?.weekday != null ? [row.weekday] : [0, 1, 2, 3, 4], date: row?.date || today,
    a: row?.start_time ? toMin(row.start_time) : 8 * 60, b: row?.end_time ? toMin(row.end_time) : 13 * 60 + 30,
    allDay: row?.start_time === "00:00" && row?.end_time === "24:00", limited: !!(row?.valid_from || row?.valid_until),
    from: row?.valid_from || today, until: row?.valid_until || "",
  }));
  const [err, setErr] = useState(""), [busy, setBusy] = useState(false), [ask, setAsk] = useState(false);
  const toggle = (d: number) => setV({ ...v, days: editing ? [d] : v.days.includes(d) ? v.days.filter((x) => x !== d) : [...v.days, d].sort() });
  async function submit(e: FormEvent) {
    e.preventDefault();
    if (v.kind === "WEEKLY" && !v.days.length) { setErr("Scegli almeno un giorno."); return; }
    const a = v.kind === "ONE_OFF" && v.allDay ? 0 : v.a, b = v.kind === "ONE_OFF" && v.allDay ? 1440 : v.b;
    if (b <= a) { setErr("L’orario di fine deve essere dopo l’inizio."); return; }
    const from = v.kind === "WEEKLY" && v.limited ? v.from : null, until = v.kind === "WEEKLY" && v.limited && v.until ? v.until : null;
    const hit = v.kind === "WEEKLY" ? v.days.map((wd) => overlapping(rows, { id: row?.id, kind: "WEEKLY", weekday: wd, a, b, from, until })).find(Boolean)
      : overlapping(rows, { id: row?.id, kind: "ONE_OFF", date: v.date, a, b });
    if (hit) { setErr(`Si sovrappone a «${labelOf(hit)}» (${hit.kind === "WEEKLY" ? WD_LONG[hit.weekday!].toLowerCase() : dateLong(hit.date!)} ${hit.start_time.slice(0, 5)}–${hit.end_time.slice(0, 5)}): cambia orario o modifica quell’impegno.`); return; }
    const [k, id] = who.id.split(":");
    const base = { label: v.label.trim(), kind: v.kind, start_time: fmt(a), end_time: b === 1440 ? "24:00" : fmt(b),
      ...(v.kind === "WEEKLY" ? { valid_from: v.limited ? v.from : null, valid_until: v.limited && v.until ? v.until : null } : { date: v.date }) };
    setBusy(true); setErr("");
    try {
      if (editing) await api(`/commitments/${row!.id}`, { method: "PATCH", body: JSON.stringify({ ...base, ...(v.kind === "WEEKLY" ? { weekday: v.days[0] } : {}) }) });
      else await api("/commitments", { method: "POST", body: JSON.stringify({ [k]: id, ...base, ...(v.kind === "WEEKLY" ? { weekdays: v.days } : {}) }) });
      onDone(editing ? "Impegno aggiornato" : v.kind === "WEEKLY" && v.days.length > 1 ? `Impegno aggiunto per ${v.days.length} giorni` : "Impegno aggiunto");
    } catch (x) { setErr(human(x).text); } finally { setBusy(false); }
  }
  async function remove() {
    setBusy(true);
    try { await api(`/commitments/${row!.id}`, { method: "DELETE" }); onDone("Impegno eliminato"); } catch (x) { setErr(human(x).text); setBusy(false); }
  }
  return <Modal open onClose={onClose} labelledBy="cm-t"><form onSubmit={submit} noValidate>
    <div className="modal-body">
      <h2 id="cm-t">{editing ? "Modifica impegno" : "Nuovo impegno"}</h2>
      <p className="lead">Per {who.name}. In questi orari il centro non programma lezioni.</p>
      <Field label="Nome" id="cm-l" optional><Input id="cm-l" value={v.label} maxLength={80} placeholder="Es. Scuola, Calcio, Pianoforte (puoi lasciarlo vuoto)" onChange={(e) => setV({ ...v, label: e.target.value })} /></Field>
      <div className="chips" role="group" aria-label="Suggerimenti">{SUGGEST.map((s) => <button key={s} type="button" className={"chip" + (v.label === s ? " on" : "")} onClick={() => setV({ ...v, label: v.label === s ? "" : s })}>{s}</button>)}</div>
      {!editing && <Field label="Si ripete?"><SegCtl label="Ripetizione" value={v.kind} onChange={(k) => setV({ ...v, kind: k })} options={[["WEEKLY", "Ogni settimana"], ["ONE_OFF", "Un giorno solo"]]} /></Field>}
      {v.kind === "WEEKLY" ? <Field label={editing ? "Giorno" : "Giorni"}><div className="day-pick" role="group" aria-label="Giorni">{WD_LONG.map((w, i) => <button key={w} type="button" aria-pressed={v.days.includes(i)} className={"day-btn" + (v.days.includes(i) ? " on" : "")} onClick={() => toggle(i)}>{w.slice(0, 3)}</button>)}</div></Field>
        : <Field label="Giorno" id="cm-d"><DateField id="cm-d" label="Giorno" value={v.date} min={today} onChange={(x) => setV({ ...v, date: x })} /></Field>}
      {v.kind === "ONE_OFF" && <Check checked={v.allDay} onChange={(x) => setV({ ...v, allDay: x })}>Tutto il giorno</Check>}
      {!(v.kind === "ONE_OFF" && v.allDay) && <div className="grid2" style={{ marginTop: 8 }}>
        <Field label="Dalle" id="cm-a"><TimeSelect id="cm-a" label="Dalle" value={v.a} onChange={(a) => setV({ ...v, a, b: v.b <= a ? Math.min(a + 60, 1440) : v.b })} /></Field>
        <Field label="Alle" id="cm-b"><TimeSelect id="cm-b" label="Alle" value={v.b} onChange={(b) => setV({ ...v, b })} /></Field>
      </div>}
      {v.kind === "WEEKLY" && <><Check checked={v.limited} onChange={(x) => setV({ ...v, limited: x })}>Solo per un periodo</Check>
        {v.limited && <div className="grid2" style={{ marginTop: 8 }}>
          <Field label="Dal" id="cm-f"><DateField id="cm-f" label="Dal" value={v.from} onChange={(x) => setV({ ...v, from: x })} /></Field>
          <Field label="Fino al" id="cm-u" optional><DateField id="cm-u" label="Fino al" value={v.until} min={v.from} onChange={(x) => setV({ ...v, until: x })} /></Field>
        </div>}</>}
      {err && <Notice kind="bad">{err}</Notice>}
    </div>
    <div className="modal-foot">
      {editing && (ask ? <Btn kind="danger" onClick={remove} disabled={busy}>Conferma eliminazione</Btn> : <Btn kind="ghost" onClick={() => setAsk(true)}>Elimina</Btn>)}
      <span style={{ flex: 1 }} />
      <Btn kind="ghost" onClick={onClose}>Annulla</Btn><Btn kind="primary" isle="check" type="submit" disabled={busy}>{busy ? "Salvataggio…" : "Salva"}</Btn>
    </div>
  </form></Modal>;
}
