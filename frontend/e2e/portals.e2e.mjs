#!/usr/bin/env node
/**
 * E2E dei portali e dell'accesso (GAP-G06) con API simulate: Playwright + axe-core.
 * Avvia `vite preview` sulla build in dist/, intercetta /api/v1/** con dati sintetici,
 * esegue i percorsi chiave a 1440 e 390 px in tema chiaro e scuro e controlla WCAG 2.2 AA.
 *
 * Requisiti (dev-dependency da aggiungere: playwright, axe-core):
 *   PLAYWRIGHT_MODULE=/percorso/node_modules/playwright  (default: import "playwright")
 *   AXE_PATH=/percorso/axe-core/axe.min.js               (default: require.resolve("axe-core"))
 *   CHROMIUM_PATH=/usr/local/bin/chromium                (facoltativo)
 *   EVIDENCE_DIR=../docs/evidence/v0.8-s6                (screenshot e report JSON)
 */
import { spawn } from "node:child_process";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join, resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const require = createRequire(import.meta.url);
const pw = await import(process.env.PLAYWRIGHT_MODULE ? join(process.env.PLAYWRIGHT_MODULE, "index.mjs") : "playwright");
const axeSource = readFileSync(process.env.AXE_PATH || require.resolve("axe-core/axe.min.js"), "utf8");
const evidence = resolve(root, process.env.EVIDENCE_DIR || "../docs/evidence/v0.8-s6");
mkdirSync(evidence, { recursive: true });
const PORT = Number(process.env.PORT || 4179), BASE = `http://127.0.0.1:${PORT}`;

