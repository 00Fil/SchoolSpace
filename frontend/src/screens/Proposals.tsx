import { useEffect, useRef, useState } from "react";
import { api, list } from "../api";
import { dayLabel, dayShort, hm, plural, rome } from "../format";
import { human, MODE } from "../messages";
import { Avatar, Btn, Empty, Icon, Notice, Skeleton, State, Tag, Tech } from "../ui/core";
import { Check } from "../ui/controls";
import { Modal, Sheet } from "../ui/layers";
import { go } from "../ui/route";
import { ViewState } from "../ui/states";
import { useData } from "../app/data";
import { Cap } from "../app/calendarApi";
import { SegCtl } from "../ui/controls";
import { AckQueue } from "../portal/PresaVisione";

export type Plan = { id: string; run: string; version: number; state: string; snapshot_revision: number; experimental_publish_available: boolean; publication_id: string | null };
type Assignment = { demand_key: string; tutor_id: string; start: number; end: number; mode: string };
export type RunResult = { epoch: string; solver_status: string; validation: { status: string }; is_complete: boolean; unassigned: { demand_key: string; reason_codes: string[] }[]; assignments: Assignment[] };

const at = (epoch: string, min: number) => rome(new Date(Date.parse(epoch) + min * 60000));
/** Motivi dei non pianificati in linguaggio del centro (codici del motore nella sezione tecnica). */
const REASON: Record<string, string> = {
  NO_COMMON_AVAILABILITY: "studente e tutor non hanno fasce in comune", NO_TUTOR: "nessun tutor abilitato per materia e livello",
  NO_SPACE: "nessuna aula libera", NO_VIDEO: "nessun canale video libero", CLOSURE: "il centro è chiuso nelle fasce possibili",
  TUTOR_LOAD: "i tutor hanno raggiunto il carico massimo", SERVICE_WINDOW: "fuori dagli orari del centro", TRAVEL: "tempo di spostamento insufficiente",
  STUDENT: "le disponibilità dello studente non bastano", RESOURCE: "mancano spazi o canali", COVERAGE: "i dati di disponibilità sono incompleti",
  REQUEST_NEW_AVAILABILITY: "servono nuove disponibilità", MOVE_WITHIN_DECLARED: "basterebbe spostare una lezione già fissata",
};
/** Le proposte del pianificatore mensile non hanno il formato del motore settimanale: non si aprono qui. */
export const weeklyResult = (r: unknown): RunResult | null => {
  const x = r as Partial<RunResult> | null;
  return x && Array.isArray(x.assignments) && Array.isArray(x.unassigned) && x.validation && typeof x.epoch === "string" ? x as RunResult : null;
};
export const reasonText = (codes: string[]) => { const t = [...new Set(codes.map((c) => REASON[c] || REASON[c.split("_")[0]]).filter(Boolean))]; return t.length ? t.join("; ") : codes.length ? "nessun orario compatibile con disponibilità, tutor e spazi" : "motivo non indicato dal motore"; };
const why = (codes: string[]) => { const t = reasonText(codes); return t[0].toUpperCase() + t.slice(1) + "."; };
type Life = { state: string; version: number; current_revision: number; snapshot_revision: number; transitions: string[]; report: { code?: string; message?: string } };

