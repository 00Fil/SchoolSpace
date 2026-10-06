import { useEffect, useState } from "react";
import { plural, todayRome } from "../format";
import { human } from "../messages";
import { Avatar, Btn, Empty, Icon, PageHead, Skeleton, Tag } from "../ui/core";
import { SegCtl } from "../ui/controls";
import { useToast } from "../ui/layers";
import { go, setQuery, useRoute } from "../ui/route";
import { useData } from "../app/data";
import { openReview, reviewIfNeeded } from "../app/Shell";
import { ApproveModal, kindGroup, KindTag, modeText, needsTutor, RequestModal, Req, review, StatusTag, tutorText, whenText } from "./requestForms";

/** Richieste didattiche. Centro: tutte, con approvazione e vincoli. Famiglie: le proprie, con «Chiedi delle lezioni».
 *  Due tipi: singola (giorno o settimana) e ricorrente (N lezioni a settimana con lo stesso tutor). */
export default function Richieste() {
  const d = useData(), r = useRoute(), toast = useToast();
  const f = r.q.get("f") || "tutte", t = r.q.get("t") || "tutti", q = r.q.get("q") || "";
  const [edit, setEdit] = useState<Req | null | undefined>(undefined), [approving, setApproving] = useState<Req | null>(null);
  const all = d.requests as Req[], canAsk = d.center || d.me.roles.includes("GUARDIAN");
  // «Chiedi delle lezioni» dalla home della famiglia o da altre schermate: ?nuova=1
  useEffect(() => { if (canAsk && r.q.get("nuova") === "1") { setEdit(null); setQuery((x) => x.delete("nuova")); } }, [r.q.get("nuova")]); // eslint-disable-line
  const rank = (x: Req) => (x.status === "PENDING" ? 0 : x.planning_state === "REVIEW" ? 1 : 2);
  const name = (x: Req) => x.student_name || d.students.find((s) => s.id === x.student)?.display_name || "Studente autorizzato";
  const today = todayRome(), current = (x: Req) => !x.period_end || x.period_end >= today;
  const rows = all.filter((x) => (f === "tutte" ? x.status !== "WITHDRAWN" : f === "attesa" ? x.status === "PENDING" : f === "verifica" ? x.status === "APPROVED" && x.planning_state === "REVIEW" : f === "gruppo" ? x.target_type === "GROUP" : f === "chiuse" ? x.status === "REJECTED" || x.status === "WITHDRAWN" || !current(x) : x.status === "APPROVED" && current(x))
    && (t === "tutti" || kindGroup(x) === t)
    && (!q || (x.subject_name + " " + name(x)).toLowerCase().includes(q.toLowerCase())))
    .sort((a, b) => rank(a) - rank(b) || String(a.period_start || "").localeCompare(String(b.period_start || "")));
  const toReview = all.filter((x) => x.status === "APPROVED" && x.planning_state === "REVIEW");
  const waiting = all.filter((x) => x.status === "PENDING"), live = all.filter((x) => x.status === "APPROVED" && current(x));
  const singles = live.filter((x) => x.kind === "SINGLE").length, recurring = live.filter((x) => kindGroup(x) === "RECURRING" && !x.derived);
  const weekly = recurring.reduce((a, x) => a + x.sessions_per_week, 0);
  async function act(x: Req, a: "approve" | "reject" | "withdraw") {
    if (a === "approve" && needsTutor(x)) { setApproving(x); return; }
    try {
      const r = await review(x.id, a); await d.refresh();
      if (!(a === "approve" && reviewIfNeeded(r))) toast(a === "approve" ? "Richiesta approvata." : a === "reject" ? "Richiesta rifiutata." : "Richiesta ritirata.");
    }
    catch (e) { toast(human(e).text); }
  }
  const kinds: [string, string][] = [["tutti", "Tutti i tipi"], ["SINGLE", "Singole"], ["RECURRING", "Ricorrenti"]];
  return <section className="module planner" aria-labelledby="h-rq">
    <PageHead id="h-rq" title={d.center ? "Richieste didattiche" : "Richieste di lezioni"}>
      {canAsk && <Btn kind="primary" isle="plus" onClick={() => setEdit(null)}>{d.center ? "Nuova richiesta" : "Chiedi delle lezioni"}</Btn>}
    </PageHead>
    <div className="stats">
      <div className="stat"><small>{d.center ? "Da approvare" : "In attesa del centro"}</small><b>{waiting.length}</b>{d.center && waiting.length > 0 && <div className="note"><button type="button" className="link-btn" onClick={() => setQuery((x) => x.set("f", "attesa"))}>Mostra solo queste</button></div>}</div>
      {d.center && <div className="stat"><small>Da verificare</small><b>{toReview.length}</b><div className="note">{toReview.length ? <button type="button" className="link-btn" onClick={() => setQuery((x) => x.set("f", "verifica"))}>Lezioni inserite dal motore da confermare</button> : "Nessuna in attesa"}</div></div>}
      <div className="stat"><small>Lezioni singole in programma</small><b>{singles}</b><div className="note">Approvate, da oggi in poi</div></div>
      <div className="stat"><small>Richieste ricorrenti attive</small><b>{recurring.length}</b><div className="note">{recurring.length ? plural(weekly, "lezione a settimana", "lezioni a settimana") : "Nessuna in corso"}</div></div>
    </div>
    <div className="toolbar rq-toolbar" style={{ marginBottom: 12 }}>
      <label className="field-search"><Icon n="search" /><span className="sr">Cerca richieste</span><input type="search" placeholder="Cerca materia o studente…" value={q} onChange={(e) => setQuery((x) => (e.target.value ? x.set("q", e.target.value) : x.delete("q")))} /></label>
      <SegCtl label="Stato" value={f} options={[["tutte", "Tutte"], ["attesa", `Da approvare (${waiting.length})`], ...(d.center ? [["verifica", `Da verificare (${toReview.length})`] as [string, string]] : []), ["approvate", "In corso"], ["chiuse", "Chiuse"], ...(d.center ? [["gruppo", "Di gruppo"] as [string, string]] : [])]} onChange={(v) => setQuery((x) => (v === "tutte" ? x.delete("f") : x.set("f", v)))} />
      <SegCtl label="Tipo" value={t} options={kinds} onChange={(v) => setQuery((x) => (v === "tutti" ? x.delete("t") : x.set("t", v)))} />
    </div>
    <div className="list-wrap">{!d.loaded ? <Skeleton /> : rows.length ? <table className="list">
      <thead><tr><th scope="col">Richiesta</th><th scope="col">Per chi</th><th scope="col" className="hide-m">Quando e con chi</th><th scope="col">Stato</th><th scope="col"><span className="sr">Azioni</span></th></tr></thead>
      <tbody>{rows.map((x) => <tr key={x.id}>
        <td><b style={{ fontWeight: 500 }}>{x.subject_name}</b><span className="block rq-tags"><KindTag r={x} />{x.target_type === "GROUP" && <Tag tone="violet">Gruppo</Tag>}</span></td>
        <td>{x.target_type === "GROUP" ? <span className="block"><b style={{ fontWeight: 500 }}>{x.group_label || "Gruppo"}</b><small className="muted block">{x.participant_names?.length ? x.participant_names.join(", ") : plural(x.participant_ids?.length || 0, "partecipante", "partecipanti")}</small></span> : <span className="who"><Avatar name={name(x)} k={x.student || ""} /><b>{name(x)}</b></span>}</td>
        <td className="hide-m">{whenText(x)}<small className="muted block">{x.duration_minutes} min · {modeText(x.mode)} · {tutorText(x)}</small></td>
        <td><StatusTag s={x.status} p={x.planning_state} />{d.center && x.derived && <small className="muted block">Da percorso parentale</small>}{x.review_note && <small className="muted block">{x.review_note}</small>}</td>
        <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
          {d.center && x.status === "PENDING" && <><Btn kind="sm ghost" onClick={() => act(x, "reject")}>Rifiuta</Btn> <Btn kind="sm ghost" onClick={() => setEdit(x)}>Modifica</Btn> <Btn kind="sm primary" onClick={() => act(x, "approve")}>{needsTutor(x) ? "Scegli tutor e approva" : "Approva"}</Btn></>}
          {d.center && x.status === "APPROVED" && x.planning_state === "REVIEW" && <><Btn kind="sm primary" onClick={() => openReview(x.id)}>Verifica lezioni</Btn> </>}
          {d.center && x.status !== "PENDING" && !x.derived && x.status !== "WITHDRAWN" && <Btn kind="sm ghost" onClick={() => setEdit(x)}>Modifica</Btn>}
          {!d.center && x.own && x.status === "PENDING" && <Btn kind="sm ghost" onClick={() => act(x, "withdraw")}>Ritira</Btn>}
        </td>
      </tr>)}</tbody></table>
      : <Empty title={all.length ? "Nessuna richiesta in questo filtro" : "Nessuna richiesta registrata"} />}</div>
    <RequestModal open={edit !== undefined} edit={edit || null} onClose={() => setEdit(undefined)} onSaved={async (r) => { setEdit(undefined); await d.refresh(); if (!reviewIfNeeded(r)) toast(d.center ? "Richiesta salvata." : "Richiesta inviata al centro."); }} />
    <ApproveModal req={approving} onClose={() => setApproving(null)} onDone={async (r) => { setApproving(null); await d.refresh(); if (!reviewIfNeeded(r)) toast("Richiesta approvata."); }} />
  </section>;
}
