/**
 * Panoramiche dei portali: una dashboard diversa per ruolo.
 * - Tutor: la giornata di oggi con tutti i dettagli (e il link per le lezioni online), il riepilogo del mese.
 * - Genitore / tutore legale: una scheda grande per figlio, con la prossima lezione in evidenza e gli impegni successivi.
 *   Le cose da fare stanno nelle notifiche; qui compaiono solo gli avvisi che chiedono un'azione immediata.
 * - Studente: prossima lezione, settimana, disponibilità e richieste.
 */
import { useConfirmations } from "./Conferme";
import { CSSProperties, ReactNode, useEffect, useMemo, useState } from "react";
import { get, post } from "../api/client";
import { addDays, addMonths, dayLabel, duration, initials, monthYear, plural, rome, timeOf, todayRome } from "../format";
import { Btn, Empty, Icon, Skeleton, Tag } from "../ui/core";
import { ErrorState, ViewState } from "../ui/states";
import { go } from "../ui/route";
import { useData } from "../app/data";
import { loadMine, MyLesson } from "../app/myApi";
import { Child, earnings, loadPending, monthStats, Overview, Pending, useOverview } from "./data";
import type { S } from "../api/schema.gen";
import InformativaGate from "./InformativaGate";
import { Alert, Alerts, dayName, DayLesson, fromMine, LessonAccordion, LessonDetail, minutes, phase, URGENT_KINDS, useHidden, useJoin, useNow } from "./widgets";

const greet = () => { const h = new Date().getHours(); return h < 13 ? "Buongiorno" : h < 18 ? "Buon pomeriggio" : "Buonasera"; };
const firstName = (n: string) => n.split(/\s+/)[0];

export default function PortalHome() {
  const d = useData(), ov = useOverview();
  const roles = d.me.roles;
  // Il contesto attivo decide la dashboard: chi ha più ruoli li cambia da «Cambia ruolo».
  const kind = roles.includes("TUTOR") ? "tutor" : roles.includes("GUARDIAN") ? "guardian" : "student";
  return <>
    <InformativaGate />
    {ov.error ? <section className="module"><ErrorState error={ov.error} onRetry={ov.reload} /></section>
      : !ov.data ? <section className="module planner"><Skeleton rows={4} /></section>
      : kind === "tutor" ? <TutorHome o={ov.data} />
      : kind === "guardian" ? <GuardianHome o={ov.data} />
      : <StudentHome o={ov.data} />}
  </>;
}

/* ---------------- elementi comuni ---------------- */
function Hero({ id, title, sub, help, children }: { id: string; title: string; sub: ReactNode; help: "tutor" | "famiglia" | "studente"; children?: ReactNode }) {
  return <section className="module planner" aria-labelledby={id}>
    <div className="m-head"><div className="titlebox"><h1 className="h-display" id={id}>{title}</h1><p className="sub-line">{sub}</p></div>
      {children && <div className="controls">{children}</div>}</div>
  </section>;
}
/** Lezioni personali in un intervallo, comprese quelle annullate. */
function useMine(from: string, until: string) {
  const [rows, setRows] = useState<MyLesson[] | null>(null);
  useEffect(() => {
    let live = true; setRows(null);
    loadMine(from, until).then((x) => live && setRows([...x].sort((a, b) => a.start_at.localeCompare(b.start_at)))).catch(() => live && setRows([]));
    return () => { live = false; };
  }, [from, until]);
  return rows;
}
function usePending(roles: string[]) {
  const [p, setP] = useState<Pending | null>(null);
  useEffect(() => { loadPending(roles).then(setP).catch(() => setP(null)); }, [roles.join(",")]); // eslint-disable-line react-hooks/exhaustive-deps
  return p;
}
/** Notifiche da leggere che chiedono attenzione immediata. */
function useUrgent() {
  const [items, set] = useState<S.Notification[]>([]);
  const load = () => get("/notifications", { quiet: true }).then((p) => set(p.results.filter((n) => !n.read_at && URGENT_KINDS.includes(n.kind)))).catch(() => set([]));
  useEffect(() => { load(); }, []);
  const read = (n: S.Notification) => { set((xs) => xs.filter((x) => x.id !== n.id)); post("/notifications/{pk}/read", undefined as never, { params: { pk: n.id }, quiet: true }).catch(() => undefined); };
  return { items, read };
}
const urgentAlert = (n: S.Notification, read: (n: S.Notification) => void): Alert => ({
  id: "n-" + n.id, tone: n.kind === "lesson.cancelled" ? "red" : n.kind.startsWith("lesson") ? "amber" : "blue", icon: n.kind.startsWith("change") ? "send" : "cal",
  title: n.title, text: n.body ? n.body.slice(0, 160) : undefined,
  action: ["Vedi", () => { read(n); go(n.kind.startsWith("change") ? "cambi" : "settimana"); }], dismiss: () => read(n),
});

