import { test } from "node:test";
import assert from "node:assert/strict";
import { cleanCode, isTotp, nextStep, passwordHints, publicPage, savePendingInvite, takePendingInvite, tokenFromHash } from "../src/auth/flow";

test("dopo il login: MFA da verificare, da attivare, contesto o fine", () => {
  assert.deepEqual(nextStep({ mfa_required: true, mfa_enrolled: true }), { kind: "mfa-verify" });
  assert.deepEqual(nextStep({ mfa_required: true, mfa_enrolled: false }), { kind: "mfa-setup" });
  assert.deepEqual(nextStep({ mfa_required: false, contexts: ["TUTOR", "GUARDIAN"], context: null, context_required: true }), { kind: "context", contexts: ["TUTOR", "GUARDIAN"], current: null });
  assert.deepEqual(nextStep({ mfa_required: false, contexts: ["GUARDIAN"], context: "GUARDIAN", context_required: false }), { kind: "done" });
  // context_required con un solo contesto non blocca
  assert.deepEqual(nextStep({ mfa_required: false, contexts: ["TUTOR"], context_required: true }), { kind: "done" });
});

test("codici di recupero mostrati prima del passo successivo", () => {
  const s = nextStep({ mfa_required: false, recovery_codes: ["a", "b"], contexts: ["CENTER", "TUTOR"], context_required: true });
  assert.equal(s.kind, "recovery-codes");
  assert.ok(s.kind === "recovery-codes" && s.then.kind === "context" && s.codes.length === 2);
});

test("pagine pubbliche e token nel frammento", () => {
  assert.equal(publicPage("/invito"), "invite");
  assert.equal(publicPage("/invito/"), "invite");
  assert.equal(publicPage("/reimposta-password"), "reset");
  assert.equal(publicPage("/"), null);
  assert.equal(tokenFromHash("#token=AbC-_123456789xyz"), "AbC-_123456789xyz");
  assert.equal(tokenFromHash("#token=<script>"), "");
  assert.equal(tokenFromHash("#token=short"), "");
  assert.equal(tokenFromHash(""), "");
});

test("invito in sospeso: letto una sola volta", () => {
  const m = new Map<string, string>();
  const store = { getItem: (k: string) => m.get(k) ?? null, setItem: (k: string, v: string) => void m.set(k, v), removeItem: (k: string) => void m.delete(k) };
  savePendingInvite("tok-123456789", store);
  assert.equal(takePendingInvite(store), "tok-123456789");
  assert.equal(takePendingInvite(store), "");
});

test("suggerimenti password e codici TOTP", () => {
  assert.deepEqual(passwordHints("una frase lunga e sicura"), []);
  assert.ok(passwordHints("corta").length >= 1);
  assert.ok(passwordHints("123456789012").includes("Non usare solo numeri."));
  assert.ok(passwordHints("mario.rossi-2026!", "mario.rossi@example.it").some((h) => h.includes("email")));
  assert.equal(cleanCode(" 123 456 "), "123456");
  assert.ok(isTotp("123 456"));
  assert.ok(!isTotp("12345"));
  assert.ok(!isTotp("abcdef"));
});
