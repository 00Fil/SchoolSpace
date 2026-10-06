/** v0.9.7: componenti grafici del pianificatore mensile.
 *  - MonthBoard: calendario del mese con le lezioni proposte, per giorno;
 *  - Checklist, PlanSteps, MonthStepper: struttura a passi della pianificazione. */
import { ReactNode } from "react";
import { addDays, monthYear, parse, todayRome, WD_SHORT } from "../format";
import { Icon } from "./core";

export type BoardItem = { id: string; date: string; start: string; title: string; sub?: string; tone: string; badge?: string; muted?: boolean };

/** Calendario mensile: una cella per giorno con le lezioni in ordine di orario. */
export function MonthBoard({ month, items, onPick, closed, max = 4 }: { month: string; items: BoardItem[]; onPick?: (it: BoardItem) => void; closed?: (d: string) => string | null; max?: number }) {
  const first = month + "-01";
  const start = addDays(first, -((parse(first).getUTCDay() + 6) % 7));
  const [yy, mm] = month.split("-").map(Number);
  const lastDay = new Date(Date.UTC(yy, mm, 0)).toISOString().slice(0, 10);
  const weeks = Math.ceil(((parse(lastDay).getTime() - parse(start).getTime()) / 86400000 + 1) / 7);
  const days = Array.from({ length: weeks * 7 }, (_, i) => addDays(start, i));
  const today = todayRome();
  const by = new Map<string, BoardItem[]>();
  for (const it of items) by.set(it.date, [...(by.get(it.date) || []), it]);
  return <div className="mb" role="grid" aria-label={monthYear(month)}>
    <div className="mb-head" role="row">{WD_SHORT.map((w) => <span key={w} role="columnheader">{w}</span>)}</div>
    <div className="mb-grid">
      {days.map((d) => {
        const list = (by.get(d) || []).sort((a, b) => a.start.localeCompare(b.start)), out = d.slice(0, 7) !== month, shut = !out && closed ? closed(d) : null;
        return <div key={d} role="gridcell" className={"mb-day" + (out ? " out" : "") + (d === today ? " today" : "") + (shut ? " shut" : "")} aria-label={`${+d.slice(8)} ${monthYear(month)}${shut ? ", " + shut : ""}, ${list.length} lezioni`}>
          <div className="mb-num"><b>{+d.slice(8)}</b>{shut && <small title={shut}>{shut}</small>}</div>
          {!out && list.slice(0, max).map((it) => <button key={it.id} type="button" className={"mb-it " + it.tone + (it.muted ? " muted" : "")} onClick={() => onPick?.(it)} title={`${it.start} ${it.title}${it.sub ? " · " + it.sub : ""}`}>
            <span className="t">{it.start}</span><span className="n">{it.title}</span>{it.badge && <span className="bd">{it.badge}</span>}
          </button>)}
          {!out && list.length > max && <button type="button" className="mb-more" onClick={() => onPick?.(list[max])}>+{list.length - max} altre</button>}
        </div>;
      })}
    </div>
  </div>;
}

export type CheckItem = { key: string; ok: boolean; blocking: boolean; title: string; text: string; go?: string };
/** Verifica dei dati: una riga per requisito, stato in parole (Completo / Obbligatorio / Consigliato). */
export function Checklist({ items, onGo }: { items: CheckItem[]; onGo?: (key: string) => void }) {
  return <ul className="ck">{items.map((i) => {
    const tone = i.ok ? "ok" : i.blocking ? "bad" : "warn";
    return <li key={i.key} className={"ck-it " + tone}>
      <span className="ck-mark" aria-hidden="true" />
      <div className="ck-txt"><b>{i.title}</b><small>{i.text}</small></div>
      <span className={"ck-state " + tone}>{i.ok ? "Completo" : i.blocking ? "Obbligatorio" : "Consigliato"}</span>
      <span className="ck-act">{i.go && onGo && !i.ok && <button type="button" className="pill-btn sm" onClick={() => onGo(i.go!)}>Apri</button>}</span>
    </li>;
  })}</ul>;
}

/** Passi numerati collegati da una linea; lo stato è scritto, non affidato al colore. */
export function PlanSteps({ steps, current }: { steps: { title: string; sub: string }[]; current: number }) {
  return <ol className="ps" aria-label="Passi della pianificazione">{steps.map((s, i) => {
    const st = i < current ? "done" : i === current ? "cur" : "next";
    return <li key={s.title} className={"ps-it " + st} aria-current={st === "cur" ? "step" : undefined}>
      <span className="ps-n" aria-hidden="true">{i + 1}</span>
      <div><b>{s.title}</b><small>{st === "done" ? "Completato" : st === "cur" ? s.sub : "Da fare"}</small></div>
    </li>;
  })}</ol>;
}

export function MonthStepper({ month, onChange, children }: { month: string; onChange: (m: string) => void; children?: ReactNode }) {
  const shift = (n: number) => { const [y, m] = month.split("-").map(Number); const t = new Date(Date.UTC(y, m - 1 + n, 1)); onChange(t.toISOString().slice(0, 7)); };
  return <div className="ms">
    <button type="button" className="circle raised" aria-label="Mese precedente" onClick={() => shift(-1)}><Icon n="left" /></button>
    <b aria-live="polite">{monthYear(month)}</b>
    <button type="button" className="circle raised" aria-label="Mese successivo" onClick={() => shift(1)}><Icon n="right" /></button>
    {children}
  </div>;
}
