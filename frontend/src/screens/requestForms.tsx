/** Richieste didattiche (v0.9.6): un solo modulo per centro e famiglie con due
 *  tipi — singola (in un giorno, anche a orario fisso, oppure da collocare in una
 *  settimana) e ricorrente (N lezioni a settimana, sempre con lo stesso tutor).
 *  v0.9.9: è anche la finestra «Nuova lezione» (barra in alto, tasto N, trascinamento
 *  in agenda); il centro può creare lezioni di gruppo; dopo il salvataggio il motore
 *  colloca subito le lezioni e si apre la verifica (RequestReview). */
import { useEffect, useState } from "react";
import { api } from "../api";
import { addDays, dateLong, dayLabel, hm, mondayOf, todayRome, weekday } from "../format";
import { human } from "../messages";
import { Btn, Icon, IconName, Notice, Tag } from "../ui/core";
import { Check, Choices, DateField, Field, Input, MultiChoices, SegCtl } from "../ui/controls";
import { GuardFoot, Modal, useDirtyGuard } from "../ui/layers";
import { useData } from "../app/data";

export type TutorRef = { id: string; display_name: string };
export type Kind = "SINGLE" | "SERIES" | "WEEKLY";
export type Req = {
  id: string; student: string | null; student_name?: string; target_type: string; participant_ids: string[]; subject?: string; subject_name: string;
  mode?: string; duration_minutes: number; sessions_per_week: number; period_start?: string; period_end?: string; version?: number;
  priority?: string; mandatory?: boolean; status?: string; origin?: string; tutor_choice?: string; preferred_tutors?: TutorRef[];
  notes?: string; review_note?: string; created_at?: string; derived?: boolean; own?: boolean;
  kind?: Kind; fixed_time?: string | null;
  planning_state?: "" | "REVIEW" | "DONE"; completed_at?: string | null; group_label?: string; participant_names?: string[];
};
/** Dati trascinati dall'agenda (tutor, giorno, minuti di inizio e fine). */
export type LessonPrefill = { tutor?: string; date?: string; start?: number; end?: number };
export const MAX_GROUP = 8;
export type Options = { subjects: { id: string; name: string; tutors: (TutorRef & { modes: string[]; levels?: string[] })[] }[] };

export const STATUS: Record<string, [string, "amber" | "green" | "red" | "plain"]> = {
  PENDING: ["Da approvare", "amber"], APPROVED: ["Approvata", "green"], REJECTED: ["Rifiutata", "red"], WITHDRAWN: ["Ritirata", "plain"],
};
/** Stato con la fase di verifica: approvata → «Da verificare» finché il centro non conferma
 *  le lezioni inserite dal motore, poi «Completata». */
export const PLANNING: Record<string, [string, "amber" | "green" | "blue"]> = { REVIEW: ["Da verificare", "blue"], DONE: ["Completata", "green"] };
export const StatusTag = ({ s, p }: { s?: string; p?: string }) => {
  const [l, t] = (s === "APPROVED" || !s) && p && PLANNING[p] ? PLANNING[p] : STATUS[s || "APPROVED"] || STATUS.APPROVED;
  return <Tag tone={t}>{l}</Tag>;
};
export const modeText = (m?: string) => (m === "ONLINE" ? "Online" : "In presenza");
const durText = (m: number) => (m === 60 ? "1 h" : m === 90 ? "1 h 30" : m === 120 ? "2 h" : `${m} min`);
const hhmm = (t?: string | null) => (t ? t.slice(0, 5) : "");
const short = (d: string) => dateLong(d);

/** "Qualsiasi tutor", "Preferisce Anna", "Solo con Anna". */
export function tutorText(r: Pick<Req, "tutor_choice" | "preferred_tutors"> & { kind?: Kind }) {
  const names = (r.preferred_tutors || []).map((t) => t.display_name).join(" o ");
  if (r.kind === "SERIES") return names ? `Sempre con ${names}` : "Tutor da assegnare";
  if (r.tutor_choice === "REQUIRED" && names) return `Solo con ${names}`;
  if (r.tutor_choice === "PREFERRED" && names) return `Preferisce ${names}`;
  return "Qualsiasi tutor competente";
}

