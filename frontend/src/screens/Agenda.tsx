import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import { addDays, dayLabel, dayShort, duration, hm, mondayOf, monthYear, parseHm, plural, rangeOf, rome, romeISO, todayRome, weekday } from "../format";
import { human, LOCATION, MODE, reasons } from "../messages";
import { Avatar, Btn, Icon, Notice, Skeleton, State, Tag, Tech } from "../ui/core";
import { CalendarGrid, Check, Choices, Field, Wheel } from "../ui/controls";
import { Modal, Pop, Sheet, useToast } from "../ui/layers";
import { openNewLesson } from "../app/Shell";
import { motionOK } from "../ui/prefs";
import { setQuery, useRoute } from "../ui/route";
import { useData } from "../app/data";
import { Cap, Lesson, loadLessons } from "../app/calendarApi";
import Proposals from "./Proposals";
import LessonActions from "./LessonActions";
import { Correction, CorrRes, DraftModal, DraftNote, draftOverlay, Ghost, MonthBar, MonthState, publishOne } from "./MonthDraft";

const Q = 15; // minuti per colonna
const SPRING = "cubic-bezier(.32,.72,0,1)", EASE = "cubic-bezier(.2,.8,.2,1)";
type Row = { id: string; name: string };
type Geo = { open: number; close: number; cols: number };
const isGroup = (l: Lesson) => l.participants.length > 1;
const lmin = (l: Lesson) => ({ date: rome(l.start_at).date, s: rome(l.start_at).min, e: rome(l.end_at).min });
const overlap = (a: number, b: number, c: number, d: number) => a < d && c < b;
const tmin = (t: string) => (t.startsWith("24:00") || t.startsWith("23:59") ? 1440 : parseHm(t.slice(0, 5)));

/** Pianificazione mensile: un tutor è libero quando il centro è aperto e non ha impegni. */
type Opening = { weekday: number; start: string; end: string };
type ClosureRow = { start_date: string; end_date: string; start_time: string | null; end_time: string | null; all_day: boolean };
type TutorBusy = { tutor: string | null; label: string; kind: "WEEKLY" | "ONE_OFF"; weekday: number | null; date: string | null; start_time: string; end_time: string; valid_from: string | null; valid_until: string | null };
export type Avail = { hours: Opening[]; closures: ClosureRow[]; busy: TutorBusy[] };
function useAvail() {
  const [a, setA] = useState<Avail | null>(null);
  useEffect(() => {
    let live = true;
    Promise.all([
      api<{ opening_hours: Opening[]; closures: ClosureRow[] }>("/planner/setup"),
      api<TutorBusy[]>("/commitments?owner=tutor").catch(() => [] as TutorBusy[]),
    ]).then(([st, busy]) => { if (live) setA({ hours: st.opening_hours || [], closures: st.closures || [], busy: busy.filter((c) => c.tutor) }); }).catch(() => undefined);
    return () => { live = false; };
  }, []);
  return a;
}
/** Intervalli [inizio, fine) in minuti in cui il centro è chiuso in quel giorno per ferie/chiusure. */
function closedSpans(a: Avail, day: string) {
  return a.closures.filter((c) => c.start_date <= day && day <= c.end_date).map((c) => {
    if (c.all_day || !c.start_time || !c.end_time) return [0, 1440];
    return [day === c.start_date ? tmin(c.start_time) : 0, day === c.end_date ? tmin(c.end_time) : 1440];
  });
}
function busySpans(a: Avail, tid: string, day: string) {
  const wd = weekday(day);
  return a.busy.filter((c) => c.tutor === tid && (c.kind === "ONE_OFF" ? c.date === day : c.weekday === wd && (!c.valid_from || c.valid_from <= day) && (!c.valid_until || day <= c.valid_until)))
    .map((c) => ({ s: tmin(c.start_time), e: tmin(c.end_time), label: c.label.trim() || "Impegno" }));
}

