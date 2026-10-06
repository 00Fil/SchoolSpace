/** Moduli delle famiglie: iscrizione guidata (genitore → famiglia e figli → accesso), genitori, figli, CSV. */
import { FormEvent, ReactNode, useState } from "react";
import { Avatar, Btn, Icon, Notice } from "../../ui/core";
import { Check, Choices, Field, Input, TextArea } from "../../ui/controls";
import { Modal } from "../../ui/layers";
import { send, writeError } from "../registry";
import { Child, Family, Guardian, guardianName, Perms, RELS, surnameOf } from "./model";
import { QrPanel } from "./Qr";

const AUTO_REASON = "Iscrizione di una nuova famiglia";
const EDIT_REASON = "Modifica dal gestionale";
const PERMS: [keyof Perms, string, string][] = [
  ["can_manage_availability", "Gestisce le disponibilità", "Indica e modifica gli orari liberi dei figli."],
  ["can_request_changes", "Chiede cambi di lezione", "Può proporre spostamenti e assenze."],
  ["can_receive_notifications", "Riceve le notifiche", "Promemoria, cambi e comunicazioni del centro."],
];
const DEFAULT_PERMS: Perms = { can_manage_availability: true, can_request_changes: true, can_receive_notifications: true };

type GForm = { name: string; email: string; phone: string; relationship: string; perms: Perms; verified: boolean; evidence: string };
const emptyG = (): GForm => ({ name: "", email: "", phone: "", relationship: "PARENT", perms: { ...DEFAULT_PERMS }, verified: true, evidence: "Documento visionato in sede" });
const gBody = (g: GForm) => ({ name: g.name.trim(), email: g.email.trim(), phone: g.phone.trim(), relationship: g.relationship, permissions: g.perms, evidence: g.verified ? g.evidence.trim() : "" });

/** Campi del genitore/tutore, condivisi tra iscrizione e aggiunta di un secondo genitore. */
function GuardianFields({ v, set, edit }: { v: GForm; set: (p: Partial<GForm>) => void; edit?: boolean }) {
  return <>
    <div className="fm-two">
      <Field label="Nome e cognome" id="g-name"><Input id="g-name" required maxLength={120} autoFocus value={v.name} onChange={(e) => set({ name: e.target.value })} autoComplete="off" /></Field>
      <Field label="Telefono" id="g-phone" optional><Input id="g-phone" type="tel" maxLength={30} value={v.phone} onChange={(e) => set({ phone: e.target.value })} /></Field>
    </div>
    {!edit && <Field label="Email" id="g-email" hint="Qui arriva l’invito per attivare l’accesso."><Input id="g-email" type="email" required value={v.email} onChange={(e) => set({ email: e.target.value })} /></Field>}
    <Field label="Relazione con i figli"><Choices label="Relazione con i figli" value={v.relationship} onChange={(r) => set({ relationship: r })} options={RELS.map(([k, l]) => ({ v: k, label: l }))} /></Field>
    <fieldset className="fm-perms"><legend>Cosa può fare nel portale</legend>
      {PERMS.map(([k, t, s]) => <label key={k} className={"fm-perm" + (v.perms[k] ? " on" : "")}><input type="checkbox" checked={v.perms[k]} onChange={(e) => set({ perms: { ...v.perms, [k]: e.target.checked } })} /><span><b>{t}</b><small>{s}</small></span><i aria-hidden><Icon n="check" /></i></label>)}
    </fieldset>
    {!edit && <div className={"fm-verify" + (v.verified ? " on" : "")}>
      <Check checked={v.verified} onChange={(x) => set({ verified: x })}><span><b>Ho verificato identità e relazione</b><small>Solo così l’invito parte subito. Altrimenti resta «da verificare».</small></span></Check>
      {v.verified && <Field label="Come l’hai verificato" id="g-ev" hint="Es. «documento visionato in sede». Non allegare documenti."><Input id="g-ev" required maxLength={200} value={v.evidence} onChange={(e) => set({ evidence: e.target.value })} /></Field>}
    </div>}
  </>;
}

type Kid = { display_name: string; level: string };

