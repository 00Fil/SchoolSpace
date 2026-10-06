import { test } from "node:test";
import assert from "node:assert/strict";
import { ApiError, collect, fillPath, get, newIdempotencyKey, nextPath, onSessionEvent, post, request, SessionEvent, withQuery } from "../src/api/client";
import { OPERATIONS } from "../src/api/schema.gen";
import { mockFetch } from "./helpers";

test("fillPath codifica i parametri e rifiuta quelli mancanti", () => {
  assert.equal(fillPath("/occurrences/{pk}/attendance/", { pk: "a b/c" }), "/occurrences/a%20b%2Fc/attendance/");
  assert.throws(() => fillPath("/x/{id}", {}), /mancante: id/);
});

test("withQuery salta i valori vuoti e accoda a query esistenti", () => {
  assert.equal(withQuery("/a", { x: 1, y: "", z: undefined, w: null, k: false }), "/a?x=1&k=false");
  assert.equal(withQuery("/a?p=1", { q: "è" }), "/a?p=1&q=%C3%A8");
});

test("nextPath accetta solo la stessa origine sotto /api/v1", () => {
  const o = "http://localhost:5173";
  assert.equal(nextPath(null, o), null);
  assert.equal(nextPath("http://localhost:5173/api/v1/portal/availability-exceptions?cursor=abc", o), "/portal/availability-exceptions?cursor=abc");
  assert.equal(nextPath("/api/v1/x?cursor=1", o), "/x?cursor=1");
  assert.throws(() => nextPath("https://evil.example/api/v1/x?cursor=1", o), (e: ApiError) => e.code === "PAGINATION_ORIGIN");
  assert.throws(() => nextPath("http://localhost:5173/admin/?cursor=1", o), (e: ApiError) => e.code === "PAGINATION_ORIGIN");
});

test("collect segue il cursore opaco fino alla fine", async () => {
  const calls = mockFetch([
    { body: { results: [1, 2], next: "http://localhost:5173/api/v1/items?cursor=c2" } },
    { body: { results: [3], next: "/api/v1/items?cursor=c3" } },
    { body: { results: [4], next: null } },
  ]);
  const r = await collect<number>("/items");
  assert.deepEqual(r, { rows: [1, 2, 3, 4], truncated: false });
  assert.deepEqual(calls.map((c) => c.url), ["/api/v1/items", "/api/v1/items?cursor=c2", "/api/v1/items?cursor=c3"]);
});

test("collect si ferma a maxPages e segnala l'elenco parziale", async () => {
  let n = 0;
  mockFetch([() => ({ body: { results: [n], next: `/api/v1/items?cursor=${++n}` } })]);
  const r = await collect<number>("/items", { maxPages: 3 });
  assert.equal(r.rows.length, 3);
  assert.equal(r.truncated, true);
});

test("collect rifiuta un cursore ripetuto (ciclo)", async () => {
  mockFetch([{ body: { results: [1], next: "/api/v1/items?cursor=same" } }]);
  await assert.rejects(collect("/items"), (e: ApiError) => e.code === "PAGINATION_LOOP");
});

test("gli errori portano status, code stabile, dati e Retry-After", async () => {
  mockFetch([{ status: 429, body: { code: "RATE_LIMITED", message: "Troppi" }, headers: { "Retry-After": "42" } }]);
  await assert.rejects(post("/auth/login", { email: "a@b.it", password: "x" }), (e: ApiError) => e.status === 429 && e.code === "RATE_LIMITED" && e.retryAfter === 42);
  mockFetch([{ status: 400, body: { code: "WEAK_PASSWORD", errors: ["Troppo corta"] } }]);
  await assert.rejects(post("/auth/password-reset/confirm", { token: "t", password: "x" }), (e: ApiError) => Array.isArray((e.data as { errors: string[] }).errors));
});

test("rete assente → ApiError status 0 NETWORK", async () => {
  (globalThis as { fetch: unknown }).fetch = async () => { throw new TypeError("Failed to fetch"); };
  await assert.rejects(get("/portal/overview"), (e: ApiError) => e.status === 0 && e.code === "NETWORK");
});

test("CSRF e Idempotency-Key negli header", async () => {
  const calls = mockFetch([{ body: {} }]);
  await post("/change-requests/", { lesson_id: "l1", kind: "ABSENCE", reason: "x", student_id: "s1" }, { idempotencyKey: "k-1" });
  assert.equal(calls[0].headers["X-CSRFToken"], "test-csrf");
  assert.equal(calls[0].headers["Idempotency-Key"], "k-1");
  assert.equal(calls[0].method, "POST");
  assert.notEqual(newIdempotencyKey(), newIdempotencyKey());
});

test("eventi di sessione: revoca, contesto, MFA; mai sui percorsi del flusso di accesso", async () => {
  const seen: SessionEvent["type"][] = [];
  const off = onSessionEvent((e) => seen.push(e.type));
  mockFetch([{ status: 403, body: { detail: "Authentication credentials were not provided." } }]);
  await assert.rejects(request("GET", "/students/"));
  mockFetch([{ status: 409, body: { code: "CONTEXT_REQUIRED", contexts: ["TUTOR", "GUARDIAN"] } }]);
  await assert.rejects(request("GET", "/students/"));
  mockFetch([{ status: 403, body: { code: "MFA_REQUIRED" } }]);
  await assert.rejects(request("GET", "/audit-events"));
  mockFetch([{ status: 401, body: { code: "NOT_AUTHENTICATED" } }]);
  await assert.rejects(request("GET", "/portal/overview"));
  mockFetch([{ status: 401, body: { code: "INVALID_CREDENTIALS" } }]);
  await assert.rejects(post("/auth/login", { email: "a@b.it", password: "x" }));
  mockFetch([{ status: 403, body: {} }]);
  await assert.rejects(request("GET", "/me"));
  off();
  assert.deepEqual(seen, ["forbidden", "context-required", "mfa-required", "session-ended"]);
});

test("il registro delle operazioni copre gli endpoint dei portali (contratto)", () => {
  const ops = OPERATIONS as Record<string, readonly [string, string]>;
  for (const [m, p] of [["GET", "/portal/overview"], ["GET", "/portal/availability-exceptions"], ["GET", "/portal/attendance-pending"], ["POST", "/change-requests/"], ["POST", "/auth/mfa/verify"], ["GET", "/notifications"], ["POST", "/calendar-feed-tokens"]]) {
    assert.ok(Object.values(ops).some(([mm, pp]) => mm === m && pp === p), `${m} ${p} mancante nel contratto`);
  }
});
