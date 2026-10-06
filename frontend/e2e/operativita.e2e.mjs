#!/usr/bin/env node
/**
 * E2E P4 scenari UAT della coda «Da gestire» (assenza, recupero, spostamento, chiusura imprevista) con API simulate: Playwright + axe-core.
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
const evidence = resolve(root, process.env.EVIDENCE_DIR || "../docs/evidence/v0.9-p4");
mkdirSync(evidence, { recursive: true });
const PORT = Number(process.env.PORT || 4182), BASE = `http://127.0.0.1:${PORT}`;

const day = (n) => new Date(Date.now() + n * 86400000).toISOString().slice(0, 10);
const S = "11111111-1111-4111-8111-111111111111", T = "33333333-3333-4333-8333-333333333333";
const me = { id: "u9", name: "Laura Bianchi", roles: ["CENTER"], tutor_id: null, experimental: true };
const seed = () => ({
  requests: [
    { id: "r1", lesson_id: "l1", kind: "ABSENCE", origin: "GUARDIAN", student_id: S, reason: "Visita medica", state: "SUBMITTED", version: 1, awaiting: "CENTER", lesson_start_at: `${day(3)}T15:00:00+02:00`, proposal: {} },
    { id: "r2", lesson_id: "l2", kind: "RESCHEDULE", origin: "GUARDIAN", student_id: S, reason: "Gara sportiva", state: "SUBMITTED", version: 1, awaiting: "CENTER", lesson_start_at: `${day(4)}T16:00:00+02:00`, proposal: { start_at: `${day(5)}T16:00:00+02:00` } }],
  obligations: [{ id: "o1", participants: [S], minutes_remaining: 60, cause: "STUDENT_ABSENCE", state: "OPEN", version: 1, origin_start_at: `${day(-2)}T15:00:00+02:00`, due_by: day(250), recovery_periods: [{ start_date: day(240), end_date: day(250), label: "Giugno" }] }],
  cases: [{ id: "c1", lesson_id: "l3", kind: "CLOSURE", codes: ["CLOSED"], state: "OPEN", version: 1, week_start: day(0), created_at: new Date().toISOString() }],
});
function mount(page, state) {
  return page.route("**/api/v1/**", async (route) => {
    const req = route.request(), url = new URL(req.url()), p = url.pathname.replace("/api/v1", ""), m = req.method();
    const json = (body, status = 200, headers = {}) => route.fulfill({ status, contentType: "application/json", headers, body: JSON.stringify(body) });
    const body = () => JSON.parse(req.postData() || "{}");
    if (p === "/auth/csrf") return json({ detail: "ok" }, 200, { "set-cookie": "csrftoken=e2e; Path=/" });
    if (p === "/auth/login") return json({ mfa_required: true, mfa_enrolled: true });
    if (p === "/auth/mfa/verify") { state.signedIn = true; return json({ mfa_required: false, id: "u9", contexts: ["CENTER"], context: "CENTER", context_required: false }); }
    if (p === "/planning/readiness") return json({ ready: false, gate: "G1", blockers: [], release: "e2e" });
    if (p === "/me") return state.signedIn ? json(me) : json({ detail: "Accesso richiesto" }, 403);
    if (!state.signedIn) return json({ detail: "Authentication credentials were not provided." }, 403);
    Object.assign(state, { ...seed(), ...state });
    if (p === "/students/") return json({ results: [{ id: S, display_name: "Giulia Rossi" }], next: null });
    if (p === "/tutors/") return json({ results: [{ id: T, display_name: "Marco Verdi" }], next: null });
    if (p === "/change-requests/") return json({ results: state.requests.filter((r) => r.state === "SUBMITTED"), next: null });
    if (p === "/recovery-obligations/") return json({ results: state.obligations.filter((o) => o.state === "OPEN") });
    if (p === "/conflict-cases/") return json({ results: state.cases.filter((c) => c.state === "OPEN") });
    let x;
    if ((x = p.match(/^\/change-requests\/(\w+)\/decide\/$/))) {
      const r = state.requests.find((y) => y.id === x[1]), b = body(); state.decide = [...(state.decide || []), b];
      if (b.expected_version !== r.version) return json({ code: "VERSION_CONFLICT" }, 409);
      r.version += 1; if (b.decision === "ACCEPT") { r.awaiting = "TUTOR"; return json({ ...r, awaiting: "TUTOR" }); } r.state = "REJECTED"; return json(r);
    }
    if ((x = p.match(/^\/recovery-obligations\/(\w+)\/makeup\/$/))) {
      const b = body(); state.makeup = b;
      if (b.start_at.slice(0, 10) > day(250)) return json({ code: "RECOVERY_PAST_DUE", message: "Oltre la fine dell’anno" }, 422);
      state.obligations[0].state = "SCHEDULED"; return json({ id: "o1", state: "SCHEDULED" });
    }
    if ((x = p.match(/^\/conflict-cases\/(\w+)\/resolve\/$/))) {
      const b = body(); state.resolve = [...(state.resolve || []), b];
      if (b.recovery_cause === "STUDENT_ABSENCE" && !b.grant_late_notice) return json({ code: "LATE_NOTICE" }, 422);
      state.cases[0].state = "RESOLVED"; return json({ id: "c1", state: "RESOLVED" });
    }
    if (p === "/conflict-cases/detect/") return json({ opened: 0 });
    if (p === "/communications/status") return json({ counts: { IN_APP: { SENT: 12 } }, dead_letter: 0, ambiguous: 0, oldest_pending_seconds: null });
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
  // UAT 1 · assenza segnalata dal genitore: il centro accetta, poi attende il tutor
  await page.goto(BASE + "/#/operativita?tab=richieste");
  await page.getByRole("heading", { name: "Da gestire" }).waitFor();
  await page.getByText("Visita medica").waitFor();
  check(`[${tag}] nessuno scorrimento orizzontale`, await noReflow(page));
  await axe(page, `richieste-${tag}`); await shot(page, `richieste-${tag}`);
  await page.getByRole("button", { name: "Accetta" }).first().click();
  await page.getByRole("dialog").getByText(/conferma anche il tutor/).waitFor();
  check(`[${tag}] nessun motivo da scrivere`, (await page.getByRole("dialog").getByLabel("Motivo").count()) === 0);
  check(`[${tag}] avviso doppia conferma`, await page.getByText(/conferma anche il tutor/).isVisible());
  await page.getByRole("dialog").getByRole("button", { name: "Accetta" }).click();
  await page.getByText("Attende il tutor").first().waitFor();
  check(`[${tag}] accettazione con versione`, state.decide?.[0]?.expected_version === 1 && state.decide[0].decision === "ACCEPT" && !!state.decide[0].reason);
  // UAT 2 · spostamento rifiutato
  await page.getByRole("button", { name: "Rifiuta" }).first().click();
  await page.getByRole("dialog").getByRole("button", { name: "Rifiuta" }).click();
  await page.getByText("Gara sportiva").waitFor({ state: "detached" });
  check(`[${tag}] spostamento rifiutato`, state.decide?.[1]?.decision === "REJECT");
  // UAT 3 · recupero fissato entro la fine dell'anno
  await page.goto(BASE + "/#/operativita?tab=recuperi");
  await page.getByRole("button", { name: "Fissa" }).first().click();
  await page.getByRole("dialog").getByLabel("Tutor", { exact: true }).selectOption(T);
  await axe(page, `recupero-${tag}`);
  await page.getByRole("button", { name: "Fissa il recupero" }).click();
  await page.getByText("Nessun recupero da fissare").waitFor();
  check(`[${tag}] recupero fissato`, state.makeup?.tutor_id === T && /T15:00:00[+-]\d\d:\d\d$/.test(state.makeup.start_at));
  // UAT 4 · chiusura imprevista: annullata con recupero
  await page.goto(BASE + "/#/operativita?tab=conflitti");
  await page.getByRole("button", { name: "Risolvi" }).first().click();
  await page.getByRole("dialog").getByRole("button", { name: "Applica" }).click();
  await page.getByText("Nessun conflitto aperto").waitFor();
  check(`[${tag}] chiusura annullata con recupero`, state.resolve?.[0]?.resolution === "CANCEL" && state.resolve[0].recovery_cause === "CLOSURE");
  await page.goto(BASE + "/#/operativita?tab=invii");
  await page.getByText("Avvisi nel portale", { exact: true }).waitFor();
  check(`[${tag}] pannello comunicazioni`, await page.getByText("Nessun invio da controllare").isVisible());
  await axe(page, `invii-${tag}`); await shot(page, `invii-${tag}`);
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
writeFileSync(join(evidence, "e2e-p4-report.json"), JSON.stringify({ generated_at: new Date().toISOString(), checks: results.checks, axe_serious_or_critical: serious, axe_all: results.axe, screenshots: results.screenshots }, null, 2));
console.log(`\n${results.checks.length - failed.length}/${results.checks.length} controlli superati · ${results.axe.length} pagine axe · ${serious.length} violazioni serie/critiche`);
process.exit(failed.length || serious.length ? 1 : 0);
