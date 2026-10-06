import { useSyncExternalStore } from "react";
export type Theme = "light" | "dark" | "system";
export type Motion = "system" | "reduce";
const KEY = "ripetizioni-ui";
type Prefs = { theme: Theme; motion: Motion };
let prefs: Prefs = { theme: "system", motion: "system" };
try { prefs = { ...prefs, ...JSON.parse(localStorage.getItem(KEY) || "{}") }; } catch { /* preferenze di default */ }
const subs = new Set<() => void>();
export const getPrefs = () => prefs;
export function setPrefs(p: Partial<Prefs>) {
  prefs = { ...prefs, ...p };
  try { localStorage.setItem(KEY, JSON.stringify(prefs)); } catch { /* storage non disponibile */ }
  document.documentElement.classList.toggle("reduce", prefs.motion === "reduce");
  subs.forEach((f) => f());
}
export const usePrefs = () => useSyncExternalStore((f) => (subs.add(f), () => subs.delete(f)), getPrefs);
export const motionOK = () => !matchMedia("(prefers-reduced-motion: reduce)").matches && prefs.motion !== "reduce";
export const resolved = (t: Theme) => (t === "system" ? (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light") : t);
export function applyTheme(t: "light" | "dark") {
  document.documentElement.setAttribute("data-theme", t);
  document.querySelectorAll('meta[name="theme-color"]').forEach((m) => m.setAttribute("content", t === "dark" ? "#0A0B0E" : "#D9DBE1"));
}
type VT = { finished: Promise<void> };
type DocVT = Document & { startViewTransition?: (cb: () => void) => VT };
/** Cambio tema con rivelazione circolare dal punto indicato. */
export function setTheme(theme: Theme, from?: DOMRect) {
  const next = resolved(theme);
  const d = document as DocVT, r = document.documentElement;
  setPrefs({ theme });
  if (next === r.getAttribute("data-theme")) return;
  if (from && d.startViewTransition && motionOK()) {
    const x = from.left + from.width / 2, y = from.top + from.height / 2;
    r.style.setProperty("--vx", x + "px"); r.style.setProperty("--vy", y + "px");
    r.style.setProperty("--vr", Math.hypot(Math.max(x, innerWidth - x), Math.max(y, innerHeight - y)) + "px");
    r.classList.add("vt-theme");
    d.startViewTransition(() => applyTheme(next)).finished.finally(() => r.classList.remove("vt-theme"));
  } else applyTheme(next);
}
export function initPrefs() {
  applyTheme(resolved(prefs.theme));
  document.documentElement.classList.toggle("reduce", prefs.motion === "reduce");
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => { if (prefs.theme === "system") applyTheme(resolved("system")); });
}
export const viewTransition = (cb: () => void) => { const d = document as DocVT; if (d.startViewTransition && motionOK()) d.startViewTransition(cb); else cb(); };
