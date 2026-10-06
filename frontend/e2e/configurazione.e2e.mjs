#!/usr/bin/env node
/**
 * E2E P2 «Configurazione» e calendario delle disponibilità con API simulate: Playwright + axe-core.
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
const evidence = resolve(root, process.env.EVIDENCE_DIR || "../docs/evidence/v0.9-p2");
mkdirSync(evidence, { recursive: true });
const PORT = Number(process.env.PORT || 4180), BASE = `http://127.0.0.1:${PORT}`;

const day = (n) => new Date(Date.now() + n * 86400000).toISOString().slice(0, 10);
const A = "11111111-1111-4111-8111-111111111111", T = "33333333-3333-4333-8333-333333333333", Y = "77777777-7777-4777-8777-777777777777";
const year = { id: Y, name: "2026/27", start_date: day(-30), end_date: day(250), active: true, version: 1,
  periods: [{ id: "p1", kind: "CHRISTMAS", kind_label: "Pausa natalizia", label: "", start_date: day(80), end_date: day(95), closes_center: true, version: 1 },
    { id: "p2", kind: "RECOVERY", kind_label: "Periodo per i recuperi", label: "Giugno", start_date: day(240), end_date: day(250), closes_center: false, version: 1 }] };
const me = { id: "u9", name: "Laura Bianchi", roles: ["CENTER"], tutor_id: null, experimental: true };

function mount(page, state) {
  return page.route("**/api/v1/**", async (route) => {
    const req = route.request(), url = new URL(req.url()), p = url.pathname.replace("/api/v1", ""), m = req.method();
    const json = (body, status = 200, headers = {}) => route.fulfill({ status, contentType: "application/json", headers, body: JSON.stringify(body) });
    const body = () => JSON.parse(req.postData() || "{}");
    if (p === "/auth/csrf") return json({ detail: "ok" }, 200, { "set-cookie": "csrftoken=e2e; Path=/" });
    if (p === "/auth/login") return json({ mfa_required: true, mfa_enrolled: true });
    if (p === "/auth/mfa/verify") { state.signedIn = true; return json({ mfa_required: false, id: "u9", contexts: ["CENTER"], context: "CENTER", context_required: false }); }
    if (p === "/me") return state.signedIn ? json(me) : json({ detail: "Accesso richiesto" }, 403);
    if (!state.signedIn) return json({ detail: "Authentication credentials were not provided." }, 403);
    if (p === "/students/") return json({ results: [{ id: A, display_name: "Anna Rossi", level: "Liceo" }], next: null });
    if (p === "/tutors/") return json({ results: [{ id: T, display_name: "Marco Verdi" }], next: null });
    if (p === "/availability-rules/" && m === "POST") { state.posted = (state.posted || 0) + 1; return json({ id: "rn", status: "DRAFT" }, 201); }
    if (p === "/availability-rules/") return json({ results: [
      { id: "r1", student: A, tutor: null, weekday: 1, start_time: "15:00:00", end_time: "18:00:00", status: "APPROVED", version: 1, period_start: day(-30), period_end: day(90), mode: "IN_PERSON", location: "ON_SITE" },
      { id: "r2", student: null, tutor: T, weekday: 3, start_time: "16:00:00", end_time: "18:00:00", status: "DRAFT", version: 1, period_start: day(-1), period_end: day(90), mode: "IN_PERSON", location: "ON_SITE" }], next: null });
    if (p === "/resources/") return json({ results: [{ id: "res1", name: "Aula 1", kind: "SPACE", student_capacity: 4, active: true }], next: null });
    if (p === "/planning/readiness") return json({ ready: false, gate: "G1", blockers: [], release: "e2e" });
    if (p === "/planning/school-years") return m === "POST" ? json(year, 201) : json({ count: 1, page: 1, results: [year] });
    if (p === "/planning/school-years/current") return json(year);
    if (p === "/planning/service-windows/replace") { state.replace = body(); return json({ created: state.replace.slots.length, removed: 0 }); }
    if (p === "/availability/bulk-review") { state.bulk = body(); return json({ changed: state.bulk.ids, skipped: [], not_found: [] }); }
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
  await page.getByLabel("Email").fill("laura@example.it");
  await page.getByLabel("Password", { exact: true }).fill("una frase lunga");
  await page.getByRole("button", { name: "Accedi" }).click();
  await page.getByLabel("Codice dell’app").fill("123456");
  await page.getByRole("button", { name: "Verifica" }).click();

  // Anno scolastico
  await page.goto(BASE + "/#/configurazione?tab=anno");
  await page.getByRole("heading", { name: "2026/27" }).waitFor();
  check(`[${tag}] la pausa natalizia risulta «Niente lezioni»`, await page.getByText("Niente lezioni").filter({ visible: true }).first().isVisible());
  check(`[${tag}] il periodo per i recuperi risulta «Recuperi»`, await page.getByText("Recuperi", { exact: true }).filter({ visible: true }).first().isVisible());
  check(`[${tag}] nessuno scorrimento orizzontale (anno)`, await noReflow(page));
  await axe(page, `cfg-anno-${tag}`); await shot(page, `cfg-anno-${tag}`);

  // Orari: calendario settimanale (alternativa da tastiera: «Aggiungi fascia»)
  await page.goto(BASE + "/#/configurazione?tab=orari");
  await page.locator(".wp").first().waitFor();
  await page.getByRole("button", { name: "Aggiungi fascia" }).first().click();
  await page.getByRole("dialog").getByRole("button", { name: "Salva" }).click();
  check(`[${tag}] la nuova fascia compare sul calendario`, (await page.locator(".wp .wp-block").count()) > 0);
  await page.getByRole("button", { name: "Salva orari" }).click();
  await page.waitForTimeout(300);
  check(`[${tag}] orari inviati con motivo e slot`, state.replace && state.replace.reason && state.replace.slots.length >= 1, JSON.stringify(state.replace?.slots));
  await axe(page, `cfg-orari-${tag}`); await shot(page, `cfg-orari-${tag}`);

  // Approvazione in blocco
  await page.goto(BASE + "/#/configurazione?tab=approva");
  await page.getByText("Seleziona tutte").click();
  await page.getByRole("button", { name: /Approva selezionate/ }).click();
  await page.waitForTimeout(300);
  check(`[${tag}] approvazione in blocco della bozza`, state.bulk?.status === "APPROVED" && state.bulk.ids.includes("r2"));
  await axe(page, `cfg-approva-${tag}`);

  // Regole di pianificazione: stato vuoto
  await page.goto(BASE + "/#/configurazione?tab=regole");
  check(`[${tag}] regole: stato vuoto`, await page.getByText("Ancora niente").waitFor({ timeout: 3000 }).then(() => true, () => false));
  await axe(page, `cfg-regole-${tag}`);

  // Disponibilità per persona sul calendario settimanale
  await page.goto(BASE + `/#/disponibilita?chi=student:${A}`);
  const g2 = page.getByRole("group", { name: /Anna Rossi/ }); await g2.waitFor();
  check(`[${tag}] la fascia approvata compare sul calendario`, (await g2.locator(".wp-block").count()) > 0);
  check(`[${tag}] nessuno scorrimento orizzontale (griglia)`, await noReflow(page));
  await axe(page, `disp-griglia-${tag}`); await shot(page, `disp-griglia-${tag}`);
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
writeFileSync(join(evidence, "e2e-p2-report.json"), JSON.stringify({ generated_at: new Date().toISOString(), checks: results.checks, axe_serious_or_critical: serious, axe_all: results.axe, screenshots: results.screenshots }, null, 2));
console.log(`\n${results.checks.length - failed.length}/${results.checks.length} controlli superati · ${results.axe.length} pagine axe · ${serious.length} violazioni serie/critiche`);
process.exit(failed.length || serious.length ? 1 : 0);
