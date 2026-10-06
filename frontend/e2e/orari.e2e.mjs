#!/usr/bin/env node
/**
 * E2E P3 «Orari da confermare» del tutor (presa visione e controproposta) con API simulate: Playwright + axe-core.
 * Stessi requisiti di portals.e2e.mjs (PLAYWRIGHT_MODULE, AXE_PATH, CHROMIUM_PATH, EVIDENCE_DIR).
 * Larghezze 1440 e 360 px (criterio §8), tema chiaro e scuro.
 */
import { spawn } from "node:child_process";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { join, resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const require = createRequire(import.meta.url);
const pw = await import(process.env.PLAYWRIGHT_MODULE ? join(process.env.PLAYWRIGHT_MODULE, "index.mjs") : "playwright");
const axeSource = readFileSync(process.env.AXE_PATH || require.resolve("axe-core/axe.min.js"), "utf8");
const evidence = resolve(root, process.env.EVIDENCE_DIR || "../docs/evidence/v0.9-p3");
mkdirSync(evidence, { recursive: true });
const PORT = Number(process.env.PORT || 4181), BASE = `http://127.0.0.1:${PORT}`;

const day = (n) => new Date(Date.now() + n * 86400000).toISOString().slice(0, 10);
const A = "11111111-1111-4111-8111-111111111111", T = "33333333-3333-4333-8333-333333333333", Y = "77777777-7777-4777-8777-777777777777";
const year = { id: Y, name: "2026/27", start_date: day(-30), end_date: day(250), active: true, version: 1,
  periods: [{ id: "p1", kind: "CHRISTMAS", kind_label: "Pausa natalizia", label: "", start_date: day(80), end_date: day(95), closes_center: true, version: 1 },
    { id: "p2", kind: "RECOVERY", kind_label: "Periodo per i recuperi", label: "Giugno", start_date: day(240), end_date: day(250), closes_center: false, version: 1 }] };
const me = { id: "u5", name: "Marco Verdi", roles: ["TUTOR"], tutor_id: T, experimental: false };
const lesson = (id, d, h) => ({ id, start_at: `${day(d)}T${h}:00:00+02:00`, end_at: `${day(d)}T${String(Number(h) + 1).padStart(2, "0")}:00:00+02:00`, subject: "Matematica", mode: "IN_PERSON" });
const acks = () => [
  { id: "k1", publication: "pub1", published_at: new Date().toISOString(), tutor: T, tutor_name: "Marco Verdi", state: "PENDING", note: "", items: [], decision: "", decision_note: "", version: 1, lessons: [lesson("l1", 3, "15"), lesson("l2", 4, "16")] },
  { id: "k2", publication: "pub0", published_at: new Date(Date.now() - 7 * 864e5).toISOString(), tutor: T, tutor_name: "Marco Verdi", state: "PENDING", note: "", items: [], decision: "REJECTED", decision_note: "Aula non disponibile", version: 3, lessons: [lesson("l3", 5, "17")] },
];
function mount(page, state) {
  return page.route("**/api/v1/**", async (route) => {
    const req = route.request(), url = new URL(req.url()), p = url.pathname.replace("/api/v1", ""), m = req.method();
    const json = (body, status = 200, headers = {}) => route.fulfill({ status, contentType: "application/json", headers, body: JSON.stringify(body) });
    const body = () => JSON.parse(req.postData() || "{}");
    if (p === "/auth/csrf") return json({ detail: "ok" }, 200, { "set-cookie": "csrftoken=e2e; Path=/" });
    if (p === "/auth/login") return json({ mfa_required: true, mfa_enrolled: true });
    if (p === "/auth/mfa/verify") { state.signedIn = true; return json({ mfa_required: false, id: "u5", contexts: ["TUTOR"], context: "TUTOR", context_required: false }); }
    if (p === "/me") return state.signedIn ? json(me) : json({ detail: "Accesso richiesto" }, 403);
    if (!state.signedIn) return json({ detail: "Authentication credentials were not provided." }, 403);
    state.rows ||= acks();
    if (p === "/schedule-acks") return json({ results: state.rows, next: null });
    const a = p.match(/^\/schedule-acks\/(\w+)\/(acknowledge|counter)$/);
    if (a && m === "POST") {
      const row = state.rows.find((r) => r.id === a[1]), b = body();
      if (!row || b.expected_version !== row.version) return json({ code: "VERSION_CONFLICT" }, 409);
      state[a[2]] = b; row.version += 1;
      if (a[2] === "acknowledge") row.state = "ACKNOWLEDGED"; else { row.state = "COUNTER"; row.items = b.items; row.note = b.note; }
      return json(row);
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
async function shot(page, name) { const f = join(evidence, `${name}.png`); await page.screenshot({ path: f }); results.screenshots.push(f); }
const noReflow = (page) => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1);

async function scenario(browser, { width, theme }) {
  const tag = `${width}-${theme}`;
  const ctx = await browser.newContext({ viewport: { width, height: 900 }, colorScheme: theme, reducedMotion: "reduce", locale: "it-IT", timezoneId: "Europe/Rome" });
  const page = await ctx.newPage(), state = {};
  await mount(page, state);
  await page.goto(BASE + "/");
  await page.getByLabel("Email").fill("marco@example.it");
  await page.getByLabel("Password", { exact: true }).fill("una frase lunga");
  await page.getByRole("button", { name: "Accedi" }).click();
  await page.getByLabel("Codice dell’app").fill("123456");
  await page.getByRole("button", { name: "Verifica" }).click();
  await page.goto(BASE + "/#/orari");
  await page.getByRole("heading", { name: "Orari da confermare" }).waitFor();
  check(`[${tag}] avviso delle pubblicazioni in attesa`, await page.getByText(/attendono la tua presa visione/).isVisible());
  check(`[${tag}] decisione precedente del centro visibile`, await page.getByText("Aula non disponibile").isVisible());
  check(`[${tag}] nessuno scorrimento orizzontale`, await noReflow(page));
  await axe(page, `orari-${tag}`); await shot(page, `orari-${tag}`);
  // Presa visione da tastiera
  const confirm = page.getByRole("button", { name: "Confermo la presa visione" }).first();
  await confirm.focus(); await page.keyboard.press("Enter");
  await page.getByText("Presa visione confermata").first().waitFor();
  check(`[${tag}] presa visione inviata con la versione`, state.acknowledge?.expected_version === 1);
  // Controproposta: validazione e invio
  await page.getByRole("button", { name: "Proponi modifiche" }).first().click();
  await page.getByRole("dialog").waitFor();
  await page.getByRole("button", { name: "Invia al centro" }).click();
  check(`[${tag}] senza lezioni scelte non invia`, !state.counter && await page.getByText("Scegli almeno una lezione.").isVisible());
  await page.getByRole("dialog").getByRole("checkbox").first().check();
  await page.getByRole("button", { name: "Invia al centro" }).click();
  check(`[${tag}] modifica vuota segnalata`, !state.counter && await page.getByText("Scrivi la modifica che proponi.").isVisible());
  await page.getByLabel("Modifica proposta").fill("Spostare a mercoledì alla stessa ora");
  await axe(page, `orari-controproposta-${tag}`);
  await page.getByRole("button", { name: "Invia al centro" }).click();
  await page.getByText("Modifiche proposte, in attesa del centro").first().waitFor();
  check(`[${tag}] controproposta inviata`, state.counter?.items?.length === 1 && state.counter.items[0].lesson_id === "l1");
  await shot(page, `orari-inviata-${tag}`);
  await ctx.close();
}
const server = spawn(process.execPath, [join(root, "node_modules/vite/bin/vite.js"), "preview", "--port", String(PORT), "--strictPort", "--host", "127.0.0.1"], { cwd: root, stdio: "pipe" });
try {
  for (let i = 0; i < 50; i++) { try { await fetch(BASE + "/"); break; } catch { await new Promise((r) => setTimeout(r, 200)); } }
  const browser = await pw.chromium.launch({ executablePath: process.env.CHROMIUM_PATH || undefined, args: ["--no-sandbox"] });
  try { for (const width of [1440, 360]) for (const theme of ["light", "dark"]) await scenario(browser, { width, theme }); }
  finally { await browser.close(); }
} catch (e) { check("esecuzione", false, String(e?.stack || e)); } finally { server.kill(); }

const serious = results.axe.flatMap((a) => a.violations.filter((v) => ["serious", "critical"].includes(v.impact)).map((v) => ({ page: a.name, ...v })));
const failed = results.checks.filter((c) => !c.ok);
writeFileSync(join(evidence, "e2e-p3-report.json"), JSON.stringify({ generated_at: new Date().toISOString(), checks: results.checks, axe_serious_or_critical: serious, axe_all: results.axe, screenshots: results.screenshots }, null, 2));
console.log(`\n${results.checks.length - failed.length}/${results.checks.length} controlli superati · ${results.axe.length} pagine axe · ${serious.length} violazioni serie/critiche`);
process.exit(failed.length || serious.length ? 1 : 0);
