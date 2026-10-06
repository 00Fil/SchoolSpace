/** DOM minimo per importare i moduli UI in Node (i test di componente usano il rendering statico). */
const g = globalThis as Record<string, unknown>;
if (!g.document) {
  const noop = () => undefined;
  const el = () => ({ style: {}, setAttribute: noop, appendChild: noop, remove: noop, classList: { add: noop, remove: noop, toggle: noop } });
  g.document = { addEventListener: noop, removeEventListener: noop, cookie: "csrftoken=test-csrf", documentElement: el(), body: el(), createElement: el, getElementById: () => null, querySelector: () => null, visibilityState: "visible", title: "" };
  g.window = g;
  g.addEventListener = noop; g.removeEventListener = noop;
  g.location = new URL("http://localhost:5173/");
  g.history = { replaceState: noop, pushState: noop };
  g.localStorage = mem(); g.sessionStorage = mem();
  g.matchMedia = () => ({ matches: false, addEventListener: noop, removeEventListener: noop });
  g.requestAnimationFrame = (f: () => void) => setTimeout(f, 0);
}
function mem() { const m = new Map<string, string>(); return { getItem: (k: string) => m.get(k) ?? null, setItem: (k: string, v: string) => void m.set(k, String(v)), removeItem: (k: string) => void m.delete(k), clear: () => m.clear() }; }
export {};
