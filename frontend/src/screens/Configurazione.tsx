/** P2 «Vincoli e configurazione»: anno scolastico, orari del centro (griglia), chiusure, aule, approvazione disponibilità. */
import { FormEvent, ReactNode, useEffect, useMemo, useState } from "react";
import { api, list } from "../api";
import { AdvancedConfig } from "./Proposte";
import { useData } from "../app/data";
import { TECH_ADMIN } from "../env";
import { ConfigForm, F, missing, Refs, SCHEMA } from "./configForms";
import { Btn, Empty, Notice, PageHead, Skeleton, Tag } from "../ui/core";
import { Check, Field, Input, SegCtl } from "../ui/controls";
import { Modal, useToast } from "../ui/layers";
import { ErrorState } from "../ui/states";
import { setQuery, useRoute } from "../ui/route";
import { Slot, SlotPlanner } from "../ui/WeekPlanner";
import { send, useList, writeError } from "./registry";

type Period = { id: string; kind: string; kind_label: string; label: string; start_date: string; end_date: string; closes_center: boolean; version: number };
type Year = { id: string; name: string; start_date: string; end_date: string; active: boolean; version: number; periods: Period[] };
type Window = { id: string; mode: string; location: string; weekday: number; start_time: string; end_time: string; period_start: string; period_end: string; resource: string | null };
type Closure = { id: string; start_at: string; end_at: string; mode: string; resource: string | null; reason: string };
type Resource = { id: string; name: string; kind: string; student_capacity: number | null; active: boolean; version: number };
type Rule = { id: string; tutor: string | null; student: string | null; weekday: number; start_time: string; end_time: string; period_start: string; period_end: string; mode: string; status: string };

export const KINDS: [string, string][] = [["START", "Inizio lezioni"], ["CHRISTMAS", "Pausa natalizia"], ["EASTER", "Pausa pasquale"], ["SUMMER", "Pausa estiva"], ["BREAK", "Altra pausa"], ["RECOVERY", "Periodo per i recuperi"]];
const BREAKS = ["CHRISTMAS", "EASTER", "SUMMER", "BREAK"];
const WD = ["Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom"];
const it = (d: string) => new Date(d + (d.length === 10 ? "T12:00:00" : "")).toLocaleDateString("it-IT", { day: "numeric", month: "short", year: "numeric" });
const dt = (d: string) => new Date(d).toLocaleString("it-IT", { dateStyle: "medium", timeStyle: "short" });
const toMin = (t: string) => +t.slice(0, 2) * 60 + +t.slice(3, 5);
type Tab = "anno" | "orari" | "chiusure" | "aule" | "approva" | "regole" | "eccezioni" | "dichiarazioni" | "avanzate";

export default function Configurazione() {
  const r = useRoute(), want = (r.q.get("tab") || "anno") as Tab, tab: Tab = TECH_ADMIN || want === "aule" ? want : "anno";
  return <section className="module planner" aria-labelledby="h-cfg">
    <PageHead id="h-cfg" title="Anno scolastico e aule" lead="Le date dell’anno (le pause diventano chiusure automatiche) e le aule disponibili per le lezioni in presenza. Orari di apertura e ferie si impostano in «Orari e chiusure»." />
    <div className="toolbar" style={{ marginBottom: 12, overflowX: "auto" }}>
      <SegCtl<Tab> label="Sezione" value={tab} onChange={(v) => setQuery((x) => x.set("tab", v))} options={TECH_ADMIN ? [["anno", "Anno scolastico"], ["aule", "Aule"], ["orari", "Finestre motore settimanale"], ["chiusure", "Chiusure (tecnico)"], ["approva", "Da approvare"], ["eccezioni", "Eccezioni"], ["dichiarazioni", "Dichiarazioni"], ["regole", "Regole di pianificazione"], ["avanzate", "Avanzate"]] : [["anno", "Anno scolastico"], ["aule", "Aule"]]} />
    </div>
    {tab === "anno" && <Anno />}{tab === "orari" && <Orari />}{tab === "chiusure" && <Chiusure />}{tab === "aule" && <Aule />}{tab === "approva" && <Approva />}{tab in TABS && <ConfigTab key={tab} {...TABS[tab]} />}{tab === "avanzate" && <AdvancedConfig />}
  </section>;
}


