/** Disponibilità settimanali sul calendario: si disegnano trascinando, si spostano e si allungano
 *  come gli impegni. Le nuove fasce dei portali restano in bozza finché il centro non le approva. */
import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { addDays, dateLong, duration, hm, plural, todayRome, WD_LONG, WD_SHORT } from "../format";
import { human, LOCATION, MODE } from "../messages";
import { Avatar, Btn, Empty, Icon, Notice, PageHead, Skeleton, Tag } from "../ui/core";
import { Combo, ComboItem, DateField, Field, SegCtl, Wheel } from "../ui/controls";
import { GuardFoot, useDirtyGuard, Modal, useToast } from "../ui/layers";
import { setQuery, useRoute } from "../ui/route";
import { PlanBlock, Slot, SlotDialog, span, toMin, WeekPlanner } from "../ui/WeekPlanner";
import { Rule, subjectName, useData } from "../app/data";
import { useOverview } from "../portal/data";

const STEPS = Array.from({ length: 61 }, (_, i) => 7 * 60 + i * 15); // 07:00–22:00
type Mode = "IN_PERSON" | "ONLINE";
const end = (m: number) => (m >= 1440 ? "23:59" : hm(m));
const slotOf = (x: Rule): Slot => ({ weekday: x.weekday, start: toMin(x.start_time), end: toMin(x.end_time) });
const whenOf = (x: Rule) => `${WD_LONG[x.weekday].toLowerCase()} ${x.start_time.slice(0, 5)}–${x.end_time.slice(0, 5)}`;

