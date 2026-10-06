import { ReactNode, useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { addDays, addMonths, dayLabel, monthYear, parse, todayRome, WD_NARROW } from "../format";
import { motionOK } from "./prefs";
import { Avatar, Icon } from "./core";

const SPRING = "cubic-bezier(.32,.72,0,1)";

/* ---------- controllo segmentato con cursore che scivola ---------- */
export function SegCtl<V extends string>({ value, options, onChange, label }: { value: V; options: [V, string][]; onChange: (v: V) => void; label: string }) {
  const ref = useRef<HTMLDivElement>(null), thumb = useRef<HTMLSpanElement>(null), first = useRef(true);
  const place = () => {
    const b = ref.current?.querySelector<HTMLElement>('[aria-pressed="true"]'), th = thumb.current;
    if (!b || !th) return;
    if (first.current) th.style.transition = "none";
    th.style.width = b.offsetWidth + "px"; th.style.transform = `translate(${b.offsetLeft}px,${b.offsetTop - 4}px)`; // anche su piu' righe (mobile)
    if (first.current) { void th.offsetWidth; th.style.transition = ""; first.current = false; }
  };
  useLayoutEffect(place, [value]);
  useEffect(() => {
    const ro = new ResizeObserver(() => { first.current = true; place(); });
    if (ref.current) ro.observe(ref.current);
    document.fonts?.ready.then(() => { first.current = true; place(); });
    return () => ro.disconnect();
  }, []);
  return <div className="seg-ctl" role="group" aria-label={label} ref={ref}>
    {options.map(([v, l]) => <button key={v} type="button" aria-pressed={v === value} onClick={() => onChange(v)}>{l}</button>)}
    <span className="thumb" ref={thumb} aria-hidden="true" />
  </div>;
}

/* ---------- campo ---------- */
export function Field({ label, optional, error, children, id, hint }: { label: ReactNode; optional?: boolean; error?: string | false; children: ReactNode; id?: string; hint?: ReactNode }) {
  return <div className={"fld" + (error ? " bad" : "")}>
    {id ? <label htmlFor={id}>{label}{optional && <span className="muted"> (facoltativo)</span>}</label> : <span className="lbl">{label}{optional && <span className="muted"> (facoltativo)</span>}</span>}
    {children}
    {hint && !error && <span className="hint">{hint}</span>}
    <span className="err">{error || ""}</span>
  </div>;
}
export const Input = (p: React.InputHTMLAttributes<HTMLInputElement> & { ref?: React.Ref<HTMLInputElement> }) => <input autoComplete="off" spellCheck={false} {...p} className={"inp " + (p.className || "")} />;
export const TextArea = (p: React.TextareaHTMLAttributes<HTMLTextAreaElement>) => <textarea spellCheck={false} {...p} className={"inp area " + (p.className || "")} />;
export function Check({ checked, onChange, children, name }: { checked: boolean; onChange: (v: boolean) => void; children: ReactNode; name?: string }) {
  return <label className="check"><input type="checkbox" name={name} checked={checked} onChange={(e) => onChange(e.target.checked)} />{children}</label>;
}

/* ---------- scelte a pillola (radio) ---------- */
export type Opt = { v: string; label: string; sub?: string; av?: string };
export function Choices({ value, options, onChange, label, name }: { value: string; options: Opt[]; onChange: (v: string) => void; label: string; name?: string }) {
  const n = useId();
  return <div className="choices" role="radiogroup" aria-label={label}>{options.map((o) =>
    <label key={o.v} className={"choice" + (o.av ? "" : " noav")}>
      <input type="radio" name={name || n} value={o.v} checked={o.v === value} onChange={() => onChange(o.v)} />
      {o.av && <Avatar name={o.av} />}<span>{o.label}</span>
    </label>)}</div>;
}
export function MultiChoices({ value, options, onChange, label }: { value: string[]; options: Opt[]; onChange: (v: string[]) => void; label: string }) {
  return <div className="choices" role="group" aria-label={label}>{options.map((o) =>
    <label key={o.v} className="choice noav">
      <input type="checkbox" value={o.v} checked={value.includes(o.v)} onChange={(e) => onChange(e.target.checked ? [...value, o.v] : value.filter((x) => x !== o.v))} />
      <span>{o.label}</span>
    </label>)}</div>;
}

/* ---------- ruota a scatto per orari e durate ---------- */
export type WheelItem<V> = { v: V; label: string; busy?: boolean };
export function Wheel<V>({ items, value, onChange, onLive, label }: { items: WheelItem<V>[]; value: V; onChange: (v: V) => void; onLive?: (v: V) => void; label: string }) {
  const H = 40, tr = useRef<HTMLDivElement>(null);
  const idx = Math.max(0, items.findIndex((x) => x.v === value));
  const live = useRef(idx), settle = useRef(0), raf = useRef(0), cur = useRef(idx), tgt = useRef(idx);
  const paint = () => {
    const t = tr.current; if (!t) return;
    const st = t.scrollTop;
    t.querySelectorAll<HTMLElement>(".wheel-it").forEach((e, i) => {
      const d = (i * H - st) / H, a = Math.min(Math.abs(d), 3);
      e.style.transform = `rotateX(${(-d * 22).toFixed(1)}deg) scale(${(1 - a * 0.07).toFixed(3)})`;
      e.style.opacity = Math.max(0.15, 1 - a * 0.3).toFixed(2);
    });
  };
  const goTo = (i: number, smooth: boolean) => { i = Math.max(0, Math.min(items.length - 1, i)); tgt.current = i; tr.current?.scrollTo({ top: i * H, behavior: smooth && motionOK() ? "smooth" : "auto" }); };
  useLayoutEffect(() => { if (tr.current && cur.current !== idx) { cur.current = idx; live.current = idx; goTo(idx, true); } }, [idx]);
  useLayoutEffect(() => { if (tr.current) { tr.current.scrollTop = idx * H; paint(); } }, []); // eslint-disable-line
  useEffect(paint, [items]);
  const onScroll = () => {
    cancelAnimationFrame(raf.current); raf.current = requestAnimationFrame(paint);
    const t = tr.current!; const l = Math.max(0, Math.min(items.length - 1, Math.round(t.scrollTop / H)));
    if (l !== live.current) { live.current = l; onLive?.(items[l].v); }
    clearTimeout(settle.current);
    settle.current = window.setTimeout(() => { tgt.current = live.current; if (live.current !== cur.current) { cur.current = live.current; onChange(items[live.current].v); } }, 110);
  };
  const it = items[idx];
  return <div className="wheel">
    <div className="wheel-band" aria-hidden="true" />
    <div className="wheel-track" ref={tr} tabIndex={0} role="spinbutton" aria-label={label} aria-valuemin={0} aria-valuemax={items.length - 1} aria-valuenow={idx}
      aria-valuetext={it ? it.label + (it.busy ? ", occupato" : "") : ""} onScroll={onScroll}
      onClick={(e) => { const el = (e.target as HTMLElement).closest<HTMLElement>("[data-i]"); if (el) goTo(Number(el.dataset.i), true); }}
      onKeyDown={(e) => {
        const k = ({ ArrowUp: -1, ArrowDown: 1, PageUp: -4, PageDown: 4 } as Record<string, number>)[e.key];
        if (k) { e.preventDefault(); goTo(tgt.current + k, true); }
        else if (e.key === "Home") { e.preventDefault(); goTo(0, true); }
        else if (e.key === "End") { e.preventDefault(); goTo(items.length - 1, true); }
      }}>
      {items.map((x, i) => <div key={i} data-i={i} className={"wheel-it" + (x.busy ? " busy" : "")}>{x.label}</div>)}
    </div>
  </div>;
}

/* ---------- calendario personalizzato ---------- */
export function CalendarGrid({ value, onPick, min, max, disabled, marks, footer }: { value: string; onPick: (d: string) => void; min?: string; max?: string; disabled?: (d: string) => boolean; marks?: (d: string) => number; footer?: boolean }) {
  const today = todayRome();
  const [view, setView] = useState(value.slice(0, 7)), [focusD, setFocusD] = useState(value);
  const grid = useRef<HTMLDivElement>(null), refocus = useRef(false), dir = useRef(0);
  useEffect(() => { setView(value.slice(0, 7)); setFocusD(value); }, [value]);
  useLayoutEffect(() => {
    if (dir.current && motionOK()) grid.current?.animate([{ transform: `translateX(${dir.current * 28}px)`, opacity: 0 }, { transform: "none", opacity: 1 }], { duration: 440, easing: SPRING });
    dir.current = 0;
    if (refocus.current) { grid.current?.querySelector<HTMLElement>(`[data-d="${focusD}"]`)?.focus(); refocus.current = false; }
  });
  const first = view + "-01";
  const start = addDays(first, -((parse(first).getUTCDay() + 6) % 7));
  const cells = Array.from({ length: 42 }, (_, i) => addDays(start, i));
  const isDis = (d: string) => (min && d < min) || (max && d > max) || (disabled ? disabled(d) : false);
  const move = (n: number) => { dir.current = n; const v = addMonths(view, n); setView(v); setFocusD(v + "-01"); };
  return <div className="cal">
    <div className="cal-head">
      <button type="button" className="circle" aria-label="Mese precedente" onClick={() => move(-1)}><Icon n="left" /></button>
      <b aria-live="polite">{monthYear(view)}</b>
      <button type="button" className="circle" aria-label="Mese successivo" onClick={() => move(1)}><Icon n="right" /></button>
    </div>
    <div className="cal-wd" aria-hidden="true">{WD_NARROW.map((w, i) => <span key={i}>{w}</span>)}</div>
    <div className="cal-grid" role="group" aria-label={monthYear(view)} ref={grid}
      onKeyDown={(e) => {
        const b = (e.target as HTMLElement).closest<HTMLElement>("[data-d]"); if (!b) return;
        const k = ({ ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7, PageUp: -28, PageDown: 28 } as Record<string, number>)[e.key];
        if (!k) return; e.preventDefault();
        const nd = addDays(b.dataset.d!, k); const nv = nd.slice(0, 7);
        dir.current = nv === view ? 0 : nv < view ? -1 : 1; refocus.current = true; setFocusD(nd); setView(nv);
      }}>
      {cells.map((d) => {
        const dis = !!isDis(d), mk = !dis && marks ? marks(d) : 0, out = d.slice(0, 7) !== view;
        return <button key={d} type="button" data-d={d} disabled={dis} tabIndex={d === focusD ? 0 : -1} aria-pressed={d === value}
          className={"cal-d" + (out ? " out" : "") + (d === today ? " today" : "")}
          aria-label={dayLabel(d) + (d === today ? ", oggi" : "") + (dis ? ", non disponibile" : mk ? `, ${mk} lezioni` : "")}
          onClick={(e) => { if (motionOK()) e.currentTarget.animate([{ transform: "scale(.82)" }, { transform: "scale(1.06)" }, { transform: "none" }], { duration: 420, easing: SPRING }); setFocusD(d); onPick(d); }}>
          {Number(d.slice(8))}{mk > 0 && <span className="mk" aria-hidden="true" />}
        </button>;
      })}
    </div>
    {footer && !isDis(today) && <div className="cal-foot"><button type="button" className="pill-btn sm" onClick={() => onPick(today)}>Oggi</button></div>}
  </div>;
}
/** Campo data: pulsante che apre il calendario sotto di sé, mai <input type="date">. */
export function DateField({ value, onChange, min, max, disabled, label, placeholder = "Scegli un giorno", id }: { value: string; onChange: (d: string) => void; min?: string; max?: string; disabled?: (d: string) => boolean; label: string; placeholder?: string; id?: string }) {
  const [open, setOpen] = useState(false); const btn = useRef<HTMLButtonElement>(null), box = useRef<HTMLDivElement>(null);
  const today = todayRome();
  useEffect(() => { if (open) setTimeout(() => box.current?.querySelector<HTMLElement>('.cal-d[tabindex="0"]')?.focus(), 30); }, [open]);
  const txt = value ? (value === today ? "Oggi, " + dayLabel(value).toLowerCase() : dayLabel(value) + " " + value.slice(0, 4)) : placeholder;
  return <div>
    <button type="button" id={id} ref={btn} className="inp pick" aria-expanded={open} aria-label={`${label}: ${value ? txt : "nessun giorno"}`} onClick={() => setOpen(!open)}>
      <Icon n="cal" /><span className={value ? "" : "ph"}>{txt}</span><i className="chev"><Icon n="chev" /></i>
    </button>
    {open && <div className="cal-box reveal" ref={box} onKeyDown={(e) => { if (e.key === "Escape") { e.stopPropagation(); e.preventDefault(); setOpen(false); btn.current?.focus(); } }}>
      <CalendarGrid value={value || (min && min > today ? min : today)} min={min} max={max} disabled={disabled} onPick={(d) => { onChange(d); setTimeout(() => { setOpen(false); btn.current?.focus(); }, motionOK() ? 240 : 0); }} />
    </div>}
  </div>;
}

/* ---------- campo con suggerimenti ---------- */
export type ComboItem = { id: string; label: string; sub?: string };
export function Combo({ value, items, onPick, placeholder, id, invalid }: { value: ComboItem | null; items: ComboItem[]; onPick: (x: ComboItem | null) => void; placeholder?: string; id: string; invalid?: boolean }) {
  const [q, setQ] = useState(value?.label || ""), [open, setOpen] = useState(false), [sel, setSel] = useState(-1);
  useEffect(() => { setQ(value?.label || ""); }, [value]);
  const s = q.trim().toLowerCase();
  const shown = items.filter((x) => !s || value?.label.toLowerCase() === s || x.label.toLowerCase().includes(s) || (x.sub || "").toLowerCase().includes(s)).slice(0, 8);
  const pick = (x: ComboItem) => { setQ(x.label); setOpen(false); onPick(x); };
  const lid = id + "-list";
  return <div className="combo">
    <input id={id} className="inp" value={q} placeholder={placeholder} autoComplete="off" spellCheck={false} role="combobox" aria-autocomplete="list" aria-controls={lid}
      aria-expanded={open && shown.length > 0} aria-invalid={invalid || undefined} aria-activedescendant={sel >= 0 ? `${lid}-${sel}` : undefined}
      onChange={(e) => { setQ(e.target.value); setOpen(true); setSel(-1); if (value) onPick(null); }}
      onClick={() => setOpen(true)} onBlur={() => setTimeout(() => setOpen(false), 120)}
      onKeyDown={(e) => {
        if (e.key === "ArrowDown") { e.preventDefault(); setOpen(true); setSel(Math.min(shown.length - 1, sel + 1)); }
        else if (e.key === "ArrowUp") { e.preventDefault(); setSel(Math.max(0, sel - 1)); }
        else if (e.key === "Enter" && open && sel >= 0) { e.preventDefault(); pick(shown[sel]); }
        else if (e.key === "Escape" && open) { e.stopPropagation(); e.preventDefault(); setOpen(false); }
      }} />
    {open && shown.length > 0 && !(value && shown.length === 1) && <div className="suggest" role="listbox" id={lid} onMouseDown={(e) => e.preventDefault()}>
      {shown.map((x, i) => <div key={x.id} id={`${lid}-${i}`} role="option" aria-selected={i === sel} className="pop-item" onClick={() => pick(x)}>
        <Avatar name={x.label} k={x.id} /><div><b>{x.label}</b>{x.sub && <small>{x.sub}</small>}</div></div>)}
    </div>}
  </div>;
}
