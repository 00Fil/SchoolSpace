import { useEffect, useRef, useState } from "react";
import { api, list } from "../api";
import { addDays, dayLabel, mondayOf, num, plural, todayRome, weekday } from "../format";
import { human } from "../messages";
import { Btn, Empty, Icon, Notice, PageHead, Skeleton, State, Tag, Tech } from "../ui/core";
import { Choices, DateField, Field, SegCtl, TextArea } from "../ui/controls";
import { GuardFoot, Modal, useDirtyGuard, useToast } from "../ui/layers";
import { go, setQuery, useRoute } from "../ui/route";
import { TECH_ADMIN } from "../env";
import { useData } from "../app/data";
import { ConfigForm, missing, Refs, SCHEMA } from "./configForms";
import { weeklyResult } from "./Proposals";

type Policy = { id: string; name: string; version: number; approved_for_exploration: boolean };
type Ready = { ready: boolean; revision: number; unit_count?: number; horizon_minutes?: number; issues: { code: string; message: string }[] };
type Run = { id: string; status: string; phase: string; stale: boolean; error_code: string; dispatch_status: string; created_at?: string; result: null | { solver_status: string; is_complete: boolean; assignments: unknown[]; unassigned?: unknown[]; validation: { status: string } } };
export type Row = { id: string; version: number; [key: string]: unknown };
const CONFIGS: [string, string, string][] = [
  ["planning-policies", "Politiche", "Budget di ricerca e regole della prova"],
  ["tutor-skills", "Competenze", "Materie e livelli approvati per tutor"],
  ["tutor-operating-policies", "Carichi e pause", "Limiti giornalieri, settimanali e transizioni"],
  ["service-windows", "Aperture", "Fasce di servizio del centro"],
  ["resource-timings", "Margini delle aule", "Minuti di margine tra una lezione e l’altra in aule e canali"],
  ["closures", "Chiusure", "Periodi in cui il centro è chiuso"],
  ["availability-declarations", "Completezza", "Disponibilità dichiarate complete o no"],
  ["availability-exceptions", "Eccezioni", "Variazioni datate alle disponibilità"],
  ["availability-conflicts", "Segnalazioni", "Indicazioni sulle disponibilità da verificare"],
];
const TEMPLATES: Record<string, object> = {
  "planning-policies": { name: "Regola di pianificazione", budget_seconds: 3, online_onsite_requires_space: true, video_channels_required: false, partial_week_rule: "BLOCK", unsupported_constraints: [], approved_for_exploration: false },
  "tutor-skills": { tutor: "UUID", subject: "UUID", level: "Livello esatto del percorso", mode: "IN_PERSON", valid_from: "2026-10-01", valid_until: "2027-06-30", approved: false },
  "tutor-operating-policies": { tutor: "UUID", daily_limit_minutes: 300, weekly_limit_minutes: 600, pause_minutes: 0, site_to_remote_minutes: 30, remote_to_site_minutes: 30 },
  "service-windows": { mode: "IN_PERSON", location: "ON_SITE", weekday: 0, start_time: "10:00", end_time: "16:00", period_start: "2026-10-01", period_end: "2027-06-30", resource: null },
  "resource-timings": { resource: "UUID", buffer_minutes: 0, inherit_service_windows: true },
  "closures": { start_at: "2026-10-05T10:00:00+02:00", end_at: "2026-10-05T11:00:00+02:00", mode: "ALL", resource: null, reason: "Chiusura" },
  "availability-declarations": { student: "UUID", tutor: null, state: "UNKNOWN" },
  "availability-exceptions": { student: "UUID", tutor: null, start_at: "2026-10-05T10:00:00+02:00", end_at: "2026-10-05T11:00:00+02:00", mode: "IN_PERSON", location: "ON_SITE", kind: "REMOVE_AVAILABLE" },
  "availability-conflicts": { student: "UUID", tutor: null, reason: "Indicazioni da verificare", open: true },
};
const ADVANCED = CONFIGS.filter(([k]) => ["resource-timings", "availability-conflicts"].includes(k));
const PHASE: Record<string, string> = { QUEUED: "In attesa", RUNNING: "Calcolo in corso", SUCCEEDED: "Calcolo concluso", FAILED: "Calcolo non riuscito", CANCELLED: "Annullato", CANCEL_REQUESTED: "Annullamento in corso" };
const live = (r: Run) => ["QUEUED", "RUNNING", "CANCEL_REQUESTED"].includes(r.status);
const rowLabel = (r: Row) => String(r.name || r.reason || r.level || r.kind || r.state || r.mode || "Record");
const WDL = ["Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom"], t5 = (v: unknown) => String(v || "").slice(0, 5);
/** Riepilogo leggibile di un record di configurazione (nomi al posto degli identificativi). */
function rowText(kind: string, r: Row, names: Record<string, string>) {
  const who = names[String(r.tutor || r.student || r.resource || "")] || "";
  const md = r.mode === "ONLINE" ? "Online" : r.mode === "ALL" ? "Tutte le modalità" : r.mode ? "In presenza" : "";
  switch (kind) {
    case "service-windows": return [`${WDL[Number(r.weekday)] || "?"} ${t5(r.start_time)}–${t5(r.end_time)}`, [md, who || "tutto il centro"].join(" · ")];
    case "tutor-skills": return [`${who || "Tutor"} · ${names[String(r.subject)] || "materia"}`, `${r.level} · ${md}${r.approved ? " · approvata" : " · da approvare"}`];
    case "tutor-operating-policies": return [who || "Tutor", `${r.daily_limit_minutes} min/giorno · ${r.weekly_limit_minutes} min/settimana · pausa ${r.pause_minutes} min`];
    case "resource-timings": return [who || "Risorsa", `Margine ${r.buffer_minutes} min${r.inherit_service_windows ? " · segue le aperture" : ""}`];
    case "availability-declarations": return [who || "Anagrafica", r.state === "APPROVED" ? "Dati approvati" : r.state === "DECLARED_NONE" ? "Nessuna disponibilità" : "Dati incompleti"];
    case "availability-exceptions": return [`${who || "Anagrafica"} · ${r.kind === "ADD_AVAILABLE" ? "aggiunge" : "toglie"}`, `${String(r.start_at || "").slice(0, 16).replace("T", " ")} · ${md}`];
    case "availability-conflicts": return [who || "Anagrafica", `${r.reason}${r.open ? " · aperto" : " · chiuso"}`];
    case "closures": return [String(r.reason || "Chiusura"), `${String(r.start_at || "").slice(0, 16).replace("T", " ")} · ${md}${who ? " · " + who : ""}`];
    default: return [rowLabel(r), `Budget ${r.budget_seconds} s${r.approved_for_exploration ? " · esplorazione approvata" : ""}`];
  }
}