/* ---------------- tutor ---------------- */
function TutorHome({ o }: { o: Overview }) {
  const d = useData(), today = todayRome(), now = useNow(), join = useJoin();
  const rows = useMine(today, addDays(today, 8)), pend = usePending(d.me.roles), urgent = useUrgent();
  const cf = useConfirmations(), cfN = (cf.rows || []).filter((x) => x.status === "PENDING").length;
  const mine = (rows || []).filter((l) => l.as_tutor).map(fromMine);
  const todays = mine.filter((l) => rome(l.start_at).date === today);
  const upcoming = mine.filter((l) => l.state === "PUBLISHED" && new Date(l.end_at).getTime() > now);
  const nextToday = todays.find((l) => l.state === "PUBLISHED" && new Date(l.end_at).getTime() > now);
  const pendingAtt = o.tutor?.week?.attendance_pending || 0;
  const alerts: Alert[] = [
    ...(cfN ? [{ id: "autoconf", tone: "amber", icon: "clock", title: plural(cfN, "lezione proposta da confermare", "lezioni proposte da confermare"), text: "L’orario sfora di poco un impegno che hai indicato: decidi tu se va bene.", action: ["Rivedi", () => go("conferme")] } as Alert] : []),
    ...(pendingAtt ? [{ id: "att", tone: "amber", icon: "clipf", title: plural(pendingAtt, "presenza da registrare", "presenze da registrare"), text: "Lezioni concluse senza registro presenze.", action: ["Registra", () => go("presenze")] } as Alert] : []),
    ...(pend?.acks ? [{ id: "acks", tone: "blue", icon: "check", title: plural(pend.acks, "nuovo orario da confermare", "nuovi orari da confermare"), text: "Il centro ti ha assegnato nuove lezioni.", action: ["Conferma", () => go("orari")] } as Alert] : []),
    ...urgent.items.map((n) => urgentAlert(n, urgent.read)),
  ];
  const sub = !o.calendar_enabled ? "Il calendario non è ancora attivo." : rows === null ? "Carico le tue lezioni…"
    : todays.length ? ` ${plural(todays.filter((l) => l.state === "PUBLISHED").length, "lezione", "lezioni")} oggi${nextToday ? (new Date(nextToday.start_at).getTime() <= now ? `: ${nextToday.subject_name} è in corso` : `, la prossima alle ${timeOf(nextToday.start_at)}`) : ", tutte concluse"}.`
    : upcoming[0] ? "Nessuna lezione oggi." : "Nessuna lezione in programma.";
  const extra = (l: DayLesson) => <>
    {l.state === "PUBLISHED" && new Date(l.end_at).getTime() <= now && <Btn kind="sm" isle="check" onClick={() => go("presenze")}>Registra presenze</Btn>}
    <Btn kind="sm ghost" onClick={() => go("settimana", { d: rome(l.start_at).date })}>Apri nel calendario</Btn>
  </>;
  return <>
    <Hero id="h-home" title={`${greet()}, ${firstName(d.me.name)}`} sub={dayLabel(today)} help="tutor"><a className="pill-btn sm island" href="#/settimana">Le mie lezioni<span className="isle"><Icon n="arrow" /></span></a></Hero>
    <Alerts items={alerts} />
    <div className="two wide-left">
      <section className="module" aria-labelledby="h-today">
        <div className="m-head"><div><h2 className="m-title" id="h-today">La tua giornata</h2><p className="sub-line">{sub}</p></div></div>
        {!o.calendar_enabled ? <Empty title="Calendario non ancora attivo" />
          : rows === null ? <Skeleton rows={3} />
          : todays.length ? <LessonAccordion rows={todays} join={join} extra={extra} />
          : <>
            <Empty title="Nessuna lezione oggi" />
            {upcoming[0] && <div className="next-box"><b className="next-title">{upcoming[0].subject_name}</b><LessonDetail l={upcoming[0]} join={join} extra={extra(upcoming[0])} /></div>}
          </>}
      </section>
      <TutorMonth o={o} />
    </div>
  </>;
}