/** Iscrizione guidata in tre passi. Prima il genitore: è lui che riceverà l’accesso. */
export function NewFamily({ onClose, onDone, onOpen }: { onClose: () => void; onDone: () => void; onOpen: (id: string) => void }) {
  const [step, setStep] = useState(1), [g, setG] = useState(emptyG), [ref, setRef] = useState(""), [kids, setKids] = useState<Kid[]>([{ display_name: "", level: "" }]);
  const [busy, setBusy] = useState(false), [err, setErr] = useState(""), [res, setRes] = useState<{ family: Family; guardian: Guardian } | null>(null), [qr, setQr] = useState(false);
  const setGp = (p: Partial<GForm>) => setG((x) => ({ ...x, ...p }));
  const next = (e: FormEvent) => {
    e.preventDefault(); setErr("");
    if (!ref) setRef(surnameOf(g.name) ? "Famiglia " + surnameOf(g.name) : "");
    setKids((k) => k.map((x) => ({ ...x, display_name: x.display_name || "" })));
    setStep(2);
  };
  async function create(e: FormEvent) {
    e.preventDefault(); setBusy(true); setErr("");
    try {
      const children = kids.filter((k) => k.display_name.trim()).map((k) => ({ display_name: k.display_name.trim(), level: k.level.trim() }));
      const r = await send<{ family: Family; guardian: Guardian }>("POST", "/registry/families/onboard", { reference: ref.trim(), guardian: gBody(g), children, reason: AUTO_REASON });
      setRes(r); setStep(3); onDone();
    } catch (x) { setErr(writeError(x)); }
    setBusy(false);
  }
  const surname = surnameOf(g.name);
  return <Modal open onClose={onClose} labelledBy="nf-h" width={640}>
    <div className="modal-body fm-wiz">
      <div className="fm-wiz-top"><h2 id="nf-h">{step === 3 ? "Famiglia creata" : "Nuova famiglia"}</h2>
        <ol className="fm-wiz-steps" aria-label="Passi">{["Genitore o tutore", "Famiglia e figli", "Accesso"].map((t, i) => <li key={t} className={step === i + 1 ? "now" : step > i + 1 ? "done" : ""} aria-current={step === i + 1 ? "step" : undefined}><span>{step > i + 1 ? <Icon n="check" /> : i + 1}</span>{t}</li>)}</ol></div>
      {err && <Notice kind="bad">{err}</Notice>}

      {step === 1 && <form onSubmit={next}>
        
        <GuardianFields v={g} set={setGp} />
        <div className="modal-foot"><Btn kind="ghost" onClick={onClose}>Annulla</Btn><Btn type="submit" kind="primary" isle="arrow">Continua</Btn></div>
      </form>}

      {step === 2 && <form onSubmit={create}>
        <div className="fm-who-sum"><Avatar name={g.name} k={g.email} /><span><b>{g.name}</b><small>{g.email} · {RELS.find((r) => r[0] === g.relationship)?.[1]}</small></span><button type="button" className="link-btn" onClick={() => setStep(1)}>Modifica</button></div>
        <Field label="Nome della famiglia" id="nf-ref" hint="Come la trovi nell’elenco. Deve essere unico."><Input id="nf-ref" required maxLength={80} value={ref} onChange={(e) => setRef(e.target.value)} /></Field>
        <div className="fm-kids"><span className="lbl">Figli</span>
          {kids.map((k, i) => <div key={i} className="fm-kid">
            <Input aria-label={`Nome del figlio ${i + 1}`} placeholder={surname ? `Nome e cognome (es. Luca ${surname})` : "Nome e cognome"} maxLength={120} value={k.display_name} onChange={(e) => setKids((x) => x.map((y, j) => (j === i ? { ...y, display_name: e.target.value } : y)))} />
            <Input aria-label={`Classe del figlio ${i + 1}`} placeholder="Classe (es. 2ª media)" maxLength={60} value={k.level} onChange={(e) => setKids((x) => x.map((y, j) => (j === i ? { ...y, level: e.target.value } : y)))} />
            {kids.length > 1 && <button type="button" className="circle sm ghost" aria-label={`Togli il figlio ${i + 1}`} onClick={() => setKids((x) => x.filter((_, j) => j !== i))}><Icon n="x" /></button>}
          </div>)}
          {kids.length < 12 && <Btn kind="sm ghost" icon="plus" onClick={() => setKids((x) => [...x, { display_name: "", level: "" }])}>Aggiungi un altro figlio</Btn>}
        </div>
        <Notice kind="info">{g.verified ? <>Alla conferma inviamo l’invito a <b>{g.email}</b>. Subito dopo potrai mostrargli anche un QR code per entrare all’istante.</> : <>L’invito resterà <b>da verificare</b>: lo invii dalla pagina della famiglia dopo aver verificato la relazione.</>}</Notice>
        <div className="modal-foot"><Btn kind="ghost" onClick={() => setStep(1)}>Indietro</Btn><Btn type="submit" kind="primary" disabled={busy} isle="send">{busy ? "Creo la famiglia…" : g.verified ? "Crea e invia l’invito" : "Crea la famiglia"}</Btn></div>
      </form>}

      {step === 3 && res && <div className="fm-done">
        <div className="fm-done-head"><span className="fm-ok"><Icon n="check" /></span><div><b>{res.family.reference} è nell’elenco</b><small>{res.family.children.length ? `${res.family.children.length === 1 ? "1 figlio" : res.family.children.length + " figli"} · ` : ""}{res.guardian.status === "INVITED" ? `invito inviato a ${res.guardian.email}` : "invito da verificare"}</small></div></div>
        {res.guardian.status === "INVITED" && res.guardian.invitation && (qr
          ? <QrPanel invitationId={res.guardian.invitation.id} name={res.guardian.name} onClose={() => setQr(false)} />
          : <button type="button" className="fm-qr-cta" onClick={() => setQr(true)}><span className="fm-qr-ic"><Icon n="qr" /></span><span><b>Il genitore è qui con te?</b><small>Mostra un QR code: lo inquadra con il telefono ed entra subito, senza aspettare l’email.</small></span><Icon n="arrow" /></button>)}
        <div className="modal-foot"><Btn kind="ghost" onClick={onClose}>Chiudi</Btn><Btn kind="primary" isle="arrow" onClick={() => onOpen(res.family.id)}>Apri la famiglia</Btn></div>
      </div>}
    </div>
  </Modal>;
}