/** Proposte del motore: confronta, valida, rifiuta, pubblica e crea le serie (P3). */
export default function Proposals({ cap, onPublished }: { cap: Cap; onPublished: (firstDay: string | null, n: number) => void }) {
  const [plans, setPlans] = useState<Plan[] | null>(null), [err, setErr] = useState(""), [open, setOpen] = useState<Plan | null>(null), [pub, setPub] = useState<{ plan: Plan; res: RunResult } | null>(null), [cmp, setCmp] = useState(false);
  const load = () => list<Plan>("/schedule-plans/").then(setPlans).catch((e) => setErr(human(e).text));
  useEffect(() => { load(); }, []);
  const ready = (plans || []).filter((p) => p.experimental_publish_available && !p.publication_id);
  const shown = [...(plans || [])].sort((a, b) => Number(b.experimental_publish_available && !b.publication_id) - Number(a.experimental_publish_available && !a.publication_id)).slice(0, 6);
  // v0.9.11: le bozze mensili e le rettifiche si gestiscono nella barra del mese dell’Agenda;
  // qui restano solo le proposte settimanali del motore, quando ce ne sono.
  if (plans && !plans.length && !err) return <AckQueue />;
  return <section className="module" aria-labelledby="h-props" style={{ marginTop: 18 }}>
    <div className="m-head"><div><h2 className="m-title" id="h-props">Proposte settimanali del motore</h2><p className="sub-line">{plans ? ready.length ? `${plural(ready.length, "proposta validata pronta", "proposte validate pronte")} per il calendario.` : "Nessuna proposta in attesa di pubblicazione." : "Carico le proposte…"}</p></div>
      <div className="controls">{(plans || []).length > 1 && <Btn kind="sm" onClick={() => setCmp(true)}>Confronta</Btn>}<a className="pill-btn sm" href="#/pianificazione"><Icon n="spark" />Pianificazione</a></div></div>
    {err && <Notice kind="bad" action={<Btn kind="sm" onClick={() => { setErr(""); load(); }}>Riprova</Btn>}>{err}</Notice>}
    {!plans ? <Skeleton rows={2} /> : !plans.length ? <Empty title="Ancora nessuna proposta">Generala da <button type="button" className="link-btn" onClick={() => go("pianificazione")}>Pianificazione</button>: lì la rivedi e la pubblichi.</Empty>
      : <div className="mini-list">{shown.map((p, i) => <button key={p.id} type="button" className="mini" onClick={() => setOpen(p)}>
        <span className="mini-ic"><Icon n="spark" /></span>
        <span className="grow"><b>Proposta {plans.length - plans.indexOf(p)}</b><small>{p.publication_id ? "Già pubblicata nel calendario" : p.experimental_publish_available ? "Pronta da rivedere e pubblicare" : "Non pubblicabile"}{i === 0 && ready.includes(p) ? " · la più recente" : ""}</small></span>
        <State s={p.state} /><Icon n="right" /></button>)}</div>}
    <PlanSheet plan={open} cap={cap} onClose={() => setOpen(null)} onChanged={load} onPublish={(plan, res) => { setOpen(null); setPub({ plan, res }); }} />
    <Compare open={cmp} plans={plans || []} onClose={() => setCmp(false)} />
    <PublishModal v={pub} onClose={() => setPub(null)} onDone={async (first, n) => { setPub(null); await load(); onPublished(first, n); }} />
    <AckQueue />
  </section>;
}

function useRun(plan: Plan | null) {
  const [res, setRes] = useState<{ id: string; r: RunResult | null } | null>(null), [err, setErr] = useState("");
  useEffect(() => {
    if (!plan) return; let live = true; setErr("");
    api<{ result: RunResult | null }>(`/schedule-runs/${plan.run}/`).then((x) => { if (live) setRes({ id: plan.id, r: weeklyResult(x.result) }); }).catch((e) => { if (live) setErr(human(e).text); });
    return () => { live = false; };
  }, [plan]);
  return { res: plan && res?.id === plan.id ? res.r : undefined, err };
}

export function Assignments({ res }: { res: RunResult }) {
  const d = useData(); const tutor = (id: string) => d.tutors.find((t) => t.id === id)?.display_name || "Tutor";
  const rows = [...res.assignments].sort((a, b) => a.start - b.start);
  return <div className="list-wrap"><table className="list">
    <thead><tr><th scope="col">Quando</th><th scope="col">Tutor</th><th scope="col" className="hide-m">Modalità</th></tr></thead>
    <tbody>{rows.map((a) => { const s = at(res.epoch, a.start), e = at(res.epoch, a.end); return <tr key={a.demand_key}>
      <td><b style={{ fontWeight: 500 }}>{dayShort(s.date)} {Number(s.date.slice(8))}</b> <span className="num muted">{hm(s.min)}–{hm(e.min)}</span></td>
      <td><span className="who"><Avatar name={tutor(a.tutor_id)} k={a.tutor_id} /><b>{tutor(a.tutor_id)}</b></span></td>
      <td className="hide-m">{MODE[a.mode] || a.mode}</td></tr>; })}</tbody></table></div>;
}

