/** v0.9.7 «Pianificazione»: calendario mensile in tre passi.
 *  1 Verifica i dati (orari, chiusure, richieste, impegni) · 2 Genera · 3 Rivedi e pubblica.
 *  Orari del centro e chiusure sono rigidi; gli impegni di famiglie e tutor si rispettano,
 *  con sforamenti fino alla tolleranza che vanno confermati dagli interessati. */
import { useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { dateLong, duration, monthYear, plural, rangeOf, rome, todayRome } from "../format";
import { human } from "../messages";
import { Btn, Empty, Notice, Skeleton, Tag } from "../ui/core";
import { Combo, ComboItem, Field } from "../ui/controls";
import { Modal, Sheet, useToast } from "../ui/layers";
import { go, setQuery, useRoute } from "../ui/route";
import { ErrorState } from "../ui/states";
import { BoardItem, Checklist, CheckItem, MonthBoard, MonthStepper, PlanSteps } from "../ui/planner";

type Conf = { id: string; party: "STUDENT" | "TUTOR"; who: string; minutes: number; labels: string[]; status: string; note: string };
export type PlanLesson = { id: string; request_id: string; kind: string; subject: string; tutor: { id: string; name: string }; students: { id: string; name: string }[]; start_at: string; end_at: string; mode: string; room: string | null; overflow_minutes: number; state: string; confirmations: Conf[] };
type Unplaced = { request_id: string; subject: string; who: string; kind: string; missing: number; reason: string; message: string; weeks?: string[] };
type Plan = { id: string; month: string; state: string; created_at: string; published_at: string | null; solver_status: string; stats: { requests: number; needed: number; placed: number; overflow: number; tolerance_minutes: number }; unplaced: Unplaced[]; lessons?: PlanLesson[] };
type Existing = { id: string; subject: string; tutor: string; students: string[]; start_at: string; end_at: string; mode: string };
type Ready = { items: CheckItem[]; can_generate: boolean; can_publish: boolean; publish_hint: string; tolerance_minutes: number };
type Month = { month: string; readiness: Ready; draft: Plan | null; published: Plan[]; follow_up: PlanLesson[]; existing: Existing[]; closed_days: Record<string, string> };

const nextMonth = () => { const t = todayRome(); const [y, m] = t.split("-").map(Number); return new Date(Date.UTC(y, m, 1)).toISOString().slice(0, 7); };
const KIND: Record<string, string> = { SINGLE: "Singola", SERIES: "Ricorrente", WEEKLY: "Settimanale" };
const CONF: Record<string, [string, string]> = { DRAFT: ["Da inviare", "plain"], PENDING: ["In attesa", "amber"], ACCEPTED: ["Accettata", "green"], REJECTED: ["Rifiutata", "red"] };
const GO: Record<string, [string, Record<string, string>?]> = { orari: ["apertura"], richieste: ["richieste"], aule: ["configurazione", { tab: "aule" }], impegni: ["impegni"] };

export default function PianoMensile() {
  const r = useRoute(), toast = useToast();
  const month = r.q.get("mese") || nextMonth();
  const [data, setData] = useState<Month | null>(null), [err, setErr] = useState<unknown>(null);
  const [busy, setBusy] = useState<"" | "gen" | "pub" | "del">(""), [msg, setMsg] = useState("");
  const [pick, setPick] = useState<PlanLesson | null>(null), [ask, setAsk] = useState(false);
  const [who, setWho] = useState<ComboItem | null>(null);
  const load = () => { setErr(null); api<Month>(`/planner/plans?month=${month}`).then(setData).catch(setErr); };
  useEffect(() => { setData(null); setWho(null); load(); }, [month]); // eslint-disable-line react-hooks/exhaustive-deps
  const plan = data?.draft || null;
  const step = !data ? 0 : plan ? 2 : data.published.length ? 3 : data.readiness.can_generate ? 1 : 0;
  async function generate() {
    setBusy("gen"); setMsg("");
    try { await api(`/planner/plans`, { method: "POST", body: JSON.stringify({ month }) }); load(); toast("Calendario generato: controllalo e pubblicalo"); }
    catch (x) { setMsg(human(x).text); } finally { setBusy(""); }
  }
  async function publish() {
    if (!plan) return;
    setBusy("pub"); setMsg("");
    try {
      const res = await api<{ published: number; awaiting: number; confirmations_sent: number }>(`/planner/plans/${plan.id}/publish`, { method: "POST", body: "{}" });
      setAsk(false); load();
      toast(`${plural(res.published, "lezione pubblicata", "lezioni pubblicate")}${res.awaiting ? `, ${plural(res.awaiting, "in attesa", "in attesa")} di conferma (${plural(res.confirmations_sent, "richiesta inviata", "richieste inviate")})` : ""}`);
    } catch (x) { setMsg(human(x).text); setAsk(false); } finally { setBusy(""); }
  }
  async function discard() {
    if (!plan) return;
    setBusy("del");
    try { await api(`/planner/plans/${plan.id}/discard`, { method: "POST", body: "{}" }); load(); toast("Bozza scartata"); } catch (x) { setMsg(human(x).text); } finally { setBusy(""); }
  }
  const lessons = plan?.lessons || [];
  const people = useMemo(() => {
    const m = new Map<string, ComboItem>();
    for (const l of lessons) { m.set("t:" + l.tutor.id, { id: "t:" + l.tutor.id, label: l.tutor.name, sub: "Tutor" }); for (const s of l.students) m.set("s:" + s.id, { id: "s:" + s.id, label: s.name, sub: "Studente" }); }
    return [...m.values()].sort((a, b) => a.label.localeCompare(b.label, "it"));
  }, [lessons]);
  const shown = lessons.filter((l) => !who || (who.id.startsWith("t:") ? l.tutor.id === who.id.slice(2) : l.students.some((s) => s.id === who.id.slice(2))));
  const items: BoardItem[] = [
    ...shown.map((l) => ({ id: l.id, date: rome(l.start_at).date, start: rangeOf(l.start_at, l.end_at).split("–")[0], title: `${l.subject} · ${l.students.map((s) => s.name.split(" ")[0]).join(", ")}`, sub: l.tutor.name, tone: l.overflow_minutes ? "amber" : l.mode === "ONLINE" ? "violet" : "blue", badge: l.overflow_minutes ? `+${l.overflow_minutes}′` : undefined })),
    ...(who ? [] : (data?.existing || []).map((e) => ({ id: "e" + e.id, date: rome(e.start_at).date, start: rangeOf(e.start_at, e.end_at).split("–")[0], title: `${e.subject} · ${e.students.join(", ")}`, sub: e.tutor, tone: "plain", muted: true }))),
  ];
  const hours = lessons.reduce((a, l) => a + (new Date(l.end_at).getTime() - new Date(l.start_at).getTime()) / 60000, 0);
  const overflow = lessons.filter((l) => l.overflow_minutes);
  const missing = (plan?.unplaced || []).reduce((a, u) => a + u.missing, 0);
  const coverage = plan?.stats.needed ? Math.round((plan.stats.placed / plan.stats.needed) * 100) : 100;
  const status: [string, string] = !data ? ["", "plain"] : plan ? ["Bozza da pubblicare", "amber"] : data.published.length ? ["Pubblicato", "green"] : ["Da generare", "plain"];
  const label = monthYear(month).toLowerCase();
  return <section className="module planner pm" aria-labelledby="h-pm">
    <header className="pm-head">
      <div className="pm-title">
        <h1 id="h-pm">Pianificazione</h1>
        <p>Calendario mensile delle lezioni. Orari del centro e chiusure sono vincoli rigidi; gli impegni di famiglie e tutor si rispettano, con sforamenti fino a {data?.readiness.tolerance_minutes ?? 30} minuti solo se gli interessati confermano.</p>
      </div>
      <div className="pm-month">
        <MonthStepper month={month} onChange={(m) => setQuery((q) => q.set("mese", m))} />
        {status[0] && <Tag tone={status[1] as "plain"}>{status[0]}</Tag>}
      </div>
    </header>
    <PlanSteps current={step} steps={[{ title: "Verifica i dati", sub: "Orari, richieste e impegni del mese" }, { title: "Genera", sub: "Il motore propone il calendario" }, { title: "Rivedi e pubblica", sub: "Famiglie e tutor ricevono la notifica" }]} />
    {err ? <ErrorState error={err} onRetry={load} /> : !data ? <Skeleton rows={6} /> : <>
      {msg && <Notice kind="bad">{msg}</Notice>}

      {!plan && <div className="pm-grid">
        <section className="pm-panel" aria-labelledby="pm-s1">
          <header className="pm-ph"><div><span className="pm-step">Passo 1</span><h2 id="pm-s1">Dati di {label}</h2></div>
            <span className="pm-count">{data.readiness.items.filter((i) => i.ok).length} di {data.readiness.items.length} completi</span></header>
          <p className="pm-note">Le voci obbligatorie servono per generare; quelle consigliate migliorano il risultato.</p>
          <Checklist items={data.readiness.items} onGo={(k) => { const g = GO[k]; if (g) go(g[0], g[1]); }} />
        </section>
        <section className="pm-panel" aria-labelledby="pm-s2">
          <header className="pm-ph"><div><span className="pm-step">Passo 2</span><h2 id="pm-s2">Genera il calendario</h2></div></header>
          <p className="pm-note">Il motore sceglie giorno, ora, tutor e aula di ogni lezione rispettando queste regole, in ordine di importanza.</p>
          <table className="pm-table pm-rules">
            <thead><tr><th scope="col">Regola</th><th scope="col">Come viene applicata</th></tr></thead>
            <tbody>
              <tr><th scope="row">Orari e chiusure del centro</th><td>Sempre rispettati</td></tr>
              <tr><th scope="row">Impegni di studenti e tutor</th><td>Rispettati; sforamento massimo {data.readiness.tolerance_minutes} minuti, solo con conferma</td></tr>
              <tr><th scope="row">Stesso tutor</th><td>Per tutte le lezioni di una richiesta; stesso giorno e ora ogni settimana quando possibile</td></tr>
              <tr><th scope="row">Giornate compatte</th><td>Meno buchi tra una lezione e l’altra</td></tr>
            </tbody>
          </table>
          <div className="pm-cta">
            <Btn kind="primary" disabled={!data.readiness.can_generate || busy === "gen"} onClick={generate}>{busy === "gen" ? "Calcolo in corso…" : `Genera ${label}`}</Btn>
            <small>{busy === "gen" ? "Ci vogliono circa 15 secondi." : !data.readiness.can_generate ? "Completa prima le voci obbligatorie del passo 1." : data.published.length ? "Il mese è già pubblicato: una nuova generazione aggiunge solo le lezioni mancanti." : "Il risultato è una bozza: nessuno riceve notifiche finché non pubblichi."}</small>
          </div>
        </section>
      </div>}

      {plan && <>
        <section className="pm-panel" aria-labelledby="pm-s3">
          <header className="pm-ph"><div><span className="pm-step">Passo 3</span><h2 id="pm-s3">Rivedi {label}</h2><p>Bozza generata il {dateLong(rome(plan.created_at).date)}. Seleziona una lezione per i dettagli.</p></div>
            <div className="pm-actions">
              <Btn kind="ghost" onClick={discard} disabled={!!busy}>Scarta bozza</Btn>
              <Btn onClick={generate} disabled={!!busy}>{busy === "gen" ? "Calcolo…" : "Rigenera"}</Btn>
              <Btn kind="primary" disabled={!lessons.length || !data.readiness.can_publish || !!busy} onClick={() => setAsk(true)}>Pubblica il mese</Btn>
            </div></header>
          {!data.readiness.can_publish && <Notice kind="warn">{data.readiness.publish_hint}</Notice>}
          <dl className="pm-kpis">
            <div><dt>Lezioni proposte</dt><dd>{lessons.length}</dd><small>{duration(hours)} in totale</small></div>
            <div><dt>Copertura</dt><dd>{coverage}%</dd><small>{plan.stats.placed} su {plan.stats.needed} richieste</small></div>
            <div className={overflow.length ? "warn" : ""}><dt>Da confermare</dt><dd>{overflow.length}</dd><small>{overflow.length ? `sforamenti fino a ${plan.stats.tolerance_minutes} min` : "nessuno sforamento"}</small></div>
            <div className={missing ? "bad" : ""}><dt>Non collocate</dt><dd>{missing}</dd><small>{missing ? "motivi nella tabella sotto" : "tutto collocato"}</small></div>
          </dl>
          <div className="pm-tools">
            <div className="pm-filter"><Field label="Persona" id="pm-who"><Combo id="pm-who" value={who} items={people} placeholder="Tutti i tutor e studenti" onPick={setWho} /></Field></div>
            <div className="pm-legend" aria-label="Legenda"><span><i className="lg blue" />In sede</span><span><i className="lg violet" />Online</span><span><i className="lg amber" />Da confermare</span><span><i className="lg plain" />Già pubblicate</span></div>
          </div>
          <MonthBoard month={month} items={items} closed={(d) => data.closed_days[d] || null} onPick={(it) => setPick(lessons.find((l) => l.id === it.id) || null)} />
        </section>
        {plan.unplaced.length > 0 && <section className="pm-panel" aria-labelledby="pm-un">
          <header className="pm-ph"><div><h2 id="pm-un">Lezioni non collocate</h2><p>Correggi il dato indicato e rigenera: le lezioni già proposte restano il più possibile stabili.</p></div><span className="pm-count">{missing} mancanti</span></header>
          <table className="pm-table">
            <thead><tr><th scope="col">Richiesta</th><th scope="col">Tipo</th><th scope="col" className="num">Mancanti</th><th scope="col">Motivo</th><th scope="col"><span className="sr">Azione</span></th></tr></thead>
            <tbody>{plan.unplaced.map((u) => <tr key={u.request_id}>
              <th scope="row">{u.subject}<small>{u.who}</small></th>
              <td>{KIND[u.kind] || u.kind}{u.weeks?.length ? <small>settimane del {u.weeks.map((w) => dateLong(w)).join(", ")}</small> : null}</td>
              <td className="num">{u.missing}</td>
              <td>{u.message}</td>
              <td className="act"><Btn kind="sm" onClick={() => go("richieste", { q: u.who })}>Apri richiesta</Btn></td>
            </tr>)}</tbody>
          </table>
        </section>}
      </>}

      {!plan && data.published.length > 0 && <section className="pm-panel" aria-labelledby="pm-pubd">
        <header className="pm-ph"><div><h2 id="pm-pubd">Calendario pubblicato</h2><p>{plural(data.existing.length, "lezione", "lezioni")} in calendario{data.follow_up.length ? `, ${plural(data.follow_up.filter((l) => l.state === "AWAITING").length, "in attesa", "in attesa")} di conferma` : ""}. Seleziona un giorno per aprirlo nell’agenda.</p></div>
          <div className="pm-legend" aria-label="Legenda"><span><i className="lg blue" />In sede</span><span><i className="lg violet" />Online</span><span><i className="lg amber" />In attesa di conferma</span></div></header>
        <MonthBoard month={month} closed={(d) => data.closed_days[d] || null} onPick={(it) => { const l = data.follow_up.find((x) => x.id === it.id); if (l) setPick(l); else go("agenda", { d: it.date }); }} items={[
          ...data.existing.map((e) => ({ id: "e" + e.id, date: rome(e.start_at).date, start: rangeOf(e.start_at, e.end_at).split("–")[0], title: `${e.subject} · ${e.students.map((n) => n.split(" ")[0]).join(", ")}`, sub: e.tutor, tone: e.mode === "ONLINE" ? "violet" : "blue" })),
          ...data.follow_up.filter((l) => l.state === "AWAITING").map((l) => ({ id: l.id, date: rome(l.start_at).date, start: rangeOf(l.start_at, l.end_at).split("–")[0], title: `${l.subject} · ${l.students.map((x) => x.name.split(" ")[0]).join(", ")}`, sub: l.tutor.name, tone: "amber", badge: "?" })),
        ]} />
      </section>}
      {data.follow_up.length > 0 && <FollowUp rows={data.follow_up} onPick={setPick} />}
    </>}
    <Sheet open={!!pick} onClose={() => setPick(null)} label="Dettagli lezione">{pick && <LessonDetail l={pick} onRemove={pick.state === "PROPOSED" && plan ? async () => { try { await api(`/planner/lessons/${pick.id}/remove`, { method: "POST", body: "{}" }); setPick(null); load(); toast("Lezione tolta dalla bozza"); } catch (x) { setMsg(human(x).text); setPick(null); } } : undefined} />}</Sheet>
    <Modal open={ask} onClose={() => setAsk(false)} labelledBy="pm-pub"><div className="modal-body">
      <h2 id="pm-pub">Pubblicare {label}?</h2>
      <p className="lead">Dopo la pubblicazione le lezioni sono visibili a famiglie e tutor.</p>
      <table className="pm-table pm-sum"><tbody>
        <tr><td className="num">{lessons.length - overflow.length}</td><td><b>In calendario subito</b><small>Tutor e famiglie ricevono la notifica.</small></td></tr>
        {overflow.length > 0 && <tr><td className="num">{overflow.length}</td><td><b>In attesa di conferma</b><small>Sforano un impegno: restano riservate e chiediamo conferma agli interessati via email e notifica.</small></td></tr>}
        {missing > 0 && <tr><td className="num">{missing}</td><td><b>Non collocate</b><small>Restano da pianificare.</small></td></tr>}
      </tbody></table></div>
      <div className="modal-foot"><Btn kind="ghost" onClick={() => setAsk(false)}>Annulla</Btn><Btn kind="primary" disabled={busy === "pub"} onClick={publish}>{busy === "pub" ? "Pubblicazione…" : "Pubblica"}</Btn></div>
    </Modal>
  </section>;
}

function LessonDetail({ l, onRemove }: { l: PlanLesson; onRemove?: () => void }) {
  return <div className="sheet-body pm-detail">
    <Tag tone={l.overflow_minutes ? "amber" : "blue"}>{l.state === "AWAITING" ? "In attesa di conferma" : l.state === "REJECTED" ? "Rifiutata" : l.overflow_minutes ? `Sfora di ${l.overflow_minutes} min` : "Nessun conflitto"}</Tag>
    <h2>{l.subject}</h2>
    <dl className="pm-dl">
      <dt>Quando</dt><dd>{dateLong(rome(l.start_at).date)}, {rangeOf(l.start_at, l.end_at)}</dd>
      <dt>Studenti</dt><dd>{l.students.map((s) => s.name).join(", ")}</dd>
      <dt>Tutor</dt><dd>{l.tutor.name}</dd>
      <dt>Dove</dt><dd>{l.mode === "ONLINE" ? "Online" : l.room ? `In sede, ${l.room}` : "In sede"}</dd>
      <dt>Richiesta</dt><dd>{KIND[l.kind] || l.kind}</dd>
    </dl>
    {l.confirmations.length > 0 && <><h3>Conferme</h3><ul className="pm-conf">{l.confirmations.map((c) => <li key={c.id}>
      <div><b>{c.who}</b><small>{c.party === "TUTOR" ? "Tutor" : "Famiglia"} · sfora di {c.minutes} min{c.labels.length ? ` «${c.labels.join(", ")}»` : ""}</small>{c.note && <small>“{c.note}”</small>}</div>
      <Tag tone={CONF[c.status]?.[1] as "plain"}>{CONF[c.status]?.[0] || c.status}</Tag></li>)}</ul></>}
    {onRemove && <div style={{ marginTop: 24 }}><Btn kind="ghost" onClick={onRemove}>Togli dalla bozza</Btn><p className="fine">La lezione non verrà pubblicata; potrai rigenerare il mese o inserirla a mano dall’agenda.</p></div>}
  </div>;
}

function FollowUp({ rows, onPick }: { rows: PlanLesson[]; onPick: (l: PlanLesson) => void }) {
  const waiting = rows.filter((l) => l.state === "AWAITING"), rejected = rows.filter((l) => l.state === "REJECTED");
  return <section className="pm-panel" aria-labelledby="pm-fu">
    <header className="pm-ph"><div><h2 id="pm-fu">Conferme richieste</h2><p>{plural(waiting.length, "lezione in attesa", "lezioni in attesa")}{rejected.length ? ` · ${plural(rejected.length, "rifiutata", "rifiutate")}: rigenera il mese per trovare un altro orario` : ""}.</p></div></header>
    {rows.length ? <table className="pm-table">
      <thead><tr><th scope="col">Lezione</th><th scope="col">Quando</th><th scope="col">Tutor</th><th scope="col">Stato</th><th scope="col"><span className="sr">Azione</span></th></tr></thead>
      <tbody>{rows.map((l) => <tr key={l.id}>
        <th scope="row">{l.subject}<small>{l.students.map((s) => s.name).join(", ")}</small></th>
        <td>{dateLong(rome(l.start_at).date)}<small>{rangeOf(l.start_at, l.end_at)}</small></td>
        <td>{l.tutor.name}</td>
        <td><Tag tone={l.state === "REJECTED" ? "red" : "amber"}>{l.state === "REJECTED" ? "Rifiutata" : "In attesa"}</Tag></td>
        <td className="act"><Btn kind="sm ghost" onClick={() => onPick(l)}>Dettagli</Btn></td>
      </tr>)}</tbody>
    </table> : <Empty title="Nessuna conferma in sospeso" />}
  </section>;
}