export default function Agenda() {
  const d = useData(), r = useRoute(), toast = useToast();
  const today = todayRome();
  const day = r.q.get("d") || today, week = mondayOf(day);
  const [cap, setCap] = useState<Cap | null>(null), [err, setErr] = useState("");
  const [data, setData] = useState<{ week: string; lessons: Lesson[]; revision: number | null } | null>(null);
  const [filter, setFilter] = useState({ single: true, group: true, cancelled: false });
  const [filtAnchor, setFiltAnchor] = useState<HTMLElement | null>(null), [dayAnchor, setDayAnchor] = useState<HTMLElement | null>(null);
  const [move, setMove] = useState<{ l: Lesson; date: string; start: number } | null>(null), [cancel, setCancel] = useState<Lesson | null>(null);
  const openId = r.q.get("l");
  const av = useAvail();
  const ym = day.slice(0, 7);
  const [month, setMonth] = useState<MonthState | null>(null), [ghost, setGhost] = useState<Ghost | null>(null);
  const loadMonth = useCallback(async (m = ym) => {
    try { const x = await api<MonthState>(`/planner/calendar-months/${m}`); setMonth(x.month === m ? x : null); } catch { setMonth(null); }
  }, [ym]);
  useEffect(() => { setMonth(null); void loadMonth(); }, [loadMonth]);
  const draft = useMemo(() => draftOverlay(month && month.month === ym ? month : null), [month, ym]);
  const load = useCallback(async (w = week) => {
    const c = await api<Cap>("/calendar/capabilities"); setCap(c);
    if (!c.enabled) { setData({ week: w, lessons: [], revision: null }); return; }
    const res = await loadLessons(w, addDays(w, 7)); setData({ week: w, ...res });
  }, [week]);
  useEffect(() => { setErr(""); load().catch((e) => setErr(human(e).text)); }, [load]);
  useEffect(() => { // lezione creata da «Nuova lezione» (barra in alto o trascinamento)
    const f = () => { load().catch((e) => setErr(human(e).text)); void loadMonth(); };
    addEventListener("calendar:changed", f); return () => removeEventListener("calendar:changed", f);
  }, [load, loadMonth]);
  const lessons = data?.week === week ? data.lessons : null;
  const visible = useMemo(() => (lessons || []).filter((l) => (l.state !== "CANCELLED" || filter.cancelled) && (isGroup(l) ? filter.group : filter.single)), [lessons, filter]);
  const dayLessons = visible.filter((l) => lmin(l).date === day);
  const rows: Row[] = useMemo(() => {
    const m = new Map<string, string>(); d.tutors.forEach((t) => m.set(t.id, t.display_name)); (lessons || []).forEach((l) => m.set(l.tutor, l.tutor_name));
    return [...m].map(([id, name]) => ({ id, name })).sort((a, b) => a.name.localeCompare(b.name, "it"));
  }, [d.tutors, lessons]);
  const geo: Geo = useMemo(() => {
    const ls = (lessons || []).filter((l) => l.state !== "CANCELLED").map(lmin);
    let open = ls.length ? Math.floor(Math.min(...ls.map((x) => x.s)) / 60) * 60 : 14 * 60;
    let close = ls.length ? Math.ceil(Math.max(...ls.map((x) => x.e)) / 60) * 60 : 20 * 60;
    const all = av?.hours || [], today0 = all.filter((h) => h.weekday === weekday(day)), hrs = today0.length ? today0 : all;
    if (hrs.length) { // la griglia copre sempre gli orari di apertura della settimana
      const ho = Math.floor(Math.min(...hrs.map((h) => tmin(h.start))) / 60) * 60, hc = Math.ceil(Math.max(...hrs.map((h) => tmin(h.end))) / 60) * 60;
      open = ls.length ? Math.min(open, ho) : ho; close = ls.length ? Math.max(close, hc) : hc;
    } else open = Math.min(open, 14 * 60);
    close = Math.min(24 * 60, Math.max(close, open + 6 * 60));
    return { open, close, cols: (close - open) / Q };
  }, [lessons, av, day]);
  const setDay = (x: string) => { setQuery((q) => (x === today ? q.delete("d") : q.set("d", x))); };
  const sel = (lessons || []).find((l) => l.id === openId) || null;
  const counts = (x: string) => (lessons || []).filter((l) => l.state === "PUBLISHED" && lmin(l).date === x).length;
  const nextDay = useMemo(() => {
    const ds = [...new Set((lessons || []).filter((l) => l.state === "PUBLISHED").map((l) => lmin(l).date))].sort();
    return ds.find((x) => x > day) || ds.filter((x) => x < day).pop();
  }, [lessons, day]);
  const wait = dayLessons.filter((l) => l.state === "PUBLISHED");
  const sub = !cap ? "Carico il calendario…" : !cap.enabled ? "Calendario non disponibile." : wait.length
    ? `${plural(wait.length, "lezione", "lezioni")} con ${plural(new Set(wait.map((l) => l.tutor)).size, "tutor", "tutor")}${dayLessons.length > wait.length ? `, ${dayLessons.length - wait.length} cancellate` : ""}.` : "Nessuna lezione in programma.";
  const nf = (filter.single ? 0 : 1) + (filter.group ? 0 : 1) + (filter.cancelled ? 1 : 0);
  const title = day === today ? "Lezioni di oggi" : day === addDays(today, 1) ? "Lezioni di domani" : day === addDays(today, -1) ? "Lezioni di ieri" : `Lezioni di ${dayLabel(day).split(" ")[0].toLowerCase()} ${Number(day.slice(8))}`;
  const startMove = (l: Lesson, start?: number, date?: string) => { const m = lmin(l); setQuery((q) => q.delete("l")); setMove({ l, date: date || m.date, start: start ?? m.s }); };
  const after = async (msg: string, opt?: { action: string; onAction: () => void }) => { if (msg) toast(msg, opt); await Promise.all([load().catch((e) => setErr(human(e).text)), loadMonth()]); };
  /** Esito di un’azione sulla bozza del mese (pubblica/scarta): aggiorna stato del mese e lezioni. */
  const monthChanged = async (m: MonthState | null, msg: string) => { if (m) setMonth(m); await after(msg); };
  /** Ogni modifica del gestore è una rettifica del calendario del mese: in bozza, oppure pubblicata subito. */
  const propose = async (body: Record<string, unknown>, what: string) => {
    const res = await api<CorrRes>("/planner/corrections", { method: "POST", body: JSON.stringify(body) });
    setMonth(res.month);
    if (res.published) { await after(`${what}: pubblicato, tutor e famiglie ricevono l’avviso`); return; }
    await after(`${what}: in bozza nel calendario di ${monthYear(res.month.month).toLowerCase()}`, { action: "Pubblica subito", onAction: () => {
      publishOne(res.correction.id).then((x) => monthChanged(x.month, "Rettifica pubblicata: tutor e famiglie ricevono l’avviso")).catch((er) => toast(human(er).text));
    } });
  };
  /** Drag & drop (posizione o durata): niente menu, la modifica entra nella bozza del mese. */
  const dragChange = async (l: Lesson, s: number, e: number) => {
    const m = lmin(l);
    try { await propose({ op: "reschedule", lesson_id: l.id, start_at: romeISO(m.date, s), end_at: romeISO(m.date, e) }, `${l.subject_name} alle ${hm(s)}–${hm(e)}`); }
    catch (x) { toast(human(x).text); await load().catch(() => undefined); }
  };
  const confirmNow = async (id: string) => {
    try { await api(`/lesson-changes/${id}/confirm/`, { method: "POST", body: "{}" }); await after("Modifica confermata subito: tutor e famiglie ricevono l’avviso del nuovo orario"); }
    catch (x) { toast(human(x).text); await load().catch(() => undefined); }
  };
  /** Ctrl/⌘+clic su una lezione e clic su una seconda: le due lezioni si scambiano l’orario. */
  const [pick, setPick] = useState<Lesson | null>(null);
  const swappable = (l: Lesson) => l.state === "PUBLISHED" && new Date(l.start_at) > new Date();
  useEffect(() => {
    if (!pick) return;
    const k = (e: KeyboardEvent) => { if (e.key === "Escape") setPick(null); };
    addEventListener("keydown", k); return () => removeEventListener("keydown", k);
  }, [pick]);
  const swap = async (a: Lesson, b: Lesson) => {
    setPick(null);
    try {
      await propose({ op: "swap", lesson_id: a.id, other_id: b.id }, `Scambio ${a.subject_name} ↔ ${b.subject_name}`);
    } catch (x) { toast(human(x).text); await load().catch(() => undefined); }
  };
  const openOrSwap = (l: Lesson, mod?: boolean) => {
    if (pick) {
      if (pick.id === l.id) { setPick(null); return; }
      if (!swappable(l)) { toast("Si possono scambiare solo lezioni future in programma"); return; }
      void swap(pick, l); return;
    }
    if (mod) {
      if (!swappable(l)) { toast("Si possono scambiare solo lezioni future in programma"); return; }
      setPick(l); return;
    }
    setQuery((q) => q.set("l", l.id));
  };
  const withdraw = async (id: string) => {
    try { await api(`/lesson-changes/${id}/withdraw/`, { method: "POST", body: "{}" }); await after("Proposta ritirata: la lezione resta all’orario attuale"); }
    catch (x) { toast(human(x).text); }
  };
  return <>
    <section className="module planner" aria-labelledby="h-plan">
      <div className="m-head">
        <div className="titlebox"><RollTitle id="h-plan" text={title} dir={day} /><p className="sub-line">{sub}</p></div>
        <div className="controls">
          <div className="datenav">
            <button className="circle" aria-label="Giorno precedente" aria-keyshortcuts="[" onClick={() => setDay(addDays(day, -1))}><Icon n="left" /></button>
            <button className="datebtn" aria-haspopup="dialog" aria-expanded={false} aria-label={`Scegli il giorno, ${dayLabel(day)}`} onClick={(e) => setDayAnchor(dayAnchor ? null : e.currentTarget)}><Icon n="cal" /><span className="num">{dayLabel(day)}</span><Icon n="chev" /></button>
            <button className="circle" aria-label="Giorno successivo" aria-keyshortcuts="]" onClick={() => setDay(addDays(day, 1))}><Icon n="right" /></button>
          </div>
          {day !== today && <button className="pill-btn sm" onClick={() => setDay(today)}>Oggi</button>}
          <button className="pill-btn sm ag-filter" aria-label={nf ? `Filtri attivi: ${nf}` : "Filtra"} aria-haspopup="dialog" aria-expanded={false} aria-pressed={nf > 0} onClick={(e) => setFiltAnchor(filtAnchor ? null : e.currentTarget)}><Icon n="filter" />{nf ? `Filtri (${nf})` : "Filtra"}</button>
        </div>
      </div>
      {cap?.enabled && <MonthBar ym={ym} m={month && month.month === ym ? month : null} toast={(x) => toast(x)} onChanged={monthChanged}
        onMonth={(x) => setDay(x === today.slice(0, 7) ? today : `${x}-01`)} />}
      <DayStrip week={week} day={day} today={today} counts={counts} onPick={setDay} month={ym} />
      {pick && <Notice kind="info" action={<Btn kind="sm" onClick={() => setPick(null)}>Annulla</Btn>}>Scambio: hai scelto {pick.subject_name} ({rangeOf(pick.start_at, pick.end_at)}). Clicca la lezione con cui scambiare l’orario, anche in un altro giorno della settimana (Esc per annullare).</Notice>}
      {err && <Notice kind="bad" action={<Btn kind="sm" onClick={() => load().catch((e) => setErr(human(e).text))}>Riprova</Btn>}>{err}</Notice>}
      {!cap || !lessons ? <Skeleton rows={5} /> : !cap.enabled ? <Notice kind="warn" title="Calendario non disponibile">Il calendario non è attivo al momento, quindi lezioni e comandi restano spenti. Contatta l’assistenza del centro.<Tech><code>{cap.database} · {cap.reason_code}</code></Tech></Notice>
        : <>{!dayLessons.length && <p className="empty-hint muted">{weekday(day) === 6 ? "Domenica: nessuna lezione." : "Nessuna lezione in questo giorno."}{nextDay ? <> <button className="linklike" onClick={() => setDay(nextDay)}>Vai a {dayShort(nextDay).toLowerCase()}</button></> : null}</p>}
        <Grid rows={rows} geo={geo} day={day} lessons={dayLessons} rules={d.rules} avail={av} empty={!dayLessons.length} nextDay={nextDay} onGo={setDay}
          onOpen={openOrSwap} onDrag={dragChange} onRefuse={(m) => toast(m)} picked={pick?.id}
          drafts={draft.by} ghosts={draft.ghosts.filter((g) => rome(g.start_at).date === day)} onGhost={setGhost}
          onCreate={(tutor, s, e) => openNewLesson({ tutor, date: day, start: s, end: e })} /></>}
      {cap?.enabled && <div className="legend" aria-label="Legenda">
        <span><i style={{ background: "var(--blue)" }} />Individuale</span><span><i style={{ background: "var(--violet)" }} />Gruppo</span>
        <span><i className="cell off" style={{ borderRadius: 4 }} />{av?.hours.length ? "Centro chiuso o tutor impegnato" : "Tutor non disponibile"}</span>
        <span><Icon n="pin" />In presenza</span><span><Icon n="video" />Online</span>
        <span><i className="lg-pend" />In bozza, da pubblicare</span>
        <span><i className="lg-pend lg-rv" />Richiesta in verifica</span>
      </div>}
    </section>
    {cap?.enabled && <Proposals cap={cap} onPublished={async (firstDay, n) => { await load(mondayOf(firstDay || week)).catch(() => {}); if (firstDay) setDay(firstDay); toast(`${plural(n, "lezione pubblicata", "lezioni pubblicate")} nel calendario.`); }} />}

    <Pop open={!!dayAnchor} anchor={dayAnchor} onClose={() => setDayAnchor(null)} label="Scegli il giorno">
      <CalendarGrid value={day} footer marks={(x) => (mondayOf(x) === week ? counts(x) : 0)} onPick={(x) => { setDayAnchor(null); setDay(x); }} />
    </Pop>
    <Pop open={!!filtAnchor} anchor={filtAnchor} onClose={() => setFiltAnchor(null)} label="Filtri">
      <h2>Mostra</h2>
      <Check checked={filter.single} onChange={(v) => setFilter({ ...filter, single: v })}>Lezioni individuali<i style={{ background: "var(--blue)" }} /></Check>
      <Check checked={filter.group} onChange={(v) => setFilter({ ...filter, group: v })}>Lezioni di gruppo<i style={{ background: "var(--violet)" }} /></Check>
      <Check checked={filter.cancelled} onChange={(v) => setFilter({ ...filter, cancelled: v })}>Anche le cancellate</Check>
      <div className="foot"><button className="pill-btn sm" onClick={() => setFilter({ single: true, group: true, cancelled: false })}>Mostra tutto</button></div>
    </Pop>
    <LessonSheet l={sel} lessons={lessons || []} corr={sel ? draft.by.get(sel.id) || null : null} propose={propose} onDraftChanged={async (m, msg) => { setQuery((q) => q.delete("l")); await monthChanged(m, msg); }} onDone={async (msg) => { setQuery((q) => q.delete("l")); await after(msg); }} onClose={() => setQuery((q) => q.delete("l"))} onMove={(l) => startMove(l)} onCancel={(l) => { setQuery((q) => q.delete("l")); setCancel(l); }}
      onConfirmChange={(id) => { setQuery((q) => q.delete("l")); confirmNow(id); }} onWithdrawChange={(id) => { setQuery((q) => q.delete("l")); withdraw(id); }} />
    <MoveModal m={move} week={lessons || []} onClose={() => setMove(null)} propose={propose} />
    <CancelModal l={cancel} onClose={() => setCancel(null)} propose={propose} />
    <DraftModal g={ghost} onClose={() => setGhost(null)} onChanged={monthChanged} toast={(x) => toast(x)} />
  </>;
}

