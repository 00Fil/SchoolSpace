import { ReactNode, useEffect, useState } from "react";
import { api } from "../api";
import { nextPath } from "../api/client";
import { dateLong, hm, rome } from "../format";
import { human } from "../messages";
import { Btn, Notice, PageHead, Skeleton, Tag, Tech } from "../ui/core";
import { Field, SegCtl } from "../ui/controls";
import { Modal, useToast } from "../ui/layers";

/** P6 · Area privacy del centro: richieste degli interessati, export, conservazione con approvazione,
 *  registro delle operazioni consultabile, revisione maggiore età. Solo ruolo CENTER (il server lo impone). */
type Page<T> = { results: T[]; next?: string | null };
type Req = { id: string; kind: string; subject_type: string; subject_id: string; subject_pseudonym: string; channel: string; requester_role: string; received_at: string; due_at: string; status: string; identity_verified_at: string | null; extension_reason: string; outcome: string };
type Policy = { id: string; category: string; label: string; purpose: string; legal_basis: string; duration_days: number | null; action: string; status: string; approved_at: string | null; approval_reference: string; version: number };
type Run = { id: string; started_at: string; finished_at: string | null; dry_run: boolean; results: unknown; receipt_hash: string };
type Exp = { id: string; created_at: string; audience: string; purpose: string; filename: string; expires_at: string; downloaded_at: string | null; revoked_at: string | null; available: boolean };
type Ev = { id: string; occurred_at: string; category: string; operation: string; actor: string | null; object_type: string; object_id: string; purpose: string; reason: string; correlation_id: string };

const KIND: Record<string, string> = { ACCESS: "Accesso (art. 15)", RECTIFICATION: "Rettifica (art. 16)", ERASURE: "Cancellazione (art. 17)", RESTRICTION: "Limitazione (art. 18)", PORTABILITY: "Portabilità (art. 20)", OBJECTION: "Opposizione (art. 21)" };
const STATUS: Record<string, [string, "blue" | "amber" | "green" | "plain" | "red"]> = { RECEIVED: ["Ricevuta", "blue"], VERIFIED: ["Identità verificata", "amber"], EXTENDED: ["Prorogata", "amber"], COMPLETED: ["Evasa", "green"], REJECTED: ["Respinta", "plain"] };
const when = (iso: string | null) => iso ? `${dateLong(rome(iso).date)} ${hm(rome(iso).min)}` : "—";
const late = (r: Req) => ["RECEIVED", "VERIFIED", "EXTENDED"].includes(r.status) && new Date(r.due_at).getTime() < Date.now();

type FieldDef = { key: string; label: string; value: string; long?: boolean; options?: [string, string][] };
type Act = { title: string; note?: ReactNode; fields: FieldDef[]; confirm: string; danger?: boolean; run: (v: Record<string, string>) => Promise<unknown> };

function ActModal({ act, onClose, onDone }: { act: Act | null; onClose: () => void; onDone: (msg: string) => void }) {
  const [v, setV] = useState<Record<string, string>>({}), [busy, setBusy] = useState(false), [err, setErr] = useState("");
  useEffect(() => { setV(Object.fromEntries((act?.fields || []).map((f) => [f.key, f.value]))); setErr(""); }, [act]);
  if (!act) return null;
  const empty = act.fields.some((f) => !String(v[f.key] || "").trim());
  async function submit() {
    setBusy(true); setErr("");
    try { await act!.run(v); onDone(act!.title + ": fatto."); } catch (e) { setErr(human(e).text); } finally { setBusy(false); }
  }
  return <Modal open onClose={onClose} labelledBy="pv-act"><div className="modal-body">
    <h2 id="pv-act">{act.title}</h2>{act.note && <p className="muted">{act.note}</p>}
    {act.fields.map((f) => <Field key={f.key} label={f.label} id={"pv-" + f.key}>{f.options
      ? <select id={"pv-" + f.key} className="inp" value={v[f.key] || ""} onChange={(e) => setV({ ...v, [f.key]: e.target.value })}><option value="">Scegli…</option>{f.options.map(([id, l]) => <option key={id} value={id}>{l}</option>)}</select>
      : f.long
      ? <textarea id={"pv-" + f.key} className="inp" rows={3} value={v[f.key] || ""} onChange={(e) => setV({ ...v, [f.key]: e.target.value })} />
      : <input id={"pv-" + f.key} className="inp" value={v[f.key] || ""} onChange={(e) => setV({ ...v, [f.key]: e.target.value })} />}</Field>)}
    {err && <Notice kind="bad">{err}</Notice>}
  </div><div className="modal-foot"><button type="button" className="pill-btn ghost" onClick={onClose}>Annulla</button>
    <Btn kind="primary" disabled={busy || empty} onClick={submit}>{busy ? "Attendi…" : act.confirm}</Btn></div></Modal>;
}