/** Aggiunge o modifica un genitore/tutore di una famiglia esistente. */
export function GuardianModal({ family, guardian, onClose, onDone }: { family: Family; guardian?: Guardian; onClose: () => void; onDone: (msg: string) => void }) {
  const [v, setV] = useState<GForm>(() => guardian ? { ...emptyG(), name: guardian.name, email: guardian.email, phone: guardian.phone, relationship: guardian.relationship || "PARENT", perms: guardian.permissions || { ...DEFAULT_PERMS } } : emptyG());
  const [busy, setBusy] = useState(false), [err, setErr] = useState("");
  async function submit(e: FormEvent) {
    e.preventDefault(); setBusy(true); setErr("");
    try {
      if (guardian?.id) await send("PATCH", `/registry/family-guardians/${guardian.id}`, { name: v.name.trim(), phone: v.phone.trim(), relationship: v.relationship, permissions: v.perms, expected_version: guardian.version, reason: EDIT_REASON });
      else await send("POST", `/registry/families/${family.id}/guardians`, { guardian: gBody(v), reason: "Nuovo genitore della famiglia" });
      onDone(guardian ? "Genitore aggiornato" : v.verified ? "Genitore aggiunto e invito inviato" : "Genitore aggiunto: verifica la relazione per invitarlo");
    } catch (x) { setErr(writeError(x)); }
    setBusy(false);
  }
  return <Modal open onClose={onClose} labelledBy="gm-h" width={600}>
    <form className="modal-body" onSubmit={submit}>
      <h2 id="gm-h">{guardian ? `Modifica ${guardianName(guardian)}` : "Aggiungi genitore o tutore"}</h2>
      
      {err && <Notice kind="bad">{err}</Notice>}
      <GuardianFields v={v} set={(p) => setV((x) => ({ ...x, ...p }))} edit={!!guardian} />
      <div className="modal-foot"><Btn kind="ghost" onClick={onClose}>Annulla</Btn><Btn type="submit" kind="primary" disabled={busy}>{guardian ? "Salva" : v.verified ? "Aggiungi e invita" : "Aggiungi"}</Btn></div>
    </form>
  </Modal>;
}

