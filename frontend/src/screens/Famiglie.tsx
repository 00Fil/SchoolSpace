/** Famiglie (v0.9.5): elenco a schede, pagina della famiglia, schede rapide di figli e genitori.
 *  Unico punto d’ingresso per figli e genitori/tutori: la vecchia sezione «Studenti» del centro rimanda qui. */
import { ReactNode, useEffect, useMemo, useState } from "react";
import { plural, WD_LONG } from "../format";
import { Avatar, Btn, Empty, Icon, PageHead, Skeleton, State, Tag, Tech } from "../ui/core";
import { SegCtl } from "../ui/controls";
import { Sheet, useToast } from "../ui/layers";
import { ErrorState } from "../ui/states";
import { go, setQuery, useRoute } from "../ui/route";
import { useData } from "../app/data";
import type { Tone } from "../messages";
import { send, useList, writeError } from "./registry";
import { Child, Family, familyState, G_STATUS, Guardian, guardianKey, guardianName, relText } from "./famiglie/model";
import { AskModal, ChildModal, FamilyModal, GuardianModal, ImportModal, NewFamily } from "./famiglie/forms";
import { QrPanel } from "./famiglie/Qr";
import { RequestModal } from "./requestForms";

type Form =
  | { k: "new" } | { k: "import" } | { k: "family"; f: Family } | { k: "child"; f: Family; c?: Child } | { k: "guardian"; f: Family; g?: Guardian }
  | { k: "request"; student: string }
  | { k: "ask"; title: string; text: ReactNode; label?: string; hint?: string; initial?: string; cta: string; danger?: boolean; run: (v: string) => Promise<unknown>; ok: string };
type Ctx = { setForm: (f: Form) => void; reload: () => void; act: (p: Promise<unknown>, ok: string) => void; qr: string | null; setQr: (id: string | null) => void };
type Filter = "tutte" | "attesa" | "senza-figli";

const Pill = ({ tone, children }: { tone: Tone; children: ReactNode }) => <span className={"fm-pill " + tone}>{children}</span>;
const pending = (g: Guardian) => g.status !== "ACTIVE";

export default function Famiglie() {
  const r = useRoute(), toast = useToast();
  const fid = r.q.get("f"), sid = r.q.get("s"), gid = r.q.get("g"), q = r.q.get("q") || "", filter = (r.q.get("vista") as Filter) || "tutte";
  const fams = useList<Family>("/registry/families?expand=1");
  const [form, setForm] = useState<Form | null>(null), [qr, setQr] = useState<string | null>(null);
  const wantsNew = r.q.get("nuova") === "1";
  useEffect(() => { if (wantsNew) { setForm({ k: "new" }); setQuery((x) => x.delete("nuova")); } }, [wantsNew]);
  const reload = fams.reload;
  const act = (p: Promise<unknown>, ok: string) => p.then(() => { toast(ok); reload(); }).catch((e) => toast(writeError(e)));
  const ctx: Ctx = { setForm, reload, act, qr, setQr };
  const all = fams.data || [];
  const fam = fid ? all.find((f) => f.id === fid) : null;
  const childOf = sid ? all.flatMap((f) => f.children.map((c) => [f, c] as const)).find(([, c]) => c.id === sid) : undefined;
  const guardOf = gid ? all.flatMap((f) => f.guardians.map((g) => [f, g] as const)).find(([, g]) => guardianKey(g) === gid) : undefined;
  const closeSheet = () => setQuery((x) => { x.delete("s"); x.delete("g"); });

  let body: ReactNode;
  if (fams.error) body = <section className="module"><ErrorState error={fams.error} onRetry={reload} /></section>;
  else if (!fams.data) body = <section className="module"><Skeleton rows={5} /></section>;
  else if (fid && !fam) body = <section className="module"><Empty title="Famiglia non trovata" /><Btn kind="sm" icon="left" onClick={() => go("anagrafica")}>Tutte le famiglie</Btn></section>;
  else if (fam) body = <FamilyPage f={fam} ctx={ctx} />;
  else body = <FamilyList all={all} q={q} filter={filter} ctx={ctx} />;

  return <>
    {body}
    <Sheet open={!!childOf || !!guardOf} onClose={closeSheet} labelledBy="fm-sheet-h">
      {childOf && <ChildSheet f={childOf[0]} c={childOf[1]} ctx={ctx} onClose={closeSheet} />}
      {guardOf && <GuardianSheet f={guardOf[0]} g={guardOf[1]} ctx={ctx} onClose={closeSheet} />}
    </Sheet>
    {form && <Forms form={form} close={() => setForm(null)} done={(m) => { setForm(null); toast(m); reload(); }} reload={reload} />}
  </>;
}