/** Titolo che esce e rientra a molla quando cambia il giorno. */
function RollTitle({ id, text, dir }: { id: string; text: string; dir: string }) {
  const ref = useRef<HTMLSpanElement>(null), last = useRef(text), lastDir = useRef(dir);
  const [shown, setShown] = useState(text);
  useEffect(() => {
    if (text === last.current) return;
    const s = dir < lastDir.current ? -1 : 1; last.current = text; lastDir.current = dir;
    const h = ref.current;
    if (!h || !motionOK()) { setShown(text); return; }
    h.animate([{ transform: "none", opacity: 1 }, { transform: `translateY(${-40 * s}%)`, opacity: 0 }], { duration: 180, easing: "cubic-bezier(.4,0,1,1)" }).onfinish = () => {
      setShown(text); h.animate([{ transform: `translateY(${40 * s}%)`, opacity: 0 }, { transform: "none", opacity: 1 }], { duration: 520, easing: SPRING });
    };
  }, [text, dir]);
  return <h1 className="h-display" id={id}><span ref={ref}>{shown}</span></h1>;
}

export function DayStrip({ week, day, today, counts, onPick, month }: { week: string; day: string; today: string; counts: (d: string) => number; onPick: (d: string) => void; month?: string }) {
  return <div className="daystrip" role="group" aria-label="Giorni della settimana">{Array.from({ length: 7 }, (_, i) => addDays(week, i)).map((x) => {
    const n = counts(x);
    return <button key={x} className={"ds" + (x === today ? " today" : "") + (month && !x.startsWith(month) ? " out" : "")} aria-pressed={x === day} onClick={() => onPick(x)} aria-label={`${dayLabel(x)}, ${n ? plural(n, "lezione", "lezioni") : "nessuna lezione"}`}>
      <span>{dayShort(x).split(" ")[0]}{month && !x.startsWith(month) && x.slice(8) === "01" ? " · " + monthYear(x.slice(0, 7)).split(" ")[0].slice(0, 3).toLowerCase() : ""}</span><b className="num">{Number(x.slice(8))}</b><em>{n ? plural(n, "lezione", "lezioni") : "—"}</em>
    </button>;
  })}</div>;
}

