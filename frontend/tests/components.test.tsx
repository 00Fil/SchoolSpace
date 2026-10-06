import { test } from "node:test";
import assert from "node:assert/strict";
import { renderToStaticMarkup as html } from "react-dom/server";
import { ViewState } from "../src/ui/states";
import { Help } from "../src/ui/help";
import { ContextPicker, InviteAccept, Login, MfaVerify, RecoveryCodes, ResetConfirm, SessionEnded } from "../src/auth/Auth";
import { KidCard } from "../src/portal/PortalHome";
import { monthStats, earnings } from "../src/portal/data";
import { phase } from "../src/portal/widgets";
import type { S } from "../src/api/schema.gen";

const noop = () => undefined;

test("ViewState: stati G04 con titolo, ruolo ARIA e azione", () => {
  for (const k of ["revoked", "stale", "inconclusive", "partial", "conflict", "offline", "disabled"] as const) {
    const out = html(<ViewState kind={k} onAction={noop} />);
    assert.match(out, new RegExp(`data-state="${k}"`));
    assert.match(out, /role="(status|alert)"/);
  }
  assert.match(html(<ViewState kind="conflict" />), /role="alert"/);
  assert.match(html(<ViewState kind="loading" />), /aria-label="Caricamento in corso"/);
  assert.match(html(<ViewState kind="empty" title="Vuoto" />), /Vuoto/);
});

test("Help: pulsante richiuso con aria-expanded", () => {
  const out = html(<Help topic="famiglia" />);
  assert.match(out, /aria-expanded="false"/);
  assert.match(out, /Come funziona/);
});

test("Login: email con autocomplete, etichette e reset password", () => {
  const out = html(<Login onStep={noop} onForgot={noop} />);
  assert.match(out, /<label for="l-email">Email<\/label>/);
  assert.match(out, /type="email"[^>]*autoComplete="username"|autocomplete="username"/i);
  assert.match(out, /autocomplete="current-password"/i);
  assert.match(out, /Password dimenticata\?/);
  assert.doesNotMatch(out, /Nome utente/);
});

test("MFA: codice one-time con tastiera numerica e alternativa di recupero", () => {
  const out = html(<MfaVerify onStep={noop} onRestart={noop} />);
  assert.match(out, /autocomplete="one-time-code"/i);
  assert.match(out, /inputMode="numeric"|inputmode="numeric"/i);
  assert.match(out, /codice di recupero/);
});

test("Codici di recupero: elencati e «Continua» disabilitato finché non confermi", () => {
  const out = html(<RecoveryCodes codes={["aaaa-bbbb", "cccc-dddd"]} onContinue={noop} />);
  assert.match(out, /aaaa-bbbb/); assert.match(out, /cccc-dddd/);
  assert.match(out, /<button[^>]*disabled=""[^>]*>Continua/);
  assert.match(out, /Li ho salvati/);
});

test("Contesto: un radio per ruolo con nomi leggibili", () => {
  const out = html(<ContextPicker contexts={["TUTOR", "GUARDIAN"]} current={null} onDone={noop} />);
  assert.match(out, /Tutor/); assert.match(out, /Famiglia/);
  assert.equal((out.match(/type="radio"/g) || []).length, 2);
});

test("Reset e invito: token assente → messaggio di link non valido", () => {
  assert.match(html(<ResetConfirm token="" onDone={noop} />), /Link non valido/);
  assert.match(html(<InviteAccept token="" signedIn={false} onDone={noop} onLogin={noop} />), /Invito non valido/);
  const inv = html(<InviteAccept token="tok-1234567890" signedIn={false} onDone={noop} onLogin={noop} />);
  assert.match(inv, /autocomplete="new-password"/i);
  assert.match(inv, /Ho già un account/);
  assert.match(html(<InviteAccept token="tok-1234567890" signedIn onDone={noop} onLogin={noop} />), /Accetta l’invito/);
});

test("Sessione terminata: schermata dedicata", () => {
  assert.match(html(<SessionEnded onLogin={noop} />), /Accesso non più disponibile/);
});

const kid = (p: Partial<S.PortalChild>): S.PortalChild => ({ student_id: "s1", display_name: "Anna Bianchi", level: "Liceo", relation: "GUARDIAN", permissions: { can_view: true, can_manage_availability: false, can_request_changes: false, can_receive_notifications: true }, read_only: true, reconfirmation: null, availability: { approved: 2, draft: 1, revoked: 0, exceptions_upcoming: 1 }, week: { lessons: 3, cancelled: 1, minutes: 180, next_lesson_at: null }, open_change_requests: 0, ...p });

test("Scheda figlio: nome, colore scelto, sola lettura e prossima lezione con dettagli", () => {
  const ro = html(<KidCard c={kid({})} color="green" lessons={[]} />);
  assert.match(ro, /Sola lettura/); assert.match(ro, /Anna Bianchi/); assert.match(ro, /3 lezioni questa settimana/); assert.match(ro, /var\(--green\)/);
  assert.match(ro, /Gestisci Anna/); assert.match(ro, /Nessuna lezione in programma/);
  const l = { id: "l1", state: "PUBLISHED", start_at: "2099-03-02T15:00:00+01:00", end_at: "2099-03-02T16:00:00+01:00", subject_name: "Fisica", tutor_name: "Marco Verdi", mode: "ONLINE", location: "REMOTE", place: null, students: ["Anna Bianchi"], others: 0, asTutor: false };
  const rw = html(<KidCard c={kid({ read_only: false })} lessons={[l]} onColor={noop} />);
  assert.doesNotMatch(rw, /Sola lettura/); assert.match(rw, /Fisica/); assert.match(rw, /Marco Verdi/); assert.match(rw, /Entra nella lezione/); assert.match(rw, /Colore della scheda/);
});

test("Mese del tutor: ore previste, svolte, annullate e guadagno stimato", () => {
  const L = (s: string, e: string, state = "PUBLISHED", as_tutor = true) => ({ state, start_at: s, end_at: e, as_tutor });
  const now = new Date("2026-03-10T12:00:00Z").getTime();
  const st = monthStats([L("2026-03-02T15:00:00Z", "2026-03-02T16:00:00Z"), L("2026-03-20T15:00:00Z", "2026-03-20T16:30:00Z"), L("2026-03-05T15:00:00Z", "2026-03-05T16:00:00Z", "CANCELLED"), L("2026-03-06T15:00:00Z", "2026-03-06T16:00:00Z", "PUBLISHED", false)], now);
  assert.deepEqual([st.lessons, st.planned, st.done, st.cancelled, st.cancelledMin, st.left], [2, 150, 60, 1, 60, 90]);
  assert.equal(earnings(150, 20), 50); assert.equal(earnings(150, null), null);
  assert.equal(phase({ state: "CANCELLED", start_at: "2026-03-02T15:00:00Z", end_at: "2026-03-02T16:00:00Z" }).label, "Annullata");
  assert.equal(phase({ state: "PUBLISHED", start_at: "2026-03-10T11:30:00Z", end_at: "2026-03-10T12:30:00Z" }, now).label, "In corso");
  assert.equal(phase({ state: "PUBLISHED", start_at: "2026-03-10T12:20:00Z", end_at: "2026-03-10T13:00:00Z" }, now).label, "Tra 20 min");
});
