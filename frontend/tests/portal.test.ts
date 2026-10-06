import { test } from "node:test";
import assert from "node:assert/strict";
import { loadOf, requestersFor } from "../src/portal/data";
import type { S } from "../src/api/schema.gen";

const perms = (p: Partial<S.PortalChild["permissions"]>) => ({ can_view: true, can_manage_availability: false, can_request_changes: false, can_receive_notifications: false, ...p });
const child = (id: string, p: Partial<S.PortalChild["permissions"]>): S.PortalChild => ({ student_id: id, display_name: id, level: "", relation: "GUARDIAN", permissions: perms(p), read_only: !p.can_request_changes && !p.can_manage_availability, reconfirmation: null, availability: { approved: 0, draft: 0, revoked: 0, exceptions_upcoming: 0 }, week: null, open_change_requests: 0 });
const ov = (children: S.PortalChild[], tutor: S.PortalTutor | null = null): S.PortalOverview => ({ context: null, roles: ["GUARDIAN"], week: { from: "2026-03-02", until: "2026-03-09" }, timezone: "Europe/Rome", calendar_enabled: true, children, tutor, open_change_requests: 0, policies: { student_can_request_changes: false, decision: "D07", status: "DA_APPROVARE" }, generated_at: "" });
const now = new Date("2026-03-01T10:00:00Z");
const lesson = (p: Partial<{ as_tutor: boolean; state: string; start_at: string; participants: { student_id: string; name: string }[] }>) => ({ as_tutor: false, state: "PUBLISHED", start_at: "2026-03-03T15:00:00Z", participants: [{ student_id: "a", name: "Anna" }, { student_id: "b", name: "Bruno" }], ...p });

test("multi-figlio: solo i figli con permesso possono chiedere cambi", () => {
  const o = ov([child("a", { can_request_changes: true }), child("b", {})]);
  assert.deepEqual(requestersFor(lesson({}), o, now), { students: [{ id: "a", name: "Anna" }], asTutor: false });
});
test("sola lettura: nessuna azione", () => {
  assert.deepEqual(requestersFor(lesson({}), ov([child("a", {}), child("b", { can_manage_availability: true })]), now).students, []);
});
test("lezioni passate, cancellate o senza panoramica: nessuna azione", () => {
  const o = ov([child("a", { can_request_changes: true })]);
  assert.equal(requestersFor(lesson({ start_at: "2026-02-01T10:00:00Z" }), o, now).students.length, 0);
  assert.equal(requestersFor(lesson({ state: "CANCELLED" }), o, now).students.length, 0);
  assert.equal(requestersFor(lesson({}), null, now).students.length, 0);
});
test("tutor della lezione: può segnalare la propria assenza", () => {
  const t = { tutor_id: "t", display_name: "T", limits: null, availability: { approved: 0, draft: 0, revoked: 0, exceptions_upcoming: 0 }, week: null };
  assert.deepEqual(requestersFor(lesson({ as_tutor: true }), ov([], t), now), { students: [], asTutor: true });
});
test("carico tutor: percentuali e superamento dei limiti", () => {
  const t: S.PortalTutor = { tutor_id: "t", display_name: "T", limits: { daily_limit_minutes: 240, weekly_limit_minutes: 600 }, availability: { approved: 1, draft: 0, revoked: 0, exceptions_upcoming: 0 },
    week: { lessons: 5, scheduled_minutes: 660, completed_minutes: 120, cancelled_minutes: 60, attendance_pending: 1, by_day: [{ date: "2026-03-02", minutes: 120 }, { date: "2026-03-03", minutes: 300 }] } };
  const l = loadOf(t);
  assert.equal(l.days[0].pct, 50); assert.equal(l.days[0].over, false);
  assert.equal(l.days[1].pct, 100); assert.equal(l.days[1].over, true);
  assert.equal(l.weeklyOver, true); assert.equal(l.weeklyPct, 100);
  assert.equal(loadOf({ ...t, limits: null }).days[1].over, false);
});