function Dialog({ id, title, onClose, onSubmit, children, foot }: { id: string; title: string; onClose: () => void; onSubmit: (e: FormEvent) => void; children: ReactNode; foot: ReactNode }) {
  return <Modal open onClose={onClose} labelledBy={id}><form onSubmit={onSubmit}><div className="modal-body"><h2 id={id}>{title}</h2>{children}</div><div className="modal-foot">{foot}</div></form></Modal>;
}

/** Effetto del periodo; su mobile la colonna «Effetto» è nascosta e il tag compare sotto il nome. */
const effect = (p: Period) => p.closes_center ? <Tag tone="amber">Niente lezioni</Tag> : p.kind === "RECOVERY" ? <Tag tone="blue">Recuperi</Tag> : <Tag tone="green">Lezioni</Tag>;

function Anno() {
  const years = useList<Year>("/planning/school-years"), toast = useToast();
  const [form, setForm] = useState<null | { kind: "year"; year?: Year } | { kind: "period"; year: Year; period?: Period }>(null);
  if (years.error) return <ErrorState error={years.error} onRetry={years.reload} />;
  if (!years.data) return <Skeleton />;
  return <>
    <div className="toolbar" style={{ marginBottom: 12 }}><Btn kind="primary" isle="plus" onClick={() => setForm({ kind: "year" })}>Nuovo anno scolastico</Btn></div>
    {!years.data.length ? <Empty title="Nessun anno scolastico">Crea l’anno: le sue date diventano il periodo di default di orari e disponibilità.</Empty>
      : years.data.map((y) => <div className="card" key={y.id} style={{ marginBottom: 12 }}>
        <h3 style={{ marginTop: 0 }}>{y.name} {!y.active && <Tag>Non attivo</Tag>}</h3>
        <p className="muted">{it(y.start_date)} – {it(y.end_date)}</p>
        <div className="toolbar"><Btn onClick={() => setForm({ kind: "year", year: y })}>Modifica anno</Btn><Btn isle="plus" onClick={() => setForm({ kind: "period", year: y })}>Aggiungi periodo</Btn></div>
        {y.periods.length ? <table className="list" style={{ marginTop: 8 }}><thead><tr><th scope="col">Periodo</th><th scope="col">Date</th><th scope="col" className="hide-m">Effetto</th><th scope="col"><span className="sr">Azioni</span></th></tr></thead>
          <tbody>{y.periods.map((p) => <tr key={p.id}>
            <td><b>{p.kind_label}</b>{p.label && <><br /><small className="muted">{p.label}</small></>}<span className="only-m"><br />{effect(p)}</span></td>
            <td><small>{it(p.start_date)} – {it(p.end_date)}</small></td>
            <td className="hide-m">{effect(p)}</td>
            <td><Btn onClick={() => setForm({ kind: "period", year: y, period: p })} aria-label={`Modifica ${p.kind_label}`}>Modifica</Btn></td></tr>)}</tbody></table>
          : <p className="muted">Nessun periodo. Aggiungi inizio lezioni, pause e periodi per i recuperi.</p>}
      </div>)}
    {form?.kind === "year" && <YearForm year={form.year} onClose={() => setForm(null)} onDone={() => { setForm(null); years.reload(); toast("Anno salvato"); }} />}
    {form?.kind === "period" && <PeriodForm year={form.year} period={form.period} onClose={() => setForm(null)} onDone={(m) => { setForm(null); years.reload(); toast(m); }} />}
  </>;
}