export default function Proposte() {
  const toast = useToast(), r = useRoute();
  const nextMonday = (() => { const t = todayRome(); return weekday(t) === 0 ? t : addDays(mondayOf(t), 7); })();
  const [policies, setPolicies] = useState<Policy[] | null>(null), [policy, setPolicy] = useState("");
  const week = r.q.get("w") || nextMonday, [mode, setMode] = useState<"STRICT" | "COVERAGE">("STRICT");
  const [ready, setReady] = useState<Ready | null>(null), [runs, setRuns] = useState<Run[] | null>(null);
  const [err, setErr] = useState(""), [busy, setBusy] = useState(false);
  const pending = useRef<{ key: string; body: string } | null>(null), [retry, setRetry] = useState(false);
  const loadRuns = () => list<Run>("/schedule-runs/").then((rs) => setRuns(rs.filter((x) => !x.result || !!weeklyResult(x.result))));
  async function load() {
    const [p] = await Promise.all([list<Policy>("/planning-policies/"), loadRuns()]);
    setPolicies(p); setPolicy((c) => c || p.find((x) => x.approved_for_exploration)?.id || p[0]?.id || "");
  }
  useEffect(() => { load().catch((e) => setErr(human(e).text)); }, []);
  const active = (runs || []).some(live);
  useEffect(() => {
    if (!active) return;
    const t = window.setInterval(() => loadRuns().catch((e) => setErr(human(e).text)), 2500);
    return () => window.clearInterval(t);
  }, [active]);
  const reset = () => { setReady(null); pending.current = null; setRetry(false); };
  async function check() {
    setBusy(true); setErr("");
    try { setReady(await api<Ready>(`/planning/data-readiness?policy_id=${encodeURIComponent(policy)}&horizon_start=${week}&mode=${mode}`)); pending.current = null; setRetry(false); }
    catch (e) { setErr(human(e).text); } finally { setBusy(false); }
  }
  async function generate() {
    if (!ready?.ready) return;
    const body = JSON.stringify({ policy_id: policy, horizon_start: week, expected_revision: ready.revision, mode });
    if (!pending.current || pending.current.body !== body) pending.current = { key: crypto.randomUUID(), body };
    setBusy(true); setErr("");
    try {
      await api("/schedule-runs", { method: "POST", headers: { "Idempotency-Key": pending.current.key }, body });
      pending.current = null; setRetry(false); setReady(null); await loadRuns();
      toast("Calcolo avviato. Al termine la proposta comparirà in Agenda, pronta da rivedere: nessuna lezione viene creata ora.");
    } catch (e) { const h = human(e); setErr(h.text); if (!h.retry) pending.current = null; setRetry(!!pending.current); } finally { setBusy(false); }
  }
  async function cancel(run: Run) {
    try { await api(`/schedule-runs/${run.id}/cancel/`, { method: "POST", body: "{}" }); await loadRuns(); toast("Annullamento richiesto."); }
    catch (e) { toast(human(e).text); }
  }
  const pol = policies?.find((p) => p.id === policy);
  return <>
    <section className="module planner" aria-labelledby="h-gen">
      <PageHead id="h-gen" title="Genera l’orario" />
      {!policies ? <Skeleton rows={3} /> : !policies.length ? <Empty title="Nessuna regola di pianificazione">Creane una in Centro › Configurazione › Regole di pianificazione.<div style={{ marginTop: 12 }}><Btn kind="sm" onClick={() => go("configurazione", { tab: "regole" })}>Apri la configurazione</Btn></div></Empty> : <>
        <div className="grid2">
          <Field label="Regola di pianificazione"><Choices label="Regola di pianificazione" value={policy} onChange={(v) => { setPolicy(v); reset(); }} options={policies.map((p) => ({ v: p.id, label: p.name + (p.approved_for_exploration ? "" : " (non abilitata)") }))} /></Field>
          <Field label="Settimana" hint="Si pianifica una settimana alla volta, da lunedì.">
            <DateField label="Settimana" value={week} placeholder="Scegli un lunedì" disabled={(d) => weekday(d) !== 0} onChange={(d) => { setQuery((q) => (d === nextMonday ? q.delete("w") : q.set("w", d))); reset(); }} />
          </Field>
        </div>
        <Field label="Che cosa deve coprire"><SegCtl label="Copertura" value={mode} onChange={(v) => { setMode(v); reset(); }} options={[["STRICT", "Tutte le richieste"], ["COVERAGE", "Il più possibile"]]} /></Field>
        <p className="muted" style={{ margin: "4px 0 14px" }}>{mode === "STRICT" ? "Se anche una sola richiesta non trova posto, la proposta non viene prodotta." : "Le richieste obbligatorie restano obbligatorie; le altre vengono collocate finché c’è spazio."}</p>
        {pol && !pol.approved_for_exploration && <Notice kind="warn">Questa regola non è ancora abilitata: la verifica lo segnalerà.</Notice>}
        {ready && (ready.ready
          ? <Notice kind="ok" title="Dati pronti">{plural(ready.unit_count || 0, "lezione da collocare", "lezioni da collocare")} nella settimana del {dayLabel(week).toLowerCase()}.<Tech><code>Revisione {ready.revision} · orizzonte {num(ready.horizon_minutes || 0)} minuti</code></Tech></Notice>
          : <Notice kind="warn" title="Dati incompleti: la proposta non si può generare">
            <ul className="issues">{ready.issues.map((i) => <li key={i.code}>{i.message}</li>)}</ul>
            <Tech><code>Revisione {ready.revision} · {ready.issues.map((i) => i.code).join(", ")}</code></Tech></Notice>)}
        {err && <Notice kind="bad">{err}</Notice>}
        <div className="toolbar" style={{ marginTop: 14 }}>
          <Btn kind={ready?.ready ? "raised" : "primary"} icon="check" disabled={busy || !policy} onClick={check}>{busy && !ready ? "Verifico…" : ready ? "Verifica di nuovo" : "Verifica i dati"}</Btn>
          <Btn kind="primary" isle="spark" disabled={busy || !ready?.ready} onClick={generate}>{retry ? "Riprova lo stesso avvio" : busy && ready ? "Avvio…" : "Genera la proposta"}</Btn>
        </div>
      </>}
    </section>

    <section className="module" aria-labelledby="h-runs" style={{ marginTop: 18 }}>
      <div className="m-head"><div><h2 className="m-title" id="h-runs">Calcoli</h2></div>
        <div className="controls"><Btn kind="sm" onClick={() => loadRuns().catch((e) => setErr(human(e).text))}>Aggiorna</Btn><a className="pill-btn sm" href="#/agenda"><Icon n="cal" />Vai all’Agenda</a></div></div>
      {!runs ? <Skeleton rows={2} /> : !runs.length ? <Empty title="Nessun calcolo avviato" />
        : <div className="mini-list">{runs.slice(0, 8).map((x, i) => <div key={x.id} className="mini">
          <span className="mini-ic"><Icon n={live(x) ? "clock" : x.status === "SUCCEEDED" ? "check" : "x"} /></span>
          <span className="grow"><b>Calcolo {runs.length - i}</b><small>{PHASE[x.status] || "Stato sconosciuto"}{x.stale ? " · dati cambiati nel frattempo: rigenera" : ""}{x.result ? ` · ${plural(x.result.assignments.length, "lezione proposta", "lezioni proposte")}${x.result.is_complete ? "" : ", parziale"}` : ""}{x.error_code ? " · non è stato possibile produrre una proposta" : ""}</small>
            <Tech><code>{x.id} · {x.status}/{x.phase} · dispatcher {x.dispatch_status}{x.error_code ? " · " + x.error_code : ""}{x.result ? ` · ${x.result.solver_status} · validatore ${x.result.validation.status}` : ""}</code></Tech></span>
          {x.result ? <State s={x.result.solver_status} /> : <State s={x.status} />}
          {["QUEUED", "RUNNING"].includes(x.status) && <Btn kind="sm ghost" onClick={() => cancel(x)}>Annulla</Btn>}
        </div>)}</div>}
    </section>
  </>;
}

