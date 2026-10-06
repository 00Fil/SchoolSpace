import { useEffect, useState } from "react";
import { api } from "../api";
import { request } from "../api/client";
import { dayLabel, hm, rome } from "../format";
import { human, MODE } from "../messages";
import { Btn, Notice, Skeleton, Tag } from "../ui/core";
import { Check, Field, SegCtl } from "../ui/controls";
import { Modal } from "../ui/layers";
import type { Lesson } from "../app/calendarApi";
import { joinLesson } from "../portal/VideoRoom";

/** P4 parte 2 · scheda lezione completa: sostituto, modifica (solo questa / da questa in poi),
 *  scambio, presenze e conclusione, correzione amministrativa, link video. */
type Sub = { tutor_id: string; name: string; ok: boolean; codes: string[] };
type Att = { lesson_version: number; entries: { student_id: string; status: string; minutes: number | null }[] };
type Scope = "ONE" | "FOLLOWING";
/** v0.10: minuti nella videolezione integrata, per precompilare le presenze. */
type Presence = { lesson_minutes: number; tutor_minutes: number; students: { student_id: string; joined: boolean; minutes: number }[] };
const key = () => ({ "Idempotency-Key": crypto.randomUUID() });
const post = <T,>(path: string, body: object) => api<T>(path, { method: "POST", headers: key(), body: JSON.stringify(body) });
const STATUS: [string, string][] = [["PRESENT", "Presente"], ["ABSENT", "Assente"], ["JUSTIFIED", "Giustificato"]];
const CODE: Record<string, string> = {
  TUTOR_AVAILABILITY: "non disponibile in quell’orario", TUTOR_DECLARED_NONE: "non ha dichiarato disponibilità", TUTOR_SKILLS_MISSING: "non abilitato per la materia",
  TUTOR_LIMIT: "supererebbe il carico massimo", TUTOR_LIMITS_MISSING: "limiti di carico non configurati", NOT_ADMISSIBLE: "non compatibile con i vincoli",
};
const why = (codes: string[]) => codes.map((c) => CODE[c] || c.toLowerCase().replaceAll("_", " ")).join(", ");
const when = (l: Lesson) => { const r = rome(l.start_at); return `${dayLabel(r.date)} alle ${hm(r.min)}`; };

function Dialog({ open, title, onClose, busy, confirm, onConfirm, err, children, disabled }: { open: boolean; title: string; onClose: () => void; busy: boolean; confirm: string; onConfirm: () => void; err: string; children: React.ReactNode; disabled?: boolean }) {
  return <Modal open={open} onClose={onClose} labelledBy="la-title"><div className="modal-body"><h2 id="la-title">{title}</h2>{children}{err && <Notice kind="bad">{err}</Notice>}</div>
    <div className="modal-foot"><button type="button" className="pill-btn ghost" onClick={onClose}>Annulla</button><Btn kind="primary" disabled={busy || disabled} onClick={onConfirm}>{busy ? "Controllo…" : confirm}</Btn></div></Modal>;
}
const ScopePick = ({ l, value, onChange }: { l: Lesson; value: Scope; onChange: (v: Scope) => void }) => l.series ?
  <SegCtl label="Applica a" value={value} options={[["ONE", "Solo questa lezione"], ["FOLLOWING", "Da questa in poi"]]} onChange={onChange} /> : null;

/** «Da questa in poi» sulle serie: nuovo segmento dalla data della lezione (split). */
async function splitFrom(l: Lesson, changes: Record<string, unknown>, reason: string) {
  const s = await api<{ version: number }>(`/lesson-series/${l.series}/`);
  return post(`/lesson-series/${l.series}/split/`, { expected_version: s.version, from_date: rome(l.start_at).date, changes, reason });
}
function message(e: unknown) {
  const h = human(e);
  if (h.code === "VERSION_CONFLICT") return "La lezione è stata appena modificata: chiudi e riapri la scheda.";
  if (h.code === "ATTENDANCE_INCOMPLETE") return "Registra la presenza di ogni partecipante prima di concludere.";
  if (h.code === "CALENDAR_VALIDATION_FAILED") return "La modifica non rispetta disponibilità o vincoli attuali. " + h.text;
  return h.text;
}

type Propose = (body: Record<string, unknown>, what: string) => Promise<void>;
/** v0.9.11: sostituto, modifica e scambio di una singola lezione sono rettifiche del calendario del mese
 *  (in bozza, o pubblicate subito); «da questa in poi» sulle serie resta immediato. */