/* ------------------------------ griglia ------------------------------ */
type GridP = { rows: Row[]; geo: Geo; day: string; lessons: Lesson[]; rules: { tutor: string | null; weekday: number; start_time: string; end_time: string; status: string; period_start?: string; period_end?: string }[]; avail: Avail | null; empty: boolean; nextDay?: string; onGo: (d: string) => void; onOpen: (l: Lesson, mod?: boolean) => void; onDrag: (l: Lesson, start: number, end: number) => void; onRefuse: (m: string) => void; picked?: string; onCreate?: (tutor: string, start: number, end: number) => void };
function Grid({ rows, geo, day, lessons, rules, avail: am, empty, nextDay, onGo, onOpen, onDrag, onRefuse, picked, onCreate, drafts, ghosts = [], onGhost }: GridP & { drafts?: Map<string, Correction>; ghosts?: Ghost[]; onGhost?: (g: Ghost) => void }) {
  const sched = useRef<HTMLDivElement>(null), scroller = useRef<HTMLDivElement>(null), bar = useRef<HTMLDivElement>(null);
  const now = rome(new Date()), isToday = now.date === day;
  const slots = Array.from({ length: geo.cols / 2 }, (_, i) => geo.open + i * 30);
  const col = (min: number) => Math.round((min - geo.open) / Q) + 2;
  const avail = (tid: string): { known: boolean; ok: (s: number) => boolean; why: (s: number) => string } => {
    if (am && am.hours.length) { // pianificazione mensile: orari del centro − chiusure − impegni del tutor
      const open = am.hours.filter((h) => h.weekday === weekday(day)).map((h) => [tmin(h.start), tmin(h.end)]);
      const closed = closedSpans(am, day), busy = busySpans(am, tid, day);
      const why = (s: number) => {
        if (!open.some(([a, b]) => a <= s && s + 30 <= b) || closed.some(([a, b]) => overlap(s, s + 30, a, b))) return "Centro chiuso";
        const c = busy.find((x) => overlap(s, s + 30, x.s, x.e));
        return c ? c.label : "";
      };
      return { known: true, ok: (s) => !why(s), why };
    }
    const mine = rules.filter((x) => x.tutor === tid && x.status === "APPROVED" && x.weekday === weekday(day) && (!x.period_start || (x.period_start <= day && (!x.period_end || day <= x.period_end))));
    const any = rules.some((x) => x.tutor === tid && x.status === "APPROVED");
    const ok = (s: number) => mine.some((x) => parseHm(x.start_time) <= s && s + 30 <= parseHm(x.end_time));
    return { known: any, ok, why: (s: number) => (ok(s) ? "" : any ? "Non disponibile" : "Disponibilità non dichiarata") };
  };
  /** Motivo per cui [a, b) non è prenotabile per il tutor (centro chiuso, chiusura, impegno), "" se libero. */
  const blockedAt = (tid: string, a: number, b: number): string => {
    if (am && am.hours.length) {
      const open = am.hours.filter((h) => h.weekday === weekday(day)).map((h) => [tmin(h.start), tmin(h.end)]);
      if (!open.some(([x, y]) => x <= a && b <= y) || closedSpans(am, day).some(([x, y]) => overlap(a, b, x, y))) return "Centro chiuso";
      const c = busySpans(am, tid, day).find((x) => overlap(a, b, x.s, x.e));
      return c ? `Tutor impegnato${c.label ? ": " + c.label : ""}` : "";
    }
    const v = avail(tid);
    if (!v.known) return "";
    for (let m = a; m < b; m += Q) if (!v.ok(Math.min(m, b - 30))) return v.why(Math.min(m, b - 30)) || "Non disponibile";
    return "";
  };
  const live = useRef({ lessons, geo, day, onDrag, onOpen, onRefuse, onCreate, blockedAt }); live.current = { lessons, geo, day, onDrag, onOpen, onRefuse, onCreate, blockedAt };
  useGestures(sched, scroller, live);
  useLayoutEffect(() => { // porta in vista l’ora corrente o la prima lezione
    const sc = scroller.current; if (!sc || sc.scrollWidth <= sc.clientWidth) return;
    const target = sc.querySelector<HTMLElement>(".c-head.is-now") || sc.querySelector<HTMLElement>(".les");
    const name = sc.querySelector<HTMLElement>(".c-name"); if (target && name) sc.scrollLeft = target.offsetLeft - name.offsetWidth - 60;
  }, [day]);
  const nowCol = isToday && now.min >= geo.open && now.min < geo.close ? Math.floor((now.min - geo.open) / 30) : -1;
  const t = isToday ? Math.min(Math.max((now.min - geo.open) / (geo.close - geo.open), 0), 1) : 0;
  const gaps = (geo.cols - 1) * 8, passed = Math.min(Math.floor(Math.max(now.min - geo.open, 0) / Q), geo.cols - 1) * 8;
  useEffect(() => { // scorrendo, la griglia si sfoca e sparisce dietro la colonna dei tutor
    const sc = scroller.current, wrap = sc?.closest<HTMLElement>(".ag-wrap"), track = bar.current; if (!sc || !wrap || !track) return;
    let raf = 0;
    const paint = () => {
      raf = 0;
      const name = sc.querySelector<HTMLElement>(".c-name"); if (!name) return;
      const n = name.getBoundingClientRect(), w = wrap.getBoundingClientRect(), b = sc.getBoundingClientRect();
      const k = Math.min(sc.scrollLeft / 48, 1), cs = getComputedStyle(name);
      const pitch = n.height + (parseFloat(getComputedStyle(name.parentElement!).rowGap) || 0);
      const rx = parseFloat(cs.borderTopLeftRadius) || 0;
      // maschera della colonna: solo le celle dei tutor (angoli arrotondati inclusi) restano visibili,
      // cosi' nulla di cio' che scorre dietro spunta negli spazi tra le righe o ai lati.
      const svg = `<svg xmlns='http://www.w3.org/2000/svg' width='${n.width}' height='${pitch}'><rect width='${n.width}' height='${n.height}' rx='${rx}'/></svg>`;
      wrap.style.setProperty("--ag-edge", `${Math.round(n.right - w.left)}px`);
      wrap.style.setProperty("--ag-sc-edge", `${n.right - b.left}px`);
      wrap.style.setProperty("--ag-col", `url("data:image/svg+xml,${encodeURIComponent(svg)}")`);
      wrap.style.setProperty("--ag-col-pos", `${n.left - b.left}px ${n.top - b.top}px`);
      wrap.style.setProperty("--ag-col-size", `${n.width}px ${pitch}px`);
      wrap.style.setProperty("--ag-k", k.toFixed(3));
      wrap.classList.toggle("is-scrolled", sc.scrollLeft > 0);
      // barra di scorrimento propria: solo sotto gli orari, fuori dalla sfocatura
      const max = sc.scrollWidth - sc.clientWidth, tw = track.clientWidth;
      const th = max > 1 ? Math.max(40, tw * sc.clientWidth / sc.scrollWidth) : tw;
      wrap.classList.toggle("has-bar", max > 1);
      track.style.setProperty("--th-w", `${th}px`);
      track.style.setProperty("--th-x", `${max > 1 ? (tw - th) * sc.scrollLeft / max : 0}px`);
    };
    let drag: { x: number; sl: number } | null = null;
    const down = (e: PointerEvent) => {
      const th = track.firstElementChild as HTMLElement, r = th.getBoundingClientRect();
      if (e.target === th) { drag = { x: e.clientX, sl: sc.scrollLeft }; track.setPointerCapture(e.pointerId); track.classList.add("is-drag"); e.preventDefault(); return; }
      sc.scrollBy({ left: (e.clientX < r.left ? -1 : 1) * sc.clientWidth * 0.8, behavior: "smooth" });
    };
    const move = (e: PointerEvent) => {
      if (!drag) return;
      const th = (track.firstElementChild as HTMLElement).offsetWidth, room = track.clientWidth - th;
      if (room > 0) sc.scrollLeft = drag.sl + (e.clientX - drag.x) * (sc.scrollWidth - sc.clientWidth) / room;
    };
    const up = () => { drag = null; track.classList.remove("is-drag"); };
    track.addEventListener("pointerdown", down); track.addEventListener("pointermove", move);
    track.addEventListener("pointerup", up); track.addEventListener("pointercancel", up);
    const queue = () => { if (!raf) raf = requestAnimationFrame(paint); };
    paint();
    sc.addEventListener("scroll", queue, { passive: true });
    window.addEventListener("resize", queue);
    const ro = new ResizeObserver(queue); ro.observe(sc); if (sc.firstElementChild) ro.observe(sc.firstElementChild);
    return () => { cancelAnimationFrame(raf); ro.disconnect(); sc.removeEventListener("scroll", queue); window.removeEventListener("resize", queue); track.removeEventListener("pointerdown", down); track.removeEventListener("pointermove", move); track.removeEventListener("pointerup", up); track.removeEventListener("pointercancel", up); };
  }, [rows.length, geo.cols]);
  return <div className="ag-wrap"><div className="ag-view"><div className="scroller ag-scroller" ref={scroller}>
    <div className="sched dyn" id="sched" ref={sched} role="group" aria-label="Lezioni per tutor e orario" style={{ "--cols": geo.cols } as React.CSSProperties}>
      <div className="c-name corner" style={{ gridRow: 1 }}>Tutor</div>
      {slots.map((m, i) => <div key={m} className={"c-head" + (i === nowCol ? " is-now" : "")} style={{ gridColumn: `${col(m)} / span 2` }} data-min={m}>{i === nowCol && <span>Ora</span>}{hm(m)}</div>)}
      {rows.map((t, ri) => {
        const row = ri + 2, mine = lessons.filter((l) => l.tutor === t.id && l.state === "PUBLISHED");
        const mins = mine.reduce((a, l) => a + (lmin(l).e - lmin(l).s), 0), av = avail(t.id);
        const cells: React.ReactNode[] = [];
        for (let i = 0; i < slots.length;) {
          const s = slots[i]; const w = av.why(s);
          if (w) { let j = i; while (j + 1 < slots.length && av.why(slots[j + 1]) === w) j++; const span = j - i + 1;
            cells.push(<div key={s} className={"cell off" + (span > 1 ? " span" : "")} style={{ gridRow: row, gridColumn: `${col(s)} / span ${span * 2}` }} aria-label={`${t.name}: ${w.toLowerCase()} dalle ${hm(s)} alle ${hm(slots[j] + 30)}`}>{span > 2 && <span>{w}</span>}</div>);
            i = j + 1; continue; }
          const past = day < now.date || (isToday && s + 30 <= now.min);
          cells.push(<div key={s} className={"cell" + (past ? " past" : "")} style={{ gridRow: row, gridColumn: `${col(s)} / span 2` }} />); i++;
        }
        return [<button key={t.id} className="c-name" style={{ gridRow: row }} data-tutor={t.id} aria-label={`${t.name}, ${plural(mine.length, "lezione", "lezioni")}`} tabIndex={-1}>
          <Avatar name={t.name} k={t.id} /><div><b>{t.name.split(" ")[0]}<span className="ln">{t.name.slice(t.name.split(" ")[0].length)}</span></b><small>{mine.length ? plural(mine.length, "lezione", "lezioni") : "Nessuna lezione"}</small></div><span className="load">{mins ? duration(mins).replace(" ore", " h").replace(" ora", " h") : ""}</span></button>,
          ...cells,
          ...lessons.filter((l) => l.tutor === t.id).map((l, li) => {
            const m = lmin(l), len = (m.e - m.s) / Q, nowIso = new Date();
            const done = new Date(l.end_at) <= nowIso, liveNow = new Date(l.start_at) <= nowIso && !done, cancelled = l.state === "CANCELLED";
            const movable = !cancelled && new Date(l.start_at) > nowIso, tc = l.time_change, dc = drafts?.get(l.id);
            const dcls = !dc ? "" : dc.op === "cancel" ? " d-cancel" : dc.op === "modify" && !dc.target ? " d-mod" : " d-from";
            const label = `${l.subject_name}, ${isGroup(l) ? "gruppo" : "individuale"}, ${(MODE[l.mode] || l.mode).toLowerCase()}, ${l.participants.map((p) => p.name).join(", ")}, con ${t.name}, ${rangeOf(l.start_at, l.end_at)}${cancelled ? ", cancellata" : done ? ", svolta" : liveNow ? ", in corso" : ""}${tc ? `, modifica a ${rangeOf(tc.start_at, tc.end_at)} in attesa di conferma` : ""}${dc ? `, rettifica in bozza: ${dc.summary}` : ""}`;
            const pend = tc && rome(tc.start_at).date === day ? (() => { const a = rome(tc.start_at).min, b = rome(tc.end_at).min; return <span key={l.id + ":p"} className="les-pend" aria-hidden="true" style={{ gridRow: row, gridColumn: `${col(a)} / span ${Math.max(1, (b - a) / Q)}` }}><b>{hm(a)}–{hm(b)}</b><small>in attesa</small></span>; })() : null;
            return [pend, <button key={l.id} data-id={l.id} data-movable={movable ? "1" : undefined} className={`les ${isGroup(l) ? "k-g" : "k-s"} len${Math.max(1, Math.round(len / 2))}${done ? " done" : ""}${cancelled ? " cancelled" : ""}${tc ? " has-pend" : ""}${dcls}${picked === l.id ? " picked" : ""}`}
              style={{ gridRow: row, gridColumn: `${col(m.s)} / span ${Math.max(1, len)}`, "--dl": `${(m.s - geo.open) / Q * 20 + ri * 35 + li * 10}ms` } as React.CSSProperties}
              aria-label={label} aria-keyshortcuts={movable ? "Alt+ArrowLeft Alt+ArrowRight Alt+Shift+ArrowLeft Alt+Shift+ArrowRight" : undefined}>
              {movable && <span className="les-grip s" data-grip="start" aria-hidden="true" />}
              <span className="ic" title={MODE[l.mode] || l.mode}><Icon n={l.mode === "ONLINE" ? "video" : "pin"} /></span>
              <span className="lt"><b>{l.subject_name}</b><small>{isGroup(l) ? plural(l.participants.length, "studente", "studenti") : l.participants[0]?.name || "—"}</small></span>
              {liveNow && !cancelled && <i className="live-dot" aria-hidden="true" />}
              {tc && <i className="pend-dot" aria-hidden="true" title="Modifica in attesa di conferma" />}
              {dc && <i className="draft-dot" aria-hidden="true" title={`In bozza: ${dc.summary}`} />}
              {movable && <span className="les-grip e" data-grip="end" aria-hidden="true" />}
            </button>];
          }),
          ...ghosts.filter((g) => g.tutor === t.id).map((g) => {
            const a = rome(g.start_at).min, b = rome(g.end_at).min, len = (b - a) / Q;
            return <button key={g.key} type="button" className={`les ghost-d${g.kind === "review" ? " review" : ""} ${g.group ? "k-g" : "k-s"} len${Math.max(1, Math.round(len / 2))}`} onClick={() => onGhost?.(g)}
              style={{ gridRow: row, gridColumn: `${col(a)} / span ${Math.max(1, len)}` }} aria-label={`In bozza: ${g.subject}, ${g.who}, ${hm(a)}–${hm(b)}${g.corr ? ", " + g.corr.summary : g.kind === "review" ? ", richiesta in verifica" : ", bozza mensile"}`}>
              <span className="ic"><Icon n={g.kind === "review" ? "clock" : g.kind === "new" ? "plus" : "move"} /></span>
              <span className="lt"><b>{g.subject}</b><small>{g.who}</small></span>
            </button>;
          })];
      })}
      <div className="nowlayer" aria-hidden="true"><i className="nowline" hidden={nowCol < 0} style={{ transform: `translateX(calc(${t} * (100% - ${gaps}px) + ${passed}px))` }} /></div>
    </div>
  </div><div className="ag-blur" aria-hidden="true" /></div><div className="ag-bar" ref={bar} aria-hidden="true"><i /></div></div>;
}