/** Tipo di richiesta in una parola, per elenco e filtri. */
export const KIND: Record<Kind, [string, "blue" | "violet" | "plain"]> = { SINGLE: ["Singola", "blue"], SERIES: ["Ricorrente", "violet"], WEEKLY: ["Ricorrente", "violet"] };
/** Filtro per tipo: le settimanali storiche contano come ricorrenti. */
export const kindGroup = (r: Pick<Req, "kind">) => (r.kind === "SINGLE" ? "SINGLE" : "RECURRING");
export const KindTag = ({ r }: { r: Pick<Req, "kind"> }) => { const [l, t] = KIND[r.kind || "WEEKLY"]; return <Tag tone={t}>{l}</Tag>; };

/** Quando: frase leggibile che non richiede di conoscere i campi tecnici. */
export function whenText(r: Pick<Req, "kind" | "period_start" | "period_end" | "fixed_time" | "sessions_per_week">) {
  const a = r.period_start || "", b = r.period_end || a;
  if (r.kind === "SINGLE") {
    if (!a) return "Una lezione";
    if (r.fixed_time) return `${dayLabel(a)} alle ${hhmm(r.fixed_time)}`;
    if (a === b) return `${dayLabel(a)}, orario da trovare`;
    return `Nella settimana dal ${short(a)} al ${short(b)}`;
  }
  const w = r.sessions_per_week || 1;
  return `${w} ${w === 1 ? "lezione" : "lezioni"} a settimana${a ? ` dal ${short(a)} al ${short(b)}` : ""}`;
}

export async function review(id: string, action: "approve" | "reject" | "withdraw", note = "", extra: Record<string, unknown> = {}) {
  return api<Req>(`/teaching-requests/${id}/${action}/`, { method: "POST", body: JSON.stringify({ ...(note ? { note } : {}), ...extra }) });
}
/** Una richiesta ricorrente senza tutor non si approva finché il centro non lo sceglie. */
export const needsTutor = (r: Req) => r.kind === "SERIES" && !(r.preferred_tutors || []).length;

const nextMonday = () => { const t = todayRome(); return weekday(t) === 0 ? t : addDays(mondayOf(t), 7); };
const schoolYearEnd = () => { const t = todayRome(); const y = Number(t.slice(0, 4)) + (Number(t.slice(5, 7)) >= 7 ? 1 : 0); return `${y}-06-30`; };
const TIMES = Array.from({ length: (21 - 8) * 4 + 1 }, (_, i) => { const m = 8 * 60 + i * 15; return `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`; });

/** Tipo nel modulo: singola o ricorrente; "WEEKLY" solo per modificare le richieste storiche. */
type Pick2 = "SINGLE" | "SERIES" | "WEEKLY";
type Form = {
  target: "ONE" | "GROUP"; members: string[]; group_label: string;
  pick: Pick2; when: "DAY" | "WEEK"; student: string; subject: string; mode: string; duration_minutes: string;
  day: string; timed: boolean; time: string; week: string; series_tutor: string;
  sessions_per_week: string; period_start: string; period_end: string;
  priority: string; mandatory: boolean; tutor_choice: string; preferred_tutor_ids: string[]; notes: string;
};
const blank = (student = "", center = false): Form => ({
  target: "ONE", members: [], group_label: "",
  pick: "SINGLE", when: "DAY", student, subject: "", mode: "IN_PERSON", duration_minutes: "60",
  day: "", timed: center, time: "15:00", week: nextMonday(), series_tutor: "",
  sessions_per_week: "1", period_start: nextMonday(), period_end: schoolYearEnd(),
  priority: "P1", mandatory: false, tutor_choice: "ANY", preferred_tutor_ids: [], notes: "",
});
function fromReq(r: Req): Form {
  const f = blank(r.student || "", true), a = r.period_start || nextMonday(), b = r.period_end || a;
  const tutors = (r.preferred_tutors || []).map((t) => t.id);
  return { ...f, pick: r.kind || "WEEKLY", when: a === b ? "DAY" : "WEEK", subject: r.subject || "", mode: r.mode || "IN_PERSON", duration_minutes: String(r.duration_minutes),
    day: a, timed: !!r.fixed_time, time: hhmm(r.fixed_time) || "15:00", week: mondayOf(a), series_tutor: tutors[0] || "",
    sessions_per_week: String(r.sessions_per_week || 1), period_start: a, period_end: b,
    priority: r.priority || "P1", mandatory: !!r.mandatory, tutor_choice: r.tutor_choice || "ANY", preferred_tutor_ids: tutors, notes: r.notes || "" };
}

