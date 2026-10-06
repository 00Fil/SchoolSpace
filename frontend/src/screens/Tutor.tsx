/** P1 «Tutor»: scheda, competenze (materia × livello × modalità) e regole di carico, pause e spostamenti. */
import { FormEvent, useState } from "react";
import { Avatar, Btn, Empty, Icon, Notice, PageHead, Skeleton, Tag } from "../ui/core";
import { Check, Field, Input, SegCtl } from "../ui/controls";
import { Modal, Sheet, useToast } from "../ui/layers";
import { ErrorState } from "../ui/states";
import { setQuery, useRoute } from "../ui/route";
import { INVITE_STATUS, send, useList, writeError } from "./registry";

type Tutor = { id: string; display_name: string; email: string; active: boolean; has_account: boolean; invitation: { status: string } | null; version: number };
type Skill = { id: string; tutor: string; subject: string; level: string; mode: "IN_PERSON" | "ONLINE"; valid_from: string; valid_until: string; approved: boolean; version: number };
type Policy = { id: string; tutor: string; daily_limit_minutes: number; weekly_limit_minutes: number; pause_minutes: number; site_to_remote_minutes: number; remote_to_site_minutes: number; version: number };
type Subject = { id: string; name: string };
const MODE = { IN_PERSON: "Presenza", ONLINE: "Online" } as const;

