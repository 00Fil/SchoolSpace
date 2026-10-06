/** Materie (v0.9.6): pagina dedicata del centro. Per ogni materia: tutor che la
 *  insegnano (livelli e modalità), richieste in corso e percorsi parentali che la
 *  usano; creazione, modifica, archiviazione ed eliminazione delle sole materie mai usate. */
import { useCallback, useEffect, useState } from "react";
import { api } from "../api";
import { plural } from "../format";
import { Avatar, Btn, Empty, Icon, Notice, PageHead, Skeleton, Tag } from "../ui/core";
import { Field, Input, SegCtl } from "../ui/controls";
import { GuardFoot, Modal, useDirtyGuard, useToast } from "../ui/layers";
import { ErrorState } from "../ui/states";
import { go, setQuery, useRoute } from "../ui/route";
import { send, writeError } from "./registry";

type SubjectTutor = { id: string; display_name: string; levels: string[]; modes: string[]; pending: boolean; expired: boolean };
export type SubjectRow = { id: string; name: string; description: string; active: boolean; version: number; tutors: SubjectTutor[]; requests: { pending: number; approved: number; series: number; single: number }; paths: number; deletable: boolean };
const MODE: Record<string, string> = { IN_PERSON: "in presenza", ONLINE: "online" };

export default function Materie() {
  const toast = useToast(), r = useRoute();
  const f = r.q.get("f") || "attive", q = r.q.get("q") || "";
  const [rows, setRows] = useState<SubjectRow[] | null>(null), [err, setErr] = useState<unknown>(null);
  const [form, setForm] = useState<SubjectRow | null | undefined>(undefined), [del, setDel] = useState<SubjectRow | null>(null);
  const load = useCallback(() => api<{ results: SubjectRow[] }>("/subjects/overview/").then((x) => { setRows(x.results); setErr(null); }).catch(setErr), []);
  useEffect(() => { load(); }, [load]);
  async function toggle(s: SubjectRow) {
    try { await send("PATCH", `/subjects/${s.id}/`, { active: !s.active }); toast(s.active ? `${s.name} archiviata: non si propone più nelle nuove richieste.` : `${s.name} di nuovo attiva.`); await load(); }
    catch (e) { toast(writeError(e)); }
  }
  async function remove() {
    try { await send("DELETE", `/subjects/${del!.id}/`); toast(`Materia eliminata: ${del!.name}.`); setDel(null); await load(); }
    catch (e) { toast(writeError(e)); setDel(null); await load(); }
  }
  if (err && !rows) return <section className="module"><ErrorState error={err} onRetry={load} /></section>;
  const all = rows || [];
  const shown = all.filter((s) => (f === "tutte" || (f === "attive") === s.active) && (!q || (s.name + " " + s.description).toLowerCase().includes(q.toLowerCase())));
  const noTutor = all.filter((s) => s.active && !s.tutors.some((t) => t.levels.length)).length;
  return <section className="module" aria-labelledby="h-sj">
    <PageHead id="h-sj" title="Materie">
      <Btn kind="primary" isle="plus" onClick={() => setForm(null)}>Nuova materia</Btn>
    </PageHead>
    <div className="stats">
      <div className="stat"><small>Materie attive</small><b>{all.filter((s) => s.active).length}</b></div>
      <div className="stat"><small>Senza tutor</small><b>{noTutor}</b><div className="note">{noTutor ? "Le famiglie non possono richiederle" : "Tutte coperte da almeno un tutor"}</div></div>
      <div className="stat"><small>Richieste da approvare</small><b>{all.reduce((a, s) => a + s.requests.pending, 0)}</b>{all.some((s) => s.requests.pending) && <div className="note"><button type="button" className="link-btn" onClick={() => go("richieste", { f: "attesa" })}>Apri le richieste</button></div>}</div>
    </div>
    <div className="toolbar" style={{ marginBottom: 14 }}>
      <label className="field-search"><Icon n="search" /><span className="sr">Cerca materie</span><input type="search" placeholder="Cerca materia…" value={q} onChange={(e) => setQuery((x) => (e.target.value ? x.set("q", e.target.value) : x.delete("q")))} /></label>
      <SegCtl label="Filtro" value={f} options={[["attive", "Attive"], ["archiviate", "Archiviate"], ["tutte", "Tutte"]]} onChange={(v) => setQuery((x) => (v === "attive" ? x.delete("f") : x.set("f", v)))} />
    </div>
    {!rows ? <Skeleton /> : shown.length ? <div className="sj-grid" role="list">{shown.map((s) => {
      const able = s.tutors.filter((t) => t.levels.length), live = s.requests.approved + s.requests.pending;
      return <article key={s.id} className={"sj-card" + (s.active ? "" : " off")} role="listitem" aria-labelledby={"sj-" + s.id}>
        <div className="sj-head"><div style={{ minWidth: 0 }}><h3 id={"sj-" + s.id}>{s.name}</h3>{s.description && <p>{s.description}</p>}</div>
          {!s.active ? <Tag tone="plain">Archiviata</Tag> : able.length ? <Tag tone="green">{plural(able.length, "tutor", "tutor")}</Tag> : <Tag tone="amber">Nessun tutor</Tag>}</div>
        <div className="sj-nums">
          <Tag tone={live ? "blue" : "plain"}>{live ? plural(live, "richiesta in corso", "richieste in corso") : "Nessuna richiesta"}</Tag>
          {s.requests.pending > 0 && <Tag tone="amber">{plural(s.requests.pending, "da approvare", "da approvare")}</Tag>}
          {s.requests.series > 0 && <Tag tone="violet">{plural(s.requests.series, "ricorrente", "ricorrenti")}</Tag>}
          {s.paths > 0 && <Tag tone="plain">{plural(s.paths, "percorso parentale", "percorsi parentali")}</Tag>}
        </div>
        {s.tutors.length ? <ul className="sj-tutors" aria-label={`Tutor di ${s.name}`}>{s.tutors.map((t) => <li key={t.id}><Avatar name={t.display_name} k={t.id} size={30} />
          <span className="sj-who"><b style={{ fontWeight: 500 }}>{t.display_name}</b><small>{t.levels.length ? `${t.levels.join(", ")} · ${t.modes.map((m) => MODE[m] || m).join(" e ")}` : t.pending ? "Competenza da approvare" : "Competenza scaduta"}</small></span>
          {!t.levels.length && <Tag tone={t.pending ? "amber" : "plain"}>{t.pending ? "Da approvare" : "Scaduta"}</Tag>}</li>)}</ul>
          : <p className="muted" style={{ margin: 0 }}>Nessun tutor registrato per questa materia.</p>}
        <div className="sj-act">
          <Btn kind="sm" onClick={() => setForm(s)}>Modifica</Btn>
          {live > 0 && <Btn kind="sm ghost" onClick={() => go("richieste", { q: s.name })}>Vedi richieste</Btn>}
          {s.active && !able.length && <Btn kind="sm ghost" icon="plus" onClick={() => go("tutor")}>Aggiungi competenza</Btn>}
          <Btn kind="sm ghost" onClick={() => toggle(s)}>{s.active ? "Archivia" : "Riattiva"}</Btn>
          {s.deletable && <Btn kind="sm ghost" onClick={() => setDel(s)}>Elimina</Btn>}
        </div>
      </article>;
    })}</div> : <Empty title={all.length ? "Nessuna materia in questo filtro" : "Nessuna materia registrata"} />}
    
    <SubjectForm edit={form} onClose={() => setForm(undefined)} onDone={async (m) => { setForm(undefined); toast(m); await load(); }} />
    <Modal open={!!del} onClose={() => setDel(null)} labelledBy="sj-del"><div className="modal-body">
      <h2 id="sj-del">Eliminare {del?.name}?</h2>
      <p className="lead">La materia non è mai stata usata da richieste, competenze o percorsi: sparisce definitivamente.</p>
    </div><div className="modal-foot"><button type="button" className="pill-btn ghost" onClick={() => setDel(null)}>Annulla</button><Btn kind="primary" onClick={remove}>Elimina</Btn></div></Modal>
  </section>;
}

