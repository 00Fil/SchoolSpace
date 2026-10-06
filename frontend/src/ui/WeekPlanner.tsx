/** Settimana tipo «drag & drop»: un solo componente per orari del centro, disponibilità e impegni.
 *  - clic o trascinamento su uno spazio vuoto: crea un blocco (il trascinamento ne decide la durata);
 *  - trascina un blocco per spostarlo (anche su un altro giorno), le maniglie sopra/sotto per ridimensionarlo;
 *  - clic su un blocco: dettagli/modifica. Da tastiera: Invio apre, Alt+frecce sposta, Alt+Maiusc+↑/↓ cambia la fine.
 *  Le fasce `bands` (orari di apertura) sono in chiaro; fuori dalle fasce la colonna è tratteggiata. */
import { KeyboardEvent as RKeyboardEvent, PointerEvent as RPointerEvent, ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { WD_LONG, WD_SHORT } from "../format";
import { Btn, Icon } from "./core";
import { Field } from "./controls";
import { Modal } from "./layers";

export type Slot = { weekday: number; start: number; end: number }; // minuti dalla mezzanotte
export type PlanTone = "violet" | "blue" | "amber" | "red" | "green" | "plain";
export type PlanBlock = Slot & { id: string; label?: string; sub?: string; tone?: PlanTone; draft?: boolean; locked?: boolean };

export const fmt = (m: number) => `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
export const fmtEnd = (m: number) => (m >= 1440 ? "24:00" : fmt(m));
export const toMin = (t: string) => (t.startsWith("24:00") || t.startsWith("23:59") ? 1440 : +t.slice(0, 2) * 60 + +t.slice(3, 5));
export const span = (s: Slot) => `${fmt(s.start)}–${fmtEnd(s.end)}`;
export const hoursOf = (min: number) => { const h = Math.floor(min / 60), m = min % 60; return `${h} h${m ? ` ${m} min` : ""}`; };

/** Unisce le fasce sovrapposte o adiacenti dello stesso giorno. */
export function mergeSlots(slots: Slot[]): Slot[] {
  const out: Slot[] = [];
  [...slots].filter((s) => s.end > s.start).sort((a, b) => a.weekday - b.weekday || a.start - b.start).forEach((s) => {
    const last = out[out.length - 1];
    if (last && last.weekday === s.weekday && s.start <= last.end) last.end = Math.max(last.end, s.end);
    else out.push({ ...s });
  });
  return out;
}
/** Minuti di [a,b) coperti dalle fasce `spans` di un giorno. */
export function covered(a: number, b: number, spans: { start: number; end: number }[]) {
  return mergeSlots(spans.map((s) => ({ weekday: 0, ...s }))).reduce((t, s) => t + Math.max(0, Math.min(b, s.end) - Math.max(a, s.start)), 0);
}

type Drag = { kind: "create" | "move" | "top" | "bottom"; id?: string; pointer: string; d0: number; m0: number; x0: number; y0: number; orig: Slot; cur: Slot; moved: boolean };
type Props = {
  label: string; blocks: PlanBlock[]; bands?: Slot[]; from?: number; to?: number; step?: number; days?: number;
  editable?: boolean; newLabel?: string; defaultLength?: number; emptyText?: ReactNode;
  /** Vieta sovrapposizioni tra blocchi dello stesso giorno: creazione e bordi si fermano sul blocco vicino,
   *  uno spostamento sopra un altro blocco viene annullato (e segnalato con `onBlocked`). */
  noOverlap?: boolean; onBlocked?: (message: string) => void;
  onCreate?: (s: Slot) => void; onChange?: (id: string, s: Slot) => void; onPick?: (b: PlanBlock) => void;
};

/** Vero se `s` si sovrappone a un blocco (diverso da `id`) dello stesso giorno. */
export const overlapsAny = (s: Slot, list: Slot[], skip?: (x: Slot) => boolean) =>
  list.some((x) => !skip?.(x) && x.weekday === s.weekday && x.start < s.end && s.start < x.end);

export function WeekPlanner({ label, blocks, bands = [], from, to, step = 15, days = 7, editable = false, newLabel = "Nuovo", defaultLength = 60, emptyText, noOverlap = false, onBlocked, onCreate, onChange, onPick }: Props) {
  const all = [...blocks, ...bands];
  const lo = Math.floor(Math.min(from ?? (bands.length ? Math.min(...bands.map((b) => b.start)) : 8 * 60), ...all.map((b) => b.start)) / 60) * 60;
  const hi = Math.min(1440, Math.ceil(Math.max(to ?? (bands.length ? Math.max(...bands.map((b) => b.end)) : 20 * 60), ...all.map((b) => b.end), lo + 4 * 60) / 60) * 60);
  const total = hi - lo, ppm = Math.min(1.1, Math.max(0.6, 560 / total)), height = Math.round(total * ppm);
  const y = (m: number) => (m - lo) * ppm;
  const cols = useRef<HTMLDivElement>(null);
  const [drag, setDrag] = useState<Drag | null>(null);
  const dragRef = useRef<Drag | null>(null); dragRef.current = drag;
  // Dopo il rilascio il blocco resta nella nuova posizione finché il genitore non aggiorna i dati.
  const [settled, setSettled] = useState<{ id: string; s: Slot } | null>(null);
  useEffect(() => setSettled(null), [blocks]);
  const snap = (m: number) => Math.round(m / step) * step;
  const minuteAt = (clientY: number) => { const r = cols.current!.getBoundingClientRect(); return lo + (clientY - r.top) / ppm; };
  const dayAt = (clientX: number, fallback: number) => {
    const list = [...(cols.current?.querySelectorAll<HTMLElement>(".wp-col") || [])];
    const i = list.findIndex((c) => { const r = c.getBoundingClientRect(); return clientX >= r.left - 3 && clientX <= r.right + 3; });
    return i < 0 ? fallback : i;
  };
  /** Spazio libero [min,max] attorno al minuto `m` del giorno `d` (escluso il blocco `id`). */
  const room = (d: number, m: number, id?: string) => {
    let a = lo, b = hi;
    if (noOverlap) blocks.forEach((x) => { if (x.id === id || x.weekday !== d) return; if (x.end <= m) a = Math.max(a, x.end); else if (x.start >= m) b = Math.min(b, x.start); });
    return [a, b] as const;
  };
  const clash = (s: Slot, id?: string) => noOverlap && overlapsAny(s, blocks, (x) => (x as PlanBlock).id === id);
  const compute = (g: Drag, clientX: number, clientY: number): Slot => {
    const m = minuteAt(clientY), len = g.orig.end - g.orig.start;
    if (g.kind === "create") {
      const [ra, rb] = room(g.d0, g.m0);
      const a = Math.max(ra, Math.min(g.m0, m)), b = Math.min(rb, Math.max(g.m0, m));
      const s = Math.max(ra, Math.floor(a / step) * step), e = Math.min(rb, Math.max(s + step, Math.ceil(b / step) * step));
      return { weekday: g.d0, start: s, end: e };
    }
    if (g.kind === "move") { const s = Math.max(lo, Math.min(hi - len, g.orig.start + snap(m - g.m0))); return { weekday: dayAt(clientX, g.orig.weekday), start: s, end: s + len }; }
    if (g.kind === "top") { const [ra] = room(g.orig.weekday, g.orig.start, g.id); return { ...g.orig, start: Math.max(lo, ra, Math.min(g.orig.end - step, snap(m))) }; }
    const [, rb] = room(g.orig.weekday, g.orig.end, g.id);
    return { ...g.orig, end: Math.min(hi, rb, Math.max(g.orig.start + step, snap(m))) };
  };
  useEffect(() => {
    if (!drag) return;
    const mv = (e: PointerEvent) => {
      const g = dragRef.current; if (!g) return;
      const far = Math.hypot(e.clientX - g.x0, e.clientY - g.y0) > 5;
      if (!g.moved && !far) return;
      if (e.pointerType === "touch" && g.kind === "create") return; // sul tocco lo spazio vuoto scorre la pagina: si crea con un tocco
      e.preventDefault();
      setDrag({ ...g, moved: true, cur: compute(g, e.clientX, e.clientY) });
    };
    const up = () => {
      const g = dragRef.current; setDrag(null); if (!g) return;
      if (g.kind === "create") {
        const s = g.moved ? g.cur : { weekday: g.d0, start: Math.max(lo, Math.min(hi - defaultLength, Math.floor(g.m0 / step) * step)), end: 0 };
        if (!g.moved) {
          const [ra, rb] = room(g.d0, g.m0);
          s.start = Math.max(s.start, ra); s.end = Math.min(rb, s.start + defaultLength);
          if (s.end - s.start < step) { onBlocked?.("Qui non c’è spazio libero: c’è già un altro blocco."); return; }
        }
        if (clash(s)) { onBlocked?.("Si sovrappone a un altro blocco."); return; }
        onCreate?.(s); return;
      }
      const b = blocks.find((x) => x.id === g.id);
      if (!g.moved) { if (b) onPick?.(b); return; }
      if (g.cur.weekday !== g.orig.weekday || g.cur.start !== g.orig.start || g.cur.end !== g.orig.end) {
        if (clash(g.cur, g.id)) { onBlocked?.("Non puoi sovrapporlo a un altro blocco: è tornato al suo posto."); return; }
        setSettled({ id: g.id!, s: g.cur }); onChange?.(g.id!, g.cur);
      }
    };
    const cancel = () => setDrag(null);
    addEventListener("pointermove", mv, { passive: false }); addEventListener("pointerup", up); addEventListener("pointercancel", cancel);
    return () => { removeEventListener("pointermove", mv); removeEventListener("pointerup", up); removeEventListener("pointercancel", cancel); };
  }, [drag?.pointer]); // eslint-disable-line react-hooks/exhaustive-deps
  const startCreate = (e: RPointerEvent, d: number) => {
    if (!editable || !onCreate || e.button !== 0 || (e.target as HTMLElement).closest(".wp-block")) return;
    const m = minuteAt(e.clientY);
    setDrag({ kind: "create", pointer: e.pointerId + ":" + Date.now(), d0: d, m0: m, x0: e.clientX, y0: e.clientY, orig: { weekday: d, start: m, end: m }, cur: { weekday: d, start: Math.floor(m / step) * step, end: Math.floor(m / step) * step + step }, moved: false });
  };
  const startBlock = (e: RPointerEvent, b: PlanBlock, kind: Drag["kind"]) => {
    if (e.button !== 0) return;
    e.stopPropagation();
    if (!editable || !onChange || b.locked) return; // sola lettura: il clic apre i dettagli (onClick)
    e.preventDefault();
    setDrag({ kind, id: b.id, pointer: e.pointerId + ":" + Date.now(), d0: b.weekday, m0: minuteAt(e.clientY), x0: e.clientX, y0: e.clientY, orig: { weekday: b.weekday, start: b.start, end: b.end }, cur: { weekday: b.weekday, start: b.start, end: b.end }, moved: false });
  };
  const key = (e: RKeyboardEvent, b: PlanBlock) => {
    if (!e.altKey || !editable || !onChange || b.locked) return;
    const len = b.end - b.start; let s: Slot | null = null;
    if (e.key === "ArrowUp") s = e.shiftKey ? { ...b, end: Math.max(b.start + step, b.end - step) } : { ...b, start: Math.max(lo, b.start - step), end: Math.max(lo, b.start - step) + len };
    if (e.key === "ArrowDown") s = e.shiftKey ? { ...b, end: Math.min(hi, b.end + step) } : { ...b, start: Math.min(hi - len, b.start + step), end: Math.min(hi - len, b.start + step) + len };
    if (e.key === "ArrowLeft") s = { ...b, weekday: Math.max(0, b.weekday - 1) };
    if (e.key === "ArrowRight") s = { ...b, weekday: Math.min(days - 1, b.weekday + 1) };
    if (s) { e.preventDefault(); const n = { weekday: s.weekday, start: s.start, end: s.end }; if (clash(n, b.id)) { onBlocked?.("Si sovrapporrebbe a un altro blocco."); return; } setSettled({ id: b.id, s: n }); onChange(b.id, n); }
  };
  const shown = blocks.map((b) => {
    if (drag?.moved && drag.id === b.id) return { ...b, ...drag.cur, live: true, bad: clash(drag.cur, b.id) };
    if (settled?.id === b.id) return { ...b, ...settled.s, live: false, bad: false };
    return { ...b, live: false, bad: false };
  });
  const hours = useMemo(() => Array.from({ length: total / 60 + 1 }, (_, i) => lo + i * 60), [lo, total]);
  const ghost = drag?.kind === "create" && drag.moved ? drag.cur : null;
  return <div className={"wp" + (editable ? " edit" : "") + (drag?.moved ? " dragging" : "")} role="group" aria-label={label}>
    <div className="wp-head" style={{ gridTemplateColumns: `52px repeat(${days}, minmax(0, 1fr))` }} aria-hidden="true">
      <span />{WD_SHORT.slice(0, days).map((w, i) => <b key={w} className={i > 4 ? "we" : ""}>{w}</b>)}
    </div>
    <div className="wp-body" style={{ gridTemplateColumns: `52px minmax(0, 1fr)`, height }}>
      <div className="wp-axis" aria-hidden="true">{hours.map((h) => <span key={h} style={{ top: y(h) }}>{fmtEnd(h)}</span>)}</div>
      <div className="wp-cols" ref={cols} style={{ gridTemplateColumns: `repeat(${days}, minmax(0, 1fr))`, "--wp-hour": `${60 * ppm}px` } as React.CSSProperties}>
        {WD_SHORT.slice(0, days).map((w, d) => {
          const dayBands = bands.filter((b) => b.weekday === d);
          return <div key={w} className={"wp-col" + (bands.length ? " hatched" : "")} onPointerDown={(e) => startCreate(e, d)}>
            {dayBands.map((b, i) => <span key={i} className="wp-band" style={{ top: y(b.start), height: (b.end - b.start) * ppm }} title={`Centro aperto ${span(b)}`} />)}
            {shown.filter((b) => b.weekday === d).map((b) => {
              const h = (b.end - b.start) * ppm, canEdit = editable && !!onChange && !b.locked;
              return <button key={b.id} type="button" className={`wp-block ${b.tone || "violet"}${b.draft ? " draft" : ""}${b.live ? " live" : ""}${b.bad ? " bad" : ""}${h < 34 ? " tiny" : ""}${canEdit ? " movable" : ""}`}
                style={{ top: y(b.start), height: Math.max(h, 14) }}
                aria-label={`${b.label || newLabel}, ${WD_LONG[d].toLowerCase()} ${span(b)}${b.draft ? ", da approvare" : ""}${b.sub ? ", " + b.sub : ""}`}
                aria-keyshortcuts={canEdit ? "Alt+ArrowUp Alt+ArrowDown Alt+ArrowLeft Alt+ArrowRight" : undefined}
                onPointerDown={(e) => startBlock(e, b, "move")} onKeyDown={(e) => key(e, b)} onClick={(e) => { if (e.detail === 0 || !canEdit) onPick?.(b); }}>
                {canEdit && <span className="wp-grip top" onPointerDown={(e) => startBlock(e, b, "top")} aria-hidden="true" />}
                <span className="wp-t">{span(b)}</span>
                {h >= 34 && <b>{b.label || newLabel}</b>}
                {h >= 52 && b.sub && <small>{b.sub}</small>}
                {canEdit && <span className="wp-grip bottom" onPointerDown={(e) => startBlock(e, b, "bottom")} aria-hidden="true" />}
              </button>;
            })}
            {ghost && ghost.weekday === d && <span className="wp-ghost" style={{ top: y(ghost.start), height: (ghost.end - ghost.start) * ppm }}><b>{span(ghost)}</b><small>{newLabel}</small></span>}
          </div>;
        })}
      </div>
    </div>
    {editable && onCreate && <p className="wp-help"><Icon n="move" size={14} />Clicca o trascina su uno spazio vuoto per aggiungere · trascina un blocco per spostarlo · tira i bordi per allungarlo</p>}
    {!blocks.length && emptyText && <p className="wp-empty">{emptyText}</p>}
  </div>;
}

/* ------------------------------------------------------------------ fasce (orari del centro) */

/** Editor di fasce senza etichetta (orari di apertura, finestre di servizio): unisce le sovrapposizioni. */
export function SlotPlanner({ value, onChange, label, from = 7 * 60, to = 22 * 60, tone = "green", newLabel = "Aperto", readOnly = false }: { value: Slot[]; onChange: (v: Slot[]) => void; label: string; from?: number; to?: number; tone?: PlanTone; newLabel?: string; readOnly?: boolean }) {
  const [pick, setPick] = useState<number | "new" | null>(null);
  const merged = mergeSlots(value);
  const blocks: PlanBlock[] = merged.map((s, i) => ({ ...s, id: String(i), label: newLabel, sub: hoursOf(s.end - s.start), tone }));
  const replace = (i: number | "new", s: Slot | null) => onChange(mergeSlots([...merged.filter((_, j) => j !== i), ...(s ? [s] : [])]));
  const fresh: Slot = useMemo(() => ({ weekday: 0, start: Math.max(from, 15 * 60), end: Math.min(to, 19 * 60) }), [from, to]);
  return <>
    <WeekPlanner label={label} blocks={blocks} from={from} to={to} editable={!readOnly} newLabel={newLabel}
      onCreate={(s) => onChange(mergeSlots([...merged, s]))} onChange={(id, s) => replace(+id, s)} onPick={(b) => !readOnly && setPick(+b.id)} />
    {!readOnly && <button type="button" className="pill-btn sm ghost" style={{ marginTop: 8 }} onClick={() => setPick("new")}><Icon n="plus" />Aggiungi fascia</button>}
    <SlotDialog slot={pick === "new" ? fresh : pick != null ? merged[pick] : null} title={pick === "new" ? "Nuova fascia" : "Fascia"} onClose={() => setPick(null)}
      onSave={(s) => { replace(pick!, s); setPick(null); }} onDelete={pick === "new" ? undefined : () => { replace(pick!, null); setPick(null); }} />
  </>;
}

/** Dialogo minimo per modificare o eliminare una fascia (alternativa da tastiera al trascinamento). */
export function SlotDialog({ slot, title, onClose, onSave, onDelete, children }: { slot: Slot | null; title: string; onClose: () => void; onSave: (s: Slot) => void; onDelete?: () => void; children?: ReactNode }) {
  const [v, setV] = useState<Slot | null>(slot);
  const [last, setLast] = useState(slot);
  if (slot !== last) { setLast(slot); setV(slot); }
  const x = v || slot;
  return <Modal open={!!slot} onClose={onClose} labelledBy="sd-t">{x && <>
    <div className="modal-body">
      <h2 id="sd-t">{title}</h2>
      <Field label="Giorno"><div className="day-pick" role="group" aria-label="Giorno">{WD_SHORT.map((w, i) => <button key={w} type="button" aria-pressed={x.weekday === i} className={"day-btn" + (x.weekday === i ? " on" : "")} onClick={() => setV({ ...x, weekday: i })}>{w}</button>)}</div></Field>
      <div className="grid2" style={{ marginTop: 8 }}>
        <Field label="Dalle" id="sd-a"><TimeSelect id="sd-a" label="Dalle" value={x.start} onChange={(a) => setV({ ...x, start: a, end: x.end <= a ? Math.min(a + 60, 1440) : x.end })} /></Field>
        <Field label="Alle" id="sd-b"><TimeSelect id="sd-b" label="Alle" value={x.end} onChange={(b) => setV({ ...x, end: b })} /></Field>
      </div>
      {children}
    </div>
    <div className="modal-foot">
      {onDelete && <Btn kind="ghost" icon="x" onClick={onDelete}>Elimina</Btn>}
      <span style={{ flex: 1 }} />
      <Btn kind="ghost" onClick={onClose}>Annulla</Btn>
      <Btn kind="primary" isle="check" disabled={x.end <= x.start} onClick={() => onSave(x)}>Salva</Btn>
    </div>
  </>}</Modal>;
}

/** Selettore orario a passi di 15 minuti (select nativo, accessibile). */
export function TimeSelect({ id, value, onChange, from = 6 * 60, to = 24 * 60, label }: { id: string; value: number; onChange: (m: number) => void; from?: number; to?: number; label: string }) {
  const opts = Array.from({ length: (to - from) / 15 + 1 }, (_, i) => from + i * 15);
  return <select id={id} className="inp" aria-label={label} value={value} onChange={(e) => onChange(+e.target.value)}>{opts.map((m) => <option key={m} value={m}>{fmtEnd(m)}</option>)}</select>;
}