const eur = new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR" });
const RATE = (id: string) => "ripetizioni-tariffa:" + id;
/** Il mese del tutor: ore previste, annullate, guadagno stimato e accesso alle fasce settimanali. */
function TutorMonth({ o }: { o: Overview }) {
  const d = useData(), cur = todayRome().slice(0, 7);
  const [ym, setYm] = useState(cur);
  const rows = useMine(ym + "-01", addMonths(ym, 1) + "-01");
  const st = useMemo(() => (rows ? monthStats(rows) : null), [rows]);
  const [rate, setRate] = useState<number | null>(() => { const v = Number(localStorage.getItem(RATE(d.me.id))); return v > 0 ? v : null; });
  const [edit, setEdit] = useState(false), [draft, setDraft] = useState("");
  const saveRate = () => { const v = Number(draft.replace(",", ".")); const ok = v > 0 && v < 1000 ? Math.round(v * 100) / 100 : null; setRate(ok); try { ok ? localStorage.setItem(RATE(d.me.id), String(ok)) : localStorage.removeItem(RATE(d.me.id)); } catch { /* ignora */ } setEdit(false); };
  const startEdit = () => { setDraft(rate ? String(rate) : ""); setEdit(true); };
  const earned = st ? earnings(st.done, rate) : null, expected = st ? earnings(st.planned, rate) : null;
  const parts = st ? [
    { k: "done", label: "Svolte", n: st.doneCount, m: st.done, tone: "green" },
    { k: "next", label: "Da svolgere", n: st.lessons - st.doneCount, m: st.left, tone: "blue" },
    { k: "off", label: "Annullate", n: st.cancelled, m: st.cancelledMin, tone: "red" },
  ] : [];
  return <section className="module month" aria-labelledby="h-month">
    <div className="m-head"><div><h2 className="m-title" id="h-month">Il tuo mese</h2>{st && <p className="sub-line">{st.planned ? `${duration(st.planned)} in programma` : "Nessuna lezione in programma"}</p>}</div>
      <div className="datenav">
        <button className="circle" aria-label="Mese precedente" onClick={() => setYm(addMonths(ym, -1))}><Icon n="left" /></button>
        <span className="datebtn" aria-live="polite">{monthYear(ym)}</span>
        <button className="circle" aria-label="Mese successivo" onClick={() => setYm(addMonths(ym, 1))}><Icon n="right" /></button>
      </div></div>
    {!o.calendar_enabled ? <Empty title="Calendario non ancora attivo" />
      : !st ? <Skeleton rows={3} /> : <div className="month-body">
        <Donut parts={parts}>
          {rate ? <><small>Ricavato finora</small><b>{eur.format(earned || 0)}</b><span>su {eur.format(expected || 0)} previsti</span></>
            : <><small>Ricavato finora</small><button className="link-btn" onClick={startEdit}>Imposta la tariffa</button></>}
        </Donut>
        <ul className="legend-list">{parts.map((p) => <li key={p.k}><i className={"dot " + p.tone} aria-hidden="true" /><span>{p.label}</span><b>{p.n}</b><small>{p.m ? duration(p.m) : "—"}</small></li>)}</ul>
      </div>}
    {edit ? <form className="rate-edit" onSubmit={(e) => { e.preventDefault(); saveRate(); }}>
      <label htmlFor="rate">Tariffa oraria (€)</label>
      <input id="rate" className="inp" inputMode="decimal" autoFocus value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="es. 18" />
      <Btn kind="sm" type="submit">Salva</Btn><Btn kind="sm ghost" onClick={() => setEdit(false)}>Annulla</Btn>
    </form> : st && <p className="fine month-note">{rate ? `Stima al lordo con ${eur.format(rate)} l’ora, salvata su questo dispositivo. ` : "Indica la tua tariffa oraria per stimare il ricavato. "}<button className="link-btn" onClick={startEdit}>{rate ? "Modifica" : "Imposta"}</button></p>}
    <div className="todo-foot"><Btn kind="sm" isle="arrow" onClick={() => go("impegni")}>Modifica gli impegni</Btn></div>
  </section>;
}