/** Impostazioni avanzate non coperte dalle altre schede di Configurazione. */
export function AdvancedConfig({ onSaved }: { onSaved?: () => void }) {
  const toast = useToast(), d = useData();
  const [subjects, setSubjects] = useState<{ id: string; name: string }[]>([]);
  useEffect(() => { list<{ id: string; name: string }>("/subjects/").then(setSubjects).catch(() => {}); }, []);
  const names: Record<string, string> = Object.fromEntries([...d.tutors.map((t) => [t.id, t.display_name]), ...d.students.map((t) => [t.id, t.display_name]), ...d.resources.map((t) => [t.id, t.name]), ...subjects.map((t) => [t.id, t.name])]);
  const [kind, setKind] = useState(ADVANCED[0][0]), [rows, setRows] = useState<Row[] | null>(null), [err, setErr] = useState("");
  const [edit, setEdit] = useState<{ row: Row | null } | null>(null);
  const load = (k = kind) => list<Row>(`/${k}/`).then(setRows).catch((e) => setErr(human(e).text));
  useEffect(() => { setRows(null); setErr(""); load(kind); }, [kind]);
  const info = ADVANCED.find((c) => c[0] === kind)!;
  return <div aria-labelledby="h-adv">
    <div className="m-head"><div><h2 className="m-title" id="h-adv">Impostazioni avanzate</h2></div>
      <div className="controls"><Btn kind="sm" icon="plus" onClick={() => setEdit({ row: null })}>Nuovo</Btn></div></div>
    <div className="seg-scroll"><SegCtl label="Categoria" value={kind} onChange={setKind} options={ADVANCED.map(([k, l]) => [k, l] as [string, string])} /></div>
    <p className="muted" style={{ margin: "10px 0" }}>{info[2]}.</p>
    {err && <Notice kind="bad">{err}</Notice>}
    {!rows ? <Skeleton rows={2} /> : !rows.length ? <Empty title="Nessun elemento" />
      : <div className="mini-list">{rows.map((x) => <button type="button" key={x.id} className="mini" onClick={() => setEdit({ row: x })}>
        <span className="mini-ic"><Icon n="gear" /></span><span className="grow"><b>{rowText(kind, x, names)[0]}</b><small>{rowText(kind, x, names)[1]}</small></span><Tag tone="plain">Modifica</Tag></button>)}</div>}
    <JsonModal v={edit} kind={kind} label={info[1]} onClose={() => setEdit(null)} onSaved={async (msg) => { setEdit(null); await load(); toast(msg); onSaved?.(); }} />
  </div>;
}

