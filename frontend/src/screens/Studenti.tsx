import type { Tone } from "../messages";
import { useMemo, useState } from "react";
import { plural, WD_LONG } from "../format";
import { Avatar, Btn, Empty, Icon, PageHead, Skeleton, State, Tag, Tech } from "../ui/core";
import { SegCtl } from "../ui/controls";
import { Sheet } from "../ui/layers";
import { go, setQuery, useRoute } from "../ui/route";
import { useData } from "../app/data";

type F = "tutti" | "richieste" | "mancanti";
export default function Studenti() {
  const d = useData(), r = useRoute();
  const f = (r.q.get("f") as F) || "tutti", q = r.q.get("q") || "", open = r.q.get("s");
  const rows = useMemo(() => d.students.map((s) => {
    const rules = d.rules.filter((x) => x.student === s.id && x.status !== "REVOKED");
    const req = d.requests.filter((x) => x.student === s.id || x.participant_ids?.includes(s.id));
    const ok = rules.some((x) => x.status === "APPROVED"), draft = rules.some((x) => x.status === "DRAFT");
    return { s, rules, req, status: (ok ? ["Disponibilità approvata", "green"] : draft ? ["Disponibilità da approvare", "amber"] : ["Disponibilità mancante", "plain"]) as [string, Tone] };
  }), [d.students, d.rules, d.requests]);
  const shown = rows.filter((x) => (f === "tutti" || (f === "richieste" ? x.req.length > 0 : x.rules.length === 0)) && (!q || (x.s.display_name + " " + x.s.level).toLowerCase().includes(q.toLowerCase())))
    .sort((a, b) => a.s.display_name.localeCompare(b.s.display_name, "it"));
  const sel = rows.find((x) => x.s.id === open);
  const close = () => setQuery((x) => x.delete("s"));
  return <section className="module planner" aria-labelledby="h-st">
    <PageHead id="h-st" title="Studenti" lead={d.loaded ? `${plural(d.students.length, "studente visibile", "studenti visibili")}.${d.center ? "" : " Vedi solo gli studenti a cui il centro ti ha collegato."}` : "Carico gli studenti…"} />
    <div className="toolbar" style={{ marginBottom: 12 }}>
      <label className="field-search"><Icon n="search" /><span className="sr">Cerca studenti</span><input type="search" placeholder="Cerca per nome o livello…" value={q} autoComplete="off" spellCheck={false} onChange={(e) => setQuery((x) => (e.target.value ? x.set("q", e.target.value) : x.delete("q")))} /></label>
      <SegCtl label="Mostra" value={f} options={[["tutti", "Tutti"], ["richieste", "Con richieste"], ["mancanti", "Senza disponibilità"]]} onChange={(v) => setQuery((x) => (v === "tutti" ? x.delete("f") : x.set("f", v)))} />
    </div>
    <div className="list-wrap">{!d.loaded ? <Skeleton /> : shown.length ? <table className="list">
      <thead><tr><th scope="col">Nome</th><th scope="col" className="hide-m">Disponibilità</th><th scope="col" className="hide-m">Richieste</th><th scope="col">Stato</th></tr></thead>
      <tbody>{shown.map((x) => <tr key={x.s.id} className="row" tabIndex={0} aria-label={`Apri la scheda di ${x.s.display_name}`} onClick={() => setQuery((p) => p.set("s", x.s.id))} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); setQuery((p) => p.set("s", x.s.id)); } }}>
        <td><span className="who"><Avatar name={x.s.display_name} k={x.s.id} /><span><b>{x.s.display_name}</b><small className="muted">{x.s.level || "Livello non indicato"}</small></span></span></td>
        <td className="hide-m num">{x.rules.length ? plural(x.rules.length, "fascia", "fasce") : <span className="muted">Nessuna</span>}</td>
        <td className="hide-m num">{x.req.length ? plural(x.req.length, "richiesta", "richieste") : <span className="muted">Nessuna</span>}</td>
        <td><Tag tone={x.status[1]}>{x.status[0]}</Tag></td>
      </tr>)}</tbody></table>
      : d.students.length ? <Empty title={q ? `Nessuno studente corrisponde a “${q}”` : "Nessuno studente in questo filtro"}>Prova con un altro nome o mostra tutti.</Empty>
        : <Empty title="Nessuno studente visibile">{d.center ? "Aggiungi famiglie e studenti dalla scheda Famiglie." : "Il centro non ha ancora collegato studenti al tuo account."}</Empty>}</div>
    <Sheet open={!!sel} onClose={close} labelledBy="sheet-st">
      {sel && <><div className="sheet-body">
        <div className="sheet-top"><div className="kind"><Tag tone="blue">Studente</Tag><Tag tone={sel.status[1]}>{sel.status[0]}</Tag></div><button className="circle sm raised" aria-label="Chiudi" onClick={close}><Icon n="x" /></button></div>
        <div className="sheet-id"><Avatar name={sel.s.display_name} k={sel.s.id} size={56} /><div><h2 id="sheet-st">{sel.s.display_name}</h2><p className="muted">{sel.s.level || "Livello non indicato"}</p></div></div>
        <h3>Disponibilità settimanali</h3>
        {sel.rules.length ? <div className="mini-list">{sel.rules.map((x) => <div key={x.id} className="mini"><span><b>{WD_LONG[x.weekday]}</b><small>{x.start_time.slice(0, 5)}–{x.end_time.slice(0, 5)}</small></span><State s={x.status} /></div>)}</div> : <p className="muted">Nessuna fascia dichiarata. Senza disponibilità lo studente non viene pianificato.</p>}
        <h3>Richieste didattiche</h3>
        {sel.req.length ? <div className="mini-list">{sel.req.map((x) => <div key={x.id} className="mini"><span><b>{x.subject_name}</b><small>{x.sessions_per_week} × {x.duration_minutes} min a settimana</small></span><Tag tone={x.target_type === "GROUP" ? "violet" : "blue"}>{x.target_type === "GROUP" ? "Gruppo" : "Individuale"}</Tag></div>)}</div> : <p className="muted">Nessuna richiesta registrata.</p>}
        <Tech><dl className="facts"><dt>ID</dt><dd><code>{sel.s.id}</code></dd></dl></Tech>
      </div>
      <div className="sheet-foot"><Btn kind="primary" isle="plus" onClick={() => go("impegni", { nuova: "1", chi: "student:" + sel.s.id })}>Aggiungi impegno</Btn></div></>}
    </Sheet>
  </section>;
}