function useList<T>(path: string) {
  const [rows, setRows] = useState<T[] | null>(null), [next, setNext] = useState<string | null>(null), [err, setErr] = useState("");
  const load = () => api<Page<T>>(path).then((p) => { setRows(p.results); setNext(nextPath(p.next, location.origin)); setErr(""); }).catch((e) => setErr(human(e).text));
  const more = () => next && api<Page<T>>(next).then((p) => { setRows((r) => [...(r || []), ...p.results]); setNext(nextPath(p.next, location.origin)); }).catch((e) => setErr(human(e).text));
  useEffect(() => { setRows(null); load(); }, [path]);
  return { rows, err, load, more, hasMore: !!next };
}
const post = (path: string, body: unknown) => api(path, { method: "POST", body: JSON.stringify(body) });

function Richieste({ act }: { act: (a: Act) => void }) {
  const toast = useToast();
  const [filter, setFilter] = useState<"open" | "overdue" | "all">("open");
  const l = useList<Req>("/privacy/requests" + (filter === "all" ? "" : `?status=${filter}`));
  const A = (r: Req, kind: string, aud: [string, string][] = []): Act => {
    const to = `/privacy/requests/${r.id}/`;
    const done = (p: Promise<unknown>) => p.then(l.load);
    switch (kind) {
      case "verify": return { title: "Verifica identità", note: "Indica come hai verificato chi ha fatto la richiesta (non scrivere numeri di documento).", fields: [{ key: "method", label: "Modalità", value: r.channel === "PORTALE" ? "Accesso autenticato al portale con account verificato" : "Riconoscimento di persona in segreteria" }], confirm: "Registra", run: (v) => done(post(to + "verify-identity", v)) };
      case "extend": return { title: "Proroga di due mesi", note: "Ammessa per richieste complesse o numerose (art. 12.3): l’interessato va informato entro il primo mese.", fields: [], confirm: "Proroga", run: (v) => done(post(to + "extend", v)) };
      case "export": return { title: "Evadi con export", note: "Il file si scarica una volta sola dall’account destinatario, entro la scadenza.", fields: [{ key: "audience", label: "Account destinatario", value: aud.length === 1 ? aud[0][0] : "", options: aud }], confirm: "Crea l’export", run: (v) => done(post(to + "export", { audience: v.audience.trim(), format: "json" })) };
      case "erase": return { title: "Cancella o anonimizza", danger: true, note: "Operazione irreversibile. I dati con obbligo di conservazione (pagamenti, registri) restano e vengono indicati nell’esito.", fields: [{ key: "motivation", label: "Motivazione", value: "Richiesta di cancellazione dell’interessato (art. 17)", long: true }], confirm: "Cancella", run: (v) => done(post(to + "erase", v)) };
      case "close": return { title: "Chiudi con esito", note: "Per rettifiche fatte a mano, limitazioni e opposizioni.", fields: [{ key: "outcome", label: "Esito", value: "", long: true }, { key: "motivation", label: "Motivazione", value: "Richiesta evasa come indicato nell’esito" }], confirm: "Chiudi", run: (v) => done(post(to + "close", v)) };
      default: return { title: "Respingi", danger: true, note: "Solo se infondata o eccessiva (art. 12.5): la motivazione va comunicata all’interessato.", fields: [{ key: "motivation", label: "Motivazione", value: "", long: true }], confirm: "Respingi", run: (v) => done(post(to + "reject", v)) };
    }
  };
  return <div>
    <div className="controls"><SegCtl label="Mostra" value={filter} onChange={setFilter} options={[["open", "Aperte"], ["overdue", "Scadute"], ["all", "Tutte"]]} /></div>
    {l.err && <Notice kind="bad" action={<Btn kind="sm" onClick={l.load}>Riprova</Btn>}>{l.err}</Notice>}
    {!l.rows ? <Skeleton rows={4} /> : !l.rows.length ? <p className="muted">Nessuna richiesta {filter === "open" ? "aperta" : filter === "overdue" ? "scaduta" : ""}.</p> :
      <div className="list-rows">{l.rows.map((r) => { const open = ["RECEIVED", "VERIFIED", "EXTENDED"].includes(r.status), s = STATUS[r.status] || [r.status, "plain"]; return <div className="list-row" key={r.id}>
        <div><b>{KIND[r.kind] || r.kind}</b> <Tag tone={s[1]}>{s[0]}</Tag>{late(r) && <> <Tag tone="red">Oltre la scadenza</Tag></>}
          <small>{r.subject_type === "STUDENT" ? "Studente" : "Account"} {r.subject_pseudonym} · {r.channel} · {r.requester_role} · ricevuta {when(r.received_at)} · entro {when(r.due_at)}</small>
          {r.outcome && <small>Esito: {r.outcome}</small>}</div>
        {open && <div className="controls" style={{ flexWrap: "wrap", gap: 6 }}>
          {!r.identity_verified_at && <Btn kind="sm" onClick={() => act(A(r, "verify"))}>Verifica identità</Btn>}
          {r.identity_verified_at && ["ACCESS", "PORTABILITY"].includes(r.kind) && <Btn kind="sm" onClick={() => api<{ results: { id: string; label: string }[] }>(`/privacy/requests/${r.id}/audiences`).then((p) => act(A(r, "export", p.results.map((u) => [u.id, u.label] as [string, string])))).catch((e) => toast(human(e).text))}>Evadi con export</Btn>}
          {r.identity_verified_at && r.kind === "ERASURE" && <Btn kind="sm" onClick={() => act(A(r, "erase"))}>Cancella</Btn>}
          {r.identity_verified_at && <Btn kind="sm" onClick={() => act(A(r, "close"))}>Chiudi con esito</Btn>}
          {r.status !== "EXTENDED" && <Btn kind="sm" onClick={() => act(A(r, "extend"))}>Proroga</Btn>}
          <Btn kind="sm" onClick={() => act(A(r, "reject"))}>Respingi</Btn>
        </div>}</div>; })}</div>}
    {l.hasMore && <Btn kind="sm" onClick={l.more}>Carica altre</Btn>}
  </div>;
}