function Forms({ form, close, done, reload }: { form: Form; close: () => void; done: (m: string) => void; reload: () => void }) {
  const d = useData();
  switch (form.k) {
    case "request": return <RequestModal open student={form.student} onClose={close} onSaved={async () => { done("Richiesta salvata."); await d.refresh(); }} />;
    case "new": return <NewFamily onClose={close} onDone={reload} onOpen={(id) => { close(); go("anagrafica", { f: id }); }} />;
    case "import": return <ImportModal onClose={close} onDone={done} />;
    case "family": return <FamilyModal family={form.f} onClose={close} onDone={done} />;
    case "child": return <ChildModal family={form.f} child={form.c} onClose={close} onDone={done} />;
    case "guardian": return <GuardianModal family={form.f} guardian={form.g} onClose={close} onDone={done} />;
    case "ask": return <AskModal {...form} onClose={close} onConfirm={async (v) => { await form.run(v); done(form.ok); }} />;
  }
}

/* ---------------- elenco a schede ---------------- */

function FamilyList({ all, q, filter, ctx }: { all: Family[]; q: string; filter: Filter; ctx: Ctx }) {
  const needle = q.trim().toLowerCase();
  const shown = useMemo(() => all.filter((f) => {
    if (filter === "attesa" && !f.guardians.some(pending) && f.guardians.length) return false;
    if (filter === "senza-figli" && f.children.length) return false;
    if (!needle) return true;
    return [f.reference, f.contact_name, f.contact_email, ...f.children.map((c) => c.display_name), ...f.guardians.flatMap((g) => [g.name, g.email])].some((s) => (s || "").toLowerCase().includes(needle));
  }), [all, needle, filter]);
  const kids = all.reduce((n, f) => n + f.children.length, 0), waiting = all.reduce((n, f) => n + f.guardians.filter(pending).length, 0);
  const lead = all.length ? `${plural(all.length, "famiglia", "famiglie")} · ${plural(kids, "figlio", "figli")}${waiting ? ` · ${plural(waiting, "accesso da completare", "accessi da completare")}` : ""}` : "";
  return <section className="fm" aria-labelledby="h-fm">
    <PageHead id="h-fm" title="Famiglie" lead={lead}>
      <Btn kind="ghost" icon="download" onClick={() => ctx.setForm({ k: "import" })}>Importa CSV</Btn>
      <Btn kind="primary" isle="plus" onClick={() => ctx.setForm({ k: "new" })}>Nuova famiglia</Btn>
    </PageHead>
    {all.length > 0 && <div className="fm-bar">
      <label className="field-search"><Icon n="search" /><span className="sr">Cerca famiglie, figli o genitori</span><input type="search" placeholder="Cerca famiglia, figlio o genitore…" value={q} autoComplete="off" spellCheck={false} onChange={(e) => setQuery((x) => (e.target.value ? x.set("q", e.target.value) : x.delete("q")))} /></label>
      <SegCtl label="Mostra" value={filter} onChange={(v) => setQuery((x) => (v === "tutte" ? x.delete("vista") : x.set("vista", v)))} options={[["tutte", "Tutte"], ["attesa", "Accesso da completare"], ["senza-figli", "Senza figli"]]} />
    </div>}
    {!all.length ? <div className="module fm-empty"><span className="fm-empty-ic"><Icon n="users" /></span><b>Nessuna famiglia ancora</b><p>Parti dal genitore o tutore: gli mandi l’invito (o gli mostri un QR code) e poi aggiungi i figli.</p><Btn kind="primary" isle="plus" onClick={() => ctx.setForm({ k: "new" })}>Nuova famiglia</Btn></div>
      : !shown.length ? <div className="module"><Empty title={needle ? `Nessun risultato per “${q}”` : "Nessuna famiglia in questo filtro"} /></div>
      : <div className="fm-grid">{shown.map((f) => <FamilyCard key={f.id} f={f} ctx={ctx} />)}</div>}
  </section>;
}