const PICKS: { v: Pick2; icon: IconName; title: string; sub: string }[] = [
  { v: "SINGLE", icon: "cal", title: "Singola", sub: "Una lezione: in un giorno preciso, anche a orario fisso, oppure da collocare in una settimana." },
  { v: "SERIES", icon: "spark", title: "Ricorrente", sub: "Lezioni ogni settimana, sempre con lo stesso tutor: scegli quante a settimana." },
];
function KindPicker({ value, onChange }: { value: Pick2; onChange: (v: Pick2) => void }) {
  return <div className="rq-kinds two" role="radiogroup" aria-label="Tipo di richiesta">{PICKS.map((p) =>
    <label key={p.v} className="rq-kind">
      <input type="radio" name="rq-kind" value={p.v} checked={value === p.v} onChange={() => onChange(p.v)} />
      <span className="rq-kind-ic"><Icon n={p.icon} /></span><b>{p.title}</b><small>{p.sub}</small>
    </label>)}</div>;
}

const DURS = [60, 90, 120];
/** Modulo precompilato dal trascinamento in agenda: lezione singola in quel giorno, a
 *  quell'ora, con quel tutor (obbligatorio). */
function fromPrefill(p: LessonPrefill, student: string): Form {
  const f = blank(student, true);
  const len = p.start !== undefined && p.end !== undefined ? p.end - p.start : 60;
  const dur = DURS.reduce((a, b) => (Math.abs(b - len) < Math.abs(a - len) ? b : a), 60);
  const start = p.start !== undefined ? Math.round(p.start / 15) * 15 : undefined;
  return { ...f, pick: "SINGLE", when: "DAY", day: p.date || "", timed: start !== undefined, time: start !== undefined ? hm(start) : f.time,
    duration_minutes: String(dur), tutor_choice: p.tutor ? "REQUIRED" : "ANY", preferred_tutor_ids: p.tutor ? [p.tutor] : [], series_tutor: p.tutor || "" };
}

/** Frase di riepilogo: ciò che il centro (o la famiglia) sta per chiedere. */
function recap(f: Form, who: string, subject: string, tutorName: string) {
  const what = subject || "la materia scelta", per = who ? ` per ${who}` : "";
  const how = `${durText(Number(f.duration_minutes))}, ${modeText(f.mode).toLowerCase()}`;
  if (f.pick === "SINGLE" && f.when === "DAY") return f.day ? `Una lezione di ${what}${per} ${dayLabel(f.day).toLowerCase()}${f.timed ? ` alle ${f.time}` : ", all’orario che troverà il calcolo"} (${how}).` : "";
  if (f.pick === "SINGLE") return `Una lezione di ${what}${per} nella settimana dal ${short(f.week)} al ${short(addDays(f.week, 6))} (${how}).`;
  const w = Number(f.sessions_per_week);
  return `${w} ${w === 1 ? "lezione" : "lezioni"} di ${what} a settimana${per}, dal ${short(f.period_start)} al ${short(f.period_end)}${tutorName ? `, sempre con ${tutorName}` : ""} (${how}).`;
}