export function JsonModal({ v, kind, label, onClose, onSaved }: { v: { row: Row | null } | null; kind: string; label: string; onClose: () => void; onSaved: (m: string) => Promise<void> }) {
  const d = useData();
  const initial = (row: Row | null): Record<string, unknown> => { if (!row) return { ...(TEMPLATES[kind] as Record<string, unknown>) }; const { id: _i, version: _v, created_at: _c, updated_at: _u, ...w } = row; return w; };
  const [val, setVal] = useState<Record<string, unknown>>({}), [text, setText] = useState(""), [start, setStart] = useState(""), [err, setErr] = useState(""), [busy, setBusy] = useState(false);
  const [mode, setMode] = useState<"form" | "json">("form"), [bad, setBad] = useState<string[]>([]), [subjects, setSubjects] = useState<{ id: string; name: string }[]>([]);
  const [last, setLast] = useState(v);
  useEffect(() => { list<{ id: string; name: string }>("/subjects/").then(setSubjects).catch(() => setSubjects([])); }, []);
  useEffect(() => {
    if (!v) return;
    const w = initial(v.row);
    // I segnaposto "UUID" dei modelli diventano campi vuoti nel modulo.
    for (const k of Object.keys(w)) if (w[k] === "UUID") w[k] = "";
    setLast(v); setVal(w); const t = JSON.stringify(w, null, 2); setText(t); setStart(t); setErr(""); setBad([]); setMode(SCHEMA[kind] ? "form" : "json"); g.reset();
  }, [v]); // eslint-disable-line
  const current = mode === "form" ? JSON.stringify(val, null, 2) : text;
  const g = useDirtyGuard(!!v && current !== start);
  const x = v || last; if (!x) return null;
  const refs: Refs = {
    tutor: d.tutors.map((t) => ({ id: t.id, label: t.display_name })),
    student: d.students.map((t) => ({ id: t.id, label: t.display_name, sub: t.level })),
    subject: subjects.map((t) => ({ id: t.id, label: t.name })),
    resource: d.resources.map((t) => ({ id: t.id, label: t.name, sub: t.student_capacity ? `${t.student_capacity} posti` : undefined })),
  };
  function switchTo(m: "form" | "json") {
    if (m === mode) return;
    if (m === "json") { setText(JSON.stringify(val, null, 2)); setMode("json"); setErr(""); return; }
    try { const parsed = JSON.parse(text); if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw Error(); setVal(parsed); setMode("form"); setErr(""); }
    catch { setErr("Il testo non è JSON valido: correggilo prima di tornare al modulo."); }
  }
  async function save(e: React.FormEvent) {
    e.preventDefault(); setErr(""); let body: Record<string, unknown>;
    if (mode === "form") {
      const miss = missing(kind, val); setBad(miss);
      if (miss.length) { setErr("Completa i campi obbligatori evidenziati."); document.getElementById(`cf-${miss[0]}`)?.focus(); return; }
      body = { ...val };
    } else {
      try { body = JSON.parse(text); } catch { setErr("Il testo non è JSON valido: controlla virgole, virgolette e parentesi."); return; }
    }
    if (x!.row) body.expected_version = x!.row.version;
    setBusy(true);
    try { await api(`/${kind}/${x!.row ? x!.row.id + "/" : ""}`, { method: x!.row ? "PATCH" : "POST", body: JSON.stringify(body) }); g.allow(); await onSaved("Configurazione salvata. Verifica di nuovo i dati prima di generare."); }
    catch (er) { setErr(human(er).text); } finally { setBusy(false); }
  }
  return <Modal open={!!v} onClose={onClose} guard={g.guard} labelledBy="js-title" width={680}><form onSubmit={save} noValidate>
    <div className="modal-body">
      <h2 id="js-title">{x.row ? `Modifica: ${label.toLowerCase()}` : `Nuovo: ${label.toLowerCase()}`}</h2>
      <p className="lead">{mode === "form" ? "Scegli tutor, studenti, materie e spazi per nome." : "Formato tecnico avanzato: usa gli identificativi delle anagrafiche."} {x.row ? "Il salvataggio non riesce se qualcuno l’ha modificato nel frattempo." : "Controlla i valori proposti prima di salvare."}</p>
      {(TECH_ADMIN || !SCHEMA[kind]) && <div className="seg-scroll" style={{ marginBottom: 14 }}><SegCtl label="Modalità di modifica" value={mode} onChange={switchTo} options={[["form", "Modulo"], ["json", "JSON avanzato"]]} /></div>}
      {mode === "form" ? <ConfigForm kind={kind} value={val} onChange={(nv) => { setVal(nv); setBad((b) => b.filter((k) => nv[k] === "" || nv[k] === null || nv[k] === undefined)); }} refs={refs} bad={bad} />
        : <Field label="Contenuto (JSON)" id="js-text"><TextArea id="js-text" rows={14} value={text} onChange={(e) => setText(e.target.value)} /></Field>}
      {err && <Notice kind="bad">{err}</Notice>}
    </div>
    {g.asking ? <GuardFoot onKeep={g.keep} onDiscard={() => { g.allow(); onClose(); }} />
      : <div className="modal-foot"><button type="button" className="pill-btn ghost" onClick={() => { if (g.guard()) onClose(); }}>Chiudi</button>
        <button className="pill-btn primary island" disabled={busy}>{busy ? "Salvataggio…" : "Salva"}<span className="isle"><Icon n="check" /></span></button></div>}
  </form></Modal>;
}