/* ---------------- dati sintetici ---------------- */
const day = (n) => new Date(Date.now() + n * 86400000).toISOString().slice(0, 10);
const at = (n, h, m = 0) => { const d = new Date(Date.now() + n * 86400000); d.setUTCHours(h - 1, m, 0, 0); return d.toISOString(); };
const monday = (() => { const d = new Date(); const wd = (d.getUTCDay() + 6) % 7; return day(-wd); })();
const perms = (p = {}) => ({ can_view: true, can_manage_availability: false, can_request_changes: false, can_receive_notifications: true, ...p });
const kid = (id, name, p, extra = {}) => ({ student_id: id, display_name: name, level: "Liceo", relation: "GUARDIAN", permissions: perms(p), read_only: !p.can_request_changes && !p.can_manage_availability, reconfirmation: null, availability: { approved: 2, draft: 1, revoked: 0, exceptions_upcoming: 3 }, week: { lessons: 3, cancelled: 0, minutes: 180, next_lesson_at: at(1, 15) }, open_change_requests: 1, ...extra });
const A = "11111111-1111-4111-8111-111111111111", B = "22222222-2222-4222-8222-222222222222", T = "33333333-3333-4333-8333-333333333333";
const L1 = "44444444-4444-4444-8444-444444444444", L2 = "55555555-5555-4555-8555-555555555555", L3 = "66666666-6666-4666-8666-666666666666";
const byDay = Array.from({ length: 7 }, (_, i) => ({ date: day(i - ((new Date().getUTCDay() + 6) % 7)), minutes: [120, 300, 60, 0, 180, 0, 0][i] }));
const users = {
  guardian: { me: { id: "u1", name: "Giulia Rossi", roles: ["GUARDIAN"], tutor_id: null, experimental: true }, contexts: ["GUARDIAN"],
    overview: { context: "GUARDIAN", roles: ["GUARDIAN"], week: { from: monday, until: day(7) }, timezone: "Europe/Rome", calendar_enabled: true,
      children: [kid(A, "Anna Rossi", { can_request_changes: true, can_manage_availability: true }), kid(B, "Bruno Rossi", {}, { level: "Medie", open_change_requests: 0 })],
      tutor: null, open_change_requests: 1, policies: { student_can_request_changes: false, decision: "D07", status: "DA_APPROVARE" }, generated_at: new Date().toISOString() },
    students: [{ id: A, display_name: "Anna Rossi", level: "Liceo" }, { id: B, display_name: "Bruno Rossi", level: "Medie" }],
    lessons: [
      { id: L1, state: "PUBLISHED", start_at: at(0, 23, 0) > new Date().toISOString() ? at(1, 15) : at(1, 15), end_at: at(1, 16), subject_name: "Matematica", tutor_name: "Marco Verdi", mode: "IN_PERSON", location: "ON_SITE", space_name: "Aula 1", as_tutor: false, participants: [{ student_id: A, name: "Anna Rossi" }], other_participants: 0 },
      { id: L2, state: "PUBLISHED", start_at: at(1, 17), end_at: at(1, 18), subject_name: "Inglese", tutor_name: "Sara Neri", mode: "ONLINE", location: "REMOTE", space_name: null, as_tutor: false, participants: [{ student_id: B, name: "Bruno Rossi" }], other_participants: 1 },
    ] },
  tutor: { me: { id: "u2", name: "Marco Verdi", roles: ["TUTOR"], tutor_id: T, experimental: true }, contexts: ["TUTOR"],
    overview: { context: "TUTOR", roles: ["TUTOR"], week: { from: monday, until: day(7) }, timezone: "Europe/Rome", calendar_enabled: true, children: [],
      tutor: { tutor_id: T, display_name: "Marco Verdi", limits: { daily_limit_minutes: 240, weekly_limit_minutes: 900, pause_minutes: 15 }, availability: { approved: 3, draft: 0, revoked: 0, exceptions_upcoming: 1 },
        week: { lessons: 9, scheduled_minutes: 660, completed_minutes: 240, cancelled_minutes: 60, by_day: byDay, attendance_pending: 2 } },
      open_change_requests: 0, policies: { student_can_request_changes: false, decision: "D07", status: "DA_APPROVARE" }, generated_at: new Date().toISOString() },
    students: [], lessons: [
      { id: L3, state: "PUBLISHED", start_at: at(-1, 15), end_at: at(-1, 16), subject_name: "Fisica", tutor_name: "Marco Verdi", mode: "IN_PERSON", location: "ON_SITE", space_name: "Aula 2", as_tutor: true, participants: [{ student_id: A, name: "Anna Rossi" }, { student_id: B, name: "Bruno Rossi" }], other_participants: 0 },
    ] },
};
const exceptions = Array.from({ length: 25 }, (_, i) => ({ id: `e${i}`, kind: i % 3 ? "REMOVE_AVAILABLE" : "ADD_AVAILABLE", mode: "IN_PERSON", location: "ON_SITE", start_at: at(i + 2, 15), end_at: at(i + 2, 17) }));

