import { useMemo, useState } from "react";
import { api } from "../api";
import { LOC, plural } from "../format";
import { human, LOCATION, MODE, stateOf } from "../messages";
import { Btn, Empty, Icon, Notice, PageHead, Stat, State, Tag, Tech } from "../ui/core";
import { Check, Field, SegCtl, TextArea } from "../ui/controls";
import { useToast } from "../ui/layers";
import { ViewState } from "../ui/states";

type Assignment = { demand_key: string; tutor_id: string; mode: string; location: string; space_id: string | null; video_id: string | null; start: number; end: number };
type Result = {
  solver_status: string; epoch: string; timezone: string; assignments: Assignment[]; unassigned: { demand_key: string; reason_codes: string[] }[];
  is_complete: boolean; input_hash: string; solver_version: string; optimality_proven_levels: string[];
  validation: { status: string; violations: { code: string; demand_key: string }[] };
  diagnostics: { code: string; message: string }[]; empty_domain_diagnostics?: { demand_key: string; reason_codes: string[] }[];
  statistics: { wall_time_seconds: number; candidate_count?: number };
};
const OUTCOME: Record<string, string> = {
  OPTIMAL: "La migliore copertura possibile sui livelli di priorità P0, P1 e P2 implementati.",
  FEASIBLE: "Proposta valida, ma non è dimostrato che sia la migliore.",
  INFEASIBLE: "Con questi dati non esiste un orario che rispetti tutti i vincoli.",
  UNKNOWN: "Ricerca non conclusiva nel tempo concesso: non significa che sia impossibile.",
  BLOCKED: "Mancano dati, si superano i limiti del prototipo o ci sono vincoli non supportati: la ricerca non è partita.",
  MODEL_INVALID: "Errore tecnico del modello, non dovuto alle disponibilità.",
  VALIDATION_FAILED: "Il validatore indipendente ha rifiutato la proposta.",
};
type Win = { mode?: string; location?: string; start: number; end: number };
type Dto = { epoch: string; timezone: string; students: { id: string; availability_state: string; availability: Win[] }[]; tutors: { id: string; availability_state: string; availability: Win[]; daily_limit_minutes: number; weekly_limit_minutes: number; skills: { subject: string }[] }[];
  resources: { id: string; kind: string; student_capacity: number | null; availability: Win[] }[]; units: { demand_key: string; type: string; subject: string; participants: string[]; duration_minutes: number; priority: string; mandatory: boolean; allowed_modes: string[]; allowed_tutors: string[] }[] };
function asDto(text: string): Dto | null {
  try { const d = JSON.parse(text); return d && Array.isArray(d.students) && Array.isArray(d.tutors) && Array.isArray(d.units) && Array.isArray(d.resources) ? d : null; } catch { return null; }
}
const AV: Record<string, string> = { APPROVED: "disponibilità approvate", DECLARED_NONE: "nessuna disponibilità", UNKNOWN: "disponibilità incomplete" };
const BUDGETS: [string, string][] = [["1", "1 s"], ["3", "3 s"], ["5", "5 s"], ["10", "10 s"]];

