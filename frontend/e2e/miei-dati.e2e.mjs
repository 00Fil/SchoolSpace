#!/usr/bin/env node
/**
 * E2E P5 · portali: «I miei dati» (genitore), consenso e riconferma deleghe (studente maggiorenne),
 * sola visione (studente minorenne). API simulate, Playwright + axe-core, 1440 e 360 px, tema chiaro e scuro.
 * Stessi requisiti di portals.e2e.mjs (PLAYWRIGHT_MODULE, AXE_PATH, CHROMIUM_PATH, EVIDENCE_DIR).
 */
import { spawn } from "node:child_process";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { join, resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const require = createRequire(import.meta.url);
const pw = await import(process.env.PLAYWRIGHT_MODULE ? join(process.env.PLAYWRIGHT_MODULE, "index.mjs") : "playwright");
const axeSource = readFileSync(process.env.AXE_PATH || require.resolve("axe-core/axe.min.js"), "utf8");
const evidence = resolve(root, process.env.EVIDENCE_DIR || "../docs/evidence/v0.9-p5");
mkdirSync(evidence, { recursive: true });
const PORT = Number(process.env.PORT || 4183), BASE = `http://127.0.0.1:${PORT}`;
const day = (n) => new Date(Date.now() + n * 86400000).toISOString();
const KID = "22222222-2222-4222-8222-222222222222";

const users = {
  guardian: { me: { id: "u1", name: "Giulia Rossi", roles: ["GUARDIAN"], tutor_id: null, experimental: true }, ctx: "GUARDIAN",
    data: () => ({ notice_version: "2026-10", role: "GUARDIAN", consent: null, requests: [], exports: [],
      subjects: [{ type: "ACCOUNT", id: "u1", label: "I miei dati di accesso" }, { type: "STUDENT", id: KID, label: "Luca Rossi" }] }) },
  adult: { me: { id: "u2", name: "Sara Neri", roles: ["STUDENT"], tutor_id: null, experimental: true }, ctx: "STUDENT",
    data: () => ({ notice_version: "2026-10", role: "STUDENT", requests: [], exports: [], subjects: [{ type: "ACCOUNT", id: "u2", label: "I miei dati di accesso" }],
      consent: { adult_confirmed: true, consent_at: null, reconfirmations: [{ link_id: "g1", guardian: "Paola Neri", due_at: day(20) }, { link_id: "g2", guardian: "Carlo Neri", due_at: day(20) }] } }) },
  minor: { me: { id: "u3", name: "Luca Rossi", roles: ["STUDENT"], tutor_id: null, experimental: true }, ctx: "STUDENT",
    data: () => ({ notice_version: "2026-10", role: "STUDENT", requests: [], exports: [], subjects: [{ type: "ACCOUNT", id: "u3", label: "I miei dati di accesso" }],
      consent: { adult_confirmed: false, consent_at: null, reconfirmations: [] } }) },
};

function mount(page, state, who) {
  const u = users[who];
  return page.route("**/api/v1/**", async (route) => {
    const req = route.request(), url = new URL(req.url()), p = url.pathname.replace("/api/v1", ""), m = req.method();
    const json = (body, status = 200, headers = {}) => route.fulfill({ status, contentType: "application/json", headers, body: JSON.stringify(body) });
    const body = () => JSON.parse(req.postData() || "{}");
    if (p === "/auth/csrf") return json({ detail: "ok" }, 200, { "set-cookie": "csrftoken=e2e; Path=/" });
    if (p === "/auth/login") { state.signedIn = true; return json({ mfa_required: false, id: u.me.id, contexts: [u.ctx], context: u.ctx, context_required: false }); }
    if (p === "/auth/context") return json({ id: u.me.id, contexts: [u.ctx], context: u.ctx, context_required: false });
    if (p === "/me") return state.signedIn ? json(u.me) : json({ detail: "Accesso richiesto" }, 403);
    if (!state.signedIn) return json({ detail: "Authentication credentials were not provided." }, 403);
    if (p === "/auth/mfa") return json({ required: false, enrolled: false, verified: false, recovery_codes_remaining: 0 });
    if (p === "/portal/overview") return json({ context: u.ctx, roles: [u.ctx], week: { from: day(0).slice(0, 10), until: day(7).slice(0, 10) }, timezone: "Europe/Rome", calendar_enabled: false,
      children: [], tutor: null, open_change_requests: 0, policies: { student_can_request_changes: false, decision: "CENTER", status: "e2e" }, generated_at: day(0) });
    if (p === "/my/lessons") return json({ results: [] });
    state.data ||= u.data();
    if (p === "/me/data") return json(state.data);
    if (p === "/me/data/export") {
      state.exports = [...(state.exports || []), body()];
      if (state.exports.length > 1) return json({ code: "EXPORT_RECENT", message: "Hai già un export da scaricare" }, 409);
      return json({ id: "e1", created_at: day(0), expires_at: day(2), available: true, filename: "miei-dati.json", token: "tok-e2e" }, 201);
    }
    if (p === "/privacy/exports/e1/download") { state.download = body(); return route.fulfill({ status: 200, contentType: "application/json", headers: { "content-disposition": "attachment; filename=\"miei-dati.json\"" }, body: "{}" }); }
    if (p === "/me/data/requests") {
      const b = body(); state.request = b;
      state.data.requests = [{ id: "r1", kind: b.kind, subject_id: b.subject_id, status: "RECEIVED", received_at: day(0), due_at: day(30) }];
      return json(state.data.requests[0], 201);
    }
    if (p === "/auth/student-consent") { state.consent = body().granted; state.data.consent.consent_at = state.consent ? day(0) : null; return json({ consent: state.consent }); }
    let x;
    if ((x = p.match(/^\/registry\/guardian-links\/(\w+)\/(reconfirm|decline)$/))) {
      state.links = [...(state.links || []), { id: x[1], action: x[2], body: body() }];
      state.data.consent.reconfirmations = state.data.consent.reconfirmations.filter((r) => r.link_id !== x[1]);
      return json({ id: x[1] });
    }
    if (m === "GET") return json({ results: [], next: null });
    return json({ code: "NOT_FOUND" }, 404);
  });
}
const results = { checks: [], axe: [], screenshots: [] };
async function axe(page, name) {
  await page.addScriptTag({ content: axeSource });
  const r = await page.evaluate(async () => (await window.axe.run(document, { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"] } })).violations.map((v) => ({ id: v.id, impact: v.impact, nodes: v.nodes.slice(0, 3).map((n) => n.target.join(" ")) })));
  results.axe.push({ name, violations: r });
}
function check(name, ok, info = "") { results.checks.push({ name, ok: !!ok, info }); console.log(`${ok ? "✔" : "✘"} ${name}${info ? " — " + info : ""}`); }
async function shot(page, name) { const f = join(evidence, `${name}.png`); await page.screenshot({ path: f, fullPage: true }); results.screenshots.push(f); }
const noReflow = (page) => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1);

async function open(browser, who, width, theme) {
  const ctx = await browser.newContext({ viewport: { width, height: 900 }, colorScheme: theme, reducedMotion: "reduce", locale: "it-IT", timezoneId: "Europe/Rome", acceptDownloads: true });
  const page = await ctx.newPage(), state = {};
  await mount(page, state, who);
  await page.goto(BASE + "/");
  await page.getByLabel("Email").fill("utente@example.it");
  await page.getByLabel("Password", { exact: true }).fill("una frase lunga");
  await page.getByRole("button", { name: "Accedi" }).click();
  await page.waitForTimeout(300);
  await page.goto(BASE + "/#/dati");
  await page.getByRole("heading", { name: "I miei dati" }).first().waitFor();
  return { ctx, page, state };
}

async function guardian(browser, width, theme) {
  const tag = `genitore-${width}-${theme}`, { ctx, page, state } = await open(browser, "guardian", width, theme);
  await page.getByText("Informativa").first().waitFor();
  check(`[${tag}] nessuno scorrimento orizzontale`, await noReflow(page));
  await axe(page, `dati-${tag}`); await shot(page, `dati-${tag}`);
  await page.getByText("Luca Rossi").first().click();
  await page.getByRole("button", { name: "Prepara la copia dei dati" }).click();
  await page.getByText("Copia pronta").waitFor();
  check(`[${tag}] export del figlio`, state.exports?.[0]?.subject_type === "STUDENT" && state.exports[0].subject_id === KID);
  const dl = page.waitForEvent("download");
  await page.getByRole("button", { name: "Scarica" }).click();
  const file = await dl;
  check(`[${tag}] download monouso con token nel corpo`, state.download?.token === "tok-e2e" && file.suggestedFilename() === "miei-dati.json");
  await page.getByRole("button", { name: "Prepara la copia dei dati" }).click();
  await page.getByText(/file pronto da scaricare/).waitFor();
  check(`[${tag}] secondo export bloccato`, true);
  await page.getByRole("button", { name: "Chiedi cancellazione" }).click();
  await axe(page, `richiesta-${tag}`);
  await page.getByRole("dialog").getByRole("button", { name: "Invia la richiesta" }).click();
  await page.getByText("Ricevuta", { exact: true }).waitFor();
  check(`[${tag}] richiesta di cancellazione`, state.request?.kind === "ERASURE" && state.request.subject_id === KID);
  await ctx.close();
}

async function adult(browser, width) {
  const tag = `maggiorenne-${width}`, { ctx, page, state } = await open(browser, "adult", width, "light");
  await page.getByText("Deleghe da riconfermare").waitFor();
  check(`[${tag}] nessuno scorrimento orizzontale`, await noReflow(page));
  await axe(page, `consenso-${tag}`); await shot(page, `consenso-${tag}`);
  await page.getByRole("button", { name: "Consenti l’accesso" }).click();
  await page.getByText(/Consentito dal/).waitFor();
  check(`[${tag}] consenso registrato`, state.consent === true);
  await page.getByRole("button", { name: "Confermo" }).first().click();
  await page.getByText("Paola Neri").waitFor({ state: "detached" });
  await page.getByRole("button", { name: "Non confermo" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Chiudi la delega" }).click();
  await page.getByText("Carlo Neri").waitFor({ state: "detached" });
  const l = state.links || [];
  check(`[${tag}] riconferma e chiusura con motivo`, l[0]?.action === "reconfirm" && l[0].body.reason && l[1]?.action === "decline" && l[1].body.reason);
  await ctx.close();
}

async function minor(browser, width) {
  const tag = `minorenne-${width}`, { ctx, page } = await open(browser, "minor", width, "light");
  await page.getByText(/sola visione/).waitFor();
  check(`[${tag}] nessuna richiesta di cancellazione`, (await page.getByRole("button", { name: "Chiedi cancellazione" }).count()) === 0);
  check(`[${tag}] nessuno scorrimento orizzontale`, await noReflow(page));
  await axe(page, `minorenne-${tag}`);
  await ctx.close();
}

const server = spawn(process.execPath, [join(root, "node_modules/vite/bin/vite.js"), "preview", "--port", String(PORT), "--strictPort", "--host", "127.0.0.1"], { cwd: root, stdio: "pipe" });
try {
  for (let i = 0; i < 50; i++) { try { await fetch(BASE + "/"); break; } catch { await new Promise((r) => setTimeout(r, 200)); } }
  const browser = await pw.chromium.launch({ executablePath: process.env.CHROMIUM_PATH || undefined, args: ["--no-sandbox"] });
  try {
    for (const width of [1440, 360]) {
      for (const theme of ["light", "dark"]) await guardian(browser, width, theme);
      await adult(browser, width); await minor(browser, width);
    }
  } finally { await browser.close(); }
} catch (e) { check("esecuzione", false, String(e?.stack || e)); } finally { server.kill(); }

const serious = results.axe.flatMap((a) => a.violations.filter((v) => ["serious", "critical"].includes(v.impact)).map((v) => ({ page: a.name, ...v })));
const failed = results.checks.filter((c) => !c.ok);
writeFileSync(join(evidence, "e2e-p5-report.json"), JSON.stringify({ generated_at: new Date().toISOString(), checks: results.checks, axe_serious_or_critical: serious, axe_all: results.axe, screenshots: results.screenshots }, null, 2));
console.log(`\n${results.checks.length - failed.length}/${results.checks.length} controlli superati · ${results.axe.length} pagine axe · ${serious.length} violazioni serie/critiche`);
process.exit(failed.length || serious.length ? 1 : 0);
