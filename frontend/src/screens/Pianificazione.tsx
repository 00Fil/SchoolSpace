/** Pianificazione orari (v0.9.4) — percorso guidato in tre passi.
 *  In cima c'è sempre UNA cosa da fare («Prossimo passo»); sotto, il passo scelto:
 *  1 Rivedi (decisioni, correzioni, vincoli) · 2 Calcola · 3 Pubblica. */
import { ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { api, list } from "../api";
import { addDays, dateLong, mondayOf, num, plural, todayRome, weekday, WD_SHORT } from "../format";
import { human } from "../messages";
import { Avatar, Btn, Empty, Icon, IconName, Skeleton, Tech } from "../ui/core";
import { DateField, SegCtl } from "../ui/controls";
import { useToast } from "../ui/layers";
import { go, setQuery, useRoute } from "../ui/route";
import { useData } from "../app/data";
import { reasonText, weeklyResult } from "./Proposals";
import { JsonModal, Row } from "./Proposte";
import { ApproveModal, KIND, modeText, needsTutor, RequestModal, Req, review, tutorText, whenText } from "./requestForms";

type OvReq = Req & { level: string; competent_tutors: { id: string; display_name: string }[]; problems: string[] };
type ReqAn = { units: number; placeable_units: number; min_options: number | null; slots: number; tutors: { id: string; display_name: string; options: number }[]; reasons: string[] };
type Ov = {
  horizon_start: string; planning_enabled: boolean; revision?: number; ready: boolean;
  policy: null | { id: string; name: string; budget_seconds: number; horizon_weeks: number; approved_for_exploration: boolean };
  thorough: { budget_seconds: number; search_workers: number };
  requests: OvReq[]; issues: { code: string; message: string; request_id?: string }[];
  analysis: null | {
    units: number; candidates: number; demand_minutes: number; service_minutes: number; requests: Record<string, ReqAn>;
    tutors: { id: string; available_minutes: number; eligible_demand_minutes: number; weekly_limit_minutes: number | null }[];
    students: { id: string; display_name: string; available_minutes: number; demand_minutes: number }[];
  };
};
type Run = {
  id: string; status: string; phase: string; stale: boolean; error_code: string; started_at?: string | null; finished_at?: string | null; budget_seconds?: number; horizon_start?: string;
  result: null | { solver_status: string; assignments: unknown[]; unassigned: { demand_key: string; reason_codes: string[] }[]; validation: { status: string }; optimality_proven_levels?: string[] };
};
type Tone = "red" | "amber" | "blue" | "green" | "violet";
type Win = { weekday: number; start: number; end: number };

const PROBLEM: Record<string, string> = {
  REQUEST_SKILLS_MISSING: "Nessun tutor ha la competenza approvata per materia, livello e modalità.",
  REQUIRED_TUTOR_UNAVAILABLE: "Il tutor obbligatorio non ha la competenza approvata.",
  PREFERRED_TUTOR_NOT_COMPETENT: "Il tutor preferito non ha la competenza: verrà ignorato.",
  SERIES_TUTOR_MISSING: "Richiesta ricorrente senza tutor: sceglilo per tenere lo stesso tutor ogni settimana.",
  LEVEL_MISSING: "Manca il livello didattico dello studente.",
  REQUEST_MODE_MISSING: "Manca la modalità (presenza o online).",
};
const live = (r: Run) => ["QUEUED", "RUNNING", "CANCEL_REQUESTED"].includes(r.status);
const hours = (m: number) => String(Math.round(m / 6) / 10).replace(".", ",");
const span = (s: number) => (s >= 3600 ? `${String(Math.round(s / 360) / 10).replace(".", ",")} h` : s >= 60 ? `${Math.round(s / 60)} min` : `${Math.round(s)} s`);
const reqOf = (key: string) => key.split("/")[0].replace(/^req:/, "");
const mins = (t: unknown) => { const [h, m] = String(t || "0:0").split(":").map(Number); return h * 60 + (m || 0); };
const hhmm = (m: number) => `${Math.floor(m / 60)}:${String(m % 60).padStart(2, "0")}`;
function room(a?: ReqAn): [string, Tone] | null {
  if (!a) return null;
  const n = a.min_options ?? 0;
  return !n ? ["Nessun orario", "red"] : n <= 3 ? ["Pochi orari", "amber"] : n <= 15 ? ["Margine medio", "blue"] : ["Margine ampio", "green"];
}
const Pill = ({ tone, children }: { tone: Tone; children: ReactNode }) => <span className={"pv-pill " + tone}>{children}</span>;
const Dot = ({ tone, icon }: { tone: Tone; icon: IconName }) => <span className={"pv-dot " + tone} aria-hidden><Icon n={icon} /></span>;

function WeekStrip({ wins, tone }: { wins: Win[]; tone: Tone }) {
  const A = 8 * 60, B = 21 * 60;
  return <span className="pv-strip" role="img" aria-label={wins.length ? "Fasce: " + wins.map((w) => `${WD_SHORT[w.weekday]} ${hhmm(w.start)}–${hhmm(w.end)}`).join(", ") : "Nessuna fascia"}>
    {WD_SHORT.map((d, i) => <span key={i} className="pv-day"><span className="pv-col">{wins.filter((w) => w.weekday === i).map((w, k) => {
      const s = Math.max(A, w.start), e = Math.min(B, w.end); if (e <= s) return null;
      return <i key={k} className={tone} style={{ top: ((s - A) / (B - A)) * 100 + "%", height: ((e - s) / (B - A)) * 100 + "%" }} />;
    })}</span><small>{d[0]}</small></span>)}
  </span>;
}

export default function Pianificazione() {
  const d = useData(), toast = useToast(), r = useRoute();
  const nextMonday = (() => { const t = todayRome(); return weekday(t) === 0 ? t : addDays(mondayOf(t), 7); })();
  const week = r.q.get("w") || nextMonday, view = r.q.get("vincoli") || "famiglie";
  const [mode, setMode] = useState<"STRICT" | "COVERAGE">("COVERAGE"), [effort, setEffort] = useState<"STANDARD" | "THOROUGH">("THOROUGH");
  const [ov, setOv] = useState<Ov | null>(null), [runs, setRuns] = useState<Run[] | null>(null), [err, setErr] = useState(""), [busy, setBusy] = useState(false);
  const [edit, setEdit] = useState<Req | null | undefined>(undefined), [step, setStep] = useState<number | null>(null), [approving, setApproving] = useState<Req | null>(null);
  const [windows, setWindows] = useState<Row[] | null>(null), [closures, setClosures] = useState<Row[]>([]), [skills, setSkills] = useState<Row[]>([]), [subjects, setSubjects] = useState<Record<string, string>>({});
  const [cfg, setCfg] = useState<{ kind: string; label: string; row: Row | null } | null>(null);
  const pending = useRef<{ key: string; body: string } | null>(null);
  const loadRuns = () => list<Run>("/schedule-runs/").then((rs) => setRuns(rs.filter((x) => !x.result || !!weeklyResult(x.result))));
  const loadOv = () => api<Ov>(`/planning/overview?horizon_start=${week}&mode=${mode}`).then(setOv);
  const loadCenter = () => Promise.all([list<Row>("/service-windows/").then(setWindows), list<Row>("/closures/").then(setClosures)]);
  useEffect(() => {
    loadRuns().catch(() => setRuns([])); loadCenter().catch(() => setWindows([]));
    list<Row>("/tutor-skills/").then(setSkills).catch(() => {});
    list<{ id: string; name: string }>("/subjects/").then((s) => setSubjects(Object.fromEntries(s.map((x) => [x.id, x.name])))).catch(() => {});
  }, []);
  useEffect(() => { setOv(null); setStep(null); loadOv().catch((e) => setErr(human(e).text)); }, [week, mode]); // eslint-disable-line
  const active = (runs || []).some(live);
  useEffect(() => { if (!active) return; const t = window.setInterval(() => loadRuns().catch(() => {}), 4000); return () => window.clearInterval(t); }, [active]);
  const refresh = async () => { await Promise.all([loadOv(), loadRuns(), loadCenter(), d.refresh()]); };

  // ---------- dati derivati ----------
  const weekEnd = addDays(week, 6);
  const inWeek = (x: Record<string, unknown>) => (!x.period_start || String(x.period_start) <= weekEnd) && (!x.period_end || String(x.period_end) >= week);
  const reqs = ov?.requests || [], an = ov?.analysis;
  const pend = reqs.filter((x) => x.status === "PENDING"), approved = reqs.filter((x) => x.status === "APPROVED");
  const names = useMemo(() => Object.fromEntries(reqs.map((x) => [x.id, `${x.subject_name} di ${x.student_name}`])), [reqs]);
  const rulesOf = (k: "student" | "tutor", id: string) => d.rules.filter((x) => x[k] === id && x.status === "APPROVED" && inWeek(x as unknown as Record<string, unknown>)).map((x) => ({ weekday: x.weekday, start: mins(x.start_time), end: mins(x.end_time) }));
  const drafts = d.rules.filter((x) => x.status === "DRAFT"), draftT = drafts.filter((x) => x.tutor).length;
  const weekRuns = (runs || []).filter((x) => !x.horizon_start || x.horizon_start === week);
  const running = weekRuns.find(live), lastDone = weekRuns.find((x) => x.status === "SUCCEEDED" && x.result && x.result.validation.status === "PASSED");

  type Item = { key: string; tone: Tone; icon: IconName; title: string; sub?: string; actions?: ReactNode };
  const fix: Item[] = [], decide: Item[] = [], watch: Item[] = [];
  const editBtn = (id?: string) => { const x = reqs.find((q) => q.id === id && !q.derived); return x ? <Btn kind="sm" onClick={() => setEdit(x)}>Correggi</Btn> : undefined; };
  for (const i of ov?.issues || []) fix.push({ key: "i" + i.code, tone: "red", icon: "x", title: i.request_id && names[i.request_id] ? names[i.request_id] : "Dati del centro", sub: i.message, actions: editBtn(i.request_id) });
  for (const x of approved.filter((q) => q.problems.some((p) => p !== "PREFERRED_TUTOR_NOT_COMPETENT"))) fix.push({ key: "p" + x.id, tone: "red", icon: "x", title: names[x.id], sub: x.problems.map((p) => PROBLEM[p] || p).join(" "), actions: editBtn(x.id) });
  for (const x of pend) decide.push({ key: "q" + x.id, tone: "blue", icon: "book", title: names[x.id], sub: [KIND[x.kind || "WEEKLY"][0], whenText(x), `${x.duration_minutes} min`, modeText(x.mode), x.kind === "SERIES" || x.tutor_choice !== "ANY" ? tutorText(x) : "", x.notes ? `«${x.notes}»` : ""].filter(Boolean).join(" · "),
    actions: <><Btn kind="sm ghost" onClick={() => setEdit(x)}>Modifica</Btn><Btn kind="sm ghost" onClick={() => act(x, "reject")}>Rifiuta</Btn><Btn kind="sm approve" icon="check" onClick={() => act(x, "approve")}>{needsTutor(x) ? "Scegli tutor e approva" : "Approva"}</Btn></> });
  if (drafts.length) decide.push({ key: "d", tone: "violet", icon: "clock", title: plural(drafts.length, "fascia di disponibilità", "fasce di disponibilità"), sub: [drafts.length - draftT ? `${drafts.length - draftT} dalle famiglie` : "", draftT ? `${draftT} dai tutor` : ""].filter(Boolean).join(" e ") + ": il motore usa solo quelle approvate.", actions: <Btn kind="sm" onClick={() => go("disponibilita", { f: "DRAFT" })}>Rivedi le fasce</Btn> });
  for (const x of approved.filter((q) => q.problems.includes("PREFERRED_TUTOR_NOT_COMPETENT"))) watch.push({ key: "w" + x.id, tone: "amber", icon: "user", title: names[x.id], sub: PROBLEM.PREFERRED_TUTOR_NOT_COMPETENT });
  for (const s of (an?.students || []).filter((s) => s.demand_minutes > s.available_minutes)) watch.push({ key: "s" + s.id, tone: "amber", icon: "user", title: `${s.display_name} è libero meno ore di quelle richieste`, sub: `${hours(s.demand_minutes)} h di lezioni, ${hours(s.available_minutes)} h di disponibilità.`, actions: <Btn kind="sm ghost" onClick={() => go("disponibilita", { nuova: "1", chi: "student:" + s.id })}>Aggiungi fascia</Btn> });
  for (const x of approved.filter((q) => !q.problems.length && room(an?.requests[q.id])?.[1] === "amber")) watch.push({ key: "t" + x.id, tone: "amber", icon: "clock", title: `${names[x.id]}: pochi orari possibili`, sub: `Solo ${plural(an!.requests[x.id].slots, "orario compatibile", "orari compatibili")} tra studente, tutor e aperture.` });

  // ---------- passi ----------
  const reviewDone = !fix.length && !decide.length;
  const calcDone = !!lastDone && !lastDone.stale;
  const current = !reviewDone ? 1 : !calcDone || running ? 2 : 3;
  const shown = step ?? current;
  const canRun = !!ov?.ready && !!ov.planning_enabled && !!ov.policy?.approved_for_exploration && !busy && !fix.length;

  async function act(x: Req, a: "approve" | "reject") {
    if (a === "approve" && needsTutor(x)) { setApproving(x); return; }
    try { await review(x.id, a); toast(a === "approve" ? "Richiesta approvata." : "Richiesta rifiutata."); await refresh(); } catch (e) { toast(human(e).text); }
  }
  async function start() {
    if (!ov?.ready || ov.revision === undefined || !ov.policy) return;
    const body = JSON.stringify({ policy_id: ov.policy.id, horizon_start: week, expected_revision: ov.revision, mode, ...(effort === "THOROUGH" ? { effort } : {}) });
    if (!pending.current || pending.current.body !== body) pending.current = { key: crypto.randomUUID(), body };
    setBusy(true); setErr("");
    try {
      await api("/schedule-runs", { method: "POST", headers: { "Idempotency-Key": pending.current.key }, body });
      pending.current = null; await loadRuns(); setStep(null);
      toast(effort === "THOROUGH" ? "Calcolo accurato avviato. Puoi chiudere la pagina: il risultato resta qui." : "Calcolo avviato.");
    } catch (e) { const h = human(e); setErr(h.text); if (!h.retry) pending.current = null; } finally { setBusy(false); }
  }
  async function cancel(x: Run) {
    try { await api(`/schedule-runs/${x.id}/cancel/`, { method: "POST", body: "{}" }); await loadRuns(); toast("Annullamento richiesto."); } catch (e) { toast(human(e).text); }
  }

  // ---------- «Prossimo passo» ----------
  let hero: { tone: Tone; icon: IconName; title: string; text: string; action?: ReactNode };
  if (!ov) hero = { tone: "blue", icon: "clock", title: "Controllo i dati della settimana…", text: "" };
  else if (fix.length) hero = { tone: "red", icon: "x", title: fix.length === 1 ? "Una cosa impedisce il calcolo" : `${fix.length} cose impediscono il calcolo`, text: "Correggile e il motore potrà partire.", action: <Btn kind="primary" onClick={() => { setStep(1); document.getElementById("pv-fix")?.scrollIntoView({ behavior: "smooth" }); }}>Vedi cosa correggere</Btn> };
  else if (decide.length) hero = { tone: "blue", icon: "check", title: `${plural(pend.length + drafts.length, "richiesta aspetta", "richieste aspettano")} la tua approvazione`, text: [pend.length ? plural(pend.length, "richiesta di lezioni", "richieste di lezioni") : "", drafts.length ? plural(drafts.length, "fascia di disponibilità", "fasce di disponibilità") : ""].filter(Boolean).join(" e ") + ". Puoi anche calcolare subito: verranno ignorate.", action: <Btn kind="primary" onClick={() => setStep(1)}>Rivedi le richieste</Btn> };
  else if (running) hero = { tone: "blue", icon: "clock", title: "Il motore sta calcolando l’orario", text: (running.budget_seconds || 0) > 30 ? "Calcolo accurato: puoi chiudere la pagina, il risultato resta qui." : "Ci vuole meno di un minuto.", action: <Btn kind="ghost" onClick={() => setStep(2)}>Vedi l’avanzamento</Btn> };
  else if (calcDone && lastDone?.result) { const u = lastDone.result.unassigned.length; hero = { tone: u ? "amber" : "green", icon: "cal", title: u ? `Proposta pronta: ${plural(u, "lezione resta", "lezioni restano")} senza posto` : "Proposta pronta: tutte le lezioni hanno un posto", text: "Controllala nell’Agenda e pubblicala: solo allora le famiglie la vedono.", action: <Btn kind="primary" isle="arrow" onClick={() => go("agenda", { d: week })}>Rivedi e pubblica</Btn> }; }
  else hero = { tone: "green", icon: "spark", title: "Dati pronti: puoi calcolare l’orario", text: an ? `${plural(an.units, "lezione", "lezioni")} da collocare in ${hours(an.service_minutes)} h di apertura.` : "", action: <Btn kind="primary" isle="spark" disabled={!canRun} onClick={start}>{busy ? "Avvio…" : `Avvia il calcolo ${effort === "THOROUGH" ? "accurato" : "rapido"}`}</Btn> };

  const STEPS: [number, string, string][] = [
    [1, "Rivedi", reviewDone ? "Tutto in ordine" : fix.length ? plural(fix.length, "da correggere", "da correggere") : plural(pend.length + drafts.length, "da decidere", "da decidere")],
    [2, "Calcola", running ? "In corso" : calcDone ? "Fatto" : lastDone?.stale ? "Da rifare: dati cambiati" : "Da avviare"],
    [3, "Pubblica", calcDone ? "Proposta pronta" : "Dopo il calcolo"],
  ];
  const stateOf = (n: number) => (n === 1 ? reviewDone : n === 2 ? calcDone && !running : false) ? "done" : n === current ? "now" : "next";

  return <div className="pv">
    <header className="pv-head">
      <div><h1 className="h-display">Pianificazione</h1><p>Settimana dal {dateLong(week)} al {dateLong(weekEnd)}</p></div>
      <div className="pv-head-act">
        <DateField label="Settimana" value={week} placeholder="Scegli un lunedì" disabled={(x) => weekday(x) !== 0} onChange={(x) => setQuery((q) => (x === nextMonday ? q.delete("w") : q.set("w", x)))} />
        <Btn kind="sm" icon="plus" onClick={() => setEdit(null)}>Nuova richiesta</Btn>
      </div>
    </header>

    <section className={"pv-hero " + hero.tone} aria-live="polite">
      <Dot tone={hero.tone} icon={hero.icon} />
      <div className="pv-hero-txt"><small>Prossimo passo</small><h2>{hero.title}</h2>{hero.text && <p>{hero.text}</p>}</div>
      {hero.action && <div className="pv-hero-act">{hero.action}</div>}
    </section>
    {err && <p className="pv-err">{err}</p>}

    <nav className="pv-steps" aria-label="Passi">{STEPS.map(([n, t, s]) => <button key={n} type="button" className={"pv-step " + stateOf(n) + (shown === n ? " open" : "")} aria-current={shown === n ? "step" : undefined} onClick={() => setStep(n)}>
      <span className="pv-num">{stateOf(n) === "done" ? <Icon n="check" /> : n}</span><span><b>{t}</b><small>{s}</small></span>
    </button>)}</nav>

    {!ov ? <section className="module"><Skeleton rows={4} /></section> : <>
      {shown === 1 && <>
        {fix.length > 0 && <Group id="pv-fix" title="Da correggere" note="Senza queste correzioni il calcolo non parte." items={fix} />}
        {decide.length > 0 && <Group title="Da decidere" note="Inviate da famiglie e tutor. Il motore usa solo ciò che approvi." items={decide} count={pend.length + drafts.length} />}
        {!fix.length && !decide.length && <section className="module pv-clear"><Dot tone="green" icon="check" /><div><b>Niente da correggere o approvare</b><small>Puoi passare al calcolo.</small></div><Btn kind="sm" isle="arrow" onClick={() => setStep(2)}>Vai al calcolo</Btn></section>}
        {watch.length > 0 && <Group title="Da tenere d’occhio" note="Non bloccano il calcolo, ma possono lasciare lezioni senza posto." items={watch} quiet />}
        <Constraints />
      </>}
      {shown === 2 && <section className="module pv-calc">
        <h2 className="m-title">Calcola l’orario</h2>
        {an && <p className="pv-lead">{plural(an.units, "lezione", "lezioni")} da collocare ({hours(an.demand_minutes)} h) in {hours(an.service_minutes)} h di apertura, scegliendo tra {num(an.candidates)} combinazioni di orario, tutor e aula.</p>}
        <div className="pv-opts">
          <div><span className="pv-lbl">Durata del calcolo</span>
            <div className="pv-effort" role="radiogroup" aria-label="Durata del calcolo">
              {([["THOROUGH", "moon", "Accurato", `Fino a ${span(ov.thorough.budget_seconds)}. Da lanciare la sera.`], ["STANDARD", "spark", "Rapido", `Circa ${span(ov.policy?.budget_seconds || 3)}. Per una prima idea.`]] as const).map(([k, ic, t, s]) =>
                <label key={k} className={"pv-eff" + (effort === k ? " on" : "")}><input type="radio" name="effort" checked={effort === k} onChange={() => setEffort(k)} /><Icon n={ic} /><span><b>{t}</b><small>{s}</small></span></label>)}
            </div></div>
          <div><span className="pv-lbl">Se non c’è posto per tutti</span><SegCtl label="Copertura" value={mode} onChange={setMode} options={[["COVERAGE", "Colloca il più possibile"], ["STRICT", "Nessuna proposta"]]} /></div>
        </div>
        <div className="pv-go">
          <Btn kind="primary" isle="spark" disabled={!canRun} onClick={start}>{busy ? "Avvio…" : `Avvia il calcolo ${effort === "THOROUGH" ? "accurato" : "rapido"}`}</Btn>
          <small>{!ov.planning_enabled ? "Il calcolo è spento in questo ambiente." : ov.policy && !ov.policy.approved_for_exploration ? `La regola «${ov.policy.name}» non è abilitata in Configurazione.` : fix.length ? "Prima correggi i punti segnalati nel passo 1." : "Ordine del motore: obbligatorie e priorità, equità, tutor preferiti, meno buchi."}</small>
        </div>
        {weekRuns.length > 0 && <div className="pv-runs"><h3>Calcoli di questa settimana</h3>{weekRuns.slice(0, 4).map((x) => <RunRow key={x.id} x={x} names={names} onCancel={() => cancel(x)} />)}</div>}
      </section>}
      {shown === 3 && <section className="module pv-pub">
        <h2 className="m-title">Pubblica</h2>
        {!lastDone?.result ? <Empty title="Ancora nessuna proposta per questa settimana" /> : <>
          <div className="pv-score"><b>{lastDone.result.assignments.length}</b><span>di {lastDone.result.assignments.length + lastDone.result.unassigned.length} lezioni collocate{lastDone.result.solver_status === "OPTIMAL" ? " · soluzione ottima" : ""}{lastDone.stale ? " · i dati sono cambiati dopo il calcolo" : ""}</span></div>
          {lastDone.result.unassigned.length > 0 && <ul className="pv-list">{[...new Set(lastDone.result.unassigned.map((u) => reqOf(u.demand_key)))].map((id) => { const u = lastDone.result!.unassigned.find((x) => reqOf(x.demand_key) === id)!; return <li key={id}><Dot tone="amber" icon="x" /><span className="pv-txt"><b>{names[id] || "Richiesta"}</b><small>{reasonText(u.reason_codes)}</small></span>{editBtn(id)}</li>; })}</ul>}
          <div className="pv-go"><Btn kind="primary" isle="arrow" onClick={() => go("agenda", { d: week })}>Rivedi e pubblica nell’Agenda</Btn><small>Le lezioni nascono solo alla pubblicazione; le non collocate le accetti esplicitamente.</small></div>
        </>}
      </section>}
    </>}

    <RequestModal open={edit !== undefined} edit={edit || null} onClose={() => setEdit(undefined)} onSaved={async () => { setEdit(undefined); toast("Richiesta salvata."); await refresh(); }} />
    <ApproveModal req={approving} onClose={() => setApproving(null)} onDone={async () => { setApproving(null); toast("Richiesta approvata."); await refresh(); }} />
    <JsonModal v={cfg ? { row: cfg.row } : null} kind={cfg?.kind || "service-windows"} label={cfg?.label || "Apertura"} onClose={() => setCfg(null)} onSaved={async (msg) => { setCfg(null); toast(msg); await refresh(); }} />
  </div>;

  // ---------- sotto-componenti con accesso ai dati ----------
  function Group({ id, title, note, items, quiet, count }: { id?: string; title: string; note: string; items: Item[]; quiet?: boolean; count?: number }) {
    return <section id={id} className={"module pv-group" + (quiet ? " quiet" : "")}>
      <div className="pv-ghead"><h2 className="m-title">{title} <span className="pv-n">{count ?? items.length}</span></h2><p>{note}</p></div>
      <ul className="pv-list">{items.map((i) => <li key={i.key}><Dot tone={i.tone} icon={i.icon} /><span className="pv-txt"><b>{i.title}</b>{i.sub && <small>{i.sub}</small>}</span>{i.actions && <span className="pv-act">{i.actions}</span>}</li>)}</ul>
    </section>;
  }
  function Constraints() {
    const students = (() => {
      const by = new Map<string, { id: string; name: string; reqs: OvReq[] }>();
      for (const x of approved) { const id = x.student || x.id; if (!by.has(id)) by.set(id, { id, name: x.student_name || "Studente", reqs: [] }); by.get(id)!.reqs.push(x); }
      return [...by.values()].sort((a, b) => a.name.localeCompare(b.name));
    })();
    const ids = new Set([...(an?.tutors || []).map((t) => t.id), ...skills.filter((s) => s.approved).map((s) => String(s.tutor))]);
    const tutors = d.tutors.filter((t) => ids.has(t.id));
    const sw = (windows || []).filter((w) => inWeek(w)), cl = closures.filter((c) => String(c.end_at) >= week && String(c.start_at) <= weekEnd + "T23:59");
    return <section className="module pv-cons" aria-labelledby="h-cons">
      <div className="pv-ghead row"><div><h2 className="m-title" id="h-cons">Vincoli della settimana</h2></div>
        <SegCtl label="Vincoli" value={view} onChange={(v) => setQuery((q) => (v === "famiglie" ? q.delete("vincoli") : q.set("vincoli", v)))} options={[["famiglie", "Famiglie"], ["tutor", "Tutor"], ["centro", "Orari del centro"]]} /></div>

      {view === "famiglie" && (!students.length ? <Empty title="Nessuna richiesta approvata" /> : <div className="pv-table">
        <div className="pv-th"><span>Studente</span><span>Disponibilità</span><span>Richieste</span></div>
        {students.map((s) => { const st = an?.students.find((x) => x.id === s.id); return <div key={s.id} className="pv-tr">
          <div className="pv-who"><Avatar name={s.name} k={s.id} /><div><b>{s.name}</b><small>{st ? `${hours(st.available_minutes)} h libere · ${hours(st.demand_minutes)} h richieste` : "—"}</small></div></div>
          <button type="button" className="pv-stripbtn" title="Apri le disponibilità" onClick={() => go("disponibilita", { chi: "student:" + s.id })}><WeekStrip wins={rulesOf("student", s.id)} tone="green" /></button>
          <div className="pv-reqs">{s.reqs.map((x) => { const m = room(an?.requests[x.id]); return <button type="button" key={x.id} className="pv-req" disabled={x.derived} onClick={() => setEdit(x)}>
            <span><b>{x.subject_name}</b><small>{x.sessions_per_week} × {x.duration_minutes} min · {modeText(x.mode)}{x.tutor_choice !== "ANY" ? " · " + tutorText(x) : ""}{x.mandatory ? " · obbligatoria" : ""}</small></span>{m && <Pill tone={m[1]}>{m[0]}</Pill>}
          </button>; })}</div>
        </div>; })}
      </div>)}

      {view === "tutor" && (!tutors.length ? <Empty title="Nessun tutor con competenze approvate" /> : <div className="pv-table">
        <div className="pv-th"><span>Tutor</span><span>Disponibilità</span><span>Carico possibile</span></div>
        {tutors.map((t) => { const a = an?.tutors.find((x) => x.id === t.id); const cap = a ? Math.min(a.available_minutes, a.weekly_limit_minutes ?? Infinity) : 0; const pct = cap && a ? Math.min(100, Math.round((a.eligible_demand_minutes / cap) * 100)) : 0;
          const subj = [...new Set(skills.filter((s) => s.approved && s.tutor === t.id).map((s) => subjects[String(s.subject)]).filter(Boolean))];
          const bound = approved.filter((x) => x.tutor_choice !== "ANY" && x.preferred_tutors?.some((p) => p.id === t.id));
          return <div key={t.id} className="pv-tr">
            <div className="pv-who"><Avatar name={t.display_name} k={t.id} /><div><b>{t.display_name}</b><small>{subj.join(", ") || "Nessuna competenza approvata"}</small></div></div>
            <button type="button" className="pv-stripbtn" title="Apri le disponibilità" onClick={() => go("disponibilita", { chi: "tutor:" + t.id })}><WeekStrip wins={rulesOf("tutor", t.id)} tone="blue" /></button>
            <div className="pv-load">{a ? <><span className="pv-meter"><i className={pct >= 100 ? "red" : pct >= 70 ? "amber" : "blue"} style={{ width: Math.max(pct, 3) + "%" }} /></span><small>{hours(a.eligible_demand_minutes)} h di richieste che può coprire su {hours(cap)} h</small></> : <small>Non coinvolto questa settimana</small>}
              {bound.length > 0 && <span className="pv-tags">{bound.map((x) => <Pill key={x.id} tone={x.tutor_choice === "REQUIRED" ? "violet" : "blue"}>{x.tutor_choice === "REQUIRED" ? "Obbligatorio" : "Preferito"} per {x.student_name?.split(" ")[0]}</Pill>)}</span>}</div>
          </div>; })}
      </div>)}

      {view === "centro" && (!windows ? <Skeleton /> : <div className="pv-center">
        <div className="pv-ctl"><span className="pv-legend"><span><i />In presenza</span><span><i className="violet" />Online</span><span><i className="red" />Chiuso</span></span>
          <Btn kind="sm" icon="plus" onClick={() => setCfg({ kind: "service-windows", label: "Apertura", row: null })}>Apertura</Btn><Btn kind="sm" icon="plus" onClick={() => setCfg({ kind: "closures", label: "Chiusura", row: null })}>Chiusura</Btn></div>
        {!sw.length ? <Empty title="Nessuna apertura in questa settimana" /> : <div className="pv-tl">
          <div className="pv-tl-row axis" aria-hidden><span /><span className="pv-tl-scale">{[8, 10, 12, 14, 16, 18, 20].map((h) => <small key={h} style={{ left: ((h - 7) / 15) * 100 + "%" }}>{h}:00</small>)}</span></div>
          {WD_SHORT.map((dn, i) => { const day = addDays(week, i), off = cl.filter((c) => String(c.start_at).slice(0, 10) <= day && String(c.end_at).slice(0, 10) >= day); const ws = sw.filter((w) => Number(w.weekday) === i);
            return <div key={i} className="pv-tl-row"><b>{dn}</b><span className="pv-tl-track">
              {ws.map((w) => { const s = mins(w.start_time), e = mins(w.end_time), on = w.mode === "ONLINE"; return <button type="button" key={w.id} className={"pv-tl-bar" + (on ? " online" : "")} style={{ left: ((s - 420) / 900) * 100 + "%", width: ((e - s) / 900) * 100 + "%" }} title={`${on ? "Online" : "In presenza"} ${hhmm(s)}–${hhmm(e)}: modifica`} onClick={() => setCfg({ kind: "service-windows", label: "Apertura", row: w })}>{on ? "" : `${hhmm(s)}–${hhmm(e)}`}</button>; })}
              {off.map((c) => <button type="button" key={c.id} className="pv-tl-off" onClick={() => setCfg({ kind: "closures", label: "Chiusura", row: c })}>Chiuso · {String(c.reason)}</button>)}
            </span></div>; })}
        </div>}
      </div>)}
    </section>;
  }
}

function RunRow({ x, names, onCancel }: { x: Run; names: Record<string, string>; onCancel: () => void }) {
  const thorough = (x.budget_seconds || 0) > 30, res = x.result;
  const [now, setNow] = useState(Date.now());
  useEffect(() => { if (x.status !== "RUNNING") return; const t = window.setInterval(() => setNow(Date.now()), 5000); return () => window.clearInterval(t); }, [x.status]);
  const elapsed = x.started_at ? (now - new Date(x.started_at).getTime()) / 1000 : 0;
  const pct = x.status === "RUNNING" && x.budget_seconds ? Math.min(99, Math.round((elapsed / x.budget_seconds) * 100)) : 0;
  const un = res?.unassigned || [], byReq = [...new Set(un.map((u) => reqOf(u.demand_key)))];
  const [tone, label]: [Tone, string] = live(x) ? ["blue", x.status === "QUEUED" ? "In coda" : "In corso"] : x.status === "SUCCEEDED" && res ? (un.length ? ["amber", "Parziale"] : ["green", "Completo"]) : x.status === "CANCELLED" ? ["violet", "Annullato"] : ["red", "Non riuscito"];
  return <div className="pv-run">
    <div className="pv-txt"><b>{thorough ? "Accurato" : "Rapido"} <Pill tone={tone}>{label}</Pill></b>
      <small>{x.status === "RUNNING" ? `${span(elapsed)} trascorsi, al massimo ${span(x.budget_seconds || 0)}` : res ? `${plural(res.assignments.length, "lezione collocata", "lezioni collocate")}${un.length ? `, ${un.length} senza posto` : ""}` : x.error_code ? "Nessuna proposta prodotta" : "In attesa"}{x.stale ? " · dati cambiati: ricalcola" : ""}</small>
      {pct > 0 && <span className="pv-meter thin"><i className="blue" style={{ width: pct + "%" }} /></span>}
      {byReq.length > 0 && <small>Senza posto: {byReq.slice(0, 3).map((id) => names[id] || "richiesta").join(", ")}{byReq.length > 3 ? ` e altre ${byReq.length - 3}` : ""}</small>}
      <Tech><code>{x.id} · {x.status}/{x.phase}{x.error_code ? " · " + x.error_code : ""}{res ? ` · ${res.solver_status} · validatore ${res.validation.status}` : ""}</code></Tech>
    </div>
    {["QUEUED", "RUNNING"].includes(x.status) && <Btn kind="sm ghost" onClick={onCancel}>Annulla</Btn>}
  </div>;
}