export default function Laboratorio() {
  const toast = useToast();
  const [input, setInput] = useState(""), [result, setResult] = useState<Result | null>(null), [err, setErr] = useState(""), [busy, setBusy] = useState<"" | "ex" | "run">("");
  const [mode, setMode] = useState<"STRICT" | "COVERAGE">("STRICT"), [budget, setBudget] = useState("3");
  const [view, setView] = useState<"sum" | "json">("sum"), [off, setOff] = useState<string[]>([]);
  const dto = useMemo(() => asDto(input), [input]);
  const at = (min: number) => dto ? new Intl.DateTimeFormat(LOC, { timeZone: dto.timezone, weekday: "short", hour: "2-digit", minute: "2-digit" }).format(new Date(Date.parse(dto.epoch) + min * 60000)) : "";
  const span = (w: Win[]) => w.length ? [...new Set(w.map((x) => `${at(x.start)}–${at(x.end).split(" ").pop()}`))].join(", ") : "nessuna fascia";
  const nameOf = (id: string, kind: "s" | "t" | "r") => { const list = kind === "s" ? dto?.students : kind === "t" ? dto?.tutors : dto?.resources; const i = (list || []).findIndex((x) => x.id === id); return i < 0 ? id : `${kind === "s" ? "Studente" : kind === "t" ? "Tutor" : "Spazio"} ${i + 1}`; };
  async function example() {
    setBusy("ex"); setErr("");
    try { setInput(JSON.stringify(await api<object>("/planning/example"), null, 2)); setResult(null); setOff([]); setView("sum"); toast("Scenario di prova caricato: 4 studenti, 2 tutor, 3 spazi."); }
    catch (e) { setErr(human(e).text); } finally { setBusy(""); }
  }
  async function run(e: React.FormEvent) {
    e.preventDefault(); setErr(""); let dto: Record<string, unknown>;
    try { dto = JSON.parse(input); } catch { setErr("Lo scenario non è JSON valido: controlla virgole, virgolette e parentesi."); return; }
    if (!dto || typeof dto !== "object" || Array.isArray(dto)) { setErr("Lo scenario deve essere un oggetto JSON."); return; }
    if (Array.isArray(dto.units) && off.length) dto = { ...dto, units: (dto.units as { demand_key: string }[]).filter((u) => !off.includes(u.demand_key)) };
    setBusy("run"); setResult(null);
    try { setResult(await api<Result>("/planning/simulate", { method: "POST", body: JSON.stringify({ ...dto, mode, budget_seconds: Number(budget) }) })); }
    catch (er) { setErr(human(er).text); } finally { setBusy(""); }
  }
  function exportResult() {
    if (!result) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(result, null, 2)], { type: "application/json" }));
    const a = document.createElement("a"); a.href = url; a.download = "simulazione-ripetizioni.json"; a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  const time = (min: number) => result ? new Intl.DateTimeFormat(LOC, { timeZone: result.timezone, weekday: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(new Date(Date.parse(result.epoch) + min * 60000)) : "";
  const hhmm = (min: number) => result ? new Intl.DateTimeFormat(LOC, { timeZone: result.timezone, hour: "2-digit", minute: "2-digit" }).format(new Date(Date.parse(result.epoch) + min * 60000)) : "";
  const tutors = result ? [...new Set(result.assignments.map((a) => a.tutor_id))] : [];
  const problems = result ? result.diagnostics.length + (result.empty_domain_diagnostics?.length || 0) + result.validation.violations.length : 0;
  return <>
    <section className="module planner" aria-labelledby="h-lab">
      <PageHead id="h-lab" title="Laboratorio">
        <Btn icon="download" disabled={!!busy} onClick={example}>{busy === "ex" ? "Carico…" : "Carica lo scenario di prova"}</Btn>
      </PageHead>
      <form onSubmit={run} noValidate>
        <div className="seg-scroll" style={{ marginBottom: 12 }}><SegCtl label="Vista dello scenario" value={view} onChange={setView} options={[["sum", "Riepilogo"], ["json", "JSON avanzato"]]} /></div>
        {view === "json" ? <Field label="Scenario (JSON)" id="lab-in" hint="Solo dati sintetici, nel formato del contratto planning-input.">
          <TextArea id="lab-in" rows={10} value={input} placeholder="Carica lo scenario di prova o incolla uno scenario compatibile…" onChange={(e) => setInput(e.target.value)} />
        </Field> : !input.trim() ? <Empty title="Nessuno scenario" />
          : !dto ? <Notice kind="warn" title="Riepilogo non disponibile">Lo scenario non è leggibile come planning-input: correggilo in “JSON avanzato”.</Notice>
          : <div className="lab-sum">
            <div className="stats">
              <Stat label="Studenti" value={dto.students.length} note={[...new Set(dto.students.map((x) => AV[x.availability_state] || x.availability_state))].join(", ")} />
              <Stat label="Tutor" value={dto.tutors.length} note={dto.tutors.map((t, i) => `T${i + 1}: ${t.daily_limit_minutes} min/giorno`).join(" · ")} />
              <Stat label="Spazi e canali" value={dto.resources.length} note={dto.resources.map((r, i) => `${r.kind === "SPACE" ? "S" : "V"}${i + 1}: ${r.student_capacity ?? "—"} posti`).join(" · ")} />
            </div>
            <dl className="facts lab-facts">
              {dto.students.map((x) => <div key={x.id}><dt>{nameOf(x.id, "s")}</dt><dd>{span(x.availability)}</dd></div>)}
              {dto.tutors.map((x) => <div key={x.id}><dt>{nameOf(x.id, "t")}</dt><dd>{span(x.availability)} · {plural(new Set(x.skills.map((k) => k.subject)).size, "materia", "materie")}</dd></div>)}
            </dl>
            <h3 className="lab-h">Richieste da collocare <span className="muted">({dto.units.length - off.filter((k) => dto.units.some((u) => u.demand_key === k)).length} di {dto.units.length} incluse)</span></h3>
            <div className="mini-list">{dto.units.map((u) => <div key={u.demand_key} className="mini lab-unit">
              <Check checked={!off.includes(u.demand_key)} onChange={(on) => setOff((o) => on ? o.filter((k) => k !== u.demand_key) : [...o, u.demand_key])}>
                <span className="grow"><b>{u.subject} · {u.duration_minutes} min</b><small>{u.type === "GROUP" ? "Gruppo" : "Individuale"}: {u.participants.map((p) => nameOf(p, "s")).join(", ")} · {u.allowed_modes.map((m) => MODE[m] || m).join("/")} · {u.mandatory ? "obbligatoria" : "facoltativa"} · {u.priority}</small></span>
              </Check></div>)}</div>
            
          </div>}
        <div className="grid2">
          <Field label="Che cosa deve coprire"><SegCtl label="Copertura" value={mode} onChange={setMode} options={[["STRICT", "Tutte le richieste"], ["COVERAGE", "Il più possibile"]]} /></Field>
          <Field label="Tempo massimo di ricerca"><SegCtl label="Tempo massimo" value={budget} onChange={setBudget} options={BUDGETS} /></Field>
        </div>
        
        {err && <Notice kind="bad">{err}</Notice>}
        <div className="toolbar"><button className="pill-btn primary island" disabled={!!busy || !input.trim() || (!!dto && dto.units.every((u) => off.includes(u.demand_key)))}>{busy === "run" ? "Ricerca e controllo in corso…" : "Calcola la proposta"}<span className="isle"><Icon n="spark" /></span></button></div>
      </form>
    </section>

    {result && <section className="module reveal" aria-labelledby="h-res" aria-live="polite" style={{ marginTop: 18 }}>
      <div className="m-head"><div><h2 className="m-title" id="h-res">Risultato <State s={result.solver_status} /></h2><p className="sub-line">{OUTCOME[result.solver_status] || "Esito tecnico non classificato."}</p></div>
        <div className="controls"><Tag tone="amber">Solo simulazione</Tag><Btn kind="sm" icon="download" onClick={exportResult}>Esporta</Btn></div></div>
      {result.solver_status === "UNKNOWN" && <ViewState kind="inconclusive">{OUTCOME.UNKNOWN} Aumenta il tempo concesso o riduci la domanda e riprova.</ViewState>}
      {result.solver_status !== "UNKNOWN" && !result.is_complete && <ViewState kind="partial" title="Risultato parziale">Alcune richieste non sono state collocate: i motivi sono elencati sotto.</ViewState>}
      <div className="stats">
        <Stat label="Lezioni collocate" value={result.assignments.length} note={result.is_complete ? "Tutta la domanda" : `${plural(result.unassigned.length, "richiesta esclusa", "richieste escluse")}`} />
        <Stat label="Controllo indipendente" value={stateOf(result.validation.status)[0]} note={result.validation.violations.length ? plural(result.validation.violations.length, "violazione", "violazioni") : "Nessuna violazione"} />
        <Stat label="Tempo di ricerca" value={`${result.statistics.wall_time_seconds.toLocaleString(LOC, { maximumFractionDigits: 2 })} s`} note={result.statistics.candidate_count != null ? `${result.statistics.candidate_count.toLocaleString(LOC)} orari valutati` : undefined} />
      </div>
      {problems > 0 && <Notice kind="warn" title="Segnalazioni">
        <ul className="issues">{result.diagnostics.map((d, i) => <li key={"d" + i}>{d.message}</li>)}
          {result.empty_domain_diagnostics?.length ? <li>{plural(result.empty_domain_diagnostics.length, "richiesta non ha", "richieste non hanno")} nessun orario possibile.</li> : null}
          {result.validation.violations.length ? <li>Il validatore ha trovato {plural(result.validation.violations.length, "violazione", "violazioni")}.</li> : null}</ul>
        <Tech><code>{[...result.diagnostics.map((d) => d.code), ...(result.empty_domain_diagnostics || []).map((d) => `${d.demand_key}: ${d.reason_codes.join(", ")}`), ...result.validation.violations.map((v) => `${v.code} · ${v.demand_key}`)].join("\n")}</code></Tech>
      </Notice>}
      {result.assignments.length ? <div className="list-wrap"><table className="list">
        <thead><tr><th scope="col">Quando</th><th scope="col">Tutor</th><th scope="col" className="hide-m">Modalità</th><th scope="col" className="hide-m">Spazio</th></tr></thead>
        <tbody>{[...result.assignments].sort((a, b) => a.start - b.start).map((a) => <tr key={a.demand_key}>
          <td><b style={{ fontWeight: 500 }}>{time(a.start)}</b><span className="muted num">–{hhmm(a.end)}</span></td>
          <td>Tutor {tutors.indexOf(a.tutor_id) + 1}</td>
          <td className="hide-m">{MODE[a.mode] || a.mode}, {(LOCATION[a.location] || a.location).toLowerCase()}</td>
          <td className="hide-m">{a.space_id ? "Assegnato" : a.video_id ? "Canale video" : "Nessuno"}</td></tr>)}</tbody></table></div>
        : <Empty title="Nessuna lezione collocata">{OUTCOME[result.solver_status]}</Empty>}
      
      <Tech><dl className="facts"><dt>Hash scenario</dt><dd><code>{result.input_hash}</code></dd><dt>Motore</dt><dd><code>{result.solver_version}</code></dd>
        <dt>Livelli dimostrati</dt><dd>{result.optimality_proven_levels.join(", ") || "nessuno"}</dd><dt>Fuso</dt><dd>{result.timezone}</dd>
        <dt>Unità</dt><dd><code>{result.assignments.map((a) => `${a.demand_key} → ${a.tutor_id}${a.space_id ? " @ " + a.space_id : ""}`).join("\n")}</code></dd>
        {result.unassigned.length > 0 && <><dt>Escluse</dt><dd><code>{result.unassigned.map((u) => `${u.demand_key}: ${u.reason_codes.join(", ")}`).join("\n")}</code></dd></>}</dl></Tech>
    </section>}
    {!result && !busy && input && <div style={{ marginTop: 18 }}><Empty title="Pronto per il calcolo" /></div>}
  </>;
}