function FamilyCard({ f, ctx }: { f: Family; ctx: Ctx }) {
  const [label, tone] = familyState(f), open = () => go("anagrafica", { f: f.id });
  return <article className="fm-card">
    <header className="fm-card-head">
      <button type="button" className="fm-card-title" onClick={open}><h3>{f.reference}</h3><small>{plural(f.guardians.length, "genitore", "genitori")} · {plural(f.children.length, "figlio", "figli")}</small></button>
      <Pill tone={tone}>{label}</Pill>
    </header>
    <div className="fm-sec"><span className="fm-sec-h">Genitori e tutori</span>
      {f.guardians.length ? <ul className="fm-people">{f.guardians.map((g) => <li key={guardianKey(g)}><button type="button" className="fm-person" onClick={() => setQuery((x) => { x.delete("s"); x.set("g", guardianKey(g)); })}>
        <Avatar name={guardianName(g)} k={g.email} /><span><b>{guardianName(g)}</b><small>{relText(g.relationship)}</small></span><span className={"fm-st " + G_STATUS[g.status][1]}>{G_STATUS[g.status][0]}</span></button></li>)}</ul>
        : <button type="button" className="fm-add" onClick={() => ctx.setForm({ k: "guardian", f })}><Icon n="plus" />Aggiungi genitore o tutore</button>}
    </div>
    <div className="fm-sec"><span className="fm-sec-h">Figli</span>
      {f.children.length ? <ul className="fm-chips">{f.children.map((c) => <li key={c.id}><button type="button" className="fm-chip" onClick={() => setQuery((x) => { x.delete("g"); x.set("s", c.id); })}><Avatar name={c.display_name} k={c.id} size={26} /><span>{c.display_name}{c.level && <small>{c.level}</small>}</span></button></li>)}</ul>
        : <button type="button" className="fm-add" onClick={() => ctx.setForm({ k: "child", f })}><Icon n="plus" />Aggiungi il primo figlio</button>}
    </div>
    <footer className="fm-card-foot"><Btn kind="sm" isle="arrow" onClick={open}>Apri famiglia</Btn></footer>
  </article>;
}

/* ---------------- pagina della famiglia ---------------- */

