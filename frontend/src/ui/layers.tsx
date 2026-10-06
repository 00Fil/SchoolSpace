import { createContext, ReactNode, useCallback, useContext, useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

type Kind = "pop" | "sheet" | "modal";
type Rec = { kind: Kind; el: () => HTMLElement | null; close: () => void; anchor?: HTMLElement | null };
const stack: Rec[] = [];
export const layersOpen = () => stack.length > 0;
const FOCUSABLE = 'a[href],button:not([disabled]),input:not([disabled]):not([type=hidden]),select,textarea,[tabindex]:not([tabindex="-1"])';
document.addEventListener("keydown", (e) => {
  const top = stack[stack.length - 1];
  if (!top) return;
  if (e.key === "Escape" && !e.defaultPrevented) { e.preventDefault(); top.close(); return; }
  if (e.key === "Tab" && top.kind !== "pop") {
    const el = top.el(); if (!el) return;
    const f = [...el.querySelectorAll<HTMLElement>(FOCUSABLE)].filter((x) => x.offsetParent !== null);
    if (!f.length) return;
    const first = f[0], last = f[f.length - 1];
    if (!el.contains(document.activeElement)) { e.preventDefault(); first.focus(); }
    else if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  }
});
document.addEventListener("pointerdown", (e) => {
  const top = stack[stack.length - 1];
  const t = e.target as Node;
  if (top && top.kind === "pop" && !top.el()?.contains(t) && !top.anchor?.contains(t)) top.close();
}, true);

type LayerProps = { open: boolean; onClose: () => void; kind: Kind; guard?: () => boolean; anchor?: HTMLElement | null; label?: string; labelledBy?: string; className?: string; children: ReactNode; width?: number };
/** Un livello della pila unica: velo, ingresso a molla, Esc, trappola di focus, ritorno del focus. */
export function Layer({ open, onClose, kind, guard, anchor, label, labelledBy, className = "", children, width }: LayerProps) {
  const [mounted, setMounted] = useState(open), [show, setShow] = useState(false);
  const ref = useRef<HTMLDivElement>(null), prev = useRef<Element | null>(null);
  const close = useRef(() => {}); close.current = () => { if (guard && guard() === false) return; onClose(); };
  const [pos, setPos] = useState<React.CSSProperties>({});
  useEffect(() => {
    if (open) {
      setMounted(true);
      prev.current = document.activeElement;
      const rec: Rec = { kind, el: () => ref.current, close: () => close.current(), anchor };
      stack.push(rec);
      anchor?.setAttribute("aria-expanded", "true");
      let r2 = 0; const r1 = requestAnimationFrame(() => { r2 = requestAnimationFrame(() => setShow(true)); });
      const t = setTimeout(() => {
        const el = ref.current; if (!el || el.contains(document.activeElement)) return;
        (el.querySelector<HTMLElement>("[autofocus],[data-autofocus]") || el.querySelector<HTMLElement>(FOCUSABLE))?.focus({ preventScroll: true });
      }, 60);
      return () => {
        cancelAnimationFrame(r1); cancelAnimationFrame(r2); clearTimeout(t);
        const i = stack.indexOf(rec); if (i >= 0) stack.splice(i, 1);
        anchor?.setAttribute("aria-expanded", "false");
        setShow(false);
        const p = prev.current as HTMLElement | null;
        if (p && document.contains(p) && !stack.length) p.focus({ preventScroll: true });
      };
    }
    const t = setTimeout(() => setMounted(false), 460);
    return () => clearTimeout(t);
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps
  useLayoutEffect(() => {
    if (!open || kind !== "pop" || !anchor) return;
    const r = anchor.getBoundingClientRect(), w = Math.min(width || 340, innerWidth - 24);
    let left = Math.min(Math.max(12, r.right - w), innerWidth - w - 12);
    if (r.left + w < innerWidth - 12 && r.right - w < 12) left = r.left;
    setPos({ left, top: r.bottom + 10, width: w, transformOrigin: `${Math.max(0, r.left + r.width / 2 - left)}px 0` });
  }, [open, anchor, kind, width]);
  if (!mounted) return null;
  const cls = kind === "pop" ? "pop bezel" : kind === "sheet" ? "sheet bezel" : "modal bezel";
  return createPortal(<>
    <div className={(kind === "pop" ? "scrim soft" : "scrim") + (show ? " show" : "")} onClick={() => close.current()} />
    <div ref={ref} className={`${cls} ${className}${show ? " show" : ""}`} role="dialog" aria-modal={kind !== "pop" || undefined} aria-label={label} aria-labelledby={labelledBy} style={kind === "pop" ? pos : width ? { width } : undefined}>
      <div className="core">{children}</div>
    </div>
  </>, document.getElementById("layers")!);
}
export const Modal = (p: Omit<LayerProps, "kind">) => <Layer {...p} kind="modal" />;
export const Sheet = (p: Omit<LayerProps, "kind">) => <Layer {...p} kind="sheet" />;
export const Pop = (p: Omit<LayerProps, "kind">) => <Layer {...p} kind="pop" />;

/** Chiusura protetta: con modifiche non salvate il footer chiede conferma, mai confirm(). */
export function useDirtyGuard(dirty: boolean) {
  const [asking, setAsking] = useState(false);
  const pass = useRef(false);
  useEffect(() => {
    if (!dirty) return;
    const f = (e: BeforeUnloadEvent) => { e.preventDefault(); };
    addEventListener("beforeunload", f); return () => removeEventListener("beforeunload", f);
  }, [dirty]);
  const guard = useCallback(() => { if (pass.current || !dirty) return true; if (asking) return true; setAsking(true); return false; }, [dirty, asking]);
  return { asking, guard, keep: () => setAsking(false), allow: () => { pass.current = true; }, reset: () => { pass.current = false; setAsking(false); } };
}
export function GuardFoot({ onKeep, onDiscard }: { onKeep: () => void; onDiscard: () => void }) {
  const ref = useRef<HTMLButtonElement>(null);
  useEffect(() => { ref.current?.focus(); }, []);
  return <div className="modal-foot"><span style={{ marginRight: "auto", alignSelf: "center", color: "var(--text-2)" }}>Hai modifiche non salvate.</span>
    <button type="button" ref={ref} className="pill-btn ghost" onClick={onKeep}>Continua a modificare</button>
    <button type="button" className="pill-btn danger" onClick={onDiscard}>Chiudi senza salvare</button></div>;
}

/* ---------- toast ---------- */
type ToastOpt = { action?: string; onAction?: () => void; ms?: number };
type T = { id: number; msg: string; opt: ToastOpt; out?: boolean };
const ToastCtx = createContext<(msg: string, opt?: ToastOpt) => void>(() => {});
export const useToast = () => useContext(ToastCtx);
let tid = 0;
export function ToastHost({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<T[]>([]);
  const timers = useRef(new Map<number, number>());
  const kill = useCallback((id: number) => {
    clearTimeout(timers.current.get(id));
    setItems((xs) => xs.map((x) => (x.id === id ? { ...x, out: true } : x)));
    setTimeout(() => setItems((xs) => xs.filter((x) => x.id !== id)), 380);
  }, []);
  const arm = useCallback((t: T) => { timers.current.set(t.id, window.setTimeout(() => kill(t.id), t.opt.ms || 5200)); }, [kill]);
  const push = useCallback((msg: string, opt: ToastOpt = {}) => {
    const t = { id: ++tid, msg, opt };
    setItems((xs) => [...xs, t].slice(-3)); arm(t);
  }, [arm]);
  return <ToastCtx.Provider value={push}>{children}
    {createPortal(<div className="toasts" role="status" aria-live="polite">{items.map((t) =>
      <div key={t.id} className={"toast" + (t.out ? " out" : "")} onMouseEnter={() => clearTimeout(timers.current.get(t.id))} onMouseLeave={() => arm(t)}>
        <span>{t.msg}</span>{t.opt.action && <button type="button" onClick={() => { t.opt.onAction?.(); kill(t.id); }}>{t.opt.action}</button>}
      </div>)}</div>, document.body)}
  </ToastCtx.Provider>;
}