/* ---------------- intercettazione API ---------------- */
function mount(page, state) {
  const log = [];
  return page.route("**/api/v1/**", async (route) => {
    const req = route.request(), url = new URL(req.url()), p = url.pathname.replace("/api/v1", ""), m = req.method();
    log.push({ m, p, headers: req.headers(), body: req.postData() });
    state.log = log;
    const u = users[state.user || "guardian"];
    const json = (body, status = 200, headers = {}) => route.fulfill({ status, contentType: "application/json", headers, body: JSON.stringify(body) });
    if (state.revoked && !p.startsWith("/auth/")) return json({ detail: "Authentication credentials were not provided." }, 403);
    if (p === "/auth/csrf") return json({ detail: "ok" }, 200, { "set-cookie": "csrftoken=e2e; Path=/" });
    if (p === "/auth/login") {
      const b = JSON.parse(req.postData() || "{}");
      if (b.password !== "una frase lunga") return json({ code: "INVALID_CREDENTIALS", message: "Credenziali non valide" }, 401);
      if (state.mfa) return json({ mfa_required: true, mfa_enrolled: true });
      state.signedIn = true;
      return json({ mfa_required: false, id: "u1", contexts: state.multi ? ["TUTOR", "GUARDIAN"] : u.contexts, context: null, context_required: !!state.multi });
    }
    if (p === "/auth/mfa/verify") { const b = JSON.parse(req.postData() || "{}"); if (b.code !== "123456") return json({ code: "INVALID_CODE" }, 400); state.signedIn = true; return json({ mfa_required: false, id: "u1", contexts: u.contexts, context: u.contexts[0], context_required: false }); }
    if (p === "/auth/context") { if (m === "POST") { state.user = JSON.parse(req.postData()).context === "TUTOR" ? "tutor" : "guardian"; state.multi = false; } return json({ id: "u1", contexts: state.multiCtx ? ["TUTOR", "GUARDIAN"] : users[state.user || "guardian"].contexts, context: state.user === "tutor" ? "TUTOR" : "GUARDIAN" }); }
    if (p === "/auth/logout") { state.signedIn = false; return json({ detail: "ok" }); }
    if (p === "/invitations/accept") return json({ detail: "Invito accettato" }, 201);
    if (p === "/me") return state.signedIn ? (state.multi ? json({ code: "CONTEXT_REQUIRED", contexts: ["TUTOR", "GUARDIAN"] }, 409) : json(u.me)) : json({ detail: "Accesso richiesto" }, 403);
    if (!state.signedIn) return json({ detail: "Authentication credentials were not provided." }, 403);
    if (p === "/students/") return json({ results: u.students, next: null });
    if (p === "/tutors/") return json({ results: state.user === "tutor" ? [{ id: T, display_name: "Marco Verdi" }] : [], next: null });
    if (p === "/availability-rules/") return json({ results: state.user === "tutor"
      ? [{ id: "r3", student: null, tutor: T, weekday: 0, start_time: "14:00:00", end_time: "19:00:00", status: "APPROVED", version: 1, period_start: day(-30), period_end: day(90), mode: "IN_PERSON", location: "ON_SITE" }]
      : [{ id: "r1", student: A, tutor: null, weekday: 1, start_time: "15:00:00", end_time: "18:00:00", status: "APPROVED", version: 1, period_start: day(-30), period_end: day(90), mode: "IN_PERSON", location: "ON_SITE" },
        { id: "r2", student: B, tutor: null, weekday: 3, start_time: "16:00:00", end_time: "18:00:00", status: "DRAFT", version: 1, period_start: day(-1), period_end: day(90), mode: "ONLINE", location: "REMOTE" }], next: null });
    if (p === "/teaching-requests/") return json({ results: [], next: null });
    if (p === "/portal/overview") return json(u.overview);
    if (p === "/portal/availability-exceptions") {
      const start = Number(url.searchParams.get("cursor") || 0), size = 20;
      const rows = exceptions.slice(start, start + size);
      return json({ results: rows, next: start + size < exceptions.length ? `${BASE}/api/v1/portal/availability-exceptions?cursor=${start + size}&${url.searchParams.has("student") ? "student=" + url.searchParams.get("student") : "tutor=" + url.searchParams.get("tutor")}` : null, previous: null });
    }
    if (p === "/availability/effective") return json({ ready: false, from: monday, until: day(7), timezone: "Europe/Rome", problems: [{ code: "DRAFT_PRESENT", severity: "info", message: "Una fascia è ancora in bozza." }],
      windows: [{ mode: "IN_PERSON", location: "ON_SITE", start_at: at(1, 15), end_at: at(1, 18), minutes: 180 }] });
    if (p === "/my/lessons") return json({ results: u.lessons });
    if (p === "/change-requests/") {
      if (m === "POST") { state.cr = { headers: req.headers(), body: JSON.parse(req.postData()) }; return json({ id: "cr2", state: "SUBMITTED", version: 1 }); }
      return json({ results: [{ id: "cr1", lesson_id: L1, kind: "RESCHEDULE", proposal: { start_at: at(2, 16) }, origin: "GUARDIAN", student_id: A, reason: "Verifica a scuola", state: "SUBMITTED", resolution_note: "", version: 1, created_at: new Date().toISOString() }] });
    }
    if (p.endsWith("/withdraw/")) return json({ code: "VERSION_CONFLICT", message: "Oggetto cambiato: ricaricare" }, 409);
    if (p === "/portal/attendance-pending") return json({ results: [{ lesson_id: L3, version: 2, start_at: at(-1, 15), end_at: at(-1, 16), subject_name: "Fisica", participants: users.tutor.lessons[0].participants }], next: null, previous: null });
    if (p === `/occurrences/${L3}/attendance/`) {
      if (m === "POST") { state.att = { headers: req.headers(), body: JSON.parse(req.postData()) }; return json({ ok: true }); }
      return json({ lesson_id: L3, lesson_version: 2, entries: [{ student_id: A, status: "NOT_RECORDED", minutes: null, version: 0, recorded: false }, { student_id: B, status: "NOT_RECORDED", minutes: null, version: 0, recorded: false }], counts: {} });
    }
    if (p === "/notifications") return json({ count: 1, next: null, previous: null, unread_count: 1, pending_email_deliveries: 0, results: [{ id: "n1", kind: "change_request.submitted", category: "SERVICE", title: "Richiesta inviata", body: "Il centro valuterà lo spostamento di Matematica.", subject_ref: `lesson:${L1}`, created_at: new Date().toISOString(), read_at: null }] });
    if (p === "/notifications/preferences") return json({ preferences: [{ category: "SERVICE", channel: "IN_APP", enabled: true, mandatory: true, available: true }, { category: "SERVICE", channel: "EMAIL", enabled: true, mandatory: false, available: true }, { category: "MARKETING", channel: "EMAIL", enabled: false, mandatory: false, available: false }] });
    if (p === "/calendar-feed-tokens") return m === "POST" ? json({ id: "f2", label: "Telefono", created_at: new Date().toISOString(), expires_at: null, revoked_at: null, last_used_at: null, token: "tok_e2e", feed_path: "/api/v1/calendar.ics?token=tok_e2e" }, 201) : json({ results: [] });
    if (p === "/auth/sessions") return json({ results: [{ id: "s1", current: true, created_at: new Date().toISOString(), last_seen_at: new Date().toISOString(), user_agent: "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/130", mfa_verified: false }] });
    if (p === "/auth/mfa") return json({ required: false, enrolled: false, verified: false, recovery_codes_remaining: 0 });
    return json({ code: "NOT_FOUND" }, 404);
  });
}