/* Gesti: trascina lungo la riga per spostare (mouse dopo 6 px, touch con pressione lunga) o tira un bordo
 * per cambiare la durata. Al rilascio non si apre nessun menu: la modifica parte come proposta da confermare
 * (onDrag). Il clic semplice apre la scheda della lezione. */
function useGestures(sched: React.RefObject<HTMLDivElement | null>, scroller: React.RefObject<HTMLDivElement | null>, live: React.RefObject<{ lessons: Lesson[]; geo: Geo; day: string; onDrag: (l: Lesson, s: number, e: number) => void; onOpen: (l: Lesson, mod?: boolean) => void; onRefuse: (m: string) => void; onCreate?: (tutor: string, start: number, end: number) => void; blockedAt: (tid: string, a: number, b: number) => string }>) {
  useEffect(() => {
    const el = sched.current!; if (!el) return;
    type G = { l: Lesson; el: HTMLElement; x0: number; y0: number; on: boolean; touch: boolean; kind: "move" | "start" | "end"; timer?: number; ghost?: HTMLElement; ox?: number; oy?: number; lift?: number; heads?: DOMRect[]; sl0?: number; target?: number; end?: number; row?: string; ok?: boolean; col0?: string };
    let G: G | null = null, justEnded = false, zone: HTMLElement | null = null;
    const L = () => live.current!;
    const lesson = (id?: string) => L().lessons.find((x) => x.id === id);
    const vib = () => { try { navigator.vibrate?.(8); } catch { /* */ } };
    const showZone = (tid: string, s: number, len: number, state: string, label: string) => {
      const rows = [...el.querySelectorAll<HTMLElement>(".c-name[data-tutor]")];
      const fresh = !zone || !el.contains(zone);
      if (fresh) { zone = document.createElement("div"); zone.className = "zone instant"; zone.setAttribute("aria-hidden", "true"); zone.style.gridRow = `2 / span ${rows.length}`; zone.style.gridColumn = "2 / -1"; zone.innerHTML = '<span class="zl"></span>'; el.appendChild(zone); }
      const z = zone!; z.dataset.state = state; (z.firstChild as HTMLElement).innerHTML = label;
      const zr = z.getBoundingClientRect(), heads = [...el.querySelectorAll<HTMLElement>(".c-head")];
      const g = L().geo, hi = Math.max(0, Math.min(heads.length - 1, Math.floor((s - g.open) / 30))), he = Math.max(0, Math.min(heads.length - 1, Math.ceil((s + len - g.open) / 30) - 1));
      const a = heads[hi].getBoundingClientRect(), b = heads[he].getBoundingClientRect(), rr = rows.find((x) => x.dataset.tutor === tid)!.getBoundingClientRect();
      const fa = ((s - g.open) % 30) / 30, fb = ((s + len - g.open) % 30) / 30;
      const Lp = a.left - zr.left + fa * a.width, R = zr.right - b.right + (fb ? (1 - fb) * b.width : 0), T = rr.top - zr.top, B = zr.bottom - rr.bottom;
      z.style.setProperty("--l", Lp + "px"); z.style.setProperty("--r", R + "px"); z.style.setProperty("--t", T + "px"); z.style.setProperty("--b", B + "px");
      z.style.setProperty("--cx", Lp + (zr.width - Lp - R) / 2 + "px"); z.style.setProperty("--cy", T + rr.height / 2 + "px");
      if (fresh) { void z.offsetWidth; z.classList.remove("instant"); z.classList.add("show"); }
    };
    const hideZone = (keep = 160) => { const z = zone; zone = null; if (!z) return; z.classList.remove("show"); setTimeout(() => z.remove(), keep); };
    const conflict = (l: Lesson, s: number, e = s + (lmin(l).e - lmin(l).s)) => {
      const m = lmin(l), ids = new Set(l.participants.map((p) => p.student_id));
      return L().lessons.find((o) => o.id !== l.id && o.state === "PUBLISHED" && lmin(o).date === m.date && (o.tutor === l.tutor || o.participants.some((p) => ids.has(p.student_id))) && overlap(s, e, lmin(o).s, lmin(o).e));
    };
    const activate = () => {
      const g = G!; g.on = true; document.body.classList.add("dragging"); el.querySelectorAll(".pressing").forEach((x) => x.classList.remove("pressing"));
      if (g.touch) vib();
      if (g.kind !== "move") { // ridimensionamento: il blocco stesso si allunga/accorcia, nessun «fantasma»
        Object.assign(g, { heads: [...el.querySelectorAll<HTMLElement>(".c-head")].map((h) => h.getBoundingClientRect()), sl0: scroller.current!.scrollLeft, col0: g.el.style.gridColumn });
        g.el.classList.add("resizing"); resizeTo(g.x0); return;
      }
      const r = g.el.getBoundingClientRect(), ghost = g.el.cloneNode(true) as HTMLElement;
      ghost.classList.add("drag-ghost"); if (g.touch) ghost.classList.add("touch"); ghost.removeAttribute("data-id"); ghost.setAttribute("aria-hidden", "true"); ghost.inert = true;
      Object.assign(ghost.style, { width: r.width + "px", height: r.height + "px", gridRow: "", gridColumn: "" });
      document.body.appendChild(ghost); g.el.classList.add("lifted");
      Object.assign(g, { ghost, ox: g.x0 - r.left, oy: g.y0 - r.top + (g.touch ? 28 : 0), lift: g.touch ? -28 : 0, heads: [...el.querySelectorAll<HTMLElement>(".c-head")].map((h) => h.getBoundingClientRect()), sl0: scroller.current!.scrollLeft });
      moveTo(g.x0, g.y0);
    };
    const moveTo = (x: number, y: number) => {
      const g = G!; if (!g.ghost) return;
      const sc = scroller.current!, sr = sc.getBoundingClientRect(), nameW = matchMedia("(max-width:767px)").matches ? 150 : 232;
      if (x > sr.right - 48) sc.scrollLeft += 14; else if (x < sr.left + nameW + 40) sc.scrollLeft -= 14;
      const gx = x - g.ox!, gy = y - g.oy!; g.ghost.style.transform = `translate(${gx}px,${gy}px) scale(1.02)`;
      const dsc = sc.scrollLeft - g.sl0!, h0 = g.heads![0], geo = L().geo;
      const per = (g.heads![1] ? g.heads![1].left - h0.left : h0.width + 8) / 30; // px per minuto, gap incluso
      const m = lmin(g.l), dur = m.e - m.s;
      let s = geo.open + Math.round(((gx + dsc - (h0.left)) / per) / Q) * Q;
      s = Math.max(geo.open, Math.min(geo.close - dur, s));
      const rows = [...el.querySelectorAll<HTMLElement>(".c-name[data-tutor]")];
      const ry = y - (g.lift || 0); const row = rows.find((n) => { const b = n.getBoundingClientRect(); return ry >= b.top - 4 && ry <= b.bottom + 4; })?.dataset.tutor || g.l.tutor;
      g.target = s; g.row = row;
      const past = new Date(romeISO(m.date, s)) <= new Date();
      const c = row === g.l.tutor ? conflict(g.l, s) : undefined;
      g.ok = row === g.l.tutor && !c && !past;
      showZone(row, s, dur, g.ok ? "ok" : "bad", row !== g.l.tutor ? "Tutor invariato<small>lo spostamento mantiene il tutor</small>" : past ? `Orario passato<small>${hm(s)}</small>` : c ? `Occupato<small>${hm(s)}–${hm(s + dur)}</small>` : `${hm(s)}–${hm(s + dur)}<small>${duration(dur)}</small>`);
    };
    const resizeTo = (x: number) => {
      const g = G!, sc = scroller.current!, geo = L().geo, h0 = g.heads![0];
      const per = (g.heads![1] ? g.heads![1].left - h0.left : h0.width + 8) / 30;
      const minute = geo.open + Math.round(((x + sc.scrollLeft - g.sl0! - h0.left) / per) / Q) * Q;
      const m = lmin(g.l);
      let s = m.s, e = m.e;
      if (g.kind === "end") e = Math.max(s + 30, Math.min(geo.close, minute)); else s = Math.min(e - 30, Math.max(geo.open, minute));
      g.target = s; g.end = e; g.row = g.l.tutor;
      g.el.style.gridColumn = `${Math.round((s - geo.open) / Q) + 2} / span ${Math.max(1, (e - s) / Q)}`;
      const past = new Date(romeISO(m.date, s)) <= new Date(), c = conflict(g.l, s, e);
      g.ok = !c && !past;
      showZone(g.l.tutor, s, e - s, g.ok ? "ok" : "bad", past ? `Orario passato<small>${hm(s)}</small>` : c ? `Occupato<small>${hm(s)}–${hm(e)}</small>` : `${hm(s)}–${hm(e)}<small>${duration(e - s)}</small>`);
    };
    const end = () => {
      const g = G; G = null; if (!g) return;
      clearTimeout(g.timer); document.body.classList.remove("dragging"); el.querySelectorAll(".pressing").forEach((x) => x.classList.remove("pressing"));
      if (!g.on) return;
      justEnded = true; setTimeout(() => (justEnded = false), 80);
      if (g.kind !== "move") {
        const m = lmin(g.l), changed = g.target !== m.s || g.end !== m.e;
        g.el.classList.remove("resizing"); hideZone();
        g.el.style.gridColumn = g.col0 || ""; // la lezione resta dov’è finché la modifica non è confermata
        if (!changed || !g.ok) { if (changed) L().onRefuse("In quell’orario il tutor o uno studente è già impegnato, oppure l’orario è passato."); return; }
        L().onDrag(g.l, g.target!, g.end!); return;
      }
      const m = lmin(g.l), changed = g.target !== undefined && g.target !== m.s;
      const back = () => { const b = g.el.getBoundingClientRect(); const a = g.ghost!.animate([{ transform: g.ghost!.style.transform }, { transform: `translate(${b.left}px,${b.top}px)` }], { duration: motionOK() ? 240 : 1, easing: EASE }); a.onfinish = () => { g.ghost!.remove(); g.el.classList.remove("lifted"); }; };
      if (g.row !== g.l.tutor) { hideZone(); back(); L().onRefuse("Lo spostamento mantiene tutor, durata e partecipanti: si può cambiare solo l’orario o il giorno."); return; }
      if (!changed) { hideZone(); back(); return; }
      if (!g.ok) { hideZone(); back(); L().onRefuse(new Date(romeISO(m.date, g.target!)) <= new Date() ? "Non si può spostare una lezione nel passato." : "In quell’orario il tutor o uno studente è già impegnato. Scegli un altro orario."); return; }
      setTimeout(() => hideZone(), 260); back(); L().onDrag(g.l, g.target!, g.target! + (m.e - m.s));
    };
    const cancelG = () => { const g = G; G = null; if (!g) return; clearTimeout(g.timer); document.body.classList.remove("dragging"); g.ghost?.remove(); g.el.classList.remove("lifted", "pressing", "resizing"); if (g.kind !== "move" && g.on) g.el.style.gridColumn = g.col0 || ""; hideZone(); };
    const start = (target: EventTarget | null, x: number, y: number, touch: boolean) => {
      const b = (target as HTMLElement).closest<HTMLElement>(".les[data-movable]"); if (!b) return false;
      const l = lesson(b.dataset.id); if (!l) return false;
      const grip = (target as HTMLElement).closest<HTMLElement>("[data-grip]")?.dataset.grip as "start" | "end" | undefined;
      G = { l, el: b, x0: x, y0: y, on: false, touch, kind: grip || "move" }; return true;
    };
    /** Trascinando su celle vuote di un tutor si disegna una nuova lezione (mouse e penna). */
    const minuteAt = (x: number) => {
      const heads = [...el.querySelectorAll<HTMLElement>(".c-head")].map((h) => h.getBoundingClientRect()), h0 = heads[0], geo = L().geo;
      const per = (heads[1] ? heads[1].left - h0.left : h0.width + 8) / 30;
      return Math.max(geo.open, Math.min(geo.close, geo.open + Math.round(((x - h0.left) / per) / Q) * Q));
    };
    const draw = (e: PointerEvent) => {
      const t = e.target as HTMLElement;
      if (!L().onCreate || t.closest(".les, .les-pend, .c-name, .c-head, button, a")) return false;
      const rows = [...el.querySelectorAll<HTMLElement>(".c-name[data-tutor]")];
      const tutor = rows.find((n) => { const b = n.getBoundingClientRect(); return e.clientY >= b.top - 2 && e.clientY <= b.bottom + 2; })?.dataset.tutor;
      if (!tutor) return false;
      const x0 = e.clientX, a0 = Math.floor((minuteAt(x0) - L().geo.open) / Q) * Q + L().geo.open;
      let on = false, s = a0, en = a0 + 60;
      const busy = (a: number, b: number) => L().lessons.some((o) => o.state === "PUBLISHED" && o.tutor === tutor && overlap(a, b, lmin(o).s, lmin(o).e));
      const past = (a: number) => new Date(romeISO(L().day, a)) <= new Date();
      const mv = (ev: PointerEvent) => {
        if (!on) { if (Math.abs(ev.clientX - x0) < 8) return; on = true; document.body.classList.add("dragging"); }
        ev.preventDefault();
        const m = minuteAt(ev.clientX);
        if (m >= a0) { s = a0; en = Math.max(a0 + 30, m); } else { s = m; en = a0 + Q; }
        const bad = busy(s, en) ? "Tutor già occupato" : past(s) ? "Orario passato" : L().blockedAt(tutor, s, en);
        showZone(tutor, s, en - s, bad ? "bad" : "ok", bad ? `${bad}<small>${hm(s)}–${hm(en)}</small>` : `Nuova lezione<small>${hm(s)}–${hm(en)} · ${duration(en - s)}</small>`);
      };
      const up = () => {
        removeEventListener("pointermove", mv); removeEventListener("pointerup", up); removeEventListener("pointercancel", cc);
        document.body.classList.remove("dragging"); if (!on) return;
        justEnded = true; setTimeout(() => (justEnded = false), 80); hideZone();
        if (past(s)) { L().onRefuse("Non si può creare una lezione nel passato."); return; }
        if (busy(s, en)) { L().onRefuse("In quell’orario il tutor ha già una lezione."); return; }
        const why = L().blockedAt(tutor, s, en);
        if (why) { L().onRefuse(why === "Centro chiuso" ? "Non si può creare una lezione quando il centro è chiuso." : `Non si può creare la lezione: ${why.charAt(0).toLowerCase() + why.slice(1)}.`); return; }
        L().onCreate!(tutor, s, en);
      };
      const cc = () => { removeEventListener("pointermove", mv); removeEventListener("pointerup", up); removeEventListener("pointercancel", cc); document.body.classList.remove("dragging"); hideZone(); };
      addEventListener("pointermove", mv); addEventListener("pointerup", up); addEventListener("pointercancel", cc);
      return true;
    };
    const onDown = (e: PointerEvent) => {
      if (e.button !== 0 || e.pointerType === "touch") return;
      if (!start(e.target, e.clientX, e.clientY, false)) { if (draw(e)) e.preventDefault(); return; }
      const mv = (ev: PointerEvent) => { if (!G) return; if (!G.on) { if (Math.hypot(ev.clientX - G.x0, ev.clientY - G.y0) < (G.kind === "move" ? 6 : 3)) return; activate(); } ev.preventDefault(); if (G.kind === "move") moveTo(ev.clientX, ev.clientY); else resizeTo(ev.clientX); };
      const up = () => { removeEventListener("pointermove", mv); removeEventListener("pointerup", up); removeEventListener("pointercancel", cc); end(); };
      const cc = () => { removeEventListener("pointermove", mv); removeEventListener("pointerup", up); removeEventListener("pointercancel", cc); cancelG(); };
      addEventListener("pointermove", mv); addEventListener("pointerup", up); addEventListener("pointercancel", cc);
    };
    const onTouchStart = (e: TouchEvent) => {
      if (e.touches.length > 1) { cancelG(); return; }
      const t = e.touches[0]; if (!start(e.target, t.clientX, t.clientY, true)) return;
      const g = G!; g.el.classList.add("pressing");
      g.timer = window.setTimeout(() => { if (G === g && !g.on) activate(); }, 320);
    };
    const onTouchMove = (e: TouchEvent) => { if (!G) return; const t = e.touches[0]; if (G.on) { e.preventDefault(); if (G.kind === "move") moveTo(t.clientX, t.clientY); else resizeTo(t.clientX); } else if (Math.hypot(t.clientX - G.x0, t.clientY - G.y0) > 10) cancelG(); };
    const onTouchEnd = (e: TouchEvent) => { if (!G) return; if (G.on) { e.preventDefault(); end(); } else { clearTimeout(G.timer); G.el.classList.remove("pressing"); G = null; } };
    const onClick = (e: MouseEvent) => { if (justEnded) return; const b = (e.target as HTMLElement).closest<HTMLElement>(".les"); const l = b && lesson(b.dataset.id); if (l) L().onOpen(l, e.ctrlKey || e.metaKey); };
    const onKey = (e: KeyboardEvent) => {
      const b = (e.target as HTMLElement).closest<HTMLElement>(".les[data-movable]"); if (!b || !e.altKey || !["ArrowLeft", "ArrowRight"].includes(e.key)) return;
      e.preventDefault(); const l = lesson(b.dataset.id)!, m = lmin(l), d = e.key === "ArrowRight" ? Q : -Q;
      if (e.shiftKey) { if (m.e + d - m.s >= 30) L().onDrag(l, m.s, m.e + d); return; } // Alt+Maiusc: durata
      L().onDrag(l, m.s + 2 * d, m.e + 2 * d);
    };
    const onCtx = (e: Event) => { if (G || ((e.target as HTMLElement).closest(".les") && matchMedia("(hover:none)").matches)) e.preventDefault(); };
    el.addEventListener("pointerdown", onDown); el.addEventListener("touchstart", onTouchStart, { passive: true });
    document.addEventListener("touchmove", onTouchMove, { passive: false }); document.addEventListener("touchend", onTouchEnd, { passive: false }); document.addEventListener("touchcancel", cancelG);
    el.addEventListener("click", onClick); el.addEventListener("keydown", onKey); el.addEventListener("contextmenu", onCtx);
    return () => {
      el.removeEventListener("pointerdown", onDown); el.removeEventListener("touchstart", onTouchStart);
      document.removeEventListener("touchmove", onTouchMove); document.removeEventListener("touchend", onTouchEnd); document.removeEventListener("touchcancel", cancelG);
      el.removeEventListener("click", onClick); el.removeEventListener("keydown", onKey); el.removeEventListener("contextmenu", onCtx); cancelG();
    };
  }, [sched, scroller, live]);
}