/** Figlio nuovo o esistente. */
export function ChildModal({ family, child, onClose, onDone }: { family: Family; child?: Child; onClose: () => void; onDone: (msg: string) => void }) {
  const [v, setV] = useState({ display_name: child?.display_name || "", level: child?.level || "", birth_date: child?.birth_date || "" });
  const [busy, setBusy] = useState(false), [err, setErr] = useState("");
  const set = (k: keyof typeof v) => (e: { target: { value: string } }) => setV((x) => ({ ...x, [k]: e.target.value }));
  const active = family.guardians.filter((g) => g.status === "ACTIVE");
  async function submit(e: FormEvent) {
    e.preventDefault(); setBusy(true); setErr("");
    const body = { display_name: v.display_name.trim(), level: v.level.trim(), birth_date: v.birth_date || null };
    try {
      if (child) await send("PATCH", `/registry/students/${child.id}`, { ...body, expected_version: child.version, reason: EDIT_REASON });
      else await send("POST", "/registry/students", { ...body, family: family.id, reason: "Nuovo figlio della famiglia" });
      onDone(child ? "Figlio aggiornato" : "Figlio aggiunto");
    } catch (x) { setErr(writeError(x)); }
    setBusy(false);
  }
  return <Modal open onClose={onClose} labelledBy="cm-h">
    <form className="modal-body" onSubmit={submit}>
      <h2 id="cm-h">{child ? `Modifica ${child.display_name}` : `Aggiungi un figlio a ${family.reference}`}</h2>
      {err && <Notice kind="bad">{err}</Notice>}
      <Field label="Nome e cognome" id="c-n"><Input id="c-n" required autoFocus maxLength={120} value={v.display_name} onChange={set("display_name")} /></Field>
      <div className="fm-two">
        <Field label="Classe" id="c-l" optional hint="Es. «2ª media»."><Input id="c-l" maxLength={60} value={v.level} onChange={set("level")} /></Field>
        <Field label="Data di nascita" id="c-b" optional hint="Per il passaggio alla maggiore età."><Input id="c-b" type="date" value={v.birth_date} onChange={set("birth_date")} /></Field>
      </div>
      <div className="modal-foot"><Btn kind="ghost" onClick={onClose}>Annulla</Btn><Btn type="submit" kind="primary" disabled={busy}>{child ? "Salva" : "Aggiungi"}</Btn></div>
    </form>
  </Modal>;
}

export function FamilyModal({ family, onClose, onDone }: { family: Family; onClose: () => void; onDone: (msg: string) => void }) {
  const [v, setV] = useState({ reference: family.reference, contact_name: family.contact_name, contact_email: family.contact_email, contact_phone: family.contact_phone });
  const [busy, setBusy] = useState(false), [err, setErr] = useState("");
  const set = (k: keyof typeof v) => (e: { target: { value: string } }) => setV((x) => ({ ...x, [k]: e.target.value }));
  async function submit(e: FormEvent) {
    e.preventDefault(); setBusy(true); setErr("");
    try { await send("PATCH", `/registry/families/${family.id}`, { ...v, expected_version: family.version, reason: EDIT_REASON }); onDone("Famiglia aggiornata"); } catch (x) { setErr(writeError(x)); }
    setBusy(false);
  }
  return <Modal open onClose={onClose} labelledBy="fmm-h">
    <form className="modal-body" onSubmit={submit}>
      <h2 id="fmm-h">Modifica la famiglia</h2>
      {err && <Notice kind="bad">{err}</Notice>}
      <Field label="Nome della famiglia" id="fm-ref"><Input id="fm-ref" required maxLength={80} value={v.reference} onChange={set("reference")} /></Field>
      <Field label="Referente per il centro" id="fm-cn" optional><Input id="fm-cn" maxLength={120} value={v.contact_name} onChange={set("contact_name")} /></Field>
      <div className="fm-two">
        <Field label="Email" id="fm-ce" optional><Input id="fm-ce" type="email" value={v.contact_email} onChange={set("contact_email")} /></Field>
        <Field label="Telefono" id="fm-cp" optional><Input id="fm-cp" type="tel" maxLength={30} value={v.contact_phone} onChange={set("contact_phone")} /></Field>
      </div>
      <div className="modal-foot"><Btn kind="ghost" onClick={onClose}>Annulla</Btn><Btn type="submit" kind="primary" disabled={busy}>Salva</Btn></div>
    </form>
  </Modal>;
}