export default function TutorScreen() {
  const r = useRoute(), q = r.q.get("q") || "", open = r.q.get("t"), f = (r.q.get("stato") || "attivi") as "attivi" | "tutti";
  const tutors = useList<Tutor>("/registry/tutors" + (f === "attivi" ? "?active=true" : ""));
  const skills = useList<Skill>("/tutor-skills/"), policies = useList<Policy>("/tutor-operating-policies/"), subjects = useList<Subject>("/subjects/");
  const [form, setForm] = useState<null | { kind: "tutor"; tutor?: Tutor } | { kind: "skill"; tutor: Tutor } | { kind: "policy"; tutor: Tutor; policy?: Policy } | { kind: "state"; tutor: Tutor } | { kind: "invite"; tutor: Tutor }>(null);
  const toast = useToast();
  const shown = (tutors.data || []).filter((t) => !q || (t.display_name + " " + t.email).toLowerCase().includes(q.toLowerCase()));
  const sel = tutors.data?.find((t) => t.id === open) || null;
  const subj = (id: string) => subjects.data?.find((s) => s.id === id)?.name || "Materia";
  const refresh = () => { tutors.reload(); skills.reload(); policies.reload(); };
  const accountTag = (t: Tutor) => !t.active ? <Tag>Disattivato</Tag> : t.has_account ? <Tag tone="green">Account attivo</Tag> : t.invitation ? <Tag tone="amber">Invito: {INVITE_STATUS[t.invitation.status] || t.invitation.status}</Tag> : <Tag>Da invitare</Tag>;

  return <section className="module planner" aria-labelledby="h-tu">
    <PageHead id="h-tu" title="Tutor" lead="Chi insegna, cosa può insegnare e con quali limiti. Un tutor si può registrare prima che abbia un account.">
      <Btn kind="primary" isle="plus" onClick={() => setForm({ kind: "tutor" })}>Nuovo tutor</Btn>
    </PageHead>
    <div className="toolbar" style={{ marginBottom: 12 }}>
      <label className="field-search"><Icon n="search" /><span className="sr">Cerca tutor</span><input type="search" placeholder="Cerca per nome o email…" value={q} onChange={(e) => setQuery((x) => (e.target.value ? x.set("q", e.target.value) : x.delete("q")))} /></label>
      <SegCtl label="Mostra" value={f} options={[["attivi", "Attivi"], ["tutti", "Tutti"]]} onChange={(v) => setQuery((x) => (v === "attivi" ? x.delete("stato") : x.set("stato", v)))} />
    </div>
    <div className="list-wrap">
      {tutors.error ? <ErrorState error={tutors.error} onRetry={tutors.reload} /> : !tutors.data ? <Skeleton />
        : shown.length ? <table className="list"><thead><tr><th scope="col">Tutor</th><th scope="col" className="hide-m">Competenze</th><th scope="col">Accesso</th></tr></thead>
          <tbody>{shown.map((t) => <tr key={t.id} className="row" tabIndex={0} aria-label={`Apri la scheda di ${t.display_name}`} onClick={() => setQuery((p) => p.set("t", t.id))} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setQuery((p) => p.set("t", t.id)); } }}>
            <td><span className="who"><Avatar name={t.display_name} k={t.id} /><span><b>{t.display_name}</b><small className="muted">{t.email || "Email non indicata"}</small></span></span></td>
            <td className="hide-m num">{(skills.data || []).filter((s) => s.tutor === t.id).length}</td><td>{accountTag(t)}</td></tr>)}</tbody></table>
        : <Empty title={q ? `Nessun tutor corrisponde a “${q}”` : "Nessun tutor registrato"}>Aggiungi un tutor e invialo per email.</Empty>}
    </div>

    <Sheet open={!!sel} onClose={() => setQuery((x) => x.delete("t"))} labelledBy="sheet-tu">
      {sel && <div className="sheet-body">
        <div className="sheet-top"><div className="kind"><Tag tone="blue">Tutor</Tag>{accountTag(sel)}</div><button className="circle sm raised" aria-label="Chiudi" onClick={() => setQuery((x) => x.delete("t"))}><Icon n="x" /></button></div>
        <div className="sheet-id"><Avatar name={sel.display_name} k={sel.id} size={56} /><div><h2 id="sheet-tu">{sel.display_name}</h2><p className="muted">{sel.email || "Email non indicata"}</p></div></div>
        <div className="toolbar">
          <Btn onClick={() => setForm({ kind: "tutor", tutor: sel })}>Modifica</Btn>
          {sel.active && !sel.has_account && sel.email && <Btn isle="send" onClick={() => setForm({ kind: "invite", tutor: sel })}>{sel.invitation?.status === "SENT" ? "Invita di nuovo" : "Invia invito"}</Btn>}
          <Btn kind="ghost" onClick={() => setForm({ kind: "state", tutor: sel })}>{sel.active ? "Disattiva" : "Riattiva"}</Btn>
        </div>
        <h3>Competenze</h3>
        {skills.error ? <ErrorState error={skills.error} onRetry={skills.reload} /> : (() => {
          const mine = (skills.data || []).filter((s) => s.tutor === sel.id);
          return mine.length ? <table className="list"><thead><tr><th scope="col">Materia</th><th scope="col">Livello</th><th scope="col" className="hide-m">Modalità</th><th scope="col">Stato</th></tr></thead>
            <tbody>{mine.map((s) => <tr key={s.id}><td>{subj(s.subject)}</td><td>{s.level}</td><td className="hide-m">{MODE[s.mode]}</td><td>{s.approved ? <Tag tone="green">Approvata</Tag> : <Btn onClick={async () => { try { await send("PATCH", `/tutor-skills/${s.id}/`, { approved: true, expected_version: s.version }); toast("Competenza approvata"); skills.reload(); } catch (e) { toast(writeError(e)); } }}>Approva</Btn>}</td></tr>)}</tbody></table>
            : <p className="muted">Nessuna competenza: senza competenze approvate il tutor non viene pianificato.</p>;
        })()}
        <Btn isle="plus" onClick={() => setForm({ kind: "skill", tutor: sel })}>Aggiungi competenza</Btn>
        <h3>Regole di lavoro</h3>
        {(() => { const p = (policies.data || []).find((x) => x.tutor === sel.id);
          return <>{p ? <dl className="facts"><dt>Massimo giornaliero</dt><dd>{p.daily_limit_minutes} min</dd><dt>Massimo settimanale</dt><dd>{p.weekly_limit_minutes} min</dd><dt>Pausa tra lezioni</dt><dd>{p.pause_minutes} min</dd><dt>Da sede a online</dt><dd>{p.site_to_remote_minutes} min</dd><dt>Da online a sede</dt><dd>{p.remote_to_site_minutes} min</dd></dl> : <p className="muted">Nessuna regola: valgono i limiti predefiniti del centro.</p>}
            <Btn onClick={() => setForm({ kind: "policy", tutor: sel, policy: p })}>{p ? "Modifica regole" : "Imposta regole"}</Btn></>; })()}
      </div>}
    </Sheet>
    {form && <TutorForm form={form} subjects={subjects.data || []} onClose={() => setForm(null)} onDone={(m) => { setForm(null); toast(m); refresh(); }} />}
  </section>;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function TutorForm({ form, subjects, onClose, onDone }: { form: any; subjects: Subject[]; onClose: () => void; onDone: (m: string) => void }) {
  const t: Tutor | undefined = form.tutor, p: Policy | undefined = form.policy;
  const [v, setV] = useState<Record<string, string>>({
    display_name: t?.display_name || "", email: t?.email || "", reason: "",
    subject: subjects[0]?.id || "", level: "", mode: "IN_PERSON", valid_from: new Date().toISOString().slice(0, 10), valid_until: "",
    daily: String(p?.daily_limit_minutes ?? 360), weekly: String(p?.weekly_limit_minutes ?? 1500), pause: String(p?.pause_minutes ?? 10), s2r: String(p?.site_to_remote_minutes ?? 30), r2s: String(p?.remote_to_site_minutes ?? 30),
  });
  const [invite, setInvite] = useState(true), [approved, setApproved] = useState(true), [err, setErr] = useState(""), [busy, setBusy] = useState(false);
  const set = (k: string) => (e: { target: { value: string } }) => setV((x) => ({ ...x, [k]: e.target.value }));
  const num = (k: string) => Number(v[k]);
  const titles: Record<string, string> = { tutor: t ? "Modifica tutor" : "Nuovo tutor", skill: "Nuova competenza", policy: "Regole di lavoro", state: t?.active ? "Disattiva tutor" : "Riattiva tutor", invite: "Invita il tutor" };
  async function submit(e: FormEvent) {
    e.preventDefault(); setBusy(true); setErr("");
    try {
      if (form.kind === "tutor") {
        if (t) await send("PATCH", `/registry/tutors/${t.id}`, { display_name: v.display_name, email: v.email, reason: v.reason, expected_version: t.version });
        else await send("POST", "/registry/tutors", { display_name: v.display_name, email: v.email, reason: v.reason, invite: invite && !!v.email });
        onDone("Tutor salvato");
      } else if (form.kind === "skill") {
        await send("POST", "/tutor-skills/", { tutor: t!.id, subject: v.subject, level: v.level, mode: v.mode, valid_from: v.valid_from, valid_until: v.valid_until, approved });
        onDone("Competenza aggiunta");
      } else if (form.kind === "policy") {
        const body = { daily_limit_minutes: num("daily"), weekly_limit_minutes: num("weekly"), pause_minutes: num("pause"), site_to_remote_minutes: num("s2r"), remote_to_site_minutes: num("r2s") };
        if (p) await send("PATCH", `/tutor-operating-policies/${p.id}/`, { ...body, expected_version: p.version });
        else await send("POST", "/tutor-operating-policies/", { ...body, tutor: t!.id });
        onDone("Regole salvate");
      } else if (form.kind === "state") {
        await send("POST", `/registry/tutors/${t!.id}/${t!.active ? "deactivate" : "reactivate"}`, { reason: v.reason, expected_version: t!.version });
        onDone(t!.active ? "Tutor disattivato" : "Tutor riattivato");
      } else {
        await send("POST", `/registry/tutors/${t!.id}/invite`, { reason: v.reason });
        onDone("Invito inviato");
      }
    } catch (e2) { setErr(writeError(e2)); }
    setBusy(false);
  }
  const minutes = (k: string, label: string) => <Field label={label} id={"t-" + k}><Input id={"t-" + k} type="number" min={0} required value={v[k]} onChange={set(k)} /></Field>;
  return <Modal open onClose={onClose} labelledBy="m-tu"><form className="modal-body" onSubmit={submit}>
    <h2 id="m-tu">{titles[form.kind]}</h2>
    {err && <Notice kind="bad">{err}</Notice>}
    {form.kind === "tutor" && <>
      <Field label="Nome" id="t-name"><Input id="t-name" required maxLength={120} value={v.display_name} onChange={set("display_name")} /></Field>
      <Field label="Email" id="t-email" optional hint={t?.has_account ? "Il tutor ha già un account: l’email si cambia dal suo profilo." : "Serve per inviare l’invito."}><Input id="t-email" type="email" disabled={t?.has_account} value={v.email} onChange={set("email")} /></Field>
      {!t && <Check checked={invite} onChange={setInvite}>Invia subito l’invito per creare l’account</Check>}</>}
    {form.kind === "skill" && <>
      {subjects.length ? <Field label="Materia" id="t-subj"><select id="t-subj" className="inp" value={v.subject} onChange={set("subject")}>{subjects.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select></Field> : <Notice kind="warn">Nessuna materia configurata: aggiungila nella pagina Materie.</Notice>}
      <Field label="Livello" id="t-level" hint="Usa gli stessi livelli degli studenti."><Input id="t-level" required maxLength={80} value={v.level} onChange={set("level")} /></Field>
      <Field label="Modalità" id="t-mode"><select id="t-mode" className="inp" value={v.mode} onChange={set("mode")}><option value="IN_PERSON">Presenza</option><option value="ONLINE">Online</option></select></Field>
      <Field label="Valida dal" id="t-vf"><Input id="t-vf" type="date" required value={v.valid_from} onChange={set("valid_from")} /></Field>
      <Field label="Valida fino al" id="t-vu"><Input id="t-vu" type="date" required min={v.valid_from} value={v.valid_until} onChange={set("valid_until")} /></Field>
      <Check checked={approved} onChange={setApproved}>Competenza già verificata dal centro</Check></>}
    {form.kind === "policy" && <>{minutes("daily", "Massimo minuti al giorno")}{minutes("weekly", "Massimo minuti a settimana")}{minutes("pause", "Pausa minima tra lezioni (min)")}{minutes("s2r", "Spostamento da sede a online (min)")}{minutes("r2s", "Spostamento da online a sede (min)")}</>}
    {form.kind === "state" && <>{t?.active ? <p>Il tutor non potrà più accedere e non sarà pianificato. Le lezioni già svolte restano nello storico; gli inviti aperti vengono revocati.</p> : <p>Il tutor torna pianificabile e, se ha un account, riottiene l’accesso.</p>}</>}
    {form.kind === "invite" && <><p>Invieremo a <b>{t?.email}</b> un link monouso per creare l’account da tutor.</p></>}
    <div className="modal-foot"><Btn type="button" kind="ghost" onClick={onClose}>Annulla</Btn><Btn type="submit" kind={form.kind === "state" && t?.active ? "danger" : "primary"} disabled={busy}>Conferma</Btn></div>
  </form></Modal>;
}