const NowPick = ({ value, onChange }: { value: boolean; onChange: (v: boolean) => void }) => <>
  <Check checked={value} onChange={onChange}>Pubblica subito la rettifica</Check>
  <p className="fine">{value ? "La modifica entra adesso nel calendario pubblico e tutor e famiglie ricevono l’avviso." : "La modifica entra nella bozza del mese: tutor e famiglie la vedono quando pubblichi le rettifiche."}</p>
</>;

export default function LessonActions({ l, lessons, onDone, propose }: { l: Lesson; lessons: Lesson[]; onDone: (msg: string) => Promise<void>; propose?: Propose }) {
  const [open, setOpen] = useState<"" | "sub" | "modify" | "swap" | "close" | "fix">("");
  const [reason, setReason] = useState(""), [busy, setBusy] = useState(false), [err, setErr] = useState(""), [scope, setScope] = useState<Scope>("ONE");
  const [subs, setSubs] = useState<Sub[] | null>(null), [pick, setPick] = useState(""), [mode, setMode] = useState(l.mode), [other, setOther] = useState("");
  const [now_, setNow] = useState(false);
  const [presence, setPresence] = useState<Presence | null>(null);
  const [att, setAtt] = useState<Att | null>(null), [entries, setEntries] = useState<Record<string, string>>({}), [sure, setSure] = useState(false), [link, setLink] = useState("");
  const now = Date.now(), future = new Date(l.start_at).getTime() > now, ended = new Date(l.end_at).getTime() <= now;
  const active = l.state === "PUBLISHED";
  function start(kind: typeof open, text: string) { setOpen(kind); setReason(text); setErr(""); setBusy(false); setScope("ONE"); setSure(false); setNow(false); }
  /** Rettifica del mese (se disponibile) oppure chiamata diretta come prima. */
  async function corr(body: Record<string, unknown>, what: string, direct: () => Promise<unknown>, msg: string) {
    if (!propose) return run(direct, msg);
    setBusy(true); setErr("");
    try { await propose({ ...body, lesson_id: l.id, reason: reason.trim(), publish_now: now_ }, what); setOpen(""); } catch (e) { setErr(message(e)); } finally { setBusy(false); }
  }
  async function run(fn: () => Promise<unknown>, msg: string) {
    setBusy(true); setErr("");
    try { await fn(); setOpen(""); await onDone(msg); } catch (e) { setErr(message(e)); } finally { setBusy(false); }
  }
  useEffect(() => {
    if (open === "sub") { setSubs(null); setPick(""); api<{ substitutes: Sub[] }>(`/occurrences/${l.id}/substitutes/`).then((r) => { setSubs(r.substitutes); setPick(r.substitutes.find((s) => s.ok)?.tutor_id || ""); }).catch((e) => { setSubs([]); setErr(message(e)); }); }
    if (open === "close" || open === "fix") {
      setAtt(null); setPresence(null);
      // Videolezione: chi non è mai entrato in stanza viene proposto «Assente» (il tutor conferma).
      const seen = l.mode === "ONLINE" ? request<Presence>("GET", `/occurrences/${l.id}/meeting/presence`, { quiet: true }).catch(() => null) : Promise.resolve(null);
      Promise.all([api<Att>(`/occurrences/${l.id}/attendance/`), seen]).then(([a, p]) => {
        setAtt(a); setPresence(p);
        const joined = new Map((p?.students || []).map((s) => [s.student_id, s.joined]));
        const tracked = !!p && (p.tutor_minutes > 0 || p.students.some((s) => s.joined));
        setEntries(Object.fromEntries(a.entries.map((x) => [x.student_id, x.status !== "NOT_RECORDED" ? x.status : tracked && joined.get(x.student_id) === false ? "ABSENT" : "PRESENT"])));
      }).catch((e) => setErr(message(e)));
    }
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps
  const entryList = () => Object.entries(entries).map(([student_id, status]) => ({ student_id, status }));
  const candidates = lessons.filter((x) => x.id !== l.id && x.state === "PUBLISHED" && new Date(x.start_at).getTime() > now);
  const name = (id: string) => l.participants.find((p) => p.student_id === id)?.name || "Studente";
  const ok = subs?.filter((s) => s.ok) || [], ko = subs?.filter((s) => !s.ok) || [];

  return <>
    <div className="controls" style={{ flexWrap: "wrap", gap: 8, margin: "14px 0" }}>
      {active && future && <>
        <Btn kind="sm" onClick={() => start("sub", "Sostituzione per assenza del tutor")}>Sostituisci il tutor</Btn>
        <Btn kind="sm" onClick={() => { start("modify", "Modifica concordata con la famiglia"); setMode(l.mode); }}>Modifica</Btn>
        <Btn kind="sm" disabled={!candidates.length} onClick={() => { start("swap", "Scambio di orario concordato"); setOther(""); }}>Scambia con un’altra</Btn>
      </>}
      {active && ended && <Btn kind="sm" onClick={() => start("close", "Lezione svolta")}>Presenze e conclusione</Btn>}
      {l.state === "COMPLETED" && <Btn kind="sm" onClick={() => start("fix", "Correzione delle presenze")}>Correggi le presenze</Btn>}
      {active && l.mode === "ONLINE" && <Btn kind="sm" onClick={async () => { setLink(""); try { const r = await joinLesson(l.id); if (!r.provider) setLink(r.join_url); } catch (e) { setLink("! " + (human(e).code === "MEETING_NOT_CONFIGURED" ? "Videolezioni non attive: imposta VIDEO_PROVIDER=jitsi oppure un link manuale per il canale." : human(e).text)); } }}>Entra nella videolezione</Btn>}
    </div>
    {link && (link.startsWith("! ") ? <Notice kind="warn">{link.slice(2)}</Notice> : <Notice kind="ok" title="Link della lezione"><a href={link} target="_blank" rel="noreferrer noopener">{link}</a></Notice>)}

    <Dialog open={open === "sub"} title="Sostituisci il tutor" onClose={() => setOpen("")} busy={busy} err={err}
      confirm={subs && !ok.length ? "Annulla con recupero" : "Assegna il sostituto"} disabled={!subs || (!!ok.length && !pick)}
      onConfirm={() => ok.length
        ? scope === "FOLLOWING" ? run(() => splitFrom(l, { tutor_id: pick }, reason.trim()), "Sostituto assegnato")
          : corr({ op: "modify", changes: { tutor_id: pick } }, `Sostituto per ${l.subject_name}`, () => post(`/occurrences/${l.id}/modify/`, { expected_version: l.version, reason: reason.trim(), changes: { tutor_id: pick } }), "Sostituto assegnato")
        : run(async () => { const c = await post<{ version?: number }>(`/occurrences/${l.id}/cancel/`, { expected_version: l.version, reason: reason.trim() }); await post(`/occurrences/${l.id}/recovery/`, { expected_version: c?.version ?? l.version + 1, reason: reason.trim(), cause: "TUTOR_ABSENCE", participant_ids: l.participants.map((p) => p.student_id) }); }, "Lezione annullata: recupero da fissare in «Da gestire»")}>
      <p className="muted">{when(l)} · tutor attuale {l.tutor_name}. Regola del centro: prima un sostituto, altrimenti recupero.</p>
      {!subs ? <Skeleton rows={3} /> : <>
        {ok.length ? <fieldset className="choices"><legend>Tutor disponibili e abilitati</legend>{ok.map((s) => <label key={s.tutor_id} className="radio"><input type="radio" name="sub" checked={pick === s.tutor_id} onChange={() => setPick(s.tutor_id)} /> {s.name}</label>)}</fieldset>
          : <Notice kind="warn" title="Nessun sostituto possibile">Puoi annullare la lezione e creare il recupero per {l.participants.length > 1 ? "i partecipanti" : "lo studente"}.</Notice>}
        {ko.length > 0 && <details><summary>Non disponibili ({ko.length})</summary><ul>{ko.map((s) => <li key={s.tutor_id}>{s.name}: {why(s.codes)}</li>)}</ul></details>}
        {ok.length > 0 && <ScopePick l={l} value={scope} onChange={setScope} />}
        {ok.length > 0 && scope === "ONE" && propose && <NowPick value={now_} onChange={setNow} />}
      </>}
    </Dialog>

    <Dialog open={open === "modify"} title="Modifica la lezione" onClose={() => setOpen("")} busy={busy} err={err} confirm="Salva" disabled={mode === l.mode}
      onConfirm={() => { const changes = { mode, location: mode === "ONLINE" ? "REMOTE" : "ON_SITE", ...(mode === "ONLINE" ? { space_id: null } : { video_id: null }) };
        if (scope === "FOLLOWING") run(() => splitFrom(l, changes, reason.trim()), "Lezione modificata");
        else corr({ op: "modify", changes }, `Modalità di ${l.subject_name}`, () => post(`/occurrences/${l.id}/modify/`, { expected_version: l.version, reason: reason.trim(), changes }), "Lezione modificata"); }}>
      <p className="muted">Per cambiare giorno o ora usa «Sposta»; per il tutor «Sostituisci il tutor».</p>
      <SegCtl label="Modalità" value={mode} options={[["IN_PERSON", MODE.IN_PERSON], ["ONLINE", MODE.ONLINE]]} onChange={setMode} />
      <ScopePick l={l} value={scope} onChange={setScope} />
      {scope === "FOLLOWING" && <Notice kind="info">Le lezioni della serie da {dayLabel(rome(l.start_at).date)} in poi seguiranno la nuova modalità; quelle precedenti restano com’erano.</Notice>}
      {scope === "ONE" && propose && <NowPick value={now_} onChange={setNow} />}
    </Dialog>

    <Dialog open={open === "swap"} title="Scambia l’orario" onClose={() => setOpen("")} busy={busy} err={err} confirm="Scambia" disabled={!other}
      onConfirm={() => { const o = candidates.find((x) => x.id === other)!; corr({ op: "swap", other_id: o.id }, `Scambio ${l.subject_name} ↔ ${o.subject_name}`, () => post("/occurrences/swap/", { first_id: l.id, first_version: l.version, second_id: o.id, second_version: o.version, reason: reason.trim() }), "Orari scambiati"); }}>
      <Field label="Con quale lezione" id="la-swap"><select id="la-swap" className="inp" value={other} onChange={(e) => setOther(e.target.value)}><option value="">Scegli…</option>{candidates.map((x) => <option key={x.id} value={x.id}>{when(x)} · {x.subject_name} · {x.participants.map((p) => p.name).join(", ")}</option>)}</select></Field>
      <p className="muted">Le due lezioni si scambiano giorno e ora. Il controllo verifica che entrambe restino valide.</p>
      {propose && <NowPick value={now_} onChange={setNow} />}
    </Dialog>

    <Dialog open={open === "close" || open === "fix"} title={open === "fix" ? "Correggi le presenze" : "Presenze e conclusione"} onClose={() => setOpen("")} busy={busy} err={err}
      confirm={open === "fix" ? "Salva la correzione" : "Salva e concludi"} disabled={!att || (open === "fix" && !sure)}
      onConfirm={() => open === "fix"
        ? run(() => post(`/occurrences/${l.id}/admin-correction/`, { expected_version: att!.lesson_version, reason: reason.trim(), entries: entryList(), confirm_correction: true }), "Presenze corrette")
        : run(async () => { const a = await post<{ lesson_version?: number }>(`/occurrences/${l.id}/attendance/`, { expected_version: att!.lesson_version, entries: entryList(), reason: reason.trim() }); await post(`/occurrences/${l.id}/complete/`, { expected_version: a?.lesson_version ?? att!.lesson_version, reason: reason.trim() }); }, "Lezione conclusa")}>
      {!att ? <Skeleton rows={2} /> : att.entries.map((x) => <div key={x.student_id} style={{ marginBottom: 10 }}><SegCtl label={name(x.student_id)} value={entries[x.student_id]} options={STATUS} onChange={(v) => setEntries({ ...entries, [x.student_id]: v })} />{presence && (() => { const p = presence.students.find((s) => s.student_id === x.student_id); return p ? <p className="fine">{p.joined ? `In videolezione ${p.minutes} min su ${presence.lesson_minutes}` : "Mai entrato nella videolezione"}</p> : null; })()}</div>)}
      {presence && <p className="muted">Proposta automatica dalla videolezione: controlla prima di salvare.</p>}
      {open === "fix" && <><Notice kind="warn">La lezione è già conclusa: la correzione resta nello storico.</Notice><Check checked={sure} onChange={setSure}>Confermo la correzione</Check></>}
      {open === "close" && entryList().some((e) => e.status === "ABSENT") && <p className="muted">Per un’assenza avvisata almeno 24 ore prima crea il recupero da «Da gestire».</p>}
    </Dialog>
  </>;
}
