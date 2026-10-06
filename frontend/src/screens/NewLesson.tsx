/** «Nuova lezione» (v0.9.8): il centro crea una lezione con la famiglia davanti.
 *  Stesse scelte del modulo delle famiglie (studente, materia, modalità, durata, tutor),
 *  ma l'orario si sceglie tra quelli proposti dal motore e la lezione nasce subito in
 *  calendario: famiglia e tutor ricevono la notifica. Dall'agenda arriva già con tutor,
 *  giorno e orario trascinati. */
import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import { addDays, dayLabel, hm, rangeOf, rome, romeISO, todayRome } from "../format";
import { human } from "../messages";
import { Btn, Notice } from "../ui/core";
import { Choices, Combo, ComboItem, DateField, Field, Input, SegCtl } from "../ui/controls";
import { GuardFoot, Modal, useDirtyGuard } from "../ui/layers";
import { go } from "../ui/route";
import { Slot, SlotPicker, slotKey } from "../ui/SlotPicker";
import { useData } from "../app/data";
import type { Options } from "./requestForms";

export type NewLessonPrefill = { tutor?: string; date?: string; start?: number; end?: number };
type Check = { ok: boolean; reasons: string[]; start_at: string; end_at: string; tutor_id: string; space_id: string | null };
type Res = { options: Slot[]; check: Check | null; tutors: number; message?: string };

const DURS = [60, 90, 120];
const nearest = (m: number) => DURS.reduce((a, b) => (Math.abs(b - m) < Math.abs(a - m) ? b : a), 60);