/** Nuova richiesta (centro o famiglia) o modifica dei vincoli (solo centro). */
export function RequestModal({ open, edit, student, prefill, onClose, onSaved }: { open: boolean; edit?: Req | null; student?: string; prefill?: LessonPrefill | null; onClose: () => void; onSaved: (r: Req) => void }) {
  const d = useData(), center = d.center;
  const [opts, setOpts] = useState<Options | null>(null), [f, setF] = useState<Form>(blank()), [start, setStart] = useState("");
  const [err, setErr] = useState(""), [busy, setBusy] = useState(false);
  useEffect(() => { if (open && !opts) api<Options>("/teaching-requests/options/").then(setOpts).catch((e) => setErr(human(e).text)); }, [open]); // eslint-disable-line
  useEffect(() => {
    if (!open) return;
    const who = student || (d.students.length === 1 ? d.students[0].id : "");
    const v = edit ? fromReq(edit) : prefill ? fromPrefill(prefill, who) : blank(who, center);
    setF(v); setStart(JSON.stringify(v)); setErr(""); g.reset();
  }, [open, edit, prefill]); // eslint-disable-line
  const g = useDirtyGuard(open && JSON.stringify(f) !== start);
  const set = <K extends keyof Form>(k: K, v: Form[K]) => setF((x) => ({ ...x, [k]: v }));
  /** Cambiando materia o modalità restano solo i tutor che la insegnano (es. quello trascinato dall'agenda). */
  const keepTutors = (x: Form, subject: string, mode: string): Form => {
    const ok = new Set((opts?.subjects.find((s) => s.id === subject)?.tutors || []).filter((t) => t.modes.includes(mode)).map((t) => t.id));
    const ids = x.preferred_tutor_ids.filter((t) => ok.has(t));
    return { ...x, subject, mode, preferred_tutor_ids: ids, tutor_choice: x.tutor_choice !== "ANY" && !ids.length ? "ANY" : x.tutor_choice, series_tutor: ok.has(x.series_tutor) ? x.series_tutor : "" };
  };
  const tutorSubjects = prefill?.tutor && !edit ? (opts?.subjects || []).filter((s) => s.tutors.some((t) => t.id === prefill.tutor)) : [];
  const subjectList = tutorSubjects.length ? tutorSubjects : opts?.subjects || [];
  const subj = opts?.subjects.find((s) => s.id === (edit?.subject || f.subject));
  const tutors = (subj?.tutors || []).filter((t) => t.modes.includes(f.mode));
  const tutorPool = edit && !subj ? d.tutors : tutors;
  const series = f.pick === "SERIES", single = f.pick === "SINGLE";
  const group = center && !edit && f.target === "GROUP";
  const memberNames = f.members.map((id) => d.students.find((s) => s.id === id)?.display_name || "").filter(Boolean);
  const who = group ? (f.group_label.trim() || (memberNames.length ? `il gruppo ${memberNames.join(", ")}` : "")) : d.students.find((s) => s.id === f.student)?.display_name || edit?.student_name || "";
  const tutorName = tutorPool.find((t) => t.id === f.series_tutor)?.display_name || "";
  const today = todayRome();

  async function save(e: React.FormEvent) {
    e.preventDefault(); setErr("");
    if (!edit && group && f.members.length < 2) { setErr("Una lezione di gruppo ha almeno 2 studenti."); return; }
    if (!edit && group && f.members.length > MAX_GROUP) { setErr(`Al massimo ${MAX_GROUP} studenti per gruppo.`); return; }
    if (!edit && ((!group && !f.student) || !f.subject)) { setErr(!group && !f.student ? "Scegli per chi è la richiesta." : "Scegli la materia."); return; }
    if (single && f.when === "DAY" && !f.day) { setErr("Scegli il giorno della lezione."); return; }
    if (series && center && !f.series_tutor) { setErr("Scegli il tutor che seguirà le lezioni."); return; }
    if (!series && f.tutor_choice !== "ANY" && !f.preferred_tutor_ids.length) { setErr("Scegli almeno un tutor, oppure “Qualsiasi”."); return; }
    if (!single && f.period_end < f.period_start) { setErr("La data di fine deve seguire l’inizio."); return; }
    const body: Record<string, unknown> = { mode: f.mode, duration_minutes: Number(f.duration_minutes), notes: f.notes.trim() };
    if (single && f.when === "DAY") Object.assign(body, { period_start: f.day, period_end: f.day, fixed_time: f.timed ? f.time : null });
    if (single && f.when === "WEEK") Object.assign(body, { period_start: f.week, period_end: addDays(f.week, 6), fixed_time: null });
    if (!single) Object.assign(body, { period_start: f.period_start, period_end: f.period_end, sessions_per_week: Number(f.sessions_per_week) });
    if (series) body.preferred_tutor_ids = f.series_tutor ? [f.series_tutor] : [];
    else Object.assign(body, { tutor_choice: f.tutor_choice, preferred_tutor_ids: f.tutor_choice === "ANY" ? [] : f.preferred_tutor_ids });
    if (!edit) {
      body.subject = f.subject; body.kind = f.pick;
      if (group) Object.assign(body, { participant_ids: f.members, group_label: f.group_label.trim() });
      else body.student = f.student;
    }
    if (center) { body.priority = f.priority; body.mandatory = f.mandatory; }
    setBusy(true);
    try { const r = await api<Req>(`/teaching-requests/${edit ? edit.id + "/" : ""}`, { method: edit ? "PATCH" : "POST", body: JSON.stringify(body) }); g.allow(); onSaved(r); }
    catch (er) { setErr(human(er).text); } finally { setBusy(false); }
  }

  const title = edit ? `Modifica: ${edit.subject_name}${edit.student_name ? " · " + edit.student_name : ""}` : center ? "Nuova richiesta di lezioni" : "Chiedi delle lezioni";
  const lead = edit ? (center && edit.status === "APPROVED" && !edit.derived ? "Al salvataggio il motore ricalcola le lezioni della richiesta per il primo mese utile e ti mostra l’elenco da verificare." : "Le modifiche valgono dal prossimo calcolo dell’orario.")
    : center ? "Le richieste inserite dal centro sono già approvate: il motore colloca subito le lezioni del primo mese utile e ti mostra l’elenco da verificare prima di completarla; i mesi successivi li pianifica il calendario mensile."
    : "Il centro riceve la richiesta e la approva; poi l’orario viene calcolato sulle disponibilità che hai inserito.";
  const n = (k: number) => <span className="rq-n" aria-hidden="true">{k}</span>;
  const line = recap(f, who, subj?.name || edit?.subject_name || "", tutorName);
  return <Modal open={open} onClose={onClose} guard={g.guard} labelledBy="rq-title" width={720}><form onSubmit={save} noValidate>
    <div className="modal-body rq-form">
      <h2 id="rq-title">{title}</h2>
      <p className="lead">{lead}</p>

      {!edit ? <section className="rq-sec" aria-labelledby="rq-s1"><h3 id="rq-s1">{n(1)}Che cosa serve</h3>
        <KindPicker value={f.pick} onChange={(v) => set("pick", v)} />
      </section> : <p className="rq-kind-now"><KindTag r={edit} /> <span className="muted">{whenText(edit)}</span></p>}

      {!edit && <section className="rq-sec" aria-labelledby="rq-s2"><h3 id="rq-s2">{n(2)}Per chi e quale materia</h3>
        {center && <Field label="Per chi"><SegCtl label="Per chi" value={f.target} onChange={(v) => set("target", v)} options={[["ONE", "Uno studente"], ["GROUP", "Lezione di gruppo"]]} /></Field>}
        {group ? <>
          <Field label="Studenti del gruppo" hint={`Da 2 a ${MAX_GROUP} studenti: il motore cerca un orario libero per tutti e un’aula con posti sufficienti.`}>
            {d.students.length ? <MultiChoices label="Studenti del gruppo" value={f.members} onChange={(v) => set("members", v)} options={d.students.map((s) => ({ v: s.id, label: s.display_name }))} /> : <Notice kind="warn">Nessuno studente registrato: aggiungilo nella pagina Famiglie.</Notice>}
          </Field>
          <Field label="Nome del gruppo" optional id="rq-group"><Input id="rq-group" value={f.group_label} maxLength={100} onChange={(e) => set("group_label", e.target.value)} placeholder="Es. Recupero algebra 2ª B" /></Field>
          {f.members.length > 0 && <p className="muted rq-tip">{f.members.length} {f.members.length === 1 ? "studente scelto" : "studenti scelti"}{f.members.length < 2 ? ": servono almeno 2 studenti." : f.members.length > MAX_GROUP ? `: al massimo ${MAX_GROUP}.` : "."}</p>}
        </> : <Field label="Studente">{d.students.length ? <Choices label="Studente" value={f.student} onChange={(v) => set("student", v)} options={d.students.map((s) => ({ v: s.id, label: s.display_name, av: s.display_name }))} /> : <Notice kind="warn">Nessuno studente collegato al tuo profilo.</Notice>}</Field>}
        <Field label="Materia">{!opts ? <p className="muted">Carico le materie…</p> : opts.subjects.length ? <Choices label="Materia" value={f.subject} onChange={(v) => setF((x) => keepTutors(x, v, x.mode))} options={subjectList.map((s) => ({ v: s.id, label: s.name }))} /> : <Notice kind="warn">{center ? "Nessuna materia attiva: aggiungila nella pagina Materie." : "Nessuna materia disponibile: il centro deve prima registrare le competenze dei tutor."}</Notice>}</Field>
      </section>}

      <section className="rq-sec" aria-labelledby="rq-s3"><h3 id="rq-s3">{!edit && n(3)}Quando</h3>
        {single && <>
          <Field label="Quando"><SegCtl label="Quando" value={f.when} onChange={(v) => set("when", v)} options={[["DAY", "In un giorno"], ["WEEK", "Nella settimana"]]} /></Field>
          {f.when === "DAY" ? <>
            <Field label="Giorno"><DateField label="Giorno" value={f.day} min={edit ? undefined : today} onChange={(v) => set("day", v)} /></Field>
            <Check checked={f.timed} onChange={(v) => set("timed", v)}>{center ? "Piazza la lezione a un orario preciso" : "Indica anche l’orario"}</Check>
            {f.timed ? <Field label="Ora di inizio" id="rq-time" hint={center ? "La lezione viene collocata esattamente qui, se tutor e spazio sono liberi." : "Il centro prova a rispettarlo; se non è possibile ti propone un altro orario."}>
              <select id="rq-time" className="inp" value={f.time} onChange={(e) => set("time", e.target.value)}>{TIMES.map((t) => <option key={t} value={t}>{t}</option>)}</select></Field>
              : <p className="muted rq-tip">L’orario viene scelto tra le fasce libere di studente e tutor in quel giorno.</p>}
          </> : <Field label="Settimana" hint={`Da ${dayLabel(f.week).toLowerCase()} a ${dayLabel(addDays(f.week, 6)).toLowerCase()}: giorno e ora si trovano tra le fasce libere.`}>
            <DateField label="Settimana" value={f.week} min={edit ? undefined : mondayOf(today)} onChange={(v) => set("week", mondayOf(v))} /></Field>}
        </>}
        {!single && <>
          <Field label="Lezioni a settimana"><SegCtl label="Lezioni a settimana" value={f.sessions_per_week} onChange={(v) => set("sessions_per_week", v)} options={[["1", "1"], ["2", "2"], ["3", "3"], ["4", "4"], ["5", "5"]]} /></Field>
          <div className="grid2">
            <Field label="Dal"><DateField label="Dal" value={f.period_start} min={edit ? undefined : today} onChange={(v) => set("period_start", v)} /></Field>
            <Field label="Fino al" hint="Di norma la fine dell’anno scolastico."><DateField label="Fino al" value={f.period_end} min={f.period_start} onChange={(v) => set("period_end", v)} /></Field>
          </div>
        </>}
      </section>

      <section className="rq-sec" aria-labelledby="rq-s4"><h3 id="rq-s4">{!edit && n(4)}Lezione e tutor</h3>
        <div className="grid2">
          <Field label="Modalità"><SegCtl label="Modalità" value={f.mode} onChange={(v) => setF((x) => keepTutors(x, x.subject || edit?.subject || "", v))} options={[["IN_PERSON", "In presenza"], ["ONLINE", "Online"]]} /></Field>
          <Field label="Durata"><SegCtl label="Durata" value={f.duration_minutes} onChange={(v) => set("duration_minutes", v)} options={[["60", "1 h"], ["90", "1 h 30"], ["120", "2 h"]]} /></Field>
        </div>
        {series ? <Field label="Tutor" hint={center ? "Lo stesso tutor segue tutte le lezioni: è un vincolo rigido del calcolo." : "Sarà lo stesso per tutte le lezioni. Se non hai preferenze lo sceglie il centro all’approvazione."}>
          {tutorPool.length || !center ? <Choices label="Tutor" value={f.series_tutor} onChange={(v) => set("series_tutor", v)}
            options={[...(center ? [] : [{ v: "", label: "Lo sceglie il centro" }]), ...tutorPool.map((t) => ({ v: t.id, label: t.display_name, av: t.display_name }))]} />
            : <p className="muted">{f.subject || edit ? "Nessun tutor insegna questa materia in questa modalità: aggiungi la competenza nella pagina Tutor." : "Scegli prima la materia."}</p>}
        </Field> : <>
          <Field label="Tutor" hint={f.tutor_choice === "REQUIRED" ? "Vincolo rigido: se il tutor non ha posto, la lezione non viene collocata." : f.tutor_choice === "PREFERRED" ? "Viene scelto quando possibile, senza togliere lezioni ad altri." : "Si sceglie tra i tutor che insegnano la materia."}>
            <SegCtl label="Scelta del tutor" value={f.tutor_choice} onChange={(v) => set("tutor_choice", v)} options={[["ANY", "Qualsiasi"], ["PREFERRED", "Preferito"], ["REQUIRED", "Obbligatorio"]]} />
          </Field>
          {f.tutor_choice !== "ANY" && <Field label={f.tutor_choice === "REQUIRED" ? "Solo con" : "Preferibilmente con"}>
            {tutorPool.length ? <MultiChoices label="Tutor" value={f.preferred_tutor_ids} onChange={(v) => set("preferred_tutor_ids", v)} options={tutorPool.map((t) => ({ v: t.id, label: t.display_name }))} />
              : <p className="muted">{f.subject || edit ? "Nessun tutor insegna questa materia in questa modalità." : "Scegli prima la materia."}</p>}
          </Field>}
        </>}
      </section>

      {center && <section className="rq-sec" aria-labelledby="rq-s5"><h3 id="rq-s5">{!edit && n(5)}Pianificazione</h3>
        <div className="grid2">
          <Field label="Priorità" hint="P0 è la più importante: viene coperta per prima."><SegCtl label="Priorità" value={f.priority} onChange={(v) => set("priority", v)} options={[["P0", "P0 alta"], ["P1", "P1"], ["P2", "P2 bassa"]]} /></Field>
          <Field label="Obbligatoria"><Check checked={f.mandatory} onChange={(v) => set("mandatory", v)}>Deve essere collocata anche in “Il più possibile”</Check></Field>
        </div>
      </section>}

      <Field label="Note" optional><Input value={f.notes} maxLength={500} onChange={(e) => set("notes", e.target.value)} placeholder={center ? "Es. preferenze emerse al colloquio" : "Es. verifica a fine mese, meglio il pomeriggio"} /></Field>
      {line && <div className="rq-recap" aria-live="polite"><Icon n="check" /><p><b>Riepilogo</b> {line}</p></div>}
      {err && <Notice kind="bad">{err}</Notice>}
    </div>
    {g.asking ? <GuardFoot onKeep={g.keep} onDiscard={() => { g.allow(); onClose(); }} />
      : <div className="modal-foot"><button type="button" className="pill-btn ghost" onClick={() => { if (g.guard()) onClose(); }}>Chiudi</button>
        <Btn type="submit" kind="primary" isle="check" disabled={busy}>{busy ? (center ? "Calcolo le lezioni…" : "Invio…") : edit ? "Salva" : center ? "Crea e calcola le lezioni" : "Invia al centro"}</Btn></div>}
  </form></Modal>;
}