/* ------------------------------ scheda lezione ------------------------------ */
type Propose = (body: Record<string, unknown>, what: string) => Promise<void>;
function LessonSheet({ l, lessons, corr, propose, onDraftChanged, onDone, onClose, onMove, onCancel, onConfirmChange, onWithdrawChange }: { l: Lesson | null; lessons: Lesson[]; corr: Correction | null; propose: Propose; onDraftChanged: (m: MonthState | null, msg: string) => Promise<void>; onDone: (msg: string) => Promise<void>; onClose: () => void; onMove: (l: Lesson) => void; onCancel: (l: Lesson) => void; onConfirmChange: (id: string) => void; onWithdrawChange: (id: string) => void }) {
  const [last, setLast] = useState(l); useEffect(() => { if (l) setLast(l); }, [l]);
  const x = l || last;
  const future = x ? new Date(x.start_at) > new Date() : false, active = x?.state === "PUBLISHED";
  const toast = useToast();
  return <Sheet open={!!l} onClose={onClose} labelledBy="sheet-l">{x && <>
    <div className="sheet-body">
      <div className="sheet-top"><div className="kind"><Tag tone={isGroup(x) ? "violet" : "blue"}>{isGroup(x) ? "Gruppo" : "Individuale"}</Tag><State s={x.state} />{active && !future && <Tag tone="plain">Svolta</Tag>}</div><button className="circle sm raised" aria-label="Chiudi" onClick={onClose}><Icon n="x" /></button></div>
      <h2 id="sheet-l">{x.subject_name}</h2>
      <p className="muted" style={{ marginTop: 6 }}>{x.participants.map((p) => p.name).join(", ")}</p>
      <dl className="facts">
        <dt>Quando</dt><dd>{dayLabel(rome(x.start_at).date)}, {rangeOf(x.start_at, x.end_at)}</dd>
        <dt>Durata</dt><dd>{duration((new Date(x.end_at).getTime() - new Date(x.start_at).getTime()) / 60000)}</dd>
        <dt>Tutor</dt><dd><span className="chip"><Avatar name={x.tutor_name} k={x.tutor} size={24} />{x.tutor_name}</span></dd>
        <dt>Modalità</dt><dd>{MODE[x.mode] || x.mode}, {(LOCATION[x.location] || x.location).toLowerCase()}</dd>
      </dl>
      <h3>{isGroup(x) ? "Partecipanti" : "Studente"}</h3>
      <div className="pop-list">{x.participants.map((p) => <a key={p.student_id} className="pop-item" href={`#/studenti?s=${p.student_id}`}><Avatar name={p.name} k={p.student_id} /><div><b>{p.name}</b><small>Apri la scheda</small></div></a>)}</div>
      {active && corr && <DraftNote c={corr} onChanged={onDraftChanged} toast={toast} />}
      {active && x.time_change && <PendingChange c={x.time_change} onConfirm={() => onConfirmChange(x.time_change!.id)} onWithdraw={() => onWithdrawChange(x.time_change!.id)} />}
      {!active ? <Notice kind="info">Lezione cancellata: resta nello storico e non occupa più tutor, spazi e studenti.</Notice> : !future && <Notice kind="info">La lezione è già iniziata: non si può più spostare o cancellare.</Notice>}
      <LessonActions key={x.id + ":" + x.version} l={x} lessons={lessons} onDone={onDone} propose={async (b, w) => { await propose(b, w); onClose(); }} />
      <Tech><dl className="facts"><dt>ID</dt><dd><code>{x.id}</code></dd><dt>Versione</dt><dd>{x.version}</dd>{x.demand_key && <><dt>Unità</dt><dd><code>{x.demand_key}</code></dd></>}{x.space && <><dt>Spazio</dt><dd><code>{x.space}</code></dd></>}</dl></Tech>
    </div>
    {active && future && <div className="sheet-foot"><Btn kind="ghost" icon="move" onClick={() => onMove(x)}>Sposta</Btn><span className="grow" /><Btn kind="danger" onClick={() => onCancel(x)}>Cancella lezione</Btn></div>}
  </>}</Sheet>;
}