function FamilyPage({ f, ctx }: { f: Family; ctx: Ctx }) {
  const contacts = [f.contact_name, f.contact_email, f.contact_phone].filter(Boolean);
  const verify = f.guardians.find((g) => g.status === "TO_VERIFY"), invited = f.guardians.find((g) => g.status === "INVITED"), dead = f.guardians.find((g) => g.status === "EXPIRED" || g.status === "NO_INVITE");
  let next: { tone: Tone; icon: "check" | "qr" | "x" | "plus" | "users"; title: string; text: string; act?: ReactNode } | null = null;
  if (!f.guardians.length) next = { tone: "red", icon: "users", title: "Manca un genitore o tutore", text: "Senza un genitore nessuno può seguire i figli dal portale.", act: <Btn kind="primary" isle="plus" onClick={() => ctx.setForm({ k: "guardian", f })}>Aggiungi genitore</Btn> };
  else if (verify) next = { tone: "amber", icon: "check", title: `Verifica la relazione di ${guardianName(verify)}`, text: "L’invito parte appena confermi come l’hai verificata.", act: <GuardianActions f={f} g={verify} ctx={ctx} only="primary" /> };
  else if (dead) next = { tone: "red", icon: "x", title: `L’invito di ${guardianName(dead)} non è più valido`, text: "Creane uno nuovo: puoi anche mostrargli il QR code.", act: <GuardianActions f={f} g={dead} ctx={ctx} only="primary" /> };
  else if (invited) next = { tone: "blue", icon: "qr", title: `${guardianName(invited)} non ha ancora attivato l’accesso`, text: "Se è con te, mostragli il QR code: entra subito dal telefono.", act: <GuardianActions f={f} g={invited} ctx={ctx} only="primary" /> };
  else if (!f.children.length) next = { tone: "amber", icon: "plus", title: "Aggiungi i figli", text: "I genitori li vedranno subito nel portale.", act: <Btn kind="primary" isle="plus" onClick={() => ctx.setForm({ k: "child", f })}>Aggiungi figlio</Btn> };
  return <section className="fm fm-page" aria-labelledby="h-fam">
    <button type="button" className="fm-back" onClick={() => go("anagrafica")}><Icon n="left" />Tutte le famiglie</button>
    <header className="fm-head">
      <div><h1 className="h-display" id="h-fam">{f.reference}</h1><p>{contacts.length ? contacts.join(" · ") : "Nessun contatto di riferimento"}</p></div>
      <div className="fm-head-act"><Btn kind="sm" onClick={() => ctx.setForm({ k: "family", f })}>Modifica</Btn></div>
    </header>
    {next && <div className={"fm-next " + next.tone} aria-live="polite"><span className={"fm-dot " + next.tone}><Icon n={next.icon} /></span><div><b>{next.title}</b><small>{next.text}</small></div>{next.act && <div className="fm-next-act">{next.act}</div>}</div>}
    {ctx.qr && f.guardians.some((g) => g.invitation?.id === ctx.qr) && <div className="module fm-qr-box"><QrPanel invitationId={ctx.qr} name={guardianName(f.guardians.find((g) => g.invitation?.id === ctx.qr)!)} onClose={() => ctx.setQr(null)} /></div>}
    <div className="fm-cols">
      <section className="module fm-col" aria-labelledby="h-fg">
        <div className="fm-col-h"><h2 className="m-title" id="h-fg">Genitori e tutori <span className="fm-n">{f.guardians.length}</span></h2><Btn kind="sm" icon="plus" onClick={() => ctx.setForm({ k: "guardian", f })}>Aggiungi</Btn></div>
        <p className="fm-col-p">Vedono tutti i figli della famiglia, anche quelli aggiunti dopo.</p>
        {f.guardians.length ? <div className="fm-stack">{f.guardians.map((g) => <GuardianCard key={guardianKey(g)} f={f} g={g} ctx={ctx} />)}</div> : <Empty title="Nessun genitore o tutore" />}
      </section>
      <section className="module fm-col" aria-labelledby="h-fc">
        <div className="fm-col-h"><h2 className="m-title" id="h-fc">Figli <span className="fm-n">{f.children.length}</span></h2><Btn kind="sm" icon="plus" onClick={() => ctx.setForm({ k: "child", f })}>Aggiungi</Btn></div>
        <p className="fm-col-p">Le disponibilità e le richieste di lezioni partono da qui.</p>
        {f.children.length ? <div className="fm-stack">{f.children.map((c) => <ChildCard key={c.id} f={f} c={c} />)}</div> : <Empty title="Nessun figlio" />}
      </section>
    </div>
  </section>;
}