/** Approvazione con scelta del tutor: obbligatoria per i percorsi senza tutor,
 *  facoltativa per le altre richieste (assegna un tutor obbligatorio). */
export function ApproveModal({ req, onClose, onDone }: { req: Req | null; onClose: () => void; onDone: (r: Req) => void }) {
  const [opts, setOpts] = useState<Options | null>(null), [tutor, setTutor] = useState(""), [note, setNote] = useState(""), [err, setErr] = useState(""), [busy, setBusy] = useState(false);
  useEffect(() => { if (!req) return; setTutor((req.preferred_tutors || [])[0]?.id || ""); setNote(""); setErr(""); if (!opts) api<Options>("/teaching-requests/options/").then(setOpts).catch((e) => setErr(human(e).text)); }, [req]); // eslint-disable-line
  if (!req) return null;
  const pool = (opts?.subjects.find((s) => s.id === req.subject)?.tutors || []).filter((t) => t.modes.includes(req.mode || "IN_PERSON"));
  const must = req.kind === "SERIES";
  async function go() {
    if (must && !tutor) { setErr("Scegli il tutor che seguirà le lezioni."); return; }
    setBusy(true); setErr("");
    try { onDone(await review(req!.id, "approve", note.trim(), tutor ? { tutor_id: tutor } : {})); }
    catch (e) { setErr(human(e).text); } finally { setBusy(false); }
  }
  return <Modal open onClose={onClose} labelledBy="ap-title" width={560}><div className="modal-body">
    <h2 id="ap-title">Approva: {req.subject_name}{req.student_name ? ` · ${req.student_name}` : ""}</h2>
    <p className="lead">{whenText(req)} · {durText(req.duration_minutes)} · {modeText(req.mode)}.</p>
    <Field label="Tutor" hint={must ? "Seguirà tutte le lezioni ricorrenti." : "Facoltativo: se lo scegli, la lezione si colloca solo con lui."}>
      {!opts ? <p className="muted">Carico i tutor…</p> : pool.length ? <Choices label="Tutor" value={tutor} onChange={setTutor} options={[...(must ? [] : [{ v: "", label: "Qualsiasi" }]), ...pool.map((t) => ({ v: t.id, label: t.display_name, av: t.display_name }))]} />
        : <Notice kind="warn">Nessun tutor insegna questa materia in questa modalità: aggiungi la competenza nella pagina Tutor.</Notice>}
    </Field>
    <Field label="Nota per la famiglia" optional id="ap-note"><Input id="ap-note" maxLength={300} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Es. confermato con la prof.ssa Rossi" /></Field>
    {req.notes && <p className="muted">Nota della richiesta: «{req.notes}»</p>}
    {err && <Notice kind="bad">{err}</Notice>}
  </div><div className="modal-foot"><button type="button" className="pill-btn ghost" onClick={onClose}>Annulla</button>
    <Btn kind="primary" isle="check" disabled={busy || (must && !pool.length)} onClick={go}>{busy ? "Calcolo le lezioni…" : "Approva e calcola le lezioni"}</Btn></div></Modal>;
}