export function NewLessonModal({ open, prefill, onClose, onCreated }: { open: boolean; prefill?: NewLessonPrefill | null; onClose: () => void; onCreated: (msg: string, date: string) => void }) {
  const d = useData();
  const [opts, setOpts] = useState<Options | null>(null);
  const [student, setStudent] = useState<ComboItem | null>(null), [subject, setSubject] = useState(""), [mode, setMode] = useState("IN_PERSON");
  const [dur, setDur] = useState("60"), [tutor, setTutor] = useState(""), [from, setFrom] = useState(todayRome()), [notes, setNotes] = useState("");
  const [res, setRes] = useState<Res | null>(null), [pick, setPick] = useState<Slot | null>(null), [err, setErr] = useState(""), [busy, setBusy] = useState(false);
  const seq = useRef(0);
  const dirty = open && !!(student || subject);
  const g = useDirtyGuard(dirty);
  useEffect(() => { if (open && !opts) api<Options>("/teaching-requests/options/").then(setOpts).catch((e) => setErr(human(e).text)); }, [open]); // eslint-disable-line
  useEffect(() => {
    if (!open) return;
    setStudent(null); setSubject(""); setMode("IN_PERSON"); setNotes(""); setErr(""); setPick(null); setRes(null); g.reset();
    setTutor(prefill?.tutor || ""); setFrom(prefill?.date || todayRome());
    setDur(String(prefill?.start !== undefined && prefill?.end !== undefined ? nearest(prefill.end - prefill.start) : 60));
  }, [open, prefill]); // eslint-disable-line react-hooks/exhaustive-deps
  const people = useMemo(() => d.students.map((s) => ({ id: s.id, label: s.display_name, sub: s.level || undefined })).sort((a, b) => a.label.localeCompare(b.label, "it")), [d.students]);
  // con un tutor già scelto (dall'agenda) le materie sono le sue
  const subjects = (opts?.subjects || []).filter((s) => !prefill?.tutor || s.tutors.some((t) => t.id === prefill.tutor));
  const subj = subjects.find((s) => s.id === subject);
  const tutors = (subj?.tutors || []).filter((t) => t.modes.includes(mode));
  const exact = prefill?.date && prefill.start !== undefined ? romeISO(prefill.date, prefill.start) : null;
  const ready = !!(student && subject && (!prefill?.tutor || tutors.some((t) => t.id === prefill.tutor)));

  useEffect(() => { // il tutor scelto deve insegnare la materia nella modalità
    if (tutor && subj && !tutors.some((t) => t.id === tutor)) setTutor(prefill?.tutor && tutors.some((t) => t.id === prefill.tutor) ? prefill.tutor : "");
  }, [subject, mode]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!open || !ready) { setRes(null); return; }
    const n = ++seq.current; setRes(null); setPick(null);
    const body = { student_id: student!.id, subject_id: subject, mode, duration_minutes: Number(dur), tutor_id: tutor || null, date_from: from, date_to: addDays(from, 13), ...(exact ? { start_at: exact } : {}) };
    const t = window.setTimeout(() => api<Res>("/lessons/options/", { method: "POST", body: JSON.stringify(body) }).then((r) => {
      if (n !== seq.current) return; setRes(r);
      if (r.check?.ok) setPick({ date: rome(r.check.start_at).date, start_at: r.check.start_at, end_at: r.check.end_at, tutor_id: r.check.tutor_id, tutor_name: tutors.find((x) => x.id === r.check!.tutor_id)?.display_name || "", space_id: r.check.space_id });
    }).catch((e) => { if (n === seq.current) { setErr(human(e).text); setRes({ options: [], check: null, tutors: 0 }); } }), 180);
    return () => window.clearTimeout(t);
  }, [open, ready, student?.id, subject, mode, dur, tutor, from]); // eslint-disable-line react-hooks/exhaustive-deps

  async function create() {
    if (!pick || !student) return;
    setBusy(true); setErr("");
    try {
      await api("/lessons/", { method: "POST", body: JSON.stringify({ student_id: student.id, subject_id: subject, mode, duration_minutes: Number(dur), tutor_id: pick.tutor_id, start_at: pick.start_at, notes: notes.trim() }) });
      g.allow(); onCreated(`Lezione creata: ${subj?.name} per ${student.label}, ${dayLabel(pick.date).toLowerCase()} ${rangeOf(pick.start_at, pick.end_at)}. Famiglia e tutor ricevono la notifica.`, pick.date);
    } catch (e) { setErr(human(e).text); } finally { setBusy(false); }
  }

  const tutorName = (id: string) => tutors.find((t) => t.id === id)?.display_name || d.tutors.find((t) => t.id === id)?.display_name || "";
  const fixedTutor = prefill?.tutor ? tutorName(prefill.tutor) : "";
  const n = (k: number) => <span className="rq-n" aria-hidden="true">{k}</span>;
  return <Modal open={open} onClose={onClose} guard={g.guard} labelledBy="nl-title" width={720}><form onSubmit={(e) => { e.preventDefault(); void create(); }} noValidate>
    <div className="modal-body rq-form">
      <h2 id="nl-title">Nuova lezione</h2>
      

      <section className="rq-sec" aria-labelledby="nl-s1"><h3 id="nl-s1">{n(1)}Per chi e quale materia</h3>
        <Field label="Studente" id="nl-student">{people.length ? <Combo id="nl-student" value={student} items={people} placeholder="Cerca per nome" onPick={setStudent} /> : <Notice kind="warn">Nessuno studente registrato: aggiungilo nella pagina Famiglie.</Notice>}</Field>
        <Field label="Materia">{!opts ? <p className="muted">Carico le materie…</p> : subjects.length
          ? <Choices label="Materia" value={subject} onChange={setSubject} options={subjects.map((s) => ({ v: s.id, label: s.name }))} />
          : <Notice kind="warn">{fixedTutor ? `${fixedTutor} non ha competenze approvate.` : "Nessuna materia attiva: aggiungila nella pagina Materie."}</Notice>}</Field>
      </section>

      <section className="rq-sec" aria-labelledby="nl-s2"><h3 id="nl-s2">{n(2)}Lezione e tutor</h3>
        <div className="grid2">
          <Field label="Modalità"><SegCtl label="Modalità" value={mode} onChange={setMode} options={[["IN_PERSON", "In presenza"], ["ONLINE", "Online"]]} /></Field>
          <Field label="Durata"><SegCtl label="Durata" value={dur} onChange={setDur} options={[["60", "1 h"], ["90", "1 h 30"], ["120", "2 h"]]} /></Field>
        </div>
        {fixedTutor ? <p className="fine">Tutor: <b>{fixedTutor}</b> (scelto nell’agenda)</p>
          : <Field label="Tutor" hint="Con «Qualsiasi» il motore cerca tra tutti i tutor competenti.">{subject ? (tutors.length
            ? <Choices label="Tutor" value={tutor} onChange={setTutor} options={[{ v: "", label: "Qualsiasi" }, ...tutors.map((t) => ({ v: t.id, label: t.display_name, av: t.display_name }))]} />
            : <p className="muted">Nessun tutor insegna questa materia in questa modalità.</p>) : <p className="muted">Scegli prima la materia.</p>}</Field>}
      </section>

      <section className="rq-sec" aria-labelledby="nl-s3"><h3 id="nl-s3">{n(3)}Quando</h3>
        {exact && ready && res?.check && <div className={"nl-exact " + (res.check.ok ? "ok" : "bad")}>
          <b>{dayLabel(prefill!.date!)} · {hm(prefill!.start!)}–{hm(prefill!.start! + Number(dur))}</b>
          <span>{res.check.ok ? "Orario scelto nell’agenda: libero per tutti." : `Orario scelto nell’agenda non disponibile: ${res.check.reasons.join("; ")}. Scegli tra gli orari proposti.`}</span>
        </div>}
        <Field label="A partire dal"><DateField label="A partire dal" value={from} min={todayRome()} onChange={setFrom} /></Field>
        <span className="lbl sp-lbl">Orari proposti nei prossimi 14 giorni</span>
        {!ready ? <p className="sp-empty">Scegli studente e materia per vedere gli orari liberi.</p>
          : <SlotPicker slots={res ? res.options : null} value={pick ? slotKey(pick) : ""} onPick={setPick}
            empty={res?.message || "Nessun orario libero per studente e tutor in questi 14 giorni: prova un’altra data, un altro tutor o l’altra modalità."} />}
      </section>

      <Field label="Note" optional id="nl-notes"><Input id="nl-notes" value={notes} maxLength={500} onChange={(e) => setNotes(e.target.value)} placeholder="Es. concordata in sede con la mamma" /></Field>
      {pick && student && subj && <div className="rq-recap" aria-live="polite"><p><b>Riepilogo</b> {subj.name} per {student.label}, {dayLabel(pick.date).toLowerCase()} {rangeOf(pick.start_at, pick.end_at)}, con {pick.tutor_name || tutorName(pick.tutor_id)}, {mode === "ONLINE" ? "online" : "in sede"}. Famiglia e tutor ricevono la notifica.</p></div>}
      {err && <Notice kind="bad">{err}</Notice>}
      
    </div>
    {g.asking ? <GuardFoot onKeep={g.keep} onDiscard={() => { g.allow(); onClose(); }} />
      : <div className="modal-foot"><button type="button" className="pill-btn ghost" onClick={() => { if (g.guard()) onClose(); }}>Chiudi</button>
        <Btn type="submit" kind="primary" disabled={!pick || busy}>{busy ? "Creo…" : "Crea la lezione"}</Btn></div>}
  </form></Modal>;
}