export default function Disponibilita() {
  const d = useData(), r = useRoute(), toast = useToast();
  // Portali: si propone solo per chi la delega lo consente (GAP-G01, sola lettura senza delega).
  const ov = useOverview(undefined, !d.center), o = d.center ? null : ov.data;
  const allow = d.center ? null : new Set([...(o?.tutor ? ["tutor:" + o.tutor.tutor_id] : []), ...(o?.children || []).filter((c) => c.permissions.can_manage_availability).map((c) => "student:" + c.student_id)]);
  const canAdd = d.center || (allow?.size || 0) > 0;
  const formOpen = r.q.get("nuova") === "1" && canAdd;
  const people: ComboItem[] = useMemo(() => [
    ...d.students.map((s) => ({ id: "student:" + s.id, label: s.display_name, sub: `Studente${s.level ? ", " + s.level : ""}` })),
    ...d.tutors.map((t) => ({ id: "tutor:" + t.id, label: t.display_name, sub: "Tutor" })),
  ].filter((p) => !allow || allow.has(p.id)), [d.students, d.tutors, allow]); // eslint-disable-line react-hooks/exhaustive-deps
  const chi = r.q.get("chi");
  const who = people.find((p) => p.id === chi) || (!d.center && people.length === 1 ? people[0] : null);
  const [mode, setMode] = useState<Mode>("IN_PERSON");
  const [hours, setHours] = useState<Slot[]>([]);
  useEffect(() => { api<{ opening_hours: { weekday: number; start: string; end: string }[] }>("/planner/opening-hours").then((x) => setHours(x.opening_hours.map((h) => ({ weekday: h.weekday, start: toMin(h.start), end: toMin(h.end) })))).catch(() => undefined); }, []);
  const [year, setYear] = useState<{ start_date: string; end_date: string; name: string } | null | undefined>(undefined);
  useEffect(() => { api<{ start_date: string; end_date: string; name: string } | null>("/planning/school-years/current").then(setYear).catch(() => setYear(null)); }, []);
  const [pick, setPick] = useState<Rule | null>(null), [busy, setBusy] = useState(false);
  const today = todayRome(), from = year?.start_date && year.start_date > today ? year.start_date : today, until = year?.end_date && year.end_date > from ? year.end_date : addDays(from, 180);
  const drafts = d.rules.filter((x) => x.status === "DRAFT");
  const [type, id] = (who?.id || ":").split(":");
  const mine = d.rules.filter((x) => (type === "student" ? x.student : x.tutor) === id && x.status !== "REVOKED" && (x.mode || "IN_PERSON") === mode);
  const editable = !!who && (d.center || !!allow?.has(who.id));
  const blocks: PlanBlock[] = mine.map((x) => ({ ...slotOf(x), id: x.id, label: x.status === "DRAFT" ? "In bozza" : "Disponibile", sub: x.status === "DRAFT" ? (d.center ? "Da approvare" : "In attesa del centro") : undefined, tone: x.status === "DRAFT" ? "amber" : "green", draft: x.status === "DRAFT", locked: !d.center }));
  const withPeople = useMemo(() => people.map((p) => ({ p, n: d.rules.filter((x) => x.status !== "REVOKED" && ("student:" + x.student === p.id || "tutor:" + x.tutor === p.id)).length })).filter((x) => x.n), [people, d.rules]);

  const review = (x: Rule, status: "approve" | "revoke") => api<Rule>(`/availability-rules/${x.id}/${status}/`, { method: "POST", body: JSON.stringify({ expected_version: x.version }) });
  const post = (s: Slot, base?: Rule) => api<Rule>("/availability-rules/", { method: "POST", body: JSON.stringify({ [type]: id, weekday: s.weekday, start_time: hm(s.start), end_time: end(s.end), period_start: base?.period_start || from, period_end: base?.period_end || until, timezone: "Europe/Rome", mode: base?.mode || mode, location: base?.location || (mode === "ONLINE" ? "REMOTE" : "ON_SITE") }) });
  async function run(job: () => Promise<unknown>, msg: string) {
    setBusy(true);
    try { await job(); toast(msg); } catch (x) { toast(human(x).text); } finally { await d.refresh(); setBusy(false); }
  }
  // Il centro approva subito ciò che disegna; i portali inviano una bozza.
  const create = (s: Slot) => run(async () => { const n = await post(s); if (d.center) await review(n, "approve"); }, d.center ? `Disponibilità aggiunta: ${WD_LONG[s.weekday].toLowerCase()} ${span(s)}` : "Fascia inviata al centro: resta in bozza finché non viene approvata");
  // Le fasce non si modificano: spostarne una ne crea una nuova (stesso stato) e revoca la vecchia.
  const move = (x: Rule, s: Slot) => run(async () => { const n = await post(s, x); if (x.status === "APPROVED") await review(n, "approve"); await review(x, "revoke"); }, `Disponibilità spostata: ${WD_LONG[s.weekday].toLowerCase()} ${span(s)}`);
  const approveAll = () => run(() => api("/availability/bulk-review", { method: "POST", body: JSON.stringify({ ids: drafts.map((x) => x.id), status: "APPROVED" }) }), `${plural(drafts.length, "disponibilità approvata", "disponibilità approvate")}`);

  return <section className="module planner" aria-labelledby="h-av">
    <PageHead id="h-av" title="Disponibilità">
      {canAdd ? <Btn kind="primary" isle="plus" onClick={() => setQuery((x) => { x.set("nuova", "1"); if (who) x.set("chi", who.id); })}>Nuova disponibilità</Btn> : o && <span className="tag plain" title="La delega non consente di proporre disponibilità">Sola lettura</span>}
    </PageHead>
    {d.center && drafts.length > 0 && <div className="card" style={{ marginBottom: 14 }}>
      <div className="oc-head"><span className="oc-ic amber"><Icon n="clock" /></span><div><h2>Da approvare</h2><p className="muted">{plural(drafts.length, "fascia inviata", "fasce inviate")} da famiglie e tutor. Finché sono in bozza il pianificatore non le usa.</p></div>
        {drafts.length > 1 && <Btn kind="primary" isle="check" disabled={busy} onClick={approveAll}>Approva tutte</Btn>}</div>
      <ul className="av-queue">{drafts.slice(0, 8).map((x) => { const name = subjectName(d, x); return <li key={x.id}>
        <Avatar name={name} k={x.student || x.tutor || ""} />
        <div><b>{name}</b><small>{whenOf(x)} · {MODE[x.mode || ""] || "In sede"}{x.period_start ? ` · dal ${dateLong(x.period_start)}` : ""}</small></div>
        <span className="av-acts"><button type="button" className="pill-btn sm ghost" onClick={() => { setMode((x.mode || "IN_PERSON") as Mode); setQuery((q) => q.set("chi", (x.student ? "student:" + x.student : "tutor:" + x.tutor))); }}>Vedi</button>
        <button type="button" className="pill-btn sm ghost" disabled={busy} onClick={() => run(() => review(x, "revoke"), "Fascia respinta")}>Respingi</button>
        <button type="button" className="pill-btn sm" disabled={busy} onClick={() => run(() => review(x, "approve"), "Fascia approvata")}><Icon n="check" />Approva</button></span>
      </li>; })}</ul>
      {drafts.length > 8 && <p className="fine">Altre {drafts.length - 8} in coda.</p>}
    </div>}
    <div className="card">
      <div className="av-top">
        <Field label="Persona" id="av-who"><Combo id="av-who" value={who} items={people} placeholder="Cerca uno studente o un tutor…" onPick={(x) => setQuery((q) => (x ? q.set("chi", x.id) : q.delete("chi")))} /></Field>
        <SegCtl<Mode> label="Modalità" value={mode} onChange={setMode} options={[["IN_PERSON", "In sede"], ["ONLINE", "Online"]]} />
      </div>
      {!d.loaded || year === undefined ? <Skeleton /> : !who ? <>
        <Empty title="Scegli una persona" />
        {withPeople.length > 0 && <div className="chips" role="group" aria-label="Persone con disponibilità">{withPeople.slice(0, 24).map(({ p, n }) => <button key={p.id} type="button" className="chip" onClick={() => setQuery((q) => q.set("chi", p.id))}>{p.label} · {n}</button>)}</div>}
      </> : <>
        <WeekPlanner label={`Disponibilità di ${who.label} ${mode === "ONLINE" ? "online" : "in sede"}`} blocks={blocks} bands={hours} editable={editable && !busy} newLabel="Disponibile"
          onCreate={create} onChange={(bid, s) => { const x = mine.find((y) => y.id === bid); if (x) move(x, s); }}
          onPick={(b) => { const x = mine.find((y) => y.id === b.id); if (!x) return; if (d.center) setPick(x); else toast(x.status === "DRAFT" ? "Fascia in attesa di approvazione del centro" : "Fascia approvata: per cambiarla scrivi al centro"); }}
          emptyText={editable ? undefined : "Nessuna fascia: ciò che manca non è mai considerato libero."} />
        <div className="imp-legend"><span><i className="lg" />Centro aperto</span><span><i className="lg hatch" />Centro chiuso</span><span><i className="lg green" />Disponibile</span><span><i className="lg draft" />In bozza</span>
          <span className="muted">Nuove fasce valide {year && year.end_date > from ? `per l’anno ${year.name}` : "per i prossimi sei mesi"}</span></div>
      </>}
    </div>
    <SlotDialog slot={pick ? slotOf(pick) : null} title={pick?.status === "DRAFT" ? "Fascia in bozza" : "Disponibilità"} onClose={() => setPick(null)}
      onSave={(s) => { const x = pick!; setPick(null); const o2 = slotOf(x); if (s.weekday !== o2.weekday || s.start !== o2.start || s.end !== o2.end) move(x, s); }}
      onDelete={() => { const x = pick!; setPick(null); run(() => review(x, "revoke"), "Disponibilità eliminata"); }}>
      {pick && <div style={{ marginTop: 12 }}>
        <p className="muted">{pick.period_start ? `Dal ${dateLong(pick.period_start)} al ${dateLong(pick.period_end!)}` : "Senza periodo"} · {MODE[pick.mode || ""] || "In sede"}{pick.location ? `, ${(LOCATION[pick.location] || pick.location).toLowerCase()}` : ""}</p>
        {pick.status === "DRAFT" ? <div className="toolbar"><Tag tone="amber">Da approvare</Tag><Btn kind="sm" icon="check" disabled={busy} onClick={() => { const x = pick; setPick(null); run(() => review(x, "approve"), "Fascia approvata"); }}>Approva</Btn></div> : <Tag tone="green">Approvata</Tag>}
      </div>}
    </SlotDialog>
    <RuleForm open={formOpen} allow={allow} preset={r.q.get("chi")} onClose={() => setQuery((x) => { x.delete("nuova"); })} onSaved={(msg) => { toast(msg); }} />
  </section>;
}