function Conservazione({ act }: { act: (a: Act) => void }) {
  const p = useList<Policy>("/privacy/retention-policies"), r = useList<Run>("/privacy/retention-runs");
  const pending = (p.rows || []).filter((x) => x.status !== "APPROVED").length;
  const run = (dry: boolean): Act => ({ title: dry ? "Simula la pulizia" : "Esegui la pulizia", danger: !dry, note: dry ? "Nessun dato viene toccato: vedi cosa succederebbe con le regole approvate." : "Applica solo le regole approvate. Cancellazioni e anonimizzazioni sono irreversibili; la ricevuta resta nel registro.", fields: [], confirm: dry ? "Simula" : "Esegui", run: () => post("/privacy/retention-runs", { dry_run: dry }).then(r.load) });
  return <div>
    {pending > 0 && <Notice kind="warn" title={`${pending} regole da approvare`}>Finché una regola non è approvata dal titolare, la pulizia non la applica.</Notice>}
    {p.err && <Notice kind="bad">{p.err}</Notice>}
    {!p.rows ? <Skeleton rows={4} /> : <div className="list-rows">{p.rows.map((x) => <div className="list-row" key={x.id}>
      <div><b>{x.label}</b> <Tag tone={x.status === "APPROVED" ? "green" : "amber"}>{x.status === "APPROVED" ? "Approvata" : "Da approvare"}</Tag>
        <small>{x.duration_days == null ? "Durata da definire" : `${x.duration_days} giorni`} · poi {x.action.toLowerCase()} · {x.legal_basis || "base giuridica da indicare"}</small>
        {x.approved_at && <small>Approvata {when(x.approved_at)} · rif. {x.approval_reference}</small>}</div>
      {x.status !== "APPROVED" && <Btn kind="sm" disabled={x.duration_days == null} onClick={() => act({ title: "Approva la regola", note: <>Registra l’approvazione del titolare per «{x.label}». Riporta il riferimento del verbale o della delibera.</>, fields: [{ key: "reference", label: "Riferimento dell’approvazione", value: "" }], confirm: "Approva", run: (v) => post(`/privacy/retention-policies/${x.id}/approve`, { ...v, expected_version: x.version }).then(p.load) })}>Approva</Btn>}
    </div>)}</div>}
    <h2 className="m-title" style={{ marginTop: 18 }}>Esecuzioni</h2>
    <div className="controls" style={{ gap: 8 }}><Btn kind="sm" onClick={() => act(run(true))}>Simula</Btn><Btn kind="sm" onClick={() => act(run(false))}>Esegui</Btn></div>
    {!r.rows ? <Skeleton rows={2} /> : !r.rows.length ? <p className="muted">Nessuna esecuzione.</p> : <div className="list-rows">{r.rows.map((x) => <div className="list-row" key={x.id}>
      <div><b>{x.dry_run ? "Simulazione" : "Esecuzione"} · {when(x.started_at)}</b><Tech label="Dettagli dell’esecuzione"><code>Ricevuta {x.receipt_hash || "—"}{"\n"}{JSON.stringify(x.results, null, 2)}</code></Tech></div></div>)}</div>}
  </div>;
}

