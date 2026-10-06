import { useSyncExternalStore } from "react";
export type Route = { name: string; q: URLSearchParams };
function parse(): Route {
  const h = location.hash.replace(/^#\/?/, "");
  const [name, qs] = h.split("?");
  return { name: name || "panoramica", q: new URLSearchParams(qs || "") };
}
let cur = parse(), key = location.hash;
const subs = new Set<() => void>();
const emit = () => { cur = parse(); key = location.hash; subs.forEach((f) => f()); };
addEventListener("hashchange", emit);
export const useRoute = () => { useSyncExternalStore((f) => (subs.add(f), () => subs.delete(f)), () => key); return cur; };
export function go(name: string, params?: Record<string, string>) {
  const q = new URLSearchParams(params || {}).toString();
  location.hash = `#/${name}${q ? "?" + q : ""}`;
}
/** Aggiorna la query senza creare una voce di cronologia. */
export function setQuery(mut: (q: URLSearchParams) => void) {
  const q = new URLSearchParams(cur.q); mut(q);
  const s = q.toString();
  history.replaceState(null, "", `#/${cur.name}${s ? "?" + s : ""}`);
  emit();
}
