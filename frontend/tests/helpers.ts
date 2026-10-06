/** fetch finto: risponde in ordine alle richieste registrate e conserva lo storico. */
export type Call = { url: string; method: string; headers: Record<string, string>; body: unknown };
export function mockFetch(responses: Array<{ status?: number; body?: unknown; headers?: Record<string, string> } | ((c: Call) => { status?: number; body?: unknown; headers?: Record<string, string> })>) {
  const calls: Call[] = [];
  let i = 0;
  (globalThis as { fetch: unknown }).fetch = async (url: string, init: RequestInit = {}) => {
    const call = { url, method: init.method || "GET", headers: (init.headers || {}) as Record<string, string>, body: init.body ? JSON.parse(String(init.body)) : undefined };
    calls.push(call);
    const spec = responses[Math.min(i++, responses.length - 1)];
    const r = typeof spec === "function" ? spec(call) : spec;
    return new Response(r.body === undefined ? "" : JSON.stringify(r.body), { status: r.status ?? 200, headers: { "content-type": "application/json", ...(r.headers || {}) } });
  };
  return calls;
}