/** Grafico ad anello delle lezioni del mese; al centro il contenuto passato (ricavato). */
function Donut({ parts, children }: { parts: { k: string; label: string; n: number; tone: string }[]; children: ReactNode }) {
  const total = parts.reduce((a, p) => a + p.n, 0), R = 64, C = 2 * Math.PI * R, gap = total > 1 ? 4 : 0;
  let acc = 0;
  return <div className="donut" role="img" aria-label={parts.map((p) => `${p.label}: ${p.n}`).join(", ")}>
    <svg viewBox="0 0 160 160" aria-hidden="true">
      <circle cx="80" cy="80" r={R} className="donut-track" />
      {total > 0 && parts.filter((p) => p.n).map((p) => { const len = (p.n / total) * C, seg = <circle key={p.k} cx="80" cy="80" r={R} className={"donut-seg " + p.tone}
        strokeDasharray={`${Math.max(0, len - gap)} ${C}`} strokeDashoffset={-acc} />; acc += len; return seg; })}
    </svg>
    <div className="donut-mid">{children}</div>
  </div>;
}

/* ---------------- genitore / tutore legale ---------------- */
const KID_COLORS = ["blue", "green", "violet", "amber", "red"] as const;
type KidColor = typeof KID_COLORS[number];
const COLOR_NAME: Record<KidColor, string> = { blue: "Blu", green: "Verde", violet: "Viola", amber: "Giallo", red: "Rosso" };
const COLORS_KEY = "ripetizioni-colori-figli";
function useKidColors() {
  const [m, setM] = useState<Record<string, KidColor>>(() => { try { return JSON.parse(localStorage.getItem(COLORS_KEY) || "{}"); } catch { return {}; } });
  const set = (id: string, c: KidColor) => setM((x) => { const n = { ...x, [id]: c }; try { localStorage.setItem(COLORS_KEY, JSON.stringify(n)); } catch { /* ignora */ } return n; });
  return { of: (id: string, i: number): KidColor => m[id] || KID_COLORS[i % KID_COLORS.length], set };
}

