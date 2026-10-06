// Controllo locale del layout mobile con API simulate (non e' un test): per ogni schermata
// segnala gli elementi che escono dallo schermo e salva uno screenshot. Uso: node e2e/audit-mobile.mjs <out> [w] [rotte...]
import { spawn } from "node:child_process";
import { resolve } from "node:path";
const pw = await import("playwright-core");
const root = resolve(import.meta.dirname, ".."), out = process.argv[2] || "/tmp", W = Number(process.argv[3] || 390);
const routes = process.argv.slice(4).length ? process.argv.slice(4) : ["panoramica", "statistiche", "agenda", "pianificazione", "operativita", "anagrafica", "tutor", "impegni", "richieste", "percorsi", "materie", "apertura", "configurazione", "utenti", "privacy", "impostazioni"];
const PORT = 4191, BASE = `http://127.0.0.1:${PORT}`;
const students = ["Anna Rossi", "Bruno Gallo", "Chiara Ferri", "Davide Conti"].map((n, i) => ({ id: "s" + i, display_name: n, level: "Liceo scientifico", status: "ACTIVE", guardians: [] }));
const tutors = ["Marco Bianchi", "Giulia Verdi", "Luca Neri"].map((n, i) => ({ id: "t" + i, display_name: n, levels: ["Liceo"], modes: ["IN_PERSON", "ONLINE"], active: true }));
const requests = students.map((s, i) => ({ id: "r" + i, student: s.id, target_type: "STUDENT", participant_ids: [s.id], subject_name: "Matematica", duration_minutes: 60, sessions_per_week: 2, status: "ACTIVE", student_name: s.display_name }));
const srv = spawn("npx", ["vite", "preview", "--port", String(PORT), "--strictPort"], { cwd: root, stdio: "ignore" });
await new Promise((r) => setTimeout(r, 2500));
const browser = await pw.chromium.launch({ executablePath: "/usr/local/bin/chromium", args: ["--no-sandbox"] });
try {
  const ctx = await browser.newContext({ viewport: { width: W, height: 844 }, deviceScaleFactor: 2, hasTouch: true, isMobile: true });
  const page = await ctx.newPage();
  await page.route("**/api/v1/**", (route) => {
    const u = new URL(route.request().url()), p = u.pathname.replace("/api/v1", "");
    const json = (b, s = 200, hd = {}) => route.fulfill({ status: s, contentType: "application/json", headers: hd, body: JSON.stringify(b) });
    if (p === "/auth/csrf") return json({ detail: "ok" }, 200, { "set-cookie": "csrftoken=x; Path=/" });
    if (p === "/me") return json({ id: "u1", name: "Laura Bianchi", roles: ["CENTER"], tutor_id: null, experimental: true });
    if (p === "/students/") return json({ results: students, next: null });
    if (p === "/tutors/") return json({ results: tutors, next: null });
    if (p === "/teaching-requests/") return json({ results: requests, next: null });
    if (p === "/calendar/capabilities") return json({ enabled: true, reason_code: "", database: "postgresql", production_enabled: true });
    if (p === "/calendar/") return json({ revision: 1, results: [], next: null });
    if (p === "/planner/setup") return json({ opening_hours: [], closures: [] });
    if (p === "/commitments") return json([]);
    if (p === "/planning/readiness") return json({ ready: true, blockers: [] });
    return json({ results: [], next: null });
  });
  for (const r of routes) {
    await page.goto(`${BASE}/#/${r}`); await page.waitForTimeout(1800);
    const bad = await page.evaluate((vw) => {
      const o = [];
      for (const el of document.querySelectorAll("main *")) {
        const b = el.getBoundingClientRect(); if (!b.width || !b.height) continue;
        if (b.right > vw + 1 || b.left < -1) {
          // ignora contenuti dentro contenitori che scorrono per scelta (agenda)
          if (el.closest(".ag-scroller,.tabbar")) continue;
          const par = el.parentElement?.getBoundingClientRect(); if (par && (par.right > vw + 1 || par.left < -1) && !el.matches("table,nav,.seg-ctl,.hub-tabs")) continue;
          o.push(`${el.tagName.toLowerCase()}.${[...el.classList].join(".")} [${Math.round(b.left)}..${Math.round(b.right)}]`);
        }
      }
      return { sw: document.documentElement.scrollWidth, o: o.slice(0, 8) };
    }, W);
    console.log(r, JSON.stringify(bad));
    await page.screenshot({ path: `${out}/m-${r}.png`, fullPage: true });
  }
  await ctx.close();
} finally { await browser.close(); srv.kill(); process.exit(0); }