function YearForm({ year, onClose, onDone }: { year?: Year; onClose: () => void; onDone: () => void }) {
  const [v, setV] = useState({ name: year?.name || "", start_date: year?.start_date || "", end_date: year?.end_date || "", active: year?.active ?? true });
  const reason = year ? "Correzione anno scolastico" : "Nuovo anno scolastico", [err, setErr] = useState(""), [busy, setBusy] = useState(false);
  const submit = async (e: FormEvent) => {
    e.preventDefault(); setBusy(true); setErr("");
    try {
      if (year) await send("PATCH", `/planning/school-years/${year.id}`, { ...v, expected_version: year.version, reason });
      else await send("POST", "/planning/school-years", { name: v.name, start_date: v.start_date, end_date: v.end_date, reason });
      onDone();
    } catch (x) { setErr(writeError(x)); } finally { setBusy(false); }
  };
  return <Dialog id="m-year" title={year ? "Modifica anno scolastico" : "Nuovo anno scolastico"} onClose={onClose} onSubmit={submit} foot={<><Btn onClick={onClose}>Annulla</Btn><Btn kind="primary" type="submit" disabled={busy}>Salva</Btn></>}>
    {err && <Notice kind="bad">{err}</Notice>}
    <Field label="Nome" id="y-name" hint="Es. 2026/27"><Input id="y-name" value={v.name} onChange={(e) => setV({ ...v, name: e.target.value })} maxLength={40} required /></Field>
    <Field label="Inizio" id="y-start"><Input id="y-start" type="date" value={v.start_date} onChange={(e) => setV({ ...v, start_date: e.target.value })} required /></Field>
    <Field label="Fine" id="y-end"><Input id="y-end" type="date" value={v.end_date} onChange={(e) => setV({ ...v, end_date: e.target.value })} required /></Field>
    {year && <Check checked={v.active} onChange={(c) => setV({ ...v, active: c })}>Anno attivo</Check>}
  </Dialog>;
}

