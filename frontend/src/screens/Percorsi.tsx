import { ReactNode, useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, list } from "../api";
import { LOC, parse, plural } from "../format";
import { human } from "../messages";
import { Avatar, Btn, Empty, Icon, Notice, PageHead, Skeleton, Tag, Tech } from "../ui/core";
import { Check, Choices, DateField, Field, Input, MultiChoices, SegCtl } from "../ui/controls";
import { GuardFoot, Modal, useDirtyGuard, useToast } from "../ui/layers";
import { go, setQuery, useRoute } from "../ui/route";
import { useData } from "../app/data";

type Subject = { id: string; name: string };
type Path = { id: string; title: string; kind: string; academic_year: string; level: string; period_start: string; period_end: string; required_subjects: string[]; version: number };
type Enrollment = { id: string; path: string; student: string; student_name: string };
type Group = { id: string; path: string; name: string; subject: string; approved: boolean; online_capacity: number | null };
type Member = { id: string; group: string; student: string };
type Block = { id: string; path: string; subject_name: string; objective: string; student: string | null; group: string | null; minutes_per_week: number; period_start: string; period_end: string; duration_minutes?: number; sessions_per_week?: number; mode?: string; priority?: string; mandatory?: boolean };
type Summary = { version: number; students: { student_id: string; student_name: string; subjects: { subject_name: string; covered_full_period: boolean; validation_codes: string[]; segments: { period_start: string; period_end: string; required_minutes_per_week: number; overlap: boolean }[]; scheduled_minutes: number | null; attended_minutes: number | null }[] }[] };
type Receipt = { created: number; request_ids: string[]; version: number; calendar_changed: boolean };
type FormKind = "subject" | "path" | "enroll" | "group" | "member" | "block";

