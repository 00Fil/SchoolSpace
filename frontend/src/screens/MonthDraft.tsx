import { useState } from "react";
import { api } from "../api";
import { dateLong, dayLabel, monthYear, plural, rangeOf, rome } from "../format";
import { human } from "../messages";
import { Btn, Icon, IconName, Notice, Tag } from "../ui/core";
import { Modal } from "../ui/layers";
import { go } from "../ui/route";
import { openReview } from "../app/Shell";

/** v0.9.11 · un solo calendario PUBBLICO per mese: ogni modifica del gestore è una rettifica
 *  in bozza finché non la pubblica (tutta la bozza del mese oppure subito, una alla volta). */
export type Brief = { id: string; start_at: string; end_at: string; tutor: string; tutor_name: string; subject_name: string; mode: string; participants: { student_id: string; name: string }[] };
export type Correction = { id: string; op: "reschedule" | "cancel" | "modify" | "swap" | "plan"; state: "PENDING" | "FAILED" | "APPLIED" | "DISCARDED"; summary: string; error: string; created_at: string | null; actor: string; lesson: Brief | null; other: Brief | null; target: { start_at: string; end_at: string } | null; lessons: Brief[]; request_id: string | null };
export type MonthState = { month: string; state: "DRAFT" | "PUBLISHED" | "EMPTY"; public: boolean; published_at: string | null; public_lessons: number; pending: number; failed: number; corrections: Correction[]; in_review?: { request_id: string; lessons: Brief[] }[]; draft_plan: { id: string; lessons: Brief[]; created_at: string } | null };
export type CorrRes = { correction: Correction; published: boolean; month: MonthState };

export const shiftMonth = (ym: string, n: number) => { const y = +ym.slice(0, 4), m = +ym.slice(5, 7) - 1 + n; const yy = y + Math.floor(m / 12), mm = ((m % 12) + 12) % 12 + 1; return `${yy}-${String(mm).padStart(2, "0")}`; };
const OP_ICON: Record<Correction["op"], IconName> = { reschedule: "move", cancel: "x", modify: "clip", swap: "arrow", plan: "spark" };
const OP_LABEL: Record<Correction["op"], string> = { reschedule: "Spostamento", cancel: "Cancellazione", modify: "Modifica", swap: "Scambio", plan: "Nuove lezioni" };

/** Blocco «in bozza» da disegnare nella griglia del giorno (nuovo orario, scambio, lezioni nuove). */
export type Ghost = { key: string; tutor: string; start_at: string; end_at: string; subject: string; who: string; group: boolean; corr: Correction | null; kind: "move" | "new" | "review"; request_id?: string };
export function draftOverlay(m: MonthState | null) {
  const by = new Map<string, Correction>(), ghosts: Ghost[] = [];
  if (!m) return { by, ghosts };
  const g = (key: string, b: Brief, s: string, e: string, corr: Correction | null, kind: Ghost["kind"]) => ghosts.push({ key, tutor: b.tutor, start_at: s, end_at: e, subject: b.subject_name, who: b.participants.length > 1 ? plural(b.participants.length, "studente", "studenti") : b.participants[0]?.name || "—", group: b.participants.length > 1, corr, kind });
  for (const c of m.corrections) {
    if (c.state !== "PENDING") continue;
    if (c.lesson) by.set(c.lesson.id, c);
    if (c.other) by.set(c.other.id, c);
    if (c.target && c.lesson) g(c.id, c.lesson, c.target.start_at, c.target.end_at, c, "move");
    if (c.op === "swap" && c.lesson && c.other) {
      const da = Date.parse(c.lesson.end_at) - Date.parse(c.lesson.start_at), db = Date.parse(c.other.end_at) - Date.parse(c.other.start_at);
      g(c.id + ":a", c.lesson, c.other.start_at, new Date(Date.parse(c.other.start_at) + da).toISOString(), c, "move");
      g(c.id + ":b", c.other, c.lesson.start_at, new Date(Date.parse(c.lesson.start_at) + db).toISOString(), c, "move");
    }
    if (c.op === "plan") c.lessons.forEach((b) => g(c.id + ":" + b.id, b, b.start_at, b.end_at, c, "new"));
  }
  m.draft_plan?.lessons.forEach((b) => g("dp:" + b.id, b, b.start_at, b.end_at, null, "new"));
  (m.in_review || []).forEach((r) => r.lessons.forEach((b) => { g("rv:" + b.id, b, b.start_at, b.end_at, null, "review"); ghosts[ghosts.length - 1].request_id = r.request_id; }));
  return { by, ghosts };
}