function PeriodForm({ year, period, onClose, onDone }: { year: Year; period?: Period; onClose: () => void; onDone: (m: string) => void }) {
  const [v, setV] = useState({ kind: period?.kind || "CHRISTMAS", label: period?.label || "", start_date: period?.start_date || "", end_date: period?.end_date || "" });
  const reason = "Calendario scolastico", [err, setErr] = useState(""), [busy, setBusy] = useState(false);
  const run = async (fn: () => Promise<unknown>, msg: string) => { setBusy(true); setErr(""); try { await fn(); onDone(msg); } catch (x) { setErr(writeError(x)); } finally { setBusy(false); } };
  const submit = (e: FormEvent) => { e.preventDefault(); run(() => period ? send("PATCH", `/planning/study-periods/${period.id}`, { ...v, expected_version: period.version, reason }) : send("POST", `/planning/school-years/${year.id}/periods`, { ...v, reason }), "Periodo salvato"); };
  return <Dialog id="m-period" title={period ? "Modifica periodo" : "Nuovo periodo"} onClose={onClose} onSubmit={submit} foot={<>
    {period && <Btn disabled={busy} onClick={() => { if (confirm("Eliminare questo periodo?")) run(() => send("POST", `/planning/study-periods/${period.id}/delete`, { expected_version: period.version, reason }), "Periodo eliminato"); }}>Elimina</Btn>}
    <Btn onClick={onClose}>Annulla</Btn><Btn kind="primary" type="submit" disabled={busy}>Salva</Btn></>}>
    {err && <Notice kind="bad">{err}</Notice>}
    <Field label="Tipo" id="p-kind"><select id="p-kind" className="input" value={v.kind} onChange={(e) => setV({ ...v, kind: e.target.value })}>{KINDS.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></Field>
    <Notice kind="info">{BREAKS.includes(v.kind) ? "Nelle pause non si pianificano lezioni: il centro risulta chiuso per tutte le modalità." : v.kind === "RECOVERY" ? "Nei periodi per i recuperi il centro resta aperto; serviranno per riprogrammare le lezioni perse." : "Segna l’inizio delle lezioni; non chiude il centro."}</Notice>
    <Field label="Descrizione" id="p-label" optional><Input id="p-label" value={v.label} onChange={(e) => setV({ ...v, label: e.target.value })} maxLength={80} /></Field>
    <Field label="Dal" id="p-start"><Input id="p-start" type="date" min={year.start_date} max={year.end_date} value={v.start_date} onChange={(e) => setV({ ...v, start_date: e.target.value })} required /></Field>
    <Field label="Al (incluso)" id="p-end"><Input id="p-end" type="date" min={v.start_date || year.start_date} max={year.end_date} value={v.end_date} onChange={(e) => setV({ ...v, end_date: e.target.value })} required /></Field>
  </Dialog>;
}

function useCurrentYear() {
  const [y, setY] = useState<Year | null | undefined>(undefined);
  useEffect(() => { api<Year | null>("/planning/school-years/current").then(setY).catch(() => setY(null)); }, []);
  return y;
}

function Orari() {
  const year = useCurrentYear(), windows = useList<Window>("/service-windows/"), toast = useToast();
  const [mode, setMode] = useState<"IN_PERSON" | "ONLINE">("IN_PERSON");
  const [slots, setSlots] = useState<Slot[] | null>(null), reason = "Orari del centro", [err, setErr] = useState(""), [busy, setBusy] = useState(false);
  const loc = mode === "IN_PERSON" ? "ON_SITE" : "REMOTE";
  const saved = useMemo(() => (windows.data || []).filter((w) => w.mode === mode && w.location === loc && !w.resource && year && w.period_start === year.start_date && w.period_end === year.end_date)
    .map((w) => ({ weekday: w.weekday, start: toMin(w.start_time), end: w.end_time.startsWith("23:59") ? 1440 : toMin(w.end_time) })), [windows.data, mode, loc, year]);
  useEffect(() => { setSlots(null); }, [mode]);
  if (windows.error) return <ErrorState error={windows.error} onRetry={windows.reload} />;
  if (year === undefined || !windows.data) return <Skeleton />;
  if (!year) return <Notice kind="warn" title="Prima crea l’anno scolastico">Gli orari valgono per l’anno in corso: configuralo nella sezione «Anno scolastico».</Notice>;
  const value = slots || saved, dirty = slots !== null;
  const other = windows.data.filter((w) => w.resource || w.period_start !== year.start_date || w.period_end !== year.end_date).length;
  const save = async () => {
    setBusy(true); setErr("");
    try { await send("POST", "/planning/service-windows/replace", { mode, period_start: year.start_date, period_end: year.end_date, slots: value, reason }); setSlots(null); windows.reload(); toast("Orari salvati"); }
    catch (x) { setErr(writeError(x)); } finally { setBusy(false); }
  };
  return <div className="card">
    <p className="muted">Aperture per l’anno {year.name} ({it(year.start_date)} – {it(year.end_date)}). Le pause dell’anno scolastico sono escluse automaticamente.</p>
    <SegCtl label="Modalità" value={mode} onChange={setMode} options={[["IN_PERSON", "In sede"], ["ONLINE", "Online"]]} />
    <div style={{ marginTop: 12 }}><SlotPlanner label={`Orari di apertura ${mode === "IN_PERSON" ? "in sede" : "online"}`} value={value} onChange={setSlots} /></div>
    {other > 0 && <Notice kind="info">Ci sono {other} aperture con periodo o risorsa diversi: restano invariate.</Notice>}
    {err && <Notice kind="bad">{err}</Notice>}
    {dirty && <div style={{ marginTop: 12 }}><div className="toolbar"><Btn onClick={() => setSlots(null)}>Annulla modifiche</Btn><Btn kind="primary" disabled={busy} onClick={save}>Salva orari</Btn></div></div>}
  </div>;
}

function Chiusure() {
  const closures = useList<Closure>("/closures/"), toast = useToast();
  const [open, setOpen] = useState(false), [v, setV] = useState({ start: "", end: "", mode: "ALL", reason: "" }), [err, setErr] = useState("");
  if (closures.error) return <ErrorState error={closures.error} onRetry={closures.reload} />;
  if (!closures.data) return <Skeleton />;
  const submit = async (e: FormEvent) => {
    e.preventDefault(); setErr("");
    const z = (d: string) => new Date(d).toISOString();
    try { await send("POST", "/closures/", { start_at: z(v.start), end_at: z(v.end), mode: v.mode, resource: null, reason: v.reason.trim() || "Chiusura" }); setOpen(false); closures.reload(); toast("Chiusura aggiunta"); } catch (x) { setErr(writeError(x)); }
  };
  const rows = [...closures.data].sort((a, b) => a.start_at.localeCompare(b.start_at));
  return <>
    <div className="toolbar" style={{ marginBottom: 12 }}><Btn kind="primary" isle="plus" onClick={() => setOpen(true)}>Chiusura straordinaria</Btn></div>
    <p className="muted">Le pause dell’anno scolastico compaiono qui automaticamente e si modificano dalla sezione «Anno scolastico».</p>
    {rows.length ? <table className="list"><thead><tr><th scope="col">Chiusura</th><th scope="col">Dal – al</th><th scope="col" className="hide-m">Vale per</th></tr></thead>
      <tbody>{rows.map((c) => <tr key={c.id}><td>{c.reason}</td><td><small>{dt(c.start_at)} – {dt(c.end_at)}</small></td><td className="hide-m">{c.mode === "ALL" ? "Tutte le modalità" : c.mode === "ONLINE" ? "Online" : "In sede"}</td></tr>)}</tbody></table>
      : <Empty title="Nessuna chiusura">Aggiungi le pause nell’anno scolastico o una chiusura straordinaria.</Empty>}
    {open && <Dialog id="m-clo" title="Chiusura straordinaria" onClose={() => setOpen(false)} onSubmit={submit} foot={<><Btn onClick={() => setOpen(false)}>Annulla</Btn><Btn kind="primary" type="submit">Aggiungi</Btn></>}>
      {err && <Notice kind="bad">{err}</Notice>}
      <Field label="Inizio" id="c-s"><Input id="c-s" type="datetime-local" value={v.start} onChange={(e) => setV({ ...v, start: e.target.value })} required /></Field>
      <Field label="Fine" id="c-e"><Input id="c-e" type="datetime-local" value={v.end} onChange={(e) => setV({ ...v, end: e.target.value })} required /></Field>
      <Field label="Vale per" id="c-m"><select id="c-m" className="input" value={v.mode} onChange={(e) => setV({ ...v, mode: e.target.value })}><option value="ALL">Tutte le modalità</option><option value="IN_PERSON">Solo in sede</option><option value="ONLINE">Solo online</option></select></Field>
      <Field label="Descrizione (facoltativa)" id="c-r" hint="Senza dati personali."><Input id="c-r" value={v.reason} onChange={(e) => setV({ ...v, reason: e.target.value })} maxLength={160} /></Field>
    </Dialog>}
  </>;
}

function Aule() {
  const res = useList<Resource>("/resources/"), toast = useToast();
  type Form = { id?: string; version?: number; name: string; kind: "SPACE" | "VIDEO_CHANNEL"; cap: string; active: boolean };
  const blank: Form = { name: "", kind: "SPACE", cap: "4", active: true };
  const [open, setOpen] = useState(false), [v, setV] = useState<Form>(blank), [err, setErr] = useState(""), [busy, setBusy] = useState(false);
  if (res.error) return <ErrorState error={res.error} onRetry={res.reload} />;
  if (!res.data) return <Skeleton />;
  const edit = (x?: Resource) => { setErr(""); setV(x ? { id: x.id, version: x.version, name: x.name, kind: x.kind as Form["kind"], cap: String(x.student_capacity ?? 4), active: x.active } : blank); setOpen(true); };
  const body = () => ({ name: v.name.trim(), kind: v.kind, student_capacity: v.kind === "SPACE" ? +v.cap : null, active: v.active });
  const submit = async (e: FormEvent) => {
    e.preventDefault(); setErr(""); setBusy(true);
    try {
      if (v.id) await send("PATCH", `/resources/${v.id}/`, { ...body(), expected_version: v.version });
      else await send("POST", "/resources/", body());
      setOpen(false); res.reload(); toast(v.id ? "Risorsa aggiornata" : "Risorsa aggiunta");
    } catch (x) { setErr(writeError(x)); } finally { setBusy(false); }
  };
  const toggle = async (x: Resource) => {
    try { await send("PATCH", `/resources/${x.id}/`, { active: !x.active, expected_version: x.version }); res.reload(); toast(x.active ? "Risorsa disattivata" : "Risorsa riattivata"); }
    catch (e) { toast(writeError(e)); }
  };
  return <>
    <div className="toolbar" style={{ marginBottom: 12 }}><Btn kind="primary" isle="plus" onClick={() => edit()}>Nuova aula o canale</Btn></div>
    <Notice kind="info">Le stanze delle videolezioni si creano da sole per ogni lezione online: i canali video servono solo a contare quante lezioni online possono svolgersi insieme.</Notice>
    {res.data.length ? <table className="list"><thead><tr><th scope="col">Nome</th><th scope="col">Tipo</th><th scope="col">Capienza</th><th scope="col" aria-label="Azioni"></th></tr></thead>
      <tbody>{res.data.map((x) => <tr key={x.id}><td>{x.name} {!x.active && <Tag>Non attiva</Tag>}</td><td>{x.kind === "SPACE" ? "Aula" : "Canale video"}</td><td className="num">{x.student_capacity ?? "—"}</td>
        <td><Btn kind="sm" onClick={() => edit(x)}>Modifica</Btn> <Btn kind="sm" onClick={() => toggle(x)}>{x.active ? "Disattiva" : "Riattiva"}</Btn></td></tr>)}</tbody></table>
      : <Empty title="Nessuna aula">Aggiungi le aule con la loro capienza e i canali video per le lezioni online.</Empty>}
    {open && <Dialog id="m-res" title={v.id ? "Modifica aula o canale" : "Nuova aula o canale"} onClose={() => setOpen(false)} onSubmit={submit} foot={<><Btn onClick={() => setOpen(false)}>Annulla</Btn><Btn kind="primary" type="submit" disabled={busy}>{v.id ? "Salva" : "Aggiungi"}</Btn></>}>
      {err && <Notice kind="bad">{err}</Notice>}
      <Field label="Nome" id="r-n"><Input id="r-n" value={v.name} onChange={(e) => setV({ ...v, name: e.target.value })} maxLength={80} required /></Field>
      <SegCtl label="Tipo" value={v.kind} onChange={(k) => setV({ ...v, kind: k })} options={[["SPACE", "Aula"], ["VIDEO_CHANNEL", "Canale video"]]} />
      {v.kind === "SPACE" && <Field label="Capienza (studenti)" id="r-c"><Input id="r-c" type="number" min={1} value={v.cap} onChange={(e) => setV({ ...v, cap: e.target.value })} required /></Field>}
    </Dialog>}
  </>;
}

function Approva() {
  const rules = useList<Rule>("/availability-rules/"), toast = useToast();
  const [sel, setSel] = useState<Set<string>>(new Set()), reason = "Disponibilità verificate", [err, setErr] = useState(""), [busy, setBusy] = useState(false);
  if (rules.error) return <ErrorState error={rules.error} onRetry={rules.reload} />;
  if (!rules.data) return <Skeleton />;
  const drafts = rules.data.filter((x) => x.status === "DRAFT");
  const toggle = (id: string) => setSel((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  const act = async (status: "APPROVED" | "REVOKED") => {
    setBusy(true); setErr("");
    try {
      const out = await send<{ changed: string[]; skipped: string[] }>("POST", "/availability/bulk-review", { ids: [...sel], status, reason });
      setSel(new Set()); rules.reload();
      toast(`${out.changed.length} ${status === "APPROVED" ? "approvate" : "respinte"}${out.skipped.length ? `, ${out.skipped.length} già gestite` : ""}`);
    } catch (x) { setErr(writeError(x)); } finally { setBusy(false); }
  };
  if (!drafts.length) return <Empty title="Niente da approvare">Le disponibilità inserite da famiglie e tutor compaiono qui finché il centro non le approva.</Empty>;
  return <div className="card">
    <Notice kind="info">Solo il centro approva: finché una disponibilità è in bozza, non viene usata per l’orario.</Notice>
    <Check checked={sel.size === drafts.length} onChange={(c) => setSel(c ? new Set(drafts.map((d) => d.id)) : new Set())}>Seleziona tutte ({drafts.length})</Check>
    <ul className="mini-list" style={{ listStyle: "none", padding: 0 }}>{drafts.map((x) => <li key={x.id}><Check checked={sel.has(x.id)} onChange={() => toggle(x.id)}>{`${x.tutor ? "Tutor" : "Studente"} · ${WD[x.weekday]} ${x.start_time.slice(0, 5)}–${x.end_time.slice(0, 5)} · ${x.mode === "ONLINE" ? "online" : "in sede"} · ${it(x.period_start)} – ${it(x.period_end)}`}</Check></li>)}</ul>
    {err && <Notice kind="bad">{err}</Notice>}
    <div className="toolbar"><Btn disabled={!sel.size || busy} onClick={() => act("REVOKED")}>Respingi selezionate</Btn><Btn kind="primary" disabled={!sel.size || busy} onClick={() => act("APPROVED")}>Approva selezionate ({sel.size})</Btn></div>
  </div>;
}

type Row = Record<string, unknown> & { id: string; version: number };
const TABS: Record<string, { kind: string; title: string; lead: string; empty: string }> = {
  eccezioni: { kind: "availability-exceptions", title: "eccezione", lead: "Variazioni puntuali: un giorno in più o in meno rispetto alle fasce settimanali (es. una gita, un esame).", empty: "Nessuna eccezione registrata." },
  dichiarazioni: { kind: "availability-declarations", title: "dichiarazione", lead: "Stato dei dati di ogni persona: completi, «nessuna disponibilità» o ancora incompleti. Serve alla verifica dei dati.", empty: "Nessuna dichiarazione: la verifica dei dati segnalerà chi non ha ancora dati completi." },
  regole: { kind: "planning-policies", title: "regola di pianificazione", lead: "Impostazioni con cui il sistema cerca l’orario: tempo di ricerca, requisiti di aule e canali, settimane parziali.", empty: "Nessuna regola: creane una prima di generare proposte." },
};

function ConfigTab({ kind, title, lead, empty }: { kind: string; title: string; lead: string; empty: string }) {
  const d = useData(), rows = useList<Row>(`/${kind}/`), toast = useToast(), fields: F[] = SCHEMA[kind] || [];
  const [subjects, setSubjects] = useState<{ id: string; name: string }[]>([]);
  useEffect(() => { list<{ id: string; name: string }>("/subjects/").then(setSubjects).catch(() => setSubjects([])); }, []);
  const refs: Refs = {
    tutor: d.tutors.map((t) => ({ id: t.id, label: t.display_name })),
    student: d.students.map((t) => ({ id: t.id, label: t.display_name })),
    subject: subjects.map((t) => ({ id: t.id, label: t.name })),
    resource: d.resources.map((t) => ({ id: t.id, label: t.name })),
  };
  const [open, setOpen] = useState<null | { row?: Row }>(null), [val, setVal] = useState<Record<string, unknown>>({}), [bad, setBad] = useState<string[]>([]), [err, setErr] = useState(""), [busy, setBusy] = useState(false);
  const show = (f: F, v: unknown): string => {
    if (v === null || v === undefined || v === "") return "—";
    if (f.t === "ref" && f.ref) return refs[f.ref].find((x) => x.id === v)?.label || "Non visibile";
    if (f.t === "enum") return f.opts?.find((o) => o[0] === v)?.[1] || String(v);
    if (f.t === "bool") return v ? "Sì" : "No";
    if (f.t === "dt") return dt(String(v));
    if (f.t === "date") return it(String(v));
    if (Array.isArray(v)) return v.join(", ") || "—";
    return String(v);
  };
  const start = (row?: Row) => {
    setVal(row ? Object.fromEntries(fields.map((f) => [f.k, row[f.k]])) : Object.fromEntries(fields.filter((f) => f.t === "bool").map((f) => [f.k, false])));
    setBad([]); setErr(""); setOpen({ row });
  };
  const save = async (e: FormEvent) => {
    e.preventDefault();
    const miss = missing(kind, val); setBad(miss);
    if (miss.length) { setErr("Completa i campi obbligatori evidenziati."); document.getElementById(`cf-${miss[0]}`)?.focus(); return; }
    setBusy(true); setErr("");
    try {
      const row = open?.row;
      await send(row ? "PATCH" : "POST", `/${kind}/${row ? row.id + "/" : ""}`, row ? { ...val, expected_version: row.version } : val);
      setOpen(null); rows.reload(); toast("Salvato. Verifica di nuovo i dati prima di generare.");
    } catch (x) { setErr(writeError(x)); } finally { setBusy(false); }
  };
  if (rows.error) return <ErrorState error={rows.error} onRetry={rows.reload} />;
  if (!rows.data) return <Skeleton />;
  const cols = fields.filter((f) => f.t !== "list").slice(0, 4);
  return <>
    <p className="muted">{lead}</p>
    <div className="toolbar" style={{ marginBottom: 12 }}><Btn kind="primary" isle="plus" onClick={() => start()}>{`Nuova ${title}`}</Btn></div>
    {rows.data.length ? <div className="list-wrap"><table className="list"><thead><tr>{cols.map((f, i) => <th scope="col" key={f.k} className={i > 1 ? "hide-m" : ""}>{f.label}</th>)}<th scope="col"><span className="sr">Azioni</span></th></tr></thead>
      <tbody>{rows.data.map((row) => <tr key={row.id}>{cols.map((f, i) => <td key={f.k} className={i > 1 ? "hide-m" : ""}>{show(f, row[f.k])}</td>)}
        <td><Btn onClick={() => start(row)} aria-label={`Modifica ${title} ${show(cols[0], row[cols[0].k])}`}>Modifica</Btn></td></tr>)}</tbody></table></div>
      : <Empty title="Ancora niente">{empty}</Empty>}
    {open && <Modal open onClose={() => setOpen(null)} labelledBy="m-cfg"><form onSubmit={save} noValidate>
      <div className="modal-body"><h2 id="m-cfg">{open.row ? `Modifica ${title}` : `Nuova ${title}`}</h2>
        <ConfigForm kind={kind} value={val} onChange={(nv) => { setVal(nv); setBad((b) => b.filter((k) => nv[k] === "" || nv[k] === null || nv[k] === undefined)); }} refs={refs} bad={bad} />
        {open.row && <p className="fine">Se qualcuno l’ha modificata nel frattempo, il salvataggio viene rifiutato: ricarica e riprova.</p>}
        {err && <Notice kind="bad">{err}</Notice>}</div>
      <div className="modal-foot"><Btn onClick={() => setOpen(null)}>Annulla</Btn><Btn kind="primary" type="submit" disabled={busy}>{busy ? "Salvataggio…" : "Salva"}</Btn></div>
    </form></Modal>}
  </>;
}