function Export({ act }: { act: (a: Act) => void }) {
  const l = useList<Exp>("/privacy/exports");
  return <div>
    {l.err && <Notice kind="bad">{l.err}</Notice>}
    {!l.rows ? <Skeleton rows={3} /> : !l.rows.length ? <p className="muted">Nessun export.</p> : <div className="list-rows">{l.rows.map((x) => <div className="list-row" key={x.id}>
      <div><b>{x.filename}</b> <Tag tone={x.available ? "blue" : x.revoked_at ? "plain" : "green"}>{x.available ? "Da scaricare" : x.revoked_at ? "Revocato" : "Scaricato"}</Tag>
        <small>{x.purpose} · creato {when(x.created_at)} · scade {when(x.expires_at)}{x.downloaded_at ? ` · scaricato ${when(x.downloaded_at)}` : ""}</small></div>
      {x.available && <Btn kind="sm" onClick={() => act({ title: "Revoca l’export", note: "Il file viene distrutto e il link smette di funzionare.", fields: [], confirm: "Revoca", danger: true, run: (v) => post(`/privacy/exports/${x.id}/revoke`, v).then(l.load) })}>Revoca</Btn>}
    </div>)}</div>}
    {l.hasMore && <Btn kind="sm" onClick={l.more}>Carica altri</Btn>}
  </div>;
}