/** Nuova materia o modifica di nome e descrizione. */
export function SubjectForm({ edit, onClose, onDone }: { edit: SubjectRow | null | undefined; onClose: () => void; onDone: (msg: string) => void }) {
  const open = edit !== undefined;
  const [name, setName] = useState(""), [desc, setDesc] = useState(""), [err, setErr] = useState(""), [busy, setBusy] = useState(false), [tried, setTried] = useState(false);
  useEffect(() => { if (!open) return; setName(edit?.name || ""); setDesc(edit?.description || ""); setErr(""); setTried(false); g.reset(); }, [open, edit]); // eslint-disable-line
  const g = useDirtyGuard(open && (name !== (edit?.name || "") || desc !== (edit?.description || "")));
  async function save(e: React.FormEvent) {
    e.preventDefault(); setTried(true); setErr("");
    if (!name.trim()) return;
    setBusy(true);
    try {
      const body = { name: name.trim(), description: desc.trim() };
      if (edit) await send("PATCH", `/subjects/${edit.id}/`, body); else await send("POST", "/subjects/", body);
      g.allow(); onDone(edit ? `Materia aggiornata: ${body.name}.` : `Materia aggiunta: ${body.name}.`);
    } catch (x) { setErr(writeError(x)); } finally { setBusy(false); }
  }
  return <Modal open={open} onClose={onClose} guard={g.guard} labelledBy="sj-form"><form onSubmit={save} noValidate>
    <div className="modal-body">
      <h2 id="sj-form">{edit ? `Modifica ${edit.name}` : "Nuova materia"}</h2>
      
      <Field label="Nome" id="sj-name" error={tried && !name.trim() && "Scrivi il nome della materia."}><Input id="sj-name" maxLength={80} value={name} onChange={(e) => setName(e.target.value)} placeholder="Es. Matematica" /></Field>
      <Field label="Descrizione" optional id="sj-desc" hint="Es. programma, livelli seguiti o testi adottati."><Input id="sj-desc" maxLength={300} value={desc} onChange={(e) => setDesc(e.target.value)} /></Field>
      {err && <Notice kind="bad">{err}</Notice>}
    </div>
    {g.asking ? <GuardFoot onKeep={g.keep} onDiscard={() => { g.allow(); onClose(); }} />
      : <div className="modal-foot"><button type="button" className="pill-btn ghost" onClick={() => { if (g.guard()) onClose(); }}>Chiudi</button>
        <Btn type="submit" kind="primary" isle="check" disabled={busy}>{busy ? "Salvo…" : edit ? "Salva" : "Aggiungi materia"}</Btn></div>}
  </form></Modal>;
}
