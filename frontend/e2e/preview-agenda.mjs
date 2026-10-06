// Anteprima locale dell'agenda con API simulate (non e' un test). Uso: node e2e/preview-agenda.mjs <out-dir> [pagina]
import { spawn } from "node:child_process";
import { resolve } from "node:path";
const pw = await import("playwright-core");
const root = resolve(import.meta.dirname, ".."), out = process.argv[2] || "/tmp", screen = process.argv[3] || "agenda";
const PORT = 4190, BASE = `http://127.0.0.1:${PORT}`;
const pad = (n) => String(n).padStart(2, "0");
const now = new Date(), today = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
const tutors = [["t1", "Anna Rossi"], ["t2", "Marco Bianchi"], ["t3", "Giulia Verdi"], ["t4", "Luca Neri"], ["t5", "Sara Conti"]];
const subj = ["Matematica", "Inglese", "Fisica", "Latino", "Chimica"];
const lessons = []; let k = 0;
tutors.forEach(([id, name], i) => {
  [[14 + (i % 2), 0, 60], [16, 30 * (i % 2), 90], [18 + (i % 2), 0, 30]].forEach(([h, m, d], j) => {
    const s = new Date(`${today}T${pad(h)}:${pad(m)}:00`), e = new Date(s.getTime() + d * 60000);
    const grp = (i + j) % 3 === 0;
    lessons.push({ id: `l${k++}`, version: 1, state: "PUBLISHED", start_at: s.toISOString(), end_at: e.toISOString(), tutor: id, tutor_name: name, subject: "s" + j, subject_name: subj[(i + j) % 5],
      mode: (i + j) % 2 ? "ONLINE" : "IN_PERSON", location: "CENTER", space: null, participants: grp ? [{ student_id: "a", name: "Elisa Ferri" }, { student_id: "b", name: "Paolo Gallo" }] : [{ student_id: "c" + k, name: "Sara Bianchi" }] });
  });
});
const srv = spawn("npx", ["vite", "preview", "--port", String(PORT), "--strictPort"], { cwd: root, stdio: "ignore" });
await new Promise((r) => setTimeout(r, 2500));
const browser = await pw.chromium.launch({ executablePath: "/usr/local/bin/chromium", args: ["--no-sandbox"] });
try {
  for (const [w, h, theme] of [[390, 844, "light"], [1280, 800, "light"], [390, 844, "dark"]]) {
    const ctx = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 2, colorScheme: theme, hasTouch: w < 500, isMobile: w < 500 });
    const page = await ctx.newPage();
    await page.route("**/api/v1/**", (route) => {
      const u = new URL(route.request().url()), p = u.pathname.replace("/api/v1", "");
      const json = (b, s = 200, hd = {}) => route.fulfill({ status: s, contentType: "application/json", headers: hd, body: JSON.stringify(b) });
      if (p === "/auth/csrf") return json({ detail: "ok" }, 200, { "set-cookie": "csrftoken=x; Path=/" });
      if (p === "/me") return json({ id: "u1", name: "Laura Bianchi", roles: ["CENTER"], tutor_id: null, experimental: true });
      if (p === "/tutors/") return json({ results: tutors.map(([id, n]) => ({ id, display_name: n })), next: null });
      if (p === "/calendar/capabilities") return json({ enabled: true, reason_code: "", database: "postgresql", production_enabled: true });
      if (p === "/calendar/") return json({ revision: 1, results: lessons, next: null });
      if (p === "/planner/setup") return json({ opening_hours: [0, 1, 2, 3, 4, 5].map((d) => ({ weekday: d, start: "14:00", end: "20:00" })), closures: [] });
      if (p === "/commitments") return json([]);
      if (p === "/planning/readiness") return json({ ready: true, blockers: [] });
      if (p.startsWith("/planner/calendar-months/")) return json({ detail: "x" }, 404);
      return json({ results: [], next: null });
    });
    await page.addInitScript((t) => { try { localStorage.setItem("theme", t); } catch {} document.documentElement.dataset.theme = t; }, theme);
    await page.goto(`${BASE}/#/${screen}`); await page.waitForTimeout(2500);
    await page.screenshot({ path: `${out}/${screen}-${w}-${theme}.png`, fullPage: false });
    if (screen === "agenda") { await page.evaluate(() => { const s = document.querySelector(".ag-scroller"); if (s) s.scrollLeft = 220; }); await page.waitForTimeout(500);
      await page.screenshot({ path: `${out}/${screen}-${w}-${theme}-scroll.png`, fullPage: true }); }
    await ctx.close();
  }
} finally { await browser.close(); srv.kill(); process.exit(0); }