function GuardianHome({ o }: { o: Overview }) {
  const d = useData(), today = todayRome(), now = useNow(), join = useJoin();
  const rows = useMine(today, addDays(today, 15)), pend = usePending(d.me.roles), urgent = useUrgent(), { hidden, hide } = useHidden(), colors = useKidColors();
  const cf = useConfirmations(), cfN = (cf.rows || []).filter((x) => x.status === "PENDING").length;
  const kids = o.children;
  const notified = new Set(urgent.items.map((n) => n.subject_ref));
  const cancelled = (rows || []).filter((l) => l.state === "CANCELLED" && new Date(l.start_at).getTime() > now && !notified.has("lesson:" + l.id) && !hidden.has("off-" + l.id));
  const soon = (iso: string) => (new Date(iso).getTime() - now) / 864e5 <= 30;
  const alerts: Alert[] = [
    ...(cfN ? [{ id: "autoconf", tone: "amber", icon: "clock", title: plural(cfN, "lezione proposta da confermare", "lezioni proposte da confermare"), text: "L’orario sfora di poco un impegno che hai indicato: decidi tu se va bene.", action: ["Rivedi", () => go("conferme")] } as Alert] : []),
    ...(pend?.confirm ? [{ id: "conf", tone: "amber", icon: "send", title: plural(pend.confirm, "modifica da confermare", "modifiche da confermare"), text: "Il tutor ha proposto un cambio e il centro l’ha accolto: serve la tua conferma.", action: ["Rivedi", () => go("cambi")] } as Alert] : []),
    ...urgent.items.map((n) => urgentAlert(n, urgent.read)),
    ...cancelled.map((l): Alert => ({ id: "off-" + l.id, tone: "red", icon: "cal", title: `Lezione annullata: ${l.subject_name}`, text: `${l.participants.map((p) => p.name).join(", ")} · ${dayName(rome(l.start_at).date)} alle ${timeOf(l.start_at)}`, action: ["Vedi", () => go("settimana", { d: rome(l.start_at).date })], dismiss: () => hide("off-" + l.id) })),
    ...kids.filter((c) => c.reconfirmation && soon(c.reconfirmation)).map((c): Alert => ({ id: "rec-" + c.student_id, tone: "amber", icon: "user", title: `Riconferma la delega per ${firstName(c.display_name)}`, text: `Entro il ${c.reconfirmation!.split("-").reverse().join("/")}, altrimenti non potrai più seguirne le lezioni.`, action: ["Riconferma", () => go("profilo", { s: c.student_id })] })),
  ];
  return <>
    <Hero id="h-home" title={`${greet()}, ${firstName(d.me.name)}`} sub={dayLabel(today)} help="famiglia"><a className="pill-btn sm" href="#/richieste?nuova=1">Chiedi delle lezioni</a><a className="pill-btn sm island" href="#/settimana">Calendario<span className="isle"><Icon n="arrow" /></span></a></Hero>
    <Alerts items={alerts} />
    {!o.calendar_enabled && <section className="module"><ViewState kind="disabled" title="Calendario non ancora attivo">Le lezioni dei tuoi figli compariranno qui quando il centro attiverà il calendario.</ViewState></section>}
    {kids.length ? <div className="kid-grid big" role="list" aria-label="I tuoi figli">{kids.map((c, i) => <KidCard key={c.student_id} c={c} color={colors.of(c.student_id, i)} onColor={(k) => colors.set(c.student_id, k)}
      lessons={rows === null ? null : rows.filter((l) => l.participants.some((p) => p.student_id === c.student_id) && new Date(l.end_at).getTime() > now).map(fromMine)} join={join} now={now} />)}</div>
      : <section className="module"><ViewState kind="revoked" title="Nessun figlio collegato">Non ci sono deleghe attive. Se il centro ha revocato o sospeso una delega, qui non vedi più i dati: contatta il centro.</ViewState></section>}
  </>;
}