/* ---------------- axe ---------------- */
const results = { checks: [], axe: [], screenshots: [] };
async function axe(page, name) {
  await page.addScriptTag({ content: axeSource });
  const r = await page.evaluate(async () => (await window.axe.run(document, { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"] } })).violations.map((v) => ({ id: v.id, impact: v.impact, help: v.help, nodes: v.nodes.slice(0, 3).map((n) => n.target.join(" ")) })));
  results.axe.push({ name, violations: r });
  return r;
}
function check(name, ok, info = "") { results.checks.push({ name, ok: !!ok, info }); console.log(`${ok ? "✔" : "✘"} ${name}${info ? " — " + info : ""}`); }
async function shot(page, name) { const f = join(evidence, `${name}.png`); await page.screenshot({ path: f, fullPage: false }); results.screenshots.push(f.replace(resolve(root, "..") + "/", "")); }

/* ---------------- scenari ---------------- */
async function scenario(browser, { width, theme }) {
  const tag = `${width}-${theme}`;
  const ctx = await browser.newContext({ viewport: { width, height: width > 600 ? 900 : 844 }, colorScheme: theme, reducedMotion: "reduce", locale: "it-IT", timezoneId: "Europe/Rome" });
  await ctx.addInitScript(([t]) => localStorage.setItem("ripetizioni-ui", JSON.stringify({ theme: t, motion: "reduce" })), [theme]);
  const page = await ctx.newPage();
  const errors = []; page.on("pageerror", (e) => errors.push(String(e)));
  const state = { user: "guardian", mfa: true };
  await mount(page, state);

  // 1. login → MFA → panoramica famiglia
  await page.goto(BASE + "/");
  await page.getByLabel("Email").waitFor();
  await axe(page, `login-${tag}`); await shot(page, `login-${tag}`);
  await page.getByLabel("Email").fill("giulia@example.it");
  await page.getByLabel("Password", { exact: true }).fill("sbagliata");
  await page.getByRole("button", { name: "Accedi" }).click();
  check(`[${tag}] credenziali errate → messaggio`, await page.getByText("Email o password non corrette.").isVisible().catch(() => false) || await page.getByText("Email o password non corrette.").waitFor({ timeout: 3000 }).then(() => true, () => false));
  await page.getByLabel("Password", { exact: true }).fill("una frase lunga");
  await page.getByRole("button", { name: "Accedi" }).click();
  await page.getByLabel("Codice dell’app").waitFor();
  check(`[${tag}] MFA con autocomplete one-time-code`, (await page.getByLabel("Codice dell’app").getAttribute("autocomplete")) === "one-time-code");
  await axe(page, `mfa-${tag}`); await shot(page, `mfa-${tag}`);
  await page.getByLabel("Codice dell’app").fill("123456");
  await page.getByRole("button", { name: "Verifica" }).click();
  await page.getByRole("heading", { level: 1 }).filter({ hasText: "Giulia" }).waitFor();
  await page.getByRole("list", { name: "Studenti collegati" }).waitFor();
  const cards = page.getByRole("list", { name: "Studenti collegati" }).getByRole("listitem");
  check(`[${tag}] panoramica multi-figlio (2 schede)`, (await cards.count()) === 2);
  check(`[${tag}] figlio senza delega di modifica → «Sola lettura»`, await page.getByRole("listitem").filter({ hasText: "Bruno Rossi" }).getByText("Sola lettura").isVisible());
  check(`[${tag}] nessuno scorrimento orizzontale (reflow)`, await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
  await axe(page, `famiglia-home-${tag}`); await shot(page, `famiglia-home-${tag}`);

  // 2. figli: eccezioni a cursore
  await page.goto(BASE + `/#/profilo?s=${A}`);
  await page.getByRole("heading", { name: "Eccezioni" }).waitFor();
  await page.getByRole("button", { name: "Mostra altre" }).waitFor();
  const excRows = page.locator(".list-row").filter({ hasText: /Assenza|Disponibilità in più/ });
  await page.waitForFunction(() => [...document.querySelectorAll(".list-row")].filter((r) => /Assenza|Disponibilità in più/.test(r.textContent || "")).length >= 20);
  const before = await excRows.count();
  await page.getByRole("button", { name: "Mostra altre" }).click();
  await page.waitForFunction(() => [...document.querySelectorAll(".list-row")].filter((r) => /Assenza|Disponibilità in più/.test(r.textContent || "")).length >= 25, null, { timeout: 5000 }).catch(() => undefined);
  const after = await excRows.count();
  check(`[${tag}] eccezioni: «Mostra altre» segue il cursore`, before === 20 && after === 25, `${before} → ${after}`);
  check(`[${tag}] disponibilità effettiva parziale segnalata`, await page.getByText("Disponibilità incompleta").isVisible());
  await axe(page, `figli-${tag}`); await shot(page, `figli-${tag}`);
  await page.goto(BASE + `/#/profilo?s=99999999-9999-4999-8999-999999999999`);
  check(`[${tag}] figlio non più collegato → stato revocato`, await page.getByText("Accesso non più disponibile").waitFor({ timeout: 4000 }).then(() => true, () => false));

  // 3. settimana: richiesta di cambio con chiave di idempotenza
  await page.goto(BASE + `/#/settimana?d=${day(1)}`);
  await page.getByText("Matematica").first().waitFor();
  const english = page.locator("article").filter({ hasText: "Inglese" });
  check(`[${tag}] lezione del figlio in sola lettura senza azioni`, (await english.getByRole("button").count()) === 0);
  await page.locator("article").filter({ hasText: "Matematica" }).getByRole("button", { name: "Chiedi un cambio" }).click();
  await page.getByRole("dialog").waitFor();
  let trapped = true;
  for (let i = 0; i < 25; i++) { await page.keyboard.press("Tab"); trapped &&= await page.evaluate(() => !!document.activeElement?.closest("[role=dialog]")); }
  check(`[${tag}] focus intrappolato nel dialogo con Tab`, trapped);
  await page.getByRole("button", { name: /Invia al centro/ }).click();
  await page.getByLabel("Note per il centro").fill("Verifica di latino");
  await page.getByRole("button", { name: /Invia al centro/ }).click();
  check(`[${tag}] spostamento allo stesso orario rifiutato in locale`, await page.getByText("Scegli un orario diverso da quello attuale.").isVisible());
  await page.getByRole("dialog").getByRole("button", { name: "Assenza", exact: true }).click();
  await axe(page, `cambio-modal-${tag}`); await shot(page, `cambio-modal-${tag}`);
  await page.getByRole("button", { name: /Invia al centro/ }).click();
  await page.getByRole("dialog").waitFor({ state: "detached", timeout: 4000 }).catch(() => undefined);
  check(`[${tag}] assenza inviata con Idempotency-Key e studente`, !!state.cr?.headers["idempotency-key"] && state.cr.body.student_id === A && state.cr.body.kind === "ABSENCE" && !state.cr.body.proposal, JSON.stringify(state.cr?.body || {}));

  // 4. richieste: ritiro con conflitto di versione → stato «dati non aggiornati»
  await page.goto(BASE + "/#/cambi");
  await page.getByRole("button", { name: "Ritira" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Ritira" }).click();
  check(`[${tag}] ritiro in conflitto → «Dati non aggiornati»`, await page.getByText("Dati non aggiornati").waitFor({ timeout: 4000 }).then(() => true, () => false));
  await page.keyboard.press("Escape");
  check(`[${tag}] Esc chiude il dialogo e riporta il focus`, await page.getByRole("dialog").waitFor({ state: "detached", timeout: 3000 }).then(() => true, () => false) && await page.evaluate(() => document.activeElement?.textContent === "Ritira"));
  await axe(page, `cambi-${tag}`);

  // 5. notifiche e impostazioni
  await page.goto(BASE + "/#/panoramica");
  await page.getByRole("button", { name: /Notifiche, \d+ da leggere/ }).click();
  check(`[${tag}] notifica interna reale nel pannello`, await page.getByText("Richiesta inviata").isVisible());
  await page.keyboard.press("Escape");
  await page.goto(BASE + "/#/impostazioni?t=calendario");
  await page.getByRole("button", { name: /Crea link/ }).click();
  check(`[${tag}] link ICS mostrato una volta`, await page.getByText("/api/v1/calendar.ics?token=tok_e2e").waitFor({ timeout: 4000 }).then(() => true, () => false));
  await axe(page, `ics-${tag}`); await shot(page, `ics-${tag}`);
  await page.getByRole("button", { name: "Fatto" }).click();

  // 6. revoca della sessione → schermata dedicata
  state.revoked = true; state.signedIn = false;
  await page.goto(BASE + "/#/cambi");
  check(`[${tag}] sessione revocata → «Accesso non più disponibile»`, await page.getByRole("heading", { name: "Accesso non più disponibile" }).waitFor({ timeout: 4000 }).then(() => true, () => false));
  await axe(page, `sessione-revocata-${tag}`); await shot(page, `sessione-revocata-${tag}`);
  await page.getByRole("button", { name: "Accedi di nuovo" }).click();
  check(`[${tag}] dalla revoca si torna al login`, await page.getByLabel("Email").waitFor({ timeout: 4000 }).then(() => true, () => false));
  state.revoked = false;

  // 7. tutor: carico e presenze (con scelta del contesto)
  state.mfa = false; state.multi = true; state.multiCtx = true; state.user = "guardian";
  await page.goto(BASE + "/");
  await page.getByLabel("Email").fill("marco@example.it");
  await page.getByLabel("Password", { exact: true }).fill("una frase lunga");
  await page.getByRole("button", { name: "Accedi" }).click();
  await page.getByText("Con quale ruolo entri?").waitFor();
  await axe(page, `contesto-${tag}`); await shot(page, `contesto-${tag}`);
  await page.getByText("Tutor", { exact: true }).click();
  await page.getByRole("button", { name: "Continua" }).click();
  await page.getByRole("heading", { name: "Il tuo carico" }).waitFor();
  check(`[${tag}] tutor: barre minuti con superamento limite`, await page.locator('[aria-label*="oltre il limite"]').count() === 1);
  await axe(page, `tutor-home-${tag}`); await shot(page, `tutor-home-${tag}`);
  await page.goto(BASE + "/#/presenze");
  await page.getByRole("button", { name: "Registra" }).click();
  await page.getByRole("dialog").getByText("Anna Rossi").waitFor();
  await page.getByRole("dialog").getByRole("group", { name: "Bruno Rossi" }).getByRole("button", { name: "Assente", exact: true }).click();
  await axe(page, `presenze-${tag}`); await shot(page, `presenze-${tag}`);
  await page.getByRole("button", { name: /Salva presenze/ }).click();
  await page.getByRole("dialog").waitFor({ state: "detached" }).catch(() => undefined);
  check(`[${tag}] presenze con versione attesa e Idempotency-Key`, state.att?.body.expected_version === 2 && !!state.att?.headers["idempotency-key"] && state.att.body.entries.some((e) => e.student_id === B && e.status === "ABSENT"), JSON.stringify(state.att?.body || {}));

  // 8. invito: il token esce subito dall'indirizzo
  state.signedIn = false;
  await page.goto(BASE + "/invito#token=AbCdEfGhIjKlMnOp1234");
  await page.getByText("Benvenuto nel centro").waitFor();
  check(`[${tag}] invito: token rimosso dall'URL`, !page.url().includes("token"), page.url());
  await axe(page, `invito-${tag}`); await shot(page, `invito-${tag}`);

  check(`[${tag}] nessun errore JavaScript`, errors.length === 0, errors.join(" | "));
  await ctx.close();
}

const server = spawn(process.execPath, [join(root, "node_modules/vite/bin/vite.js"), "preview", "--port", String(PORT), "--strictPort", "--host", "127.0.0.1"], { cwd: root, stdio: "pipe" });
try {
  for (let i = 0; i < 50; i++) { try { await fetch(BASE + "/"); break; } catch { await new Promise((r) => setTimeout(r, 200)); } }
  const browser = await pw.chromium.launch({ executablePath: process.env.CHROMIUM_PATH || undefined, args: ["--no-sandbox"] });
  try {
    for (const width of [1440, 390]) for (const theme of ["light", "dark"]) await scenario(browser, { width, theme });
  } finally { await browser.close(); }
} catch (e) {
  check("esecuzione", false, String(e?.stack || e));
} finally { server.kill(); }

const serious = results.axe.flatMap((a) => a.violations.filter((v) => ["serious", "critical"].includes(v.impact)).map((v) => ({ page: a.name, ...v })));
const failed = results.checks.filter((c) => !c.ok);
writeFileSync(join(evidence, "e2e-report.json"), JSON.stringify({ generated_at: new Date().toISOString(), checks: results.checks, axe_pages: results.axe.length, axe_serious_or_critical: serious, axe_all: results.axe, screenshots: results.screenshots }, null, 2));
console.log(`\n${results.checks.length - failed.length}/${results.checks.length} controlli superati · ${results.axe.length} pagine axe · ${serious.length} violazioni serie/critiche`);
for (const v of serious.slice(0, 20)) console.log(`  axe ${v.page}: ${v.id} (${v.impact}) ${v.nodes.join(", ")}`);
process.exit(failed.length || serious.length ? 1 : 0);