/** Azioni sul genitore in base allo stato. `only="primary"` mostra solo quella principale. */
function GuardianActions({ f, g, ctx, only }: { f: Family; g: Guardian; ctx: Ctx; only?: "primary" }) {
  const inv = g.invitation, out: ReactNode[] = [];
  const verify = () => inv && ctx.setForm({ k: "ask", title: `Verifica la relazione di ${guardianName(g)}`, text: <>Conferma di aver verificato che <b>{g.email}</b> ha titolo a seguire i figli di {f.reference}. Subito dopo parte l’invito.</>, label: "Come l’hai verificato", hint: "Es. «documento visionato in sede». Non allegare documenti.", initial: "Documento visionato in sede", cta: "Verifica e invia", ok: "Relazione verificata, invito inviato", run: (evidence) => send("POST", `/registry/invitations/${inv.id}/verify-relation`, { evidence }) });
  const reinvite = () => g.id && ctx.setForm({ k: "ask", title: `Nuovo invito per ${guardianName(g)}`, text: <>Mandiamo un nuovo invito a <b>{g.email}</b>. Indica come hai verificato la relazione.</>, label: "Come l’hai verificato", initial: "Documento visionato in sede", cta: "Invia il nuovo invito", ok: "Nuovo invito inviato", run: (evidence) => send("POST", `/registry/family-guardians/${g.id}/reinvite`, { evidence, reason: "Nuovo invito" }) });
  if (g.status === "TO_VERIFY" && inv) out.push(<Btn key="v" kind={only ? "primary" : "sm approve"} icon="check" onClick={verify}>Verifica e invia</Btn>);
  if (g.status === "INVITED" && inv) out.push(<Btn key="q" kind={only ? "primary" : "sm primary"} icon="qr" onClick={() => ctx.setQr(ctx.qr === inv.id ? null : inv.id)}>{ctx.qr === inv.id ? "Nascondi QR code" : "Mostra QR code"}</Btn>);
  if ((g.status === "EXPIRED" || g.status === "NO_INVITE") && g.id) out.push(<Btn key="n" kind={only ? "primary" : "sm primary"} icon="send" onClick={reinvite}>Nuovo invito</Btn>);
  if (only) return <>{out}</>;
  if (g.status === "INVITED" && inv) out.push(<Btn key="r" kind="sm" icon="mail" onClick={() => ctx.act(send("POST", `/registry/invitations/${inv.id}/resend`, {}), "Invito inviato di nuovo")}>Invia di nuovo</Btn>);
  if (!g.legacy) {
    out.push(<Btn key="e" kind="sm" onClick={() => ctx.setForm({ k: "guardian", f, g })}>Modifica</Btn>);
    out.push(<Btn key="x" kind="sm ghost" onClick={() => ctx.setForm({ k: "ask", title: `Rimuovi ${guardianName(g)}`, text: "Perde subito l’accesso a tutti i figli della famiglia e l’eventuale invito smette di valere.", cta: "Rimuovi", danger: true, ok: "Genitore rimosso", run: (reason) => send("POST", `/registry/family-guardians/${g.id}/remove`, { reason }) })}>Rimuovi</Btn>);
  } else {
    g.links.forEach((l) => out.push(<Btn key={l.id} kind="sm ghost" onClick={() => ctx.setForm({ k: "ask", title: "Revoca la delega", text: `Toglie a ${guardianName(g)} l’accesso a ${f.children.find((c) => c.id === l.student)?.display_name || "questo figlio"}.`, cta: "Revoca", danger: true, ok: "Delega revocata", run: (reason) => send("POST", `/registry/guardian-links/${l.id}/revoke`, { reason }) })}>Revoca su {f.children.find((c) => c.id === l.student)?.display_name.split(" ")[0] || "figlio"}</Btn>));
    (g.invitations || []).forEach((i) => out.push(<Btn key={i.id} kind="sm ghost" onClick={() => ctx.setForm({ k: "ask", title: "Revoca l’invito", text: `L’invito a ${i.email} smette di valere.`, cta: "Revoca", danger: true, ok: "Invito revocato", run: (reason) => send("POST", `/registry/invitations/${i.id}/revoke`, { reason }) })}>Revoca invito</Btn>));
  }
  return <div className="fm-act">{out}</div>;
}