/** Modifica proposta con il drag & drop: chi deve ancora rispondere, e override del centro. */
function PendingChange({ c, onConfirm, onWithdraw }: { c: NonNullable<Lesson["time_change"]>; onConfirm: () => void; onWithdraw: () => void }) {
  const waiting = c.answers.filter((a) => a.status === "PENDING");
  return <div className="pend-box" role="status">
    <div className="pend-head"><span className="oc-ic amber"><Icon n="clock" /></span><div><b>Modifica in attesa di conferma</b><small>{dayLabel(rome(c.start_at).date)}, {rangeOf(c.start_at, c.end_at)} · {duration((new Date(c.end_at).getTime() - new Date(c.start_at).getTime()) / 60000)}</small></div></div>
    <ul className="pend-who">{c.answers.map((a, i) => <li key={i}><span>{a.who}<small>{a.party === "TUTOR" ? "tutor" : "famiglia"}</small></span><Tag tone={a.status === "ACCEPTED" ? "green" : a.status === "REJECTED" ? "red" : "amber"}>{a.status === "ACCEPTED" ? "Ha accettato" : a.status === "REJECTED" ? "Ha rifiutato" : "Deve rispondere"}</Tag></li>)}</ul>
    
    <div className="toolbar"><Btn kind="ghost" onClick={onWithdraw}>Ritira proposta</Btn><Btn kind="primary" isle="check" onClick={onConfirm}>Conferma subito</Btn></div>
  </div>;
}