const fP = new Intl.DateTimeFormat(LOC, { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
const period = (a: string, b: string) => `${fP.format(parse(a))} – ${fP.format(parse(b))}`;
const hours = (min: number) => min % 60 ? `${Math.floor(min / 60)} h ${min % 60} min` : `${min / 60} h`;

export default function Percorsi() {
  const d = useData(), r = useRoute(), toast = useToast(); const center = d.center;
  const [paths, setPaths] = useState<Path[] | null>(null), [subjects, setSubjects] = useState<Subject[]>([]), [enrollments, setEnrollments] = useState<Enrollment[]>([]);
  const [groups, setGroups] = useState<Group[]>([]), [members, setMembers] = useState<Member[]>([]), [blocks, setBlocks] = useState<Block[]>([]);
  const [summary, setSummary] = useState<{ id: string; s: Summary } | null>(null), [err, setErr] = useState(""), [form, setForm] = useState<FormKind | null>(null), [derive, setDerive] = useState(false);
  const sel = r.q.get("p") || "";
  const load = useCallback(async () => {
    const [p, s, e] = await Promise.all([list<Path>("/learning-paths/"), list<Subject>("/subjects/"), list<Enrollment>("/path-enrollments/")]);
    if (center) { const [g, m, b] = await Promise.all([list<Group>("/teaching-groups/"), list<Member>("/group-memberships/"), list<Block>("/curriculum-blocks/")]); setGroups(g); setMembers(m); setBlocks(b); }
    setSubjects(s); setEnrollments(e); setPaths(p);
  }, [center]);
  const loadSummary = useCallback(async (id: string) => { if (id) setSummary({ id, s: await api<Summary>(`/learning-paths/${id}/curriculum-summary/`) }); }, []);
  useEffect(() => { load().catch((e) => setErr(human(e).text)); }, [load]);
  useEffect(() => { loadSummary(sel).catch((e) => setErr(human(e).text)); }, [sel, loadSummary]);
  const refresh = async () => { await load(); await loadSummary(sel); await d.refresh(); };
  const path = paths?.find((p) => p.id === sel);
  const subj = (id: string) => subjects.find((s) => s.id === id)?.name || "Materia";
  const own = { enr: enrollments.filter((e) => e.path === sel), grp: groups.filter((g) => g.path === sel), blk: blocks.filter((b) => b.path === sel) };
  const done = async (msg: string) => { setForm(null); await refresh().catch((e) => setErr(human(e).text)); toast(msg); };

  if (!paths) return <section className="module planner"><Skeleton rows={5} /></section>;
  if (!path) return <section className="module planner" aria-labelledby="h-pa">
    <PageHead id="h-pa" title="Percorsi" lead="Per chi svolge con il centro l’intero programma scolastico: materie, iscritti, sottogruppi e minuti settimanali. Il programma è interno e non certifica crediti o adempimenti.">
      {center && <><Btn icon="book" onClick={() => go("materie")}>Materie</Btn><Btn kind="primary" isle="plus" onClick={() => setForm("path")} disabled={!subjects.length}>Nuovo percorso</Btn></>}
    </PageHead>
    {err && <Notice kind="bad">{err}</Notice>}
    {center && !subjects.length && <Notice kind="info" action={<Btn kind="sm" onClick={() => go("materie")}>Apri Materie</Btn>}>Per creare un percorso aggiungi prima le materie nella pagina Materie: non viene proposto un programma standard.</Notice>}
    {paths.length ? <div className="mini-list">{paths.map((p) => { const n = enrollments.filter((e) => e.path === p.id).length; return <button type="button" key={p.id} className="mini" onClick={() => setQuery((q) => q.set("p", p.id))}>
      <span className="mini-ic"><Icon n="book" /></span><span className="grow"><b>{p.title}</b><small>{p.level} · {p.academic_year} · {plural(p.required_subjects.length, "materia", "materie")}</small></span>
      <Tag tone="plain">{plural(n, "iscritto", "iscritti")}</Tag><Icon n="right" /></button>; })}</div>
      : <Empty title="Nessun percorso">{center ? "Crea il primo percorso con le materie previste per il livello." : "Non ci sono percorsi visibili per il tuo profilo."}</Empty>}
    {subjects.length > 0 && <p className="fine">Materie registrate: {subjects.map((s) => s.name).join(", ")}. Si gestiscono nella pagina <button type="button" className="link-btn" onClick={() => go("materie")}>Materie</button>.</p>}
    <Forms kind={form} path={null} subjects={subjects} own={own} onClose={() => setForm(null)} onDone={done} />
  </section>;

  const sum = summary?.id === sel ? summary.s : null;
  return <>
    <section className="module planner" aria-labelledby="h-pd">
      <button type="button" className="linklike" onClick={() => go("percorsi")} style={{ marginBottom: 10 }}><Icon n="left" size={16} />Tutti i percorsi</button>
      <PageHead id="h-pd" title={path.title} lead={`${path.level} · ${path.academic_year} · ${period(path.period_start, path.period_end)}`}>
        {center && <Btn kind="primary" isle="send" disabled={!own.blk.length} onClick={() => setDerive(true)}>Crea le richieste</Btn>}
      </PageHead>
      {err && <Notice kind="bad">{err}</Notice>}
      <div className="chips-row">{path.required_subjects.map((id) => <Tag key={id} tone="blue">{subj(id)}</Tag>)}</div>
      <div className="stats">
        <Stat2 label="Iscritti" value={own.enr.length} />
        {center && <Stat2 label="Sottogruppi" value={own.grp.length} />}
        {center && <Stat2 label="Blocchi di programma" value={own.blk.length} note={own.blk.length ? `${hours(own.blk.reduce((a, b) => a + b.minutes_per_week, 0))} a settimana in tutto` : undefined} />}
      </div>
    </section>

    <div className="grid2" style={{ marginTop: 18 }}>
      <Card title="Iscritti" action={center && <Btn kind="sm" icon="plus" onClick={() => setForm("enroll")} disabled={d.students.every((s) => own.enr.some((e) => e.student === s.id))}>Iscrivi</Btn>}>
        {own.enr.length ? <div className="pop-list">{own.enr.map((e) => <a key={e.id} className="pop-item" href={`#/studenti?s=${e.student}`}><Avatar name={e.student_name} k={e.student} /><div><b>{e.student_name}</b><small>Apri la scheda</small></div></a>)}</div>
          : <Empty title="Nessuno studente iscritto">{center ? "Iscrivi gli studenti che seguono questo percorso." : ""}</Empty>}
      </Card>
      {center && <Card title="Sottogruppi" action={<><Btn kind="sm" onClick={() => setForm("member")} disabled={!own.grp.length || !own.enr.length}>Aggiungi membro</Btn><Btn kind="sm" icon="plus" onClick={() => setForm("group")}>Nuovo</Btn></>}>
        {own.grp.length ? <div className="mini-list">{own.grp.map((g) => { const ms = members.filter((m) => m.group === g.id).map((m) => d.students.find((s) => s.id === m.student)?.display_name || "Studente"); return <div key={g.id} className="mini">
          <span className="mini-ic"><Icon n="users" /></span><span className="grow"><b>{g.name}</b><small>{subj(g.subject)} · {ms.length ? ms.join(", ") : "nessun membro"}</small></span>
          <Tag tone={g.approved ? "green" : "amber"}>{g.approved ? "Approvato" : "Da approvare"}</Tag></div>; })}</div>
          : <Empty title="Nessun sottogruppo">Un sottogruppo raccoglie alcuni iscritti per una materia. In presenza, al massimo due studenti per lezione.</Empty>}
      </Card>}
    </div>

    {center && <section className="module" aria-labelledby="h-blk" style={{ marginTop: 18 }}>
      <div className="m-head"><div><h2 className="m-title" id="h-blk">Programma</h2><p className="sub-line">Minuti settimanali per materia, per studente o sottogruppo.</p></div>
        <div className="controls"><Btn kind="sm" icon="plus" disabled={!own.enr.length} onClick={() => setForm("block")}>Nuovo blocco</Btn></div></div>
      {own.blk.length ? <div className="list-wrap"><table className="list">
        <thead><tr><th scope="col">Materia</th><th scope="col">Per chi</th><th scope="col" className="hide-m">Periodo</th><th scope="col" style={{ textAlign: "right" }}>A settimana</th></tr></thead>
        <tbody>{own.blk.map((b) => { const who = b.student ? own.enr.find((e) => e.student === b.student)?.student_name || "Studente" : own.grp.find((g) => g.id === b.group)?.name || "Sottogruppo"; return <tr key={b.id}>
          <td><b style={{ fontWeight: 500 }}>{b.subject_name}</b><small className="muted" style={{ display: "block" }}>{b.objective}</small></td>
          <td>{b.student ? <span className="who"><Avatar name={who} k={b.student} /><b>{who}</b></span> : <Tag tone="violet">{who}</Tag>}</td>
          <td className="hide-m">{period(b.period_start, b.period_end)}</td><td className="amount">{hours(b.minutes_per_week)}</td></tr>; })}</tbody></table></div>
        : <Empty title="Programma vuoto">{own.enr.length ? "Aggiungi un blocco per ogni materia e destinatario." : "Iscrivi prima almeno uno studente."}</Empty>}
    </section>}

    <section className="module" aria-labelledby="h-cov" style={{ marginTop: 18 }}>
      <div className="m-head"><div><h2 className="m-title" id="h-cov">Copertura del programma</h2><p className="sub-line">Minuti richiesti, non ore già in calendario o presenze svolte.</p></div></div>
      {!sum ? <Skeleton rows={3} /> : sum.students.length ? <div className="cov">{sum.students.map((s) => <article key={s.student_id} className="cov-st">
        <div className="who"><Avatar name={s.student_name} k={s.student_id} /><b>{s.student_name}</b></div>
        <div className="mini-list">{s.subjects.map((x) => <div key={x.subject_name} className="mini">
          <span className="grow"><b>{x.subject_name}</b><small>{x.segments.length ? x.segments.map((g) => `${period(g.period_start, g.period_end)}: ${hours(g.required_minutes_per_week)}/sett.${g.overlap ? " (blocchi sovrapposti)" : ""}`).join(" · ") : "Nessun blocco definito"}</small>
            {x.validation_codes.length > 0 && <Tech label="Perché da verificare"><code>{x.validation_codes.join(", ")}</code></Tech>}</span>
          <Tag tone={x.covered_full_period ? "green" : "amber"}>{x.covered_full_period ? "Coperto" : "Da completare"}</Tag></div>)}</div>
      </article>)}</div> : <Empty title="Ancora nulla da mostrare">Iscrivi gli studenti e definisci il programma di ogni materia.</Empty>}
    </section>
    <Forms kind={form} path={path} subjects={subjects} own={own} onClose={() => setForm(null)} onDone={done} />
    <DeriveModal open={derive} path={path} blocks={own.blk.length} onClose={() => setDerive(false)} onDone={async (rc) => { setDerive(false); await refresh().catch(() => {}); toast(rc.created ? `${plural(rc.created, "nuova richiesta creata", "nuove richieste create")} (${rc.request_ids.length} in tutto). Calendario invariato.` : `Nessuna nuova richiesta: le ${rc.request_ids.length} esistenti sono già allineate.`, { action: "Vedi richieste", onAction: () => go("richieste") }); }} onStale={() => load().catch(() => {})} />
  </>;
}

const Stat2 = ({ label, value, note }: { label: string; value: ReactNode; note?: string }) => <div className="stat"><small>{label}</small><b>{value}</b>{note && <div className="note">{note}</div>}</div>;
function Card({ title, action, children }: { title: string; action?: ReactNode; children: ReactNode }) {
  return <section className="module"><div className="m-head"><h2 className="m-title">{title}</h2>{action && <div className="controls">{action}</div>}</div>{children}</section>;
}

/* ------------------------------ moduli ------------------------------ */
type Own = { enr: Enrollment[]; grp: Group[]; blk: Block[] };
function Forms({ kind, path, subjects, own, onClose, onDone }: { kind: FormKind | null; path: Path | null; subjects: Subject[]; own: Own; onClose: () => void; onDone: (m: string) => Promise<void> }) {
  const d = useData();
  const blank = () => ({ name: "", title: "", year: "", level: "", from: path?.period_start || "", to: path?.period_end || "", subjects: [] as string[], subject: path?.required_subjects[0] || "", student: "", group: "", objective: "", target: "student" as "student" | "group", dur: "60", ses: "1", mode: "IN_PERSON", prio: "", mandatory: false, approved: false, cap: "" });
  const [v, setV] = useState(blank()), [tried, setTried] = useState(false), [err, setErr] = useState(""), [busy, setBusy] = useState(false), [touched, setTouched] = useState(false);
  const [last, setLast] = useState(kind);
  useEffect(() => { if (kind) { setLast(kind); setV(blank()); setTried(false); setErr(""); setTouched(false); g.reset(); } }, [kind]); // eslint-disable-line
  const g = useDirtyGuard(!!kind && touched);
  const set = (p: Partial<typeof v>) => { setV((x) => ({ ...x, ...p })); setTouched(true); };
  const k = kind || last; if (!k) return null;
  const subjOpts = (ids: string[]) => ids.map((id) => ({ v: id, label: subjects.find((s) => s.id === id)?.name || "Materia" }));
  const enrOpts = own.enr.map((e) => ({ v: e.student, label: e.student_name }));
  const minutes = Number(v.dur) * Number(v.ses);
  const periodBad = !v.from || !v.to || v.to < v.from;
  const spec: Record<FormKind, { title: string; lead: string; cta: string; bad: Record<string, string | false>; url: string; body: () => object; ok: string }> = {
    subject: { title: "Nuova materia", lead: "Il nome come lo usa il centro. Potrai sceglierla nei percorsi.", cta: "Aggiungi materia", url: "/subjects/", ok: `Materia aggiunta: ${v.name.trim()}.`,
      bad: { name: !v.name.trim() && "Scrivi il nome della materia." }, body: () => ({ name: v.name.trim() }) },
    path: { title: "Nuovo percorso", lead: "Un anno di programma completo per un livello. Le materie elencate saranno tutte da coprire.", cta: "Crea percorso", url: "/learning-paths/", ok: `Percorso creato: ${v.title.trim()}.`,
      bad: { ptitle: !v.title.trim() && "Scrivi il nome del percorso.", year: !v.year.trim() && "Indica l’anno didattico.", level: !v.level.trim() && "Indica classe o livello.", period: periodBad && "Scegli inizio e fine, con la fine dopo l’inizio.", subjects: !v.subjects.length && "Scegli almeno una materia." },
      body: () => ({ title: v.title.trim(), kind: "HOME_EDUCATION", academic_year: v.year.trim(), level: v.level.trim(), period_start: v.from, period_end: v.to, required_subjects: v.subjects }) },
    enroll: { title: "Iscrivi al percorso", lead: "Lo studente seguirà il programma di questo percorso nel periodo indicato.", cta: "Iscrivi", url: "/path-enrollments/", ok: "Studente iscritto. Nessuna lezione prenotata.",
      bad: { student: !v.student && "Scegli lo studente.", period: periodBad && "Scegli inizio e fine, con la fine dopo l’inizio." },
      body: () => ({ path: path?.id, student: v.student, period_start: v.from, period_end: v.to, active: true }) },
    group: { title: "Nuovo sottogruppo", lead: "Alcuni iscritti che seguono insieme una materia. In presenza una lezione ammette al massimo due studenti.", cta: "Crea sottogruppo", url: "/teaching-groups/", ok: `Sottogruppo creato: ${v.name.trim()}.`,
      bad: { name: !v.name.trim() && "Dai un nome al sottogruppo.", subject: !v.subject && "Scegli la materia." },
      body: () => ({ path: path?.id, name: v.name.trim(), subject: v.subject, online_capacity: v.cap ? Number(v.cap) : null, approved: v.approved }) },
    member: { title: "Aggiungi al sottogruppo", lead: "Solo gli iscritti al percorso possono far parte di un suo sottogruppo.", cta: "Aggiungi", url: "/group-memberships/", ok: "Membro aggiunto al sottogruppo.",
      bad: { group: !v.group && "Scegli il sottogruppo.", student: !v.student && "Scegli lo studente.", period: periodBad && "Scegli inizio e fine, con la fine dopo l’inizio." },
      body: () => ({ group: v.group, student: v.student, period_start: v.from, period_end: v.to }) },
    block: { title: "Nuovo blocco di programma", lead: "Quanto tempo a settimana dedicare a una materia, per uno studente o un sottogruppo.", cta: "Aggiungi blocco", url: "/curriculum-blocks/", ok: "Blocco aggiunto al programma.",
      bad: { subject: !v.subject && "Scegli la materia.", objective: !v.objective.trim() && "Scrivi l’obiettivo.", who: !(v.target === "student" ? v.student : v.group) && "Scegli il destinatario.", period: periodBad && "Scegli inizio e fine, con la fine dopo l’inizio.", prio: !v.prio && "Scegli la priorità: non c’è un valore predefinito." },
      body: () => ({ path: path?.id, subject: v.subject, objective: v.objective.trim(), [v.target]: v.target === "student" ? v.student : v.group, period_start: v.from, period_end: v.to, duration_minutes: Number(v.dur), sessions_per_week: Number(v.ses), minutes_per_week: minutes, mode: v.mode, priority: v.prio, mandatory: v.mandatory }) },
  };
  const s = spec[k], e = (f: string) => (tried && s.bad[f]) || false;
  async function submit(ev: React.FormEvent) {
    ev.preventDefault(); setTried(true);
    const first = Object.keys(s.bad).find((f) => s.bad[f]);
    if (first) { document.getElementById("pf-" + first)?.focus(); return; }
    setBusy(true); setErr("");
    try { await api(s.url, { method: "POST", body: JSON.stringify(s.body()) }); g.allow(); await onDone(s.ok); }
    catch (x) { setErr(human(x).text); } finally { setBusy(false); }
  }
  const Period = () => <div className="grid2">
    <Field label="Dal" error={e("period")}><DateField id="pf-period" label="Dal" value={v.from} max={v.to || undefined} onChange={(x) => set({ from: x })} /></Field>
    <Field label="Al"><DateField label="Al" value={v.to} min={v.from || undefined} onChange={(x) => set({ to: x })} /></Field></div>;
  return <Modal open={!!kind} onClose={onClose} guard={g.guard} labelledBy="pf-title" width={k === "block" || k === "path" ? 620 : undefined}><form onSubmit={submit} noValidate>
    <div className="modal-body">
      <h2 id="pf-title">{s.title}</h2><p className="lead">{s.lead}</p>
      {k === "subject" && <Field label="Nome" id="pf-name" error={e("name")}><Input id="pf-name" autoFocus maxLength={80} value={v.name} placeholder="Es. Matematica" onChange={(x) => set({ name: x.target.value })} /></Field>}
      {k === "path" && <>
        <Field label="Nome del percorso" id="pf-ptitle" error={e("ptitle")}><Input id="pf-ptitle" autoFocus maxLength={140} value={v.title} placeholder="Es. Scuola media, primo anno" onChange={(x) => set({ title: x.target.value })} /></Field>
        <div className="grid2">
          <Field label="Anno didattico" id="pf-year" error={e("year")}><Input id="pf-year" maxLength={30} value={v.year} placeholder="Es. 2026/2027" onChange={(x) => set({ year: x.target.value })} /></Field>
          <Field label="Classe o livello" id="pf-level" error={e("level")} hint="Come definito con il centro."><Input id="pf-level" maxLength={80} value={v.level} onChange={(x) => set({ level: x.target.value })} /></Field>
        </div>
        {Period()}
        <Field label="Materie previste" error={e("subjects")}><div id="pf-subjects" tabIndex={-1}><MultiChoices label="Materie previste" value={v.subjects} options={subjOpts(subjects.map((x) => x.id))} onChange={(x) => set({ subjects: x })} /></div></Field>
      </>}
      {(k === "enroll" || k === "member") && <>
        {k === "member" && <Field label="Sottogruppo" error={e("group")}><div id="pf-group" tabIndex={-1}><Choices label="Sottogruppo" value={v.group} options={own.grp.map((x) => ({ v: x.id, label: x.name }))} onChange={(x) => set({ group: x })} /></div></Field>}
        <Field label="Studente" error={e("student")}><div id="pf-student" tabIndex={-1}><Choices label="Studente" value={v.student} onChange={(x) => set({ student: x })}
          options={k === "enroll" ? d.students.filter((x) => !own.enr.some((y) => y.student === x.id)).map((x) => ({ v: x.id, label: x.display_name, av: x.display_name })) : enrOpts.map((o) => ({ ...o, av: o.label }))} /></div></Field>
        {Period()}
      </>}
      {k === "group" && <>
        <Field label="Nome" id="pf-name" error={e("name")}><Input id="pf-name" autoFocus maxLength={80} value={v.name} placeholder="Es. Inglese A" onChange={(x) => set({ name: x.target.value })} /></Field>
        <Field label="Materia" error={e("subject")}><div id="pf-subject" tabIndex={-1}><Choices label="Materia" value={v.subject} options={subjOpts(path?.required_subjects || [])} onChange={(x) => set({ subject: x })} /></div></Field>
        <Field label="Capienza online" hint="Solo se il gruppo farà lezioni online."><SegCtl label="Capienza online" value={v.cap} onChange={(x) => set({ cap: x })} options={[["", "Non online"], ["2", "2"], ["3", "3"], ["4", "4"], ["6", "6"]]} /></Field>
        <Check checked={v.approved} onChange={(x) => set({ approved: x })}>Il centro ha approvato il gruppo dal punto di vista didattico</Check>
      </>}
      {k === "block" && <>
        <Field label="Materia" error={e("subject")}><div id="pf-subject" tabIndex={-1}><Choices label="Materia" value={v.subject} options={subjOpts(path?.required_subjects || [])} onChange={(x) => set({ subject: x })} /></div></Field>
        <Field label="Obiettivo" id="pf-objective" error={e("objective")} hint="Interno al centro, senza dati personali."><Input id="pf-objective" maxLength={300} value={v.objective} placeholder="Es. Equazioni di primo grado" onChange={(x) => set({ objective: x.target.value })} /></Field>
        <Field label="Per chi"><SegCtl label="Destinatario" value={v.target} onChange={(x) => set({ target: x })} options={[["student", "Uno studente"], ["group", "Un sottogruppo"]]} /></Field>
        <Field label={v.target === "student" ? "Studente" : "Sottogruppo"} error={e("who")}><div id="pf-who" tabIndex={-1}>
          {v.target === "student" ? <Choices label="Studente" value={v.student} options={enrOpts.map((o) => ({ ...o, av: o.label }))} onChange={(x) => set({ student: x })} />
            : own.grp.length ? <Choices label="Sottogruppo" value={v.group} options={own.grp.map((x) => ({ v: x.id, label: x.name }))} onChange={(x) => set({ group: x })} /> : <p className="muted">Nessun sottogruppo in questo percorso.</p>}</div></Field>
        {Period()}
        <div className="grid2">
          <Field label="Durata di ogni lezione"><SegCtl label="Durata" value={v.dur} onChange={(x) => set({ dur: x })} options={[["60", "1 h"], ["90", "1 h 30"], ["120", "2 h"]]} /></Field>
          <Field label="Lezioni a settimana"><SegCtl label="Lezioni a settimana" value={v.ses} onChange={(x) => set({ ses: x })} options={[["1", "1"], ["2", "2"], ["3", "3"], ["4", "4"], ["5", "5"]]} /></Field>
        </div>
        <p className="muted" style={{ margin: "-4px 0 12px" }}>In tutto <b>{hours(minutes)} a settimana</b>.</p>
        <div className="grid2">
          <Field label="Modalità"><SegCtl label="Modalità" value={v.mode} onChange={(x) => set({ mode: x })} options={[["IN_PERSON", "Presenza"], ["ONLINE", "Online"]]} /></Field>
          <Field label="Priorità" error={e("prio")} hint="P0 è la più alta."><div id="pf-prio" tabIndex={-1}><Choices label="Priorità" value={v.prio} options={["P0", "P1", "P2"].map((x) => ({ v: x, label: x }))} onChange={(x) => set({ prio: x })} /></div></Field>
        </div>
        <Check checked={v.mandatory} onChange={(x) => set({ mandatory: x })}>Obbligatoria: va collocata anche quando si chiede “il più possibile”</Check>
        <p className="fine">Due blocchi sovrapposti della stessa materia per lo stesso studente non si sommano.</p>
      </>}
      {err && <Notice kind="bad">{err}</Notice>}
    </div>
    {g.asking ? <GuardFoot onKeep={g.keep} onDiscard={() => { g.allow(); onClose(); }} />
      : <div className="modal-foot"><button type="button" className="pill-btn ghost" onClick={() => { if (g.guard()) onClose(); }}>Chiudi</button>
        <button className="pill-btn primary island" disabled={busy}>{busy ? "Salvataggio…" : s.cta}<span className="isle"><Icon n="check" /></span></button></div>}
  </form></Modal>;
}

function DeriveModal({ open, path, blocks, onClose, onDone, onStale }: { open: boolean; path: Path; blocks: number; onClose: () => void; onDone: (r: Receipt) => Promise<void>; onStale: () => void }) {
  const [err, setErr] = useState(""), [busy, setBusy] = useState(false), [retry, setRetry] = useState(false);
  const pending = useRef<{ path: string; version: number; key: string } | null>(null);
  useEffect(() => { if (open) { setErr(""); setRetry(!!pending.current); } }, [open]);
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!pending.current || pending.current.path !== path.id) pending.current = { path: path.id, version: path.version, key: crypto.randomUUID() };
    const c = pending.current; setBusy(true); setErr("");
    try {
      const rc = await api<Receipt>(`/learning-paths/${c.path}/derive-requests/`, { method: "POST", headers: { "Idempotency-Key": c.key }, body: JSON.stringify({ expected_version: c.version }) });
      pending.current = null; setRetry(false); await onDone(rc);
    } catch (x) {
      setErr(human(x).text);
      if (x instanceof ApiError && [400, 409, 422].includes(x.status)) { pending.current = null; setRetry(false); onStale(); } else setRetry(true);
    } finally { setBusy(false); }
  }
  return <Modal open={open} onClose={onClose} labelledBy="dv-title"><form onSubmit={submit} noValidate>
    <div className="modal-body">
      <h2 id="dv-title">Creare le richieste didattiche?</h2>
      <p className="lead">Per ognuno dei {blocks} blocchi di “{path.title}” viene creata una richiesta da pianificare, dopo aver verificato tutte le materie per tutti gli iscritti.</p>
      <Notice kind="warn" title="Il programma verrà congelato">Dopo questa operazione i blocchi non si potranno più modificare. Nessuna lezione viene pubblicata: le richieste andranno pianificate con una proposta.</Notice>
      {err && <Notice kind="bad">{err}</Notice>}
      <Tech><code>Percorso {path.id} · versione {path.version}</code></Tech>
    </div>
    <div className="modal-foot"><button type="button" className="pill-btn ghost" onClick={onClose}>Chiudi</button>
      <button className="pill-btn primary island" disabled={busy}>{busy ? "Verifica…" : retry ? "Riprova la stessa operazione" : "Crea le richieste"}<span className="isle"><Icon n="send" /></span></button></div>
  </form></Modal>;
}