function GuardianBody({ f, g }: { f: Family; g: Guardian }) {
  const [label, tone] = G_STATUS[g.status];
  const sees = f.children.filter((c) => g.students.includes(c.id)).map((c) => c.display_name.split(" ")[0]);
  const p = g.permissions;
  return <>
    <div className="fm-g-top"><Avatar name={guardianName(g)} k={g.email} size={48} /><div><b>{guardianName(g)}</b><small>{relText(g.relationship)}{g.legacy ? " · collegato figlio per figlio" : ""}</small></div><Pill tone={tone}>{label}</Pill></div>
    
    <ul className="fm-facts">
      <li><Icon n="mail" /><span>{g.email}</span></li>
      {g.phone && <li><Icon n="phone" /><span>{g.phone}</span></li>}
      <li><Icon n="users" /><span>{g.status === "ACTIVE" ? (sees.length ? `Vede ${sees.join(", ")}` : "Ancora nessun figlio") : `Vedrà ${f.children.length ? f.children.map((c) => c.display_name.split(" ")[0]).join(", ") : "i figli che aggiungerai"}`}</span></li>
    </ul>
    {p && <div className="fm-perm-tags">{([["can_manage_availability", "Disponibilità"], ["can_request_changes", "Cambi di lezione"], ["can_receive_notifications", "Notifiche"]] as const).map(([k, t]) => <span key={k} className={"fm-ptag" + (p[k] ? " on" : "")}>{p[k] ? <Icon n="check" /> : <Icon n="x" />}{t}</span>)}</div>}
  </>;
}

function GuardianCard({ f, g, ctx }: { f: Family; g: Guardian; ctx: Ctx }) {
  return <article className={"fm-g " + G_STATUS[g.status][1]}><GuardianBody f={f} g={g} /><GuardianActions f={f} g={g} ctx={ctx} /></article>;
}

function useChild(c: Child) {
  const d = useData();
  const rules = d.rules.filter((x) => x.student === c.id && x.status !== "REVOKED");
  const reqs = d.requests.filter((x) => x.student === c.id || x.participant_ids?.includes(c.id));
  const avail: [string, Tone] = rules.some((x) => x.status === "APPROVED") ? ["Disponibilità approvata", "green"] : rules.some((x) => x.status === "DRAFT") ? ["Disponibilità da approvare", "amber"] : ["Disponibilità mancante", "red"];
  return { rules, reqs, avail };
}

function ChildCard({ f, c }: { f: Family; c: Child }) {
  const { reqs, avail } = useChild(c);
  const sees = f.guardians.filter((g) => g.students.includes(c.id)).map((g) => guardianName(g).split(" ")[0]);
  return <article className="fm-c">
    <button type="button" className="fm-c-main" onClick={() => setQuery((x) => { x.delete("g"); x.set("s", c.id); })}>
      <Avatar name={c.display_name} k={c.id} size={44} /><span><b>{c.display_name}</b><small>{[c.level || "Classe non indicata", !c.active && "non attivo"].filter(Boolean).join(" · ")}</small></span><Icon n="chev" />
    </button>
    <div className="fm-c-tags"><Pill tone={avail[1]}>{avail[0]}</Pill><Pill tone={reqs.length ? "blue" : "plain"}>{reqs.length ? plural(reqs.length, "richiesta", "richieste") : "Nessuna richiesta"}</Pill></div>
    <small className="fm-c-sees">{sees.length ? `Lo segue ${sees.join(" e ")}` : "Nessun genitore con accesso attivo"}</small>
  </article>;
}

/* ---------------- schede rapide (pannello laterale) ---------------- */

function SheetTop({ kind, onClose }: { kind: string; onClose: () => void }) {
  return <div className="sheet-top"><div className="kind"><Tag tone="blue">{kind}</Tag></div><button className="circle sm raised" aria-label="Chiudi" onClick={onClose}><Icon n="x" /></button></div>;
}