/* ------------------------------ sposta ------------------------------ */
function MoveModal({ m, week, onClose, propose }: { m: { l: Lesson; date: string; start: number } | null; week: Lesson[]; onClose: () => void; propose: Propose }) {
  const [v, setV] = useState({ date: "", start: 0 }), [err, setErr] = useState(""), [busy, setBusy] = useState(false), [now_, setNow] = useState(false);
  const pending = useRef<{ key: string; body: string } | null>(null);
  const [last, setLast] = useState(m);
  // Opzioni calcolate dal server (validatore indipendente, nessun effetto): data → minuto → codici.
  const [opts, setOpts] = useState<{ id: string; v: number; by: Record<string, Record<number, string[]>> }>({ id: "", v: 0, by: {} });
  const lid = (m || last)?.l.id || "", lver = (m || last)?.l.version || 0;
  useEffect(() => {
    if (!m || !lid) return;
    let live = true;
    const wk0 = mondayOf(rome(m.l.start_at).date), today0 = rome(new Date()).date;
    const all = Array.from({ length: 7 }, (_, i) => addDays(wk0, i)).filter((dd) => dd >= today0);
    setOpts({ id: lid, v: lver, by: {} });
    for (const dd of all) {
      api<{ options: { start_at: string; ok: boolean; codes: string[] }[] }>(`/occurrences/${lid}/reschedule-options/?date=${dd}`).then((r) => {
        if (!live) return;
        const map: Record<number, string[]> = {};
        for (const op of r.options) { const t = rome(op.start_at); if (t.date === dd) map[t.min] = op.codes; }
        setOpts((p) => (p.id === lid && p.v === lver ? { ...p, by: { ...p.by, [dd]: map } } : p));
      }).catch(() => { /* fallback: controlli locali e verifica finale del server */ });
    }
    return () => { live = false; };
  }, [m, lid, lver]);
  if (m && m !== last) { setLast(m); setV({ date: m.date, start: m.start }); setErr(""); setNow(false); pending.current = null; return null; }
  const x = m || last; if (!x || !v.date) return null;
  const l = x.l, o = lmin(l), dur = o.e - o.s, wk = mondayOf(o.date), now = new Date();
  const days = Array.from({ length: 7 }, (_, i) => addDays(wk, i)).filter((dd) => dd >= rome(now).date);
  const server = opts.id === l.id ? opts.by : {};
  const why = (date: string, s: number) => { const codes = server[date]?.[s]; return date === o.date && s === o.s ? [] : codes || []; };
  const freeCount = (date: string) => { const mm = server[date]; return mm ? Object.entries(mm).filter(([k, cs]) => !cs.length && +k >= 7 * 60 && +k + dur <= 22 * 60).length : -1; };
  const ids = new Set(l.participants.map((p) => p.student_id));
  const clash = (date: string, s: number) => week.find((w) => w.id !== l.id && w.state === "PUBLISHED" && lmin(w).date === date && (w.tutor === l.tutor || w.participants.some((p) => ids.has(p.student_id))) && overlap(s, s + dur, lmin(w).s, lmin(w).e));
  const isPast = (date: string, s: number) => new Date(romeISO(date, s)) <= now;
  const items = Array.from({ length: (22 * 60 - dur - 7 * 60) / Q + 1 }, (_, i) => 7 * 60 + i * Q).map((s) => ({ v: s, label: hm(s), busy: !!clash(v.date, s) || isPast(v.date, s) || why(v.date, s).length > 0 }));
  const c = clash(v.date, v.start), past = isPast(v.date, v.start), same = v.date === o.date && v.start === o.s;
  const blocked = !c && !past ? reasons(why(v.date, v.start)) : [], checking = !server[v.date];
  const free = items.filter((it) => !it.busy).sort((a, b) => Math.abs(a.v - v.start) - Math.abs(b.v - v.start))[0];
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (c || past || same || blocked.length) return;
    setBusy(true); setErr("");
    try {
      await propose({ op: "reschedule", lesson_id: l.id, start_at: romeISO(v.date, v.start), end_at: romeISO(v.date, v.start + dur), publish_now: now_ }, `${l.subject_name} ${dayLabel(v.date).toLowerCase()} alle ${hm(v.start)}`);
      onClose();
    } catch (er) { setErr(human(er).text); } finally { setBusy(false); }
  }
  return <Modal open={!!m} onClose={onClose} labelledBy="mv-title"><form onSubmit={submit} noValidate>
    <div className="modal-body">
      <h2 id="mv-title">Sposta la lezione</h2>
      <p className="lead">{l.subject_name} con {l.tutor_name}.</p>
      <Field label="Giorno (stessa settimana)"><Choices label="Giorno" value={v.date} options={days.map((dd) => { const n = freeCount(dd); return { v: dd, label: dayShort(dd) + (n === 0 ? " · pieno" : "") }; })} onChange={(dd) => setV({ ...v, date: dd })} /></Field>
      <div className="when" role="group" aria-labelledby="mv-when">
        <div className="when-top"><b id="mv-when" className="num" aria-live="polite">{hm(v.start)}–{hm(v.start + dur)}</b><small>{same ? "Orario attuale" : `Prima: ${dayShort(o.date).toLowerCase()}, ${hm(o.s)}`}</small></div>
        <div className="wheels one"><div className="wheel-col"><span>Inizio</span><Wheel label="Inizio" items={items} value={v.start} onChange={(s) => setV((p) => ({ ...p, start: s }))} /></div></div>
      </div>
      {(c || past) && <div className="conflict show" role="alert">{past ? "Quell’orario è già passato." : c!.tutor === l.tutor ? `${l.tutor_name} ha già ${c!.subject_name} dalle ${timeOf(c!.start_at)}.` : `Uno studente ha già ${c!.subject_name} dalle ${timeOf(c!.start_at)}.`}{free && <> Puoi <button type="button" onClick={() => setV({ ...v, start: free.v })}>usare le {free.label}</button>.</>}</div>}
      {blocked.length > 0 && <div className="conflict show" role="alert">Non si può: {blocked.join("; ")}.{free ? <> Puoi <button type="button" onClick={() => setV({ ...v, start: free.v })}>usare le {free.label}</button>.</> : " Nessun orario libero in questo giorno: prova un altro giorno."}</div>}
      {!c && !past && !blocked.length && !same && <p className="mv-hint" aria-live="polite">{checking ? "Verifico gli orari disponibili…" : "Orario compatibile."}</p>}
      <Check checked={now_} onChange={setNow}>Pubblica subito la rettifica</Check>
      
      {err && <Notice kind="bad">{err}</Notice>}
    </div>
    <div className="modal-foot"><button type="button" className="pill-btn ghost" onClick={onClose}>Chiudi</button>
      <button className="pill-btn primary island" disabled={busy || !!c || past || same || blocked.length > 0}>{busy ? "Verifica e salvataggio…" : now_ ? "Sposta e pubblica" : "Salva in bozza"}<span className="isle"><Icon n="check" /></span></button></div>
  </form></Modal>;
}
const timeOf = (i: string) => hm(rome(i).min);

/* ------------------------------ cancella ------------------------------ */
function CancelModal({ l, onClose, propose }: { l: Lesson | null; onClose: () => void; propose: Propose }) {
  const [err, setErr] = useState(""), [busy, setBusy] = useState(false), [now_, setNow] = useState(false);
  const [last, setLast] = useState(l); useEffect(() => { if (l) { setLast(l); setErr(""); setNow(false); } }, [l]);
  const x = l || last; if (!x) return null;
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setErr("");
    try {
      await propose({ op: "cancel", lesson_id: x!.id, publish_now: now_ }, `Cancellazione di ${x!.subject_name}, ${dayLabel(rome(x!.start_at).date).toLowerCase()}`);
      onClose();
    } catch (er) { setErr(human(er).text); } finally { setBusy(false); }
  }
  return <Modal open={!!l} onClose={onClose} labelledBy="cl-title"><form onSubmit={submit} noValidate>
    <div className="modal-body">
      <h2 id="cl-title">Cancellare la lezione?</h2>
      <p className="lead">{x.subject_name}, {dayLabel(rome(x.start_at).date).toLowerCase()} {rangeOf(x.start_at, x.end_at)}.</p>
      <Check checked={now_} onChange={setNow}>Pubblica subito la rettifica</Check>
      
      {err && <Notice kind="bad">{err}</Notice>}
    </div>
    <div className="modal-foot"><button type="button" className="pill-btn ghost" onClick={onClose}>Non cancellare</button>
      <button className="pill-btn danger" disabled={busy}>{busy ? "Salvataggio…" : now_ ? "Cancella e pubblica" : "Cancella in bozza"}</button></div>
  </form></Modal>;
}