function PlanSheet({ plan, cap, onClose, onPublish, onChanged }: { plan: Plan | null; cap: Cap; onClose: () => void; onPublish: (p: Plan, r: RunResult) => void; onChanged: () => void }) {
  const [last, setLast] = useState(plan); useEffect(() => { if (plan) setLast(plan); }, [plan]);
  const p = plan || last; const { res, err } = useRun(plan);
  const [life, setLife] = useState<Life | null>(null), [busy, setBusy] = useState(""), [opErr, setOpErr] = useState(""), [rej, setRej] = useState(false), [series, setSeries] = useState<number | null>(null);
  const loadLife = () => plan ? api<Life>(`/schedule-plans/${plan.id}/lifecycle/`).then(setLife).catch(() => setLife(null)) : Promise.resolve();
  useEffect(() => { setLife(null); setOpErr(""); setRej(false); setSeries(null); loadLife(); }, [plan]);
  async function op(name: string, path: string, body: object) {
    setBusy(name); setOpErr("");
    try { const r = await api<{ series?: string[] }>(path, { method: "POST", headers: { "Idempotency-Key": crypto.randomUUID() }, body: JSON.stringify(body) }); if (r?.series) setSeries(r.series.length); await loadLife(); onChanged(); return true; }
    catch (e) { setOpErr(human(e).text); return false; } finally { setBusy(""); }
  }
  const state = p?.publication_id ? "PUBLISHED" : life?.state || p?.state || "DRAFT";
  const can = !!p && cap.enabled && p.experimental_publish_available && !p.publication_id && !!res && res.validation.status === "PASSED" && state === "VALIDATED";
  const canValidate = !!p && !p.publication_id && !!life && life.transitions.includes("VALIDATED") && state === "DRAFT";
  const canReject = !!p && !p.publication_id && !!life && life.transitions.includes("REJECTED");
  return <Sheet open={!!plan} onClose={onClose} labelledBy="sheet-p">{p && <>
    <div className="sheet-body">
      <div className="sheet-top"><div className="kind"><State s={state} />{res && <Tag tone={res.is_complete ? "green" : "amber"}>{res.is_complete ? "Copre tutta la domanda" : "Parziale"}</Tag>}</div><button className="circle sm raised" aria-label="Chiudi" onClick={onClose}><Icon n="x" /></button></div>
      <h2 id="sheet-p">Proposta della settimana</h2>
      {err ? <Notice kind="bad">{err}</Notice> : res === undefined ? <Skeleton rows={4} /> : !res ? <Notice kind="info">Il risultato non è ancora disponibile: il calcolo è in corso o non è riuscito.</Notice> : <>
        <p className="muted" style={{ marginTop: 6 }}>{res.assignments.length ? `${plural(res.assignments.length, "lezione", "lezioni")} dal ${dayLabel(at(res.epoch, Math.min(...res.assignments.map((a) => a.start))).date).toLowerCase()}.` : "Nessuna lezione collocata."} Esito del motore: <State s={res.solver_status} />, controllo indipendente: <State s={res.validation.status} />.</p>
        {res.solver_status === "UNKNOWN" && <ViewState kind="inconclusive">Il motore non ha trovato una risposta certa nel tempo concesso: non significa che sia impossibile. Rigenera la proposta con più tempo o meno richieste.</ViewState>}
        {res.assignments.length > 0 && <Assignments res={res} />}
        {res.unassigned.length > 0 && <Notice kind="warn" title={plural(res.unassigned.length, "richiesta non collocata", "richieste non collocate")}>{why(res.unassigned[0].reason_codes)} Per pubblicare dovrai accettarle esplicitamente.</Notice>}
        {p.publication_id && <Notice kind="ok">Proposta già pubblicata: le lezioni sono nel calendario.</Notice>}
        {!p.experimental_publish_available && !p.publication_id && <Notice kind="info">Questa proposta non si può pubblicare: i dati sono cambiati o il controllo non l’ha validata. Generane una nuova.</Notice>}
        {state === "DRAFT" && !p.publication_id && <Notice kind="info">Prima di pubblicare, valida la proposta: il controllo si ripete sui dati di oggi.</Notice>}
        {state === "REJECTED" && <Notice kind="info" title="Proposta rifiutata">{life?.report?.message || "Non verrà pubblicata."}</Notice>}
        {state === "STALE" && <Notice kind="warn">I dati sono cambiati dopo il calcolo: genera una nuova proposta.</Notice>}
        {series !== null && <Notice kind="ok">{plural(series, "serie ricorrente creata", "serie ricorrenti create")}: le prossime proposte terranno questi orari.</Notice>}
        {rej && <div style={{ marginTop: 10 }}><p className="muted">Rifiutare questa proposta? Potrai generarne una nuova.</p>
          <div className="controls"><Btn kind="sm" onClick={() => setRej(false)}>Annulla</Btn><Btn kind="sm" disabled={busy === "reject"} onClick={async () => { if (await op("reject", `/schedule-plans/${p.id}/reject/`, { expected_version: life!.version, reason: "Proposta non adatta alla settimana" })) setRej(false); }}>Conferma il rifiuto</Btn></div></div>}
        {opErr && <Notice kind="bad">{opErr}</Notice>}
      </>}
      <Tech><dl className="facts"><dt>Proposta</dt><dd><code>{p.id}</code></dd><dt>Calcolo</dt><dd><code>{p.run}</code></dd><dt>Versione</dt><dd>{p.version}</dd><dt>Revisione dati</dt><dd>{p.snapshot_revision}</dd>
        {res && <><dt>Unità</dt><dd><code>{res.assignments.map((a) => a.demand_key).join(", ") || "—"}</code></dd>{res.unassigned.length > 0 && <><dt>Non collocate</dt><dd><code>{res.unassigned.map((u) => `${u.demand_key}: ${u.reason_codes.join(", ")}`).join("; ")}</code></dd></>}</>}</dl></Tech>
    </div>
    {(can || canValidate || canReject || !!p.publication_id) && <div className="sheet-foot">
      {canReject && !rej && <Btn onClick={() => setRej(true)}>Rifiuta</Btn>}
      <span className="grow" />
      {canValidate && <Btn kind="primary" isle="check" disabled={busy === "validate"} onClick={() => op("validate", `/schedule-plans/${p.id}/validate/`, { expected_revision: life!.current_revision })}>{busy === "validate" ? "Valido…" : "Valida"}</Btn>}
      {can && <Btn kind="primary" isle="send" onClick={() => onPublish(p, res!)}>Pubblica nel calendario</Btn>}
      {!!p.publication_id && series === null && <Btn disabled={busy === "series"} onClick={() => op("series", `/schedule-plans/${p.id}/derive-series/`, { stability: "PREFERRED" })}>{busy === "series" ? "Creo…" : "Crea le serie ricorrenti"}</Btn>}
    </div>}
  </>}</Sheet>;
}