export async function publishOne(id: string) { return api<{ correction: Correction; month: MonthState }>(`/planner/corrections/${id}/publish`, { method: "POST", body: "{}" }); }
export async function discardOne(id: string) { return api<MonthState>(`/planner/corrections/${id}/discard`, { method: "POST", body: "{}" }); }

const stateTag = (m: MonthState) => m.state === "DRAFT"
  ? <Tag tone="amber">{m.public ? "Bozza" : "Bozza, mai pubblicato"}</Tag>
  : m.state === "PUBLISHED" ? <Tag tone="green">Pubblicato</Tag> : <Tag tone="plain">Vuoto</Tag>;

/** Barra del mese: navigazione tra i mesi, stato del calendario pubblico, rettifiche da pubblicare. */
export function MonthBar({ ym, m, onMonth, onChanged, toast }: { ym: string; m: MonthState | null; onMonth: (ym: string) => void; onChanged: (m: MonthState | null, msg: string) => Promise<void>; toast: (msg: string) => void }) {
  const [open, setOpen] = useState(false), [busy, setBusy] = useState(""), [ask, setAsk] = useState(false);
  const n = m ? m.pending + (m.draft_plan ? 1 : 0) : 0, failed = m?.corrections.filter((c) => c.state === "FAILED") || [];
  const rows = m?.corrections || [];
  const text = !m ? "Carico lo stato del mese…"
    : m.state === "DRAFT" ? `${n ? plural(n, "rettifica in bozza", "rettifiche in bozza") : "Nessuna rettifica in bozza"}${failed.length ? ` · ${plural(failed.length, "non applicata", "non applicate")}` : ""}. Tutor e famiglie vedono ${m.public ? "il calendario pubblicato" : "ancora nessuna lezione"}.`
    : m.state === "PUBLISHED" ? `${plural(m.public_lessons, "lezione", "lezioni")} nel calendario pubblico${m.published_at ? `, aggiornato il ${dateLong(rome(m.published_at).date)}` : ""}.`
    : "Nessuna lezione pubblicata in questo mese.";
  const msgRef = { v: "" };
  async function act(name: string, fn: () => Promise<MonthState | null>, msg: string | { v: string }) {
    setBusy(name);
    try { const r = await fn(); await onChanged(r, typeof msg === "string" ? msg : msg.v); } catch (e) { toast(human(e).text); await onChanged(null, ""); } finally { setBusy(""); }
  }
  const publishAll = () => act("all", async () => {
    const r = await api<MonthState & { result: { applied: number; failed: { summary: string; error: string }[]; plan: { published?: number } | null } }>(`/planner/calendar-months/${ym}/publish`, { method: "POST", body: "{}" });
    setAsk(false);
    const k = r.result.applied + (r.result.plan ? 1 : 0), ko = r.result.failed.length;
    if (ko) setOpen(true);
    msgRef.v = ko ? `${plural(k, "rettifica pubblicata", "rettifiche pubblicate")}, ${plural(ko, "non applicata", "non applicate")}: vedi il motivo nell’elenco` : `Calendario di ${monthYear(ym).toLowerCase()} pubblicato: tutor e famiglie ricevono gli avvisi`;
    return r;
  }, msgRef);
  return <div className="monthbar-wrap">
    <div className={"monthbar" + (m?.state === "DRAFT" ? " is-draft" : "")} role="group" aria-label={`Calendario di ${monthYear(ym)}`}>
      <div className="mb-nav">
        <button className="circle sm" aria-label="Mese precedente" onClick={() => onMonth(shiftMonth(ym, -1))}><Icon n="left" /></button>
        <h2 className="mb-title">{monthYear(ym)}</h2>
        <button className="circle sm" aria-label="Mese successivo" onClick={() => onMonth(shiftMonth(ym, 1))}><Icon n="right" /></button>
      </div>
      <div className="mb-state">{m && stateTag(m)}<small>{text}</small></div>
      <div className="mb-act">
        {rows.length > 0 || m?.draft_plan ? <Btn kind="sm" aria-expanded={open} onClick={() => setOpen(!open)}>{open ? "Nascondi" : "Rettifiche"}{n ? ` (${n})` : ""}</Btn> : null}
        {n > 0 && <Btn kind="primary sm" isle="send" disabled={!!busy} onClick={() => setAsk(true)}>{busy === "all" ? "Pubblico…" : `Pubblica le rettifiche (${n})`}</Btn>}
      </div>
    </div>
    {open && m && <ul className="mb-list" aria-label="Rettifiche in bozza">
      {m.draft_plan && <li><span className="mb-ic"><Icon n="spark" /></span><div className="grow"><b>Bozza mensile del pianificatore</b><small>{plural(m.draft_plan.lessons.length, "lezione proposta", "lezioni proposte")} · creata il {dateLong(rome(m.draft_plan.created_at).date)}</small></div>
        <Btn kind="sm" onClick={() => go("pianificazione", { mese: ym })}>Apri in Pianificazione</Btn></li>}
      {rows.map((c) => <li key={c.id} className={c.state === "FAILED" ? "failed" : ""}>
        <span className="mb-ic"><Icon n={OP_ICON[c.op]} /></span>
        <div className="grow"><b>{OP_LABEL[c.op]}{c.state === "FAILED" && <Tag tone="red">Non applicata</Tag>}</b><small>{c.summary}{c.actor ? ` · ${c.actor}` : ""}</small>{c.state === "FAILED" && c.error && <small className="err">{c.error}</small>}</div>
        <Btn kind="sm ghost" disabled={!!busy} onClick={() => act(c.id + "d", () => discardOne(c.id), "Rettifica scartata: resta il calendario pubblicato")}>Scarta</Btn>
        <Btn kind="sm" disabled={!!busy} onClick={() => act(c.id, async () => (await publishOne(c.id)).month, "Rettifica pubblicata: tutor e famiglie ricevono l’avviso")}>{busy === c.id ? "Pubblico…" : c.state === "FAILED" ? "Riprova" : "Pubblica subito"}</Btn>
      </li>)}
      {!rows.length && !m.draft_plan && <li className="muted">Nessuna rettifica in bozza.</li>}
    </ul>}
    <Modal open={ask} onClose={() => setAsk(false)} labelledBy="mb-pub"><div className="modal-body">
      <h2 id="mb-pub">Pubblicare il calendario di {monthYear(ym).toLowerCase()}?</h2>
      <p className="lead">{plural(n, "rettifica entra", "rettifiche entrano")} nel calendario pubblico del mese, nell’ordine in cui le hai fatte. Tutor e famiglie interessati ricevono l’avviso. Le rettifiche non più valide restano in bozza con il motivo.</p>
      {m && <ul className="mb-sum">{m.corrections.filter((c) => c.state === "PENDING").slice(0, 6).map((c) => <li key={c.id}>{c.summary}</li>)}{m.draft_plan && <li>Bozza mensile: {plural(m.draft_plan.lessons.length, "lezione", "lezioni")}</li>}{m.pending > 6 && <li className="muted">e altre {m.pending - 6}…</li>}</ul>}
    </div><div className="modal-foot"><button type="button" className="pill-btn ghost" onClick={() => setAsk(false)}>Non ora</button>
      <Btn kind="primary" isle="send" disabled={busy === "all"} onClick={publishAll}>{busy === "all" ? "Pubblico…" : "Pubblica"}</Btn></div></Modal>
  </div>;
}