function RuleForm({ open, preset, allow, onClose, onSaved }: { open: boolean; preset: string | null; allow: Set<string> | null; onClose: () => void; onSaved: (m: string) => void }) {
  const d = useData(); const today = todayRome();
  const people: (ComboItem & { kind: string })[] = useMemo(() => [
    ...d.students.map((s) => ({ id: "student:" + s.id, label: s.display_name, sub: `Studente${s.level ? ", " + s.level : ""}`, kind: "student" })),
    ...d.tutors.map((t) => ({ id: "tutor:" + t.id, label: t.display_name, sub: "Tutor", kind: "tutor" })),
  ].filter((p) => !allow || allow.has(p.id)), [d.students, d.tutors, allow]);
  const init = () => ({ who: people.find((p) => p.id === preset) || null, wd: 0, start: 15 * 60, end: 18 * 60, from: today, to: addDays(today, 180), mode: "IN_PERSON", loc: "ON_SITE" });
  const [v, setV] = useState(init), [bad, setBad] = useState<Record<string, string>>({}), [err, setErr] = useState(""), [busy, setBusy] = useState(false), [base, setBase] = useState("");
  useEffect(() => { if (open) { const i = init(); setV(i); setBase(JSON.stringify(i)); setBad({}); setErr(""); g.reset(); } }, [open]); // eslint-disable-line
  const dirty = open && base !== "" && JSON.stringify(v) !== base;
  const g = useDirtyGuard(dirty);
  const set = (p: Partial<typeof v>) => { setV((x) => ({ ...x, ...p })); setBad({}); };
  const remoteBad = v.loc === "REMOTE" && v.mode !== "ONLINE";
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const b: Record<string, string> = {};
    if (!v.who) b.who = "Scegli uno studente o un tutor dall’elenco.";
    if (v.end <= v.start) b.time = "La fine deve essere dopo l’inizio.";
    if (!v.from || !v.to || v.to < v.from) b.period = "Il periodo deve finire dopo l’inizio.";
    setBad(b);
    if (Object.keys(b).length || remoteBad) { document.getElementById(b.who ? "rf-who" : "rf-from")?.focus(); return; }
    const [type, id] = v.who!.id.split(":");
    setBusy(true); setErr("");
    try {
      const n = await api<Rule>("/availability-rules/", { method: "POST", body: JSON.stringify({ [type]: id, weekday: v.wd, start_time: hm(v.start), end_time: hm(v.end), period_start: v.from, period_end: v.to, timezone: "Europe/Rome", mode: v.mode, location: v.loc }) });
      if (d.center) await api(`/availability-rules/${n.id}/approve/`, { method: "POST", body: JSON.stringify({ expected_version: n.version }) });
      await d.refresh(); g.allow(); onClose();
      onSaved(`${d.center ? "Disponibilità aggiunta" : "Disponibilità inviata in bozza"}: ${v.who!.label}, ${WD_LONG[v.wd].toLowerCase()} ${hm(v.start)}–${hm(v.end)}`);
    } catch (x) { setErr(human(x).text); } finally { setBusy(false); }
  }
  const startItems = STEPS.slice(0, -1).map((m) => ({ v: m, label: hm(m) }));
  const endItems = STEPS.slice(1).map((m) => ({ v: m, label: hm(m), busy: m <= v.start }));
  return <Modal open={open} onClose={onClose} guard={g.guard} labelledBy="rf-title"><form onSubmit={submit} noValidate>
    <div className="modal-body">
      <h2 id="rf-title">Nuova disponibilità</h2>
      
      <Field label="Per chi" id="rf-who" error={bad.who}><Combo id="rf-who" value={v.who} items={people} invalid={!!bad.who} placeholder="Cerca uno studente o un tutor…" onPick={(x) => set({ who: x as typeof people[number] | null })} /></Field>
      <Field label="Giorno della settimana"><div className="seg-scroll"><SegCtl label="Giorno" value={String(v.wd)} options={WD_SHORT.map((w, i) => [String(i), w])} onChange={(x) => set({ wd: Number(x) })} /></div></Field>
      <div className="when" role="group" aria-labelledby="rf-when">
        <div className="when-top"><b id="rf-when" className="num" aria-live="polite">{hm(v.start)}–{hm(v.end)}</b><small>{v.end > v.start ? duration(v.end - v.start) : "Orario non valido"}</small></div>
        <div className="wheels">
          <div className="wheel-col"><span>Inizio</span><Wheel label="Inizio" items={startItems} value={v.start} onLive={(m) => setV((x) => ({ ...x, start: m }))} onChange={(m) => set({ start: m, end: v.end <= m ? Math.min(m + 60, 22 * 60) : v.end })} /></div>
          <div className="wheel-col"><span>Fine</span><Wheel label="Fine" items={endItems} value={v.end} onLive={(m) => setV((x) => ({ ...x, end: m }))} onChange={(m) => set({ end: m })} /></div>
        </div>
      </div>
      {bad.time && <div className="conflict show" role="alert">{bad.time}</div>}
      <div className="grid2">
        <Field label="Dal" id="rf-from" error={bad.period}><DateField id="rf-from" label="Dal" value={v.from} onChange={(x) => set({ from: x, to: v.to < x ? addDays(x, 90) : v.to })} /></Field>
        <Field label="Fino al" id="rf-to"><DateField id="rf-to" label="Fino al" value={v.to} min={v.from} onChange={(x) => set({ to: x })} /></Field>
      </div>
      <div className="grid2">
        <Field label="Modalità"><SegCtl label="Modalità" value={v.mode} options={[["IN_PERSON", "Presenza"], ["ONLINE", "Online"]]} onChange={(x) => set({ mode: x })} /></Field>
        <Field label="Dove"><SegCtl label="Dove" value={v.loc} options={[["ON_SITE", "In sede"], ["REMOTE", "Da remoto"]]} onChange={(x) => set({ loc: x })} /></Field>
      </div>
      {remoteBad && <div className="conflict show" role="alert">Da remoto si può fare solo lezione online. Puoi <button type="button" onClick={() => set({ mode: "ONLINE" })}>passare a online</button> oppure <button type="button" onClick={() => set({ loc: "ON_SITE" })}>scegliere in sede</button>.</div>}
      
      {err && <Notice kind="bad">{err}</Notice>}
    </div>
    {g.asking ? <GuardFoot onKeep={g.keep} onDiscard={() => { g.allow(); onClose(); }} /> :
      <div className="modal-foot"><button type="button" className="pill-btn ghost" onClick={() => { if (g.guard()) onClose(); }}>Chiudi</button>
        <button className="pill-btn primary island" disabled={busy}>{busy ? "Salvataggio…" : d.center ? "Salva" : "Invia in bozza"}<span className="isle"><Icon n="check" /></span></button></div>}
  </form></Modal>;
}