function PublishModal({ v, onClose, onDone }: { v: { plan: Plan; res: RunResult } | null; onClose: () => void; onDone: (first: string | null, n: number) => Promise<void> }) {
  const [accept, setAccept] = useState(false), [tried, setTried] = useState(false), [err, setErr] = useState(""), [busy, setBusy] = useState(false);
  const pending = useRef<{ key: string; body: string } | null>(null);
  const [last, setLast] = useState(v); useEffect(() => { if (v) { setLast(v); setAccept(false); setTried(false); setErr(""); pending.current = null; } }, [v]);
  const x = v || last; if (!x) return null;
  const missing = x.res.unassigned.map((u) => u.demand_key), partial = missing.length > 0;
  const first = x.res.assignments.length ? at(x.res.epoch, Math.min(...x.res.assignments.map((a) => a.start))).date : null;
  const bad = { accept: partial && !accept };
  async function submit(e: React.FormEvent) {
    e.preventDefault(); setTried(true);
    if (bad.accept) return;
    const body = JSON.stringify({ expected_version: x!.plan.version, expected_revision: x!.plan.snapshot_revision, accept_unassigned_demand_keys: missing });
    if (!pending.current || pending.current.body !== body) pending.current = { key: crypto.randomUUID(), body };
    setBusy(true); setErr("");
    try {
      const r = await api<{ created_lesson_ids: string[]; kept_lesson_ids?: string[] }>(`/schedule-plans/${x!.plan.id}/publish/`, { method: "POST", headers: { "Idempotency-Key": pending.current.key }, body });
      pending.current = null; await onDone(first, r.created_lesson_ids.length);
    } catch (er) { const h = human(er); setErr(h.text); if (!h.retry) pending.current = null; } finally { setBusy(false); }
  }
  return <Modal open={!!v} onClose={onClose} labelledBy="pb-title"><form onSubmit={submit} noValidate>
    <div className="modal-body">
      <h2 id="pb-title">Pubblicare la proposta?</h2>
      <p className="lead">{plural(x.res.assignments.length, "lezione verrà creata", "lezioni verranno create")}{first ? ` a partire da ${dayLabel(first).toLowerCase()}` : ""}. Lezioni, partecipanti e prenotazioni si salvano insieme, oppure nulla. Ogni tutor coinvolto riceverà gli orari da confermare.</p>
      {partial && <>
        <Notice kind="warn" title={plural(missing.length, "richiesta resta senza lezione", "richieste restano senza lezione")}>{why(x.res.unassigned[0].reason_codes)}</Notice>
        <div className={"fld" + (tried && bad.accept ? " bad" : "")}><Check checked={accept} onChange={setAccept}>Accetto che {missing.length === 1 ? "questa richiesta resti" : "queste richieste restino"} da pianificare</Check><span className="err">{tried && bad.accept ? "Serve la tua conferma esplicita." : ""}</span></div>
      </>}
      {err && <Notice kind="bad">{err}</Notice>}
    </div>
    <div className="modal-foot"><button type="button" className="pill-btn ghost" onClick={onClose}>Chiudi</button>
      <button className="pill-btn primary island" disabled={busy}>{busy ? "Pubblicazione…" : pending.current ? "Riprova la stessa pubblicazione" : "Pubblica"}<span className="isle"><Icon n="send" /></span></button></div>
  </form></Modal>;
}