/** Conferma: rimozioni e revoche (senza testo) o verifica della relazione (con testo). */
export function AskModal({ title, text, label, hint, initial = "", cta, danger, onClose, onConfirm }: { title: string; text: ReactNode; label?: string; hint?: string; initial?: string; cta: string; danger?: boolean; onClose: () => void; onConfirm: (value: string) => Promise<void> }) {
  const [v, setV] = useState(initial), [busy, setBusy] = useState(false), [err, setErr] = useState("");
  async function submit(e: FormEvent) { e.preventDefault(); setBusy(true); setErr(""); try { await onConfirm(v.trim()); } catch (x) { setErr(writeError(x)); setBusy(false); } }
  return <Modal open onClose={onClose} labelledBy="ask-h">
    <form className="modal-body" onSubmit={submit}>
      <h2 id="ask-h">{title}</h2><p className="fm-lead">{text}</p>
      {err && <Notice kind="bad">{err}</Notice>}
      {label && <Field label={label} id="ask-v" hint={hint}><Input id="ask-v" required autoFocus maxLength={200} value={v} onChange={(e) => setV(e.target.value)} /></Field>}
      <div className="modal-foot"><Btn kind="ghost" onClick={onClose}>Annulla</Btn><Btn type="submit" kind={danger ? "danger" : "primary"} disabled={busy}>{cta}</Btn></div>
    </form>
  </Modal>;
}

/** Import CSV con anteprima degli errori (invariato nel comportamento). */
export function ImportModal({ onClose, onDone }: { onClose: () => void; onDone: (msg: string) => void }) {
  const [content, setContent] = useState(""), [apply, setApply] = useState(false), [busy, setBusy] = useState(false), [err, setErr] = useState("");
  const [preview, setPreview] = useState<{ status: string; errors?: { row?: number; field?: string; message?: string }[] } | null>(null);
  async function submit(e: FormEvent) {
    e.preventDefault(); setBusy(true); setErr("");
    try {
      const res = await send<{ status: string; errors?: [] }>("POST", "/privacy/imports", { content, dry_run: !apply, create_invites: apply });
      if (!apply) setPreview(res); else onDone("Importazione completata");
    } catch (x) {
      const data = (x as { data?: { errors?: []; status?: string } }).data;
      if (data?.errors) setPreview({ status: data.status || "REJECTED", errors: data.errors }); else setErr(writeError(x));
    }
    setBusy(false);
  }
  return <Modal open onClose={onClose} labelledBy="imp-h" width={620}>
    <form className="modal-body" onSubmit={submit}>
      <h2 id="imp-h">Importa famiglie da CSV</h2>
      <p className="fm-lead"><a href="/api/v1/privacy/imports/template/v1">Modello CSV</a></p>
      {err && <Notice kind="bad">{err}</Notice>}
      <Field label="Contenuto CSV" id="imp-c"><TextArea id="imp-c" required rows={8} value={content} onChange={(e) => { setContent(e.target.value); setPreview(null); setApply(false); }} /></Field>
      {preview && (preview.errors?.length ? <Notice kind="bad" title={`${preview.errors.length} errori: correggi il file`}><ul>{preview.errors.slice(0, 50).map((x, i) => <li key={i}>{x.row ? `Riga ${x.row}: ` : ""}{x.field ? `${x.field} — ` : ""}{x.message || JSON.stringify(x)}</li>)}</ul></Notice>
        : <Notice kind="ok" title="Anteprima senza errori">Puoi confermare l’importazione.<Check checked={apply} onChange={setApply}>Importa davvero e crea gli inviti</Check></Notice>)}
      <div className="modal-foot"><Btn kind="ghost" onClick={onClose}>Annulla</Btn><Btn type="submit" kind="primary" disabled={busy}>{apply ? "Importa" : "Controlla il file"}</Btn></div>
    </form>
  </Modal>;
}