/** Scheda di una rettifica in bozza (clic su un blocco tratteggiato della griglia). */
export function DraftModal({ g, onClose, onChanged, toast }: { g: Ghost | null; onClose: () => void; onChanged: (m: MonthState | null, msg: string) => Promise<void>; toast: (msg: string) => void }) {
  const [busy, setBusy] = useState("");
  const [last, setLast] = useState(g); if (g && g !== last) setLast(g);
  const x = g || last; if (!x) return null;
  const c = x.corr;
  async function act(name: string, fn: () => Promise<MonthState>, msg: string) {
    setBusy(name);
    try { const m = await fn(); onClose(); await onChanged(m, msg); } catch (e) { toast(human(e).text); } finally { setBusy(""); }
  }
  return <Modal open={!!g} onClose={onClose} labelledBy="dm-title"><div className="modal-body">
    <div className="kind" style={{ marginBottom: 8 }}><Tag tone="amber">{x.kind === "review" ? "In verifica" : "In bozza"}</Tag>{c && <Tag tone="plain">{OP_LABEL[c.op]}</Tag>}</div>
    <h2 id="dm-title">{x.subject}</h2>
    <p className="lead">{x.who} · {dayLabel(rome(x.start_at).date)}, {rangeOf(x.start_at, x.end_at)}</p>
    {c ? <p className="muted">{c.summary}</p> : x.kind === "review" ? null : <p className="muted">Lezione della bozza mensile del pianificatore: si rivede e si pubblica in Pianificazione.</p>}
    <Notice kind="info">Tutor e famiglie vedono ancora il calendario pubblicato: {x.kind === "review" ? "questa lezione non è ancora visibile." : "la modifica arriva loro quando la pubblichi."}</Notice>
  </div><div className="modal-foot">
    {c ? <><Btn kind="ghost" disabled={!!busy} onClick={() => act("d", () => discardOne(c.id), "Rettifica scartata: resta il calendario pubblicato")}>Scarta</Btn><span className="grow" />
      <Btn kind="primary" isle="send" disabled={!!busy} onClick={() => act("p", async () => (await publishOne(c.id)).month, "Rettifica pubblicata: tutor e famiglie ricevono l’avviso")}>{busy === "p" ? "Pubblico…" : "Pubblica subito"}</Btn></>
      : x.kind === "review" && x.request_id ? <><button type="button" className="pill-btn ghost" onClick={onClose}>Chiudi</button><Btn kind="primary" onClick={() => { onClose(); openReview(x.request_id!); }}>Apri la verifica</Btn></>
      : <><button type="button" className="pill-btn ghost" onClick={onClose}>Chiudi</button><Btn kind="primary" onClick={() => { onClose(); go("pianificazione", { mese: x.start_at.slice(0, 7) }); }}>Apri in Pianificazione</Btn></>}
  </div></Modal>;
}

/** Riquadro nella scheda lezione quando la lezione ha una rettifica in bozza. */
export function DraftNote({ c, onChanged, toast }: { c: Correction; onChanged: (m: MonthState | null, msg: string) => Promise<void>; toast: (msg: string) => void }) {
  const [busy, setBusy] = useState("");
  async function act(name: string, fn: () => Promise<MonthState>, msg: string) {
    setBusy(name);
    try { await onChanged(await fn(), msg); } catch (e) { toast(human(e).text); } finally { setBusy(""); }
  }
  return <div className="pend-box draft-box" role="status">
    <div className="pend-head"><span className="oc-ic amber"><Icon n="clock" /></span><div><b>Rettifica in bozza</b><small>{c.summary}</small></div></div>
    
    <div className="toolbar"><Btn kind="ghost" disabled={!!busy} onClick={() => act("d", () => discardOne(c.id), "Rettifica scartata")}>Scarta</Btn>
      <Btn kind="primary" isle="send" disabled={!!busy} onClick={() => act("p", async () => (await publishOne(c.id)).month, "Rettifica pubblicata: tutor e famiglie ricevono l’avviso")}>{busy === "p" ? "Pubblico…" : "Pubblica subito"}</Btn></div>
  </div>;
}
