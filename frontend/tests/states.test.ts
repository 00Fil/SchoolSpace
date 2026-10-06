import { test } from "node:test";
import assert from "node:assert/strict";
import { ApiError } from "../src/api/client";
import { classify, STATE_COPY } from "../src/ui/states";
import { human } from "../src/messages";

test("classify: ogni errore API diventa uno stato di vista esplicito (G04)", () => {
  const c = (status: number, code = "") => classify(new ApiError(status, "x", code));
  assert.equal(c(0, "NETWORK"), "offline");
  assert.equal(c(409, "VERSION_CONFLICT"), "stale");
  assert.equal(c(409, "SNAPSHOT_CHANGED"), "stale");
  assert.equal(c(409), "stale");
  assert.equal(c(409, "BOOKING_CONFLICT"), "conflict");
  assert.equal(c(422, "UNKNOWN"), "inconclusive");
  assert.equal(c(503, "DEVELOPMENT_ONLY"), "disabled");
  assert.equal(c(503, "FEATURE_DISABLED"), "disabled");
  assert.equal(c(404), "revoked");
  assert.equal(c(403, "CONTEXT_NOT_GRANTED"), "revoked");
  assert.equal(c(401, "NOT_AUTHENTICATED"), "revoked");
  assert.equal(c(403, "FORBIDDEN"), "forbidden");
  assert.equal(c(500), "error");
  assert.equal(classify(new Error("boom")), "error");
});

test("ogni stato ha titolo e testo in italiano", () => {
  for (const [k, v] of Object.entries(STATE_COPY)) { assert.ok(v.title.length > 5, k); assert.ok(v.text.length > 10, k); }
});

test("messaggi umani: Retry-After e dettagli di WEAK_PASSWORD", () => {
  assert.match(human(new ApiError(429, "x", "RATE_LIMITED", null, 30)).text, /30 secondi/);
  assert.match(human(new ApiError(429, "x", "RATE_LIMITED", null, 600)).text, /10 minuti/);
  assert.match(human(new ApiError(400, "x", "WEAK_PASSWORD", { errors: ["Troppo comune."] })).text, /Troppo comune/);
  assert.match(human(new ApiError(401, "x", "INVALID_CREDENTIALS")).text, /Email o password/);
  const h = human(new ApiError(409, "Oggetto cambiato", "VERSION_CONFLICT"));
  assert.match(h.detail, /HTTP 409 · VERSION_CONFLICT/);
});