function GuardianSheet({ f, g, ctx, onClose }: { f: Family; g: Guardian; ctx: Ctx; onClose: () => void }) {
  const r = useRoute(), onPage = r.q.get("f") === f.id;
  return <><div className="sheet-body fm-sheet">
    <SheetTop kind="Genitore o tutore" onClose={onClose} />
    <h2 id="fm-sheet-h" className="sr">{guardianName(g)}</h2>
    <GuardianBody f={f} g={g} />
    {ctx.qr && g.invitation?.id === ctx.qr && <QrPanel invitationId={ctx.qr} name={guardianName(g)} onClose={() => ctx.setQr(null)} />}
    <GuardianActions f={f} g={g} ctx={ctx} />
    <Tech><dl className="facts"><dt>ID</dt><dd><code>{g.id || "delega per figlio"}</code></dd></dl></Tech>
  </div>
  {!onPage && <div className="sheet-foot"><span className="grow" /><Btn kind="primary" isle="arrow" onClick={() => go("anagrafica", { f: f.id })}>Apri {f.reference}</Btn></div>}</>;
}

function ChildSheet({ f, c, ctx, onClose }: { f: Family; c: Child; ctx: Ctx; onClose: () => void }) {
  const { rules, reqs, avail } = useChild(c), r = useRoute(), onPage = r.q.get("f") === f.id;
  const gs = f.guardians;
  return <><div className="sheet-body fm-sheet">
    <SheetTop kind="Figlio" onClose={onClose} />
    <div className="fm-g-top"><Avatar name={c.display_name} k={c.id} size={56} /><div><h2 id="fm-sheet-h">{c.display_name}</h2><small>{c.level || "Classe non indicata"} · {f.reference}</small></div></div>
    <div className="fm-c-tags"><Pill tone={avail[1]}>{avail[0]}</Pill>{!c.active && <Pill tone="red">Non attivo</Pill>}</div>
    <h3>Genitori e tutori</h3>
    {gs.length ? <ul className="fm-people">{gs.map((g) => <li key={guardianKey(g)}><button type="button" className="fm-person" onClick={() => setQuery((x) => { x.delete("s"); x.set("g", guardianKey(g)); })}><Avatar name={guardianName(g)} k={g.email} /><span><b>{guardianName(g)}</b><small>{relText(g.relationship)}</small></span><span className={"fm-st " + (g.students.includes(c.id) ? "green" : G_STATUS[g.status][1])}>{g.students.includes(c.id) ? "Lo vede" : G_STATUS[g.status][0]}</span></button></li>)}</ul> : <p className="muted">Nessun genitore: aggiungilo dalla pagina della famiglia.</p>}
    <h3>Disponibilità settimanali</h3>
    {rules.length ? <div className="mini-list">{rules.map((x) => <div key={x.id} className="mini"><span><b>{WD_LONG[x.weekday]}</b><small>{x.start_time.slice(0, 5)}–{x.end_time.slice(0, 5)}</small></span><State s={x.status} /></div>)}</div> : <p className="muted">Nessuna fascia: senza disponibilità non viene pianificato.</p>}
    <h3>Richieste di lezioni</h3>
    {reqs.length ? <div className="mini-list">{reqs.map((x) => <div key={x.id} className="mini"><span><b>{x.subject_name}</b><small>{x.sessions_per_week} × {x.duration_minutes} min a settimana</small></span><Tag tone={x.target_type === "GROUP" ? "violet" : "blue"}>{x.target_type === "GROUP" ? "Gruppo" : "Individuale"}</Tag></div>)}</div> : <p className="muted">Nessuna richiesta registrata.</p>}
    <div className="fm-act"><Btn kind="sm" onClick={() => ctx.setForm({ k: "child", f, c })}>Modifica</Btn><Btn kind="sm" icon="plus" onClick={() => go("impegni", { chi: "student:" + c.id })}>Impegni</Btn><Btn kind="sm" icon="plus" onClick={() => ctx.setForm({ k: "request", student: c.id })}>Richiesta di lezioni</Btn></div>
    <Tech><dl className="facts"><dt>ID</dt><dd><code>{c.id}</code></dd></dl></Tech>
  </div>
  {!onPage && <div className="sheet-foot"><span className="grow" /><Btn kind="primary" isle="arrow" onClick={() => go("anagrafica", { f: f.id })}>Apri {f.reference}</Btn></div>}</>;
}