const CATS = ["", "PRIVACY", "EXPORT", "RETENTION", "GUARDIANSHIP", "IDENTITY", "CALENDAR"];
function Registro() {
  const [cat, setCat] = useState(""), [obj, setObj] = useState(""), [q, setQ] = useState("");
  const l = useList<Ev>("/privacy/audit-events" + (q ? "?" + q : ""));
  const apply = () => setQ(new URLSearchParams(Object.entries({ category: cat, object_id: obj.trim() }).filter(([, v]) => v)).toString());
  return <div>
    <div className="controls" style={{ flexWrap: "wrap", gap: 8, alignItems: "flex-end" }}>
      <Field label="Categoria" id="au-cat"><select id="au-cat" className="inp" value={cat} onChange={(e) => setCat(e.target.value)}>{CATS.map((c) => <option key={c} value={c}>{c || "Tutte"}</option>)}</select></Field>
      <Field label="Oggetto (ID)" id="au-obj"><input id="au-obj" className="inp" value={obj} onChange={(e) => setObj(e.target.value)} /></Field>
      <Btn kind="sm" onClick={apply}>Filtra</Btn>
    </div>
    <p className="fine">Registro in sola aggiunta: nessuno, nemmeno il centro, può modificare o cancellare le voci. La consultazione non misura la produttività delle persone (L. 300/1970 art. 4).</p>
    {l.err && <Notice kind="bad">{l.err}</Notice>}
    {!l.rows ? <Skeleton rows={5} /> : !l.rows.length ? <p className="muted">Nessuna voce.</p> : <div className="table-wrap"><table className="tbl"><thead><tr><th>Quando</th><th>Categoria</th><th>Operazione</th><th>Oggetto</th><th>Motivo</th></tr></thead>
      <tbody>{l.rows.map((e) => <tr key={e.id}><td>{when(e.occurred_at)}</td><td>{e.category}</td><td>{e.operation}</td><td>{e.object_type} {e.object_id?.slice(0, 8)}</td><td>{e.reason || e.purpose || "—"}</td></tr>)}</tbody></table></div>}
    {l.hasMore && <Btn kind="sm" onClick={l.more}>Carica altre</Btn>}
  </div>;
}

const MAJ: Record<string, string> = { flagged: "Da riconfermare", overdue: "Scadute", suspended: "Sospese" };
function Maggiore({ act }: { act: (a: Act) => void }) {
  const [rep, setRep] = useState<Record<string, unknown> | null>(null);
  const run = (dry: boolean): Act => ({ title: dry ? "Controlla chi diventa maggiorenne" : "Avvia le riconferme", note: dry ? "Solo verifica: nessuna delega cambia." : "Gli studenti maggiorenni ricevono la richiesta di riconferma; le deleghe non riconfermate scadono alla data indicata, senza revoche silenziose.", fields: [], confirm: dry ? "Controlla" : "Avvia", run: () => post("/privacy/majority-review", { dry_run: dry }).then((r) => setRep(r as Record<string, unknown>)) });
  return <div>
    <p>Al compimento dei 18 anni le deleghe dei genitori vanno riconfermate dallo studente. Lo studente lo fa dal portale, in «I miei dati».</p>
    <div className="controls" style={{ gap: 8 }}><Btn kind="sm" onClick={() => act(run(true))}>Controlla</Btn><Btn kind="sm" onClick={() => act(run(false))}>Avvia le riconferme</Btn></div>
    {rep && <dl className="facts" style={{ marginTop: 12 }}>{Object.entries(MAJ).filter(([k]) => k in rep).map(([k, label]) => { const v = rep[k]; return <div key={k}><dt>{label}</dt><dd>{Array.isArray(v) ? v.length : String(v ?? "—")}</dd></div>; })}{rep.dry_run ? <div><dt>Modalità</dt><dd>Solo verifica</dd></div> : null}</dl>}
  </div>;
}

const TABS = [["richieste", "Richieste"], ["export", "Export"], ["conservazione", "Conservazione"], ["registro", "Registro"], ["maggiore", "Maggiore età"]] as [string, string][];
export default function Privacy() {
  const toast = useToast();
  const [tab, setTab] = useState(new URLSearchParams(location.hash.split("?")[1] || "").get("tab") || "richieste");
  const [act, setAct] = useState<Act | null>(null);
  return <section className="module" aria-labelledby="h-privacy">
    <PageHead id="h-privacy" title="Privacy" />
    <div className="controls"><SegCtl label="Sezione" value={tab} onChange={setTab} options={TABS} /></div>
    <div key={tab} style={{ marginTop: 14 }}>
      {tab === "richieste" && <Richieste act={setAct} />}
      {tab === "export" && <Export act={setAct} />}
      {tab === "conservazione" && <Conservazione act={setAct} />}
      {tab === "registro" && <Registro />}
      {tab === "maggiore" && <Maggiore act={setAct} />}
    </div>
    <ActModal act={act} onClose={() => setAct(null)} onDone={(m) => { setAct(null); toast(m); }} />
  </section>;
}