/** Scheda grande del figlio: colore scelto dal genitore, prossima lezione in evidenza, impegni successivi apribili. */
export function KidCard({ c, lessons = null, color = "blue", onColor, join: j, now = Date.now(), self }: { c: Child; lessons?: DayLesson[] | null; color?: KidColor; onColor?: (k: KidColor) => void; join?: ReturnType<typeof useJoin>; now?: number; self?: boolean }) {
  const fallback = useJoin(), join = j || fallback;
  const [pick, setPick] = useState(false);
  const next = lessons?.find((l) => l.state === "PUBLISHED"), later = (lessons || []).filter((l) => l !== next), rest = later.slice(0, 4);
  const w = c.week, name = firstName(c.display_name);
  const style = { "--kid": `var(--${color})`, "--kid-soft": `var(--${color}-soft)`, "--kid-ink": `var(--${color}-ink)`, "--kid-on": color === "amber" ? "#2A2106" : "#fff" } as CSSProperties;
  return <article className="kid big" role="listitem" aria-labelledby={"kid-" + c.student_id} style={style}>
    <header className="kid-top">
      <span className="kid-av" aria-hidden="true">{initials(c.display_name)}</span>
      <div className="kid-id"><h3 id={"kid-" + c.student_id}>{c.display_name}</h3>
        <small>{[c.level || null, w ? (w.lessons ? `${plural(w.lessons, "lezione", "lezioni")} questa settimana` : "Nessuna lezione questa settimana") : null].filter(Boolean).join(" · ")}</small></div>
      {onColor && <button type="button" className="kid-color" aria-label={`Colore della scheda di ${name}: ${COLOR_NAME[color]}`} aria-expanded={pick} onClick={() => setPick(!pick)}><span /></button>}
    </header>
    {pick && onColor && <div className="swatches" role="radiogroup" aria-label={`Colore per ${name}`}>{KID_COLORS.map((k) => <button key={k} type="button" role="radio" aria-checked={k === color} aria-label={COLOR_NAME[k]} className={"sw" + (k === color ? " on" : "")} style={{ background: `var(--${k})` }} onClick={() => { onColor(k); setPick(false); }} />)}</div>}
    {c.read_only && <div className="kid-flags"><Tag tone="plain">Sola lettura</Tag></div>}
    <div className="kid-next">
      <div className="kn-head"><small>Prossima lezione</small>{next && <Tag tone={phase(next, now).tone}>{phase(next, now).label}</Tag>}</div>
      {lessons === null ? <Skeleton rows={2} /> : next ? <>
        <b className="kn-subj">{next.subject_name}</b>
        <p className="kn-when">{dayName(rome(next.start_at).date)} · {timeOf(next.start_at)}–{timeOf(next.end_at)} · {duration(minutes(next))}</p>
        <LessonDetail l={next} join={join} noTime />
      </> : <p className="muted">{w?.next_lesson_at ? `${dayName(rome(w.next_lesson_at).date)} alle ${timeOf(w.next_lesson_at)}` : "Nessuna lezione in programma nelle prossime due settimane."}</p>}
    </div>
    {rest.length > 0 && <div className="kid-rest"><h4>Poi</h4><LessonAccordion rows={rest} join={join} showDay closed />
      {later.length > rest.length && <a className="link-btn kid-more" href="#/settimana">{plural(later.length - rest.length, "altro impegno", "altri impegni")} nel calendario</a>}</div>}
    <footer className="kid-actions"><Btn kind="sm" isle="arrow" onClick={() => go("profilo", { s: c.student_id })}>{self ? "Disponibilità e assenze" : `Gestisci ${name}`}</Btn>
      {c.open_change_requests > 0 && <span className="fine">{plural(c.open_change_requests, "richiesta in attesa", "richieste in attesa")}</span>}</footer>
  </article>;
}

/* ---------------- studente ---------------- */
function StudentHome({ o }: { o: Overview }) {
  const d = useData(), today = todayRome(), now = useNow(), join = useJoin(), urgent = useUrgent(), colors = useKidColors();
  const rows = useMine(today, addDays(today, 15));
  const me = o.children.find((c) => c.relation === "SELF") || o.children[0];
  return <>
    <Hero id="h-home" title={`Ciao, ${firstName(d.me.name)}`} sub={dayLabel(today)} help="studente"><a className="pill-btn sm island" href="#/settimana">Le mie lezioni<span className="isle"><Icon n="arrow" /></span></a></Hero>
    <Alerts items={urgent.items.map((n) => urgentAlert(n, urgent.read))} />
    <div className="two top">
      {me ? <div className="kid-grid big one"><KidCard c={me} self color={colors.of(me.student_id, 0)} onColor={(k) => colors.set(me.student_id, k)} join={join} now={now}
        lessons={rows === null ? null : rows.filter((l) => new Date(l.end_at).getTime() > now).map(fromMine)} /></div>
        : <section className="module"><Empty title="Profilo non collegato" /></section>}
      <section className="module" aria-labelledby="h-st-req">
        <div className="m-head"><h2 className="m-title" id="h-st-req">Cambi e assenze</h2></div>
        {o.policies.student_can_request_changes
          ? <>{o.open_change_requests ? <p>{plural(o.open_change_requests, "richiesta in attesa del centro", "richieste in attesa del centro")}.</p> : null}
            <div className="todo-foot"><Btn kind="sm" isle="arrow" onClick={() => go("cambi")}>Le mie richieste</Btn></div></>
          : <p className="muted">Per spostare una lezione o segnalare un’assenza chiedi a un genitore o contatta il centro.</p>}
        <div className="todo" style={{ marginTop: 14 }}>
          <button className="todo-it" onClick={() => go("impegni")}><div><b>I miei impegni</b></div><Icon n="right" /></button>
          <button className="todo-it" onClick={() => go("dati")}><div><b>I miei dati e la privacy</b></div><Icon n="right" /></button>
        </div>
      </section>
    </div>
  </>;
}