/** Confronto tra due proposte: lezioni uguali, spostate o presenti in una sola. */
function Compare({ open, plans, onClose }: { open: boolean; plans: Plan[]; onClose: () => void }) {
  const [a, setA] = useState(""), [b, setB] = useState(""), [res, setRes] = useState<Record<string, RunResult | null>>({}), [err, setErr] = useState("");
  const d = useData(); const tutor = (id: string) => d.tutors.find((t) => t.id === id)?.display_name || "Tutor";
  const opts = plans.slice(0, 6).map((p, i) => [p.id, `Proposta ${plans.length - i}`] as [string, string]);
  useEffect(() => { if (open && plans.length > 1) { setA(plans[1].id); setB(plans[0].id); } }, [open, plans]);
  useEffect(() => {
    for (const id of [a, b]) { const p = plans.find((x) => x.id === id); if (!p || id in res) continue;
      api<{ result: RunResult | null }>(`/schedule-runs/${p.run}/`).then((x) => setRes((r) => ({ ...r, [id]: weeklyResult(x.result) }))).catch((e) => setErr(human(e).text)); }
  }, [a, b]);
  const ra = res[a], rb = res[b];
  const key = (x: { tutor_id: string; start: number; end: number; mode: string }) => `${x.tutor_id}|${x.start}|${x.end}|${x.mode}`;
  let rows: { k: string; kind: string; text: string }[] = [];
  if (ra && rb) {
    const ma = new Map(ra.assignments.map((x) => [x.demand_key, x])), mb = new Map(rb.assignments.map((x) => [x.demand_key, x]));
    const line = (r: RunResult, x: Assignment) => { const s0 = at(r.epoch, x.start), e0 = at(r.epoch, x.end); return `${dayShort(s0.date)} ${hm(s0.min)}–${hm(e0.min)} · ${tutor(x.tutor_id)}`; };
    for (const [k, x] of ma) { const y = mb.get(k); rows.push(!y ? { k, kind: "Solo nella prima", text: line(ra, x) } : key(x) === key(y) ? { k, kind: "Uguale", text: line(ra, x) } : { k, kind: "Cambia", text: `${line(ra, x)} → ${line(rb, y)}` }); }
    for (const [k, y] of mb) if (!ma.has(k)) rows.push({ k, kind: "Solo nella seconda", text: line(rb, y) });
    rows = rows.sort((p, q) => Number(p.kind === "Uguale") - Number(q.kind === "Uguale"));
  }
  const count = (k: string) => rows.filter((r) => r.kind === k).length;
  return <Modal open={open} onClose={onClose} labelledBy="cmp-title" width={720}><div className="modal-body">
    <h2 id="cmp-title">Confronta due proposte</h2>
    <SegCtl label="Prima proposta" value={a} options={opts} onChange={setA} />
    <div style={{ height: 8 }} />
    <SegCtl label="Seconda proposta" value={b} options={opts} onChange={setB} />
    {err && <Notice kind="bad">{err}</Notice>}
    {a === b ? <Notice kind="info">Scegli due proposte diverse.</Notice> : !ra || !rb ? <Skeleton rows={3} /> : <>
      <p className="muted" style={{ marginTop: 10 }}>{count("Uguale")} uguali · {count("Cambia")} cambiano · {count("Solo nella prima") + count("Solo nella seconda")} in una sola · non collocate: {ra.unassigned.length} contro {rb.unassigned.length}</p>
      <div className="list-wrap"><table className="list"><thead><tr><th scope="col">Esito</th><th scope="col">Lezione</th></tr></thead>
        <tbody>{rows.map((r) => <tr key={r.k}><td><Tag tone={r.kind === "Uguale" ? "plain" : r.kind === "Cambia" ? "amber" : "green"}>{r.kind}</Tag></td><td>{r.text}</td></tr>)}</tbody></table></div>
    </>}
  </div><div className="modal-foot"><button type="button" className="pill-btn ghost" onClick={onClose}>Chiudi</button></div></Modal>;
}
