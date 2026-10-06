import { FormEvent, useRef, useState } from "react";
import { ApiError, get, post, put } from "../api/client";
import type { S } from "../api/schema.gen";
import { human } from "../messages";
import { Avatar, Btn, Icon, Notice, PageHead, Tag, Tech } from "../ui/core";
import { Check, Field, Input, SegCtl } from "../ui/controls";
import { Modal, useToast } from "../ui/layers";
import { Motion, setPrefs, setTheme, Theme, usePrefs } from "../ui/prefs";
import { setQuery, useRoute } from "../ui/route";
import { Help } from "../ui/help";
import { classify, ErrorState, ViewState } from "../ui/states";
import { useData } from "../app/data";
import { roleName } from "../app/Shell";
import { useLoad } from "../portal/data";
import { copy, RecoveryCodes } from "../auth/Auth";
import { cleanCode, isTotp, passwordHints } from "../auth/flow";

type Tab = "generale" | "sicurezza" | "notifiche" | "calendario";
const when = (iso?: string | null) => (iso ? new Intl.DateTimeFormat("it-IT", { dateStyle: "medium", timeStyle: "short", timeZone: "Europe/Rome" }).format(new Date(iso)) : "—");

export default function Impostazioni() {
  const r = useRoute(), t = (r.q.get("t") || "generale") as Tab;
  return <section className="module planner" aria-labelledby="h-set">
    <PageHead id="h-set" title="Impostazioni" lead="Account, sicurezza, notifiche e calendario personale." />
    <div className="toolbar seg-scroll" style={{ marginBottom: 14 }}>
      <SegCtl<Tab> label="Sezione" value={t} options={[["generale", "Generale"], ["sicurezza", "Sicurezza"], ["notifiche", "Notifiche"], ["calendario", "Calendario"]]} onChange={(v) => setQuery((q) => (v === "generale" ? q.delete("t") : q.set("t", v)))} />
    </div>
    {t === "sicurezza" ? <Sicurezza /> : t === "notifiche" ? <Notifiche /> : t === "calendario" ? <Calendario /> : <Generale />}
    <Help topic="account" />
  </section>;
}

function Generale() {
  const p = usePrefs(), d = useData(), toast = useToast(), box = useRef<HTMLDivElement>(null);
  return <div className="settings" ref={box}>
    <div className="setting"><div><b>Tema</b><p>Automatico segue le impostazioni del dispositivo. Vale solo per questo browser.</p></div>
      <SegCtl<Theme> label="Tema" value={p.theme} options={[["light", "Chiaro"], ["dark", "Scuro"], ["system", "Automatico"]]} onChange={(v) => setTheme(v, box.current?.getBoundingClientRect())} /></div>
    <div className="setting"><div><b>Animazioni</b><p>Ridotte elimina i movimenti. Se il dispositivo chiede meno movimento, sono già ridotte.</p></div>
      <SegCtl<Motion> label="Animazioni" value={p.motion} options={[["system", "Complete"], ["reduce", "Ridotte"]]} onChange={(v) => { setPrefs({ motion: v }); toast(v === "reduce" ? "Animazioni ridotte" : "Animazioni complete"); }} /></div>
    <div className="setting"><div className="who"><Avatar name={d.me.name} size={44} /><div><b>{d.me.name}</b><p>{d.me.roles.map(roleName).join(", ") || "Nessun ruolo attivo"}</p></div></div>
      <div className="row-actions">{d.switchContext && <Btn kind="ghost" onClick={d.switchContext}>Cambia ruolo</Btn>}<Btn kind="ghost" onClick={() => d.signOut().catch(() => toast("Uscita non riuscita. Riprova."))}>Esci</Btn></div></div>
  </div>;
}

/* ---------------- sicurezza ---------------- */
function Sicurezza() {
  return <div className="settings wide">
    <Password />
    <Mfa />
    <Sessions />
  </div>;
}

function Password() {
  const toast = useToast(), [busy, setBusy] = useState(false), [err, setErr] = useState<unknown>(null), [bad, setBad] = useState<Record<string, string>>({});
  const form = useRef<HTMLFormElement>(null);
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const f = new FormData(e.currentTarget), cur = String(f.get("current") || ""), pw = String(f.get("new") || ""), pw2 = String(f.get("new2") || "");
    const b: Record<string, string> = {};
    if (!cur) b.cur = "Scrivi la password attuale.";
    const h = passwordHints(pw); if (!pw) b.pw = "Scegli la nuova password."; else if (h.length) b.pw = h[0];
    if (pw2 !== pw) b.pw2 = "Le due password non coincidono.";
    setBad(b); if (Object.keys(b).length) return;
    setBusy(true); setErr(null);
    try { await post("/auth/password-change", { current_password: cur, new_password: pw }); form.current?.reset(); toast("Password aggiornata. Le altre sessioni sono state chiuse."); }
    catch (x) { if (x instanceof ApiError && x.code === "INVALID_CREDENTIALS") setBad({ cur: "La password attuale non è corretta." }); else setErr(x); } finally { setBusy(false); }
  }
  return <div className="setting" style={{ display: "block" }}>
    <b>Password</b><p className="muted">Cambiarla chiude le sessioni sugli altri dispositivi.</p>
    <form ref={form} onSubmit={submit} noValidate style={{ maxWidth: 420, marginTop: 10 }}>
      <Field label="Password attuale" id="pc-cur" error={bad.cur}><Input id="pc-cur" name="current" type="password" autoComplete="current-password" /></Field>
      <Field label="Nuova password" id="pc-new" error={bad.pw} hint="Almeno 12 caratteri."><Input id="pc-new" name="new" type="password" autoComplete="new-password" /></Field>
      <Field label="Ripeti la nuova password" id="pc-new2" error={bad.pw2}><Input id="pc-new2" name="new2" type="password" autoComplete="new-password" /></Field>
      {err !== null && <Notice kind="bad">{human(err).text}<Tech>{human(err).detail}</Tech></Notice>}
      <Btn kind="primary" type="submit" disabled={busy}>{busy ? "Salvataggio…" : "Cambia password"}</Btn>
    </form>
  </div>;
}

function Mfa() {
  const st = useLoad((signal) => get("/auth/mfa", { signal }), []);
  const [open, setOpen] = useState(false), [codes, setCodes] = useState<string[] | null>(null), [code, setCode] = useState(""), [err, setErr] = useState<unknown>(null), [busy, setBusy] = useState(false), [bad, setBad] = useState("");
  const s = st.data;
  async function regen(e: FormEvent) {
    e.preventDefault();
    if (!isTotp(code)) { setBad("Il codice è di 6 cifre."); return; }
    setBusy(true); setErr(null);
    try { const r = await post("/auth/mfa/recovery-codes", { code: cleanCode(code) }) as { recovery_codes?: string[] }; setCodes(r.recovery_codes || []); st.reload(); }
    catch (x) { if (x instanceof ApiError && x.code === "INVALID_CODE") setBad(human(x).text); else setErr(x); } finally { setBusy(false); }
  }
  return <div className="setting">
    <div><b>Verifica in due passaggi</b>
      <p>{!s ? (st.error ? "Stato non disponibile." : "Controllo lo stato…") : s.enrolled ? `Attiva. Codici di recupero rimasti: ${s.recovery_codes_remaining}.` : s.required ? "Obbligatoria per il tuo ruolo: ti verrà chiesta al prossimo accesso." : "Non attiva: per il tuo ruolo non è richiesta."}</p></div>
    {s?.enrolled ? <Tag tone="green">Attiva</Tag> : <Tag tone="plain">Non attiva</Tag>}
    {s?.enrolled && <Btn kind="ghost" onClick={() => { setOpen(true); setCodes(null); setCode(""); setErr(null); setBad(""); }}>Nuovi codici di recupero</Btn>}
    <Modal open={open} onClose={() => setOpen(false)} labelledBy="rc-title">
      <div className="modal-body">
        <h2 id="rc-title">Nuovi codici di recupero</h2>
        {codes ? <RecoveryCodes embedded codes={codes} onContinue={() => setOpen(false)} /> : <form onSubmit={regen} noValidate>
          <p className="lead">I codici attuali smetteranno di funzionare. Conferma con il codice dell’app di autenticazione.</p>
          <Field label="Codice dell’app" id="rc-code" error={bad}><Input id="rc-code" inputMode="numeric" autoComplete="one-time-code" maxLength={7} autoFocus value={code} onChange={(e) => { setCode(e.target.value); setBad(""); }} /></Field>
          {err !== null && <ErrorState error={err} />}
          <div className="modal-foot" style={{ padding: 0, marginTop: 12 }}><button type="button" className="pill-btn ghost" onClick={() => setOpen(false)}>Annulla</button><button className="pill-btn primary" disabled={busy}>{busy ? "Genero…" : "Genera"}</button></div>
        </form>}
      </div>
    </Modal>
  </div>;
}

function Sessions() {
  const toast = useToast(), d = useData();
  const ss = useLoad((signal) => get("/auth/sessions", { signal }), []);
  const [confirm, setConfirm] = useState<null | { all: true } | { one: S.UserSession }>(null), [busy, setBusy] = useState(false), [err, setErr] = useState<unknown>(null);
  async function go() {
    if (!confirm) return; setBusy(true); setErr(null);
    try {
      if ("all" in confirm) { const r = await post("/auth/sessions/revoke-all", { include_current: false }); toast(`${r.revoked === 1 ? "Chiusa 1 sessione" : `Chiuse ${r.revoked} sessioni`} sugli altri dispositivi.`); }
      else { await post("/auth/sessions/{id}/revoke", undefined as never, { params: { id: confirm.one.id } }); if (confirm.one.current) { await d.signOut().catch(() => undefined); return; } toast("Sessione chiusa."); }
      setConfirm(null); ss.reload();
    } catch (x) { setErr(x); } finally { setBusy(false); }
  }
  const rows = ss.data?.results || [];
  return <div className="setting" style={{ display: "block" }}>
    <div className="m-head"><div><b>Sessioni attive</b><p className="muted">I browser in cui hai effettuato l’accesso.</p></div>
      {rows.filter((x) => !x.current).length > 0 && <Btn kind="sm ghost" onClick={() => { setErr(null); setConfirm({ all: true }); }}>Chiudi le altre</Btn>}</div>
    {ss.error ? <ErrorState error={ss.error} onRetry={ss.reload} /> : !ss.data ? <ViewState kind="loading" compact /> : <div className="list-rows">{rows.map((x) => <div className="list-row" key={x.id}>
      <div><b>{device(x.user_agent)}{x.current ? " · questo browser" : ""}</b><small>Accesso {when(x.created_at)} · ultima attività {when(x.last_seen_at)}{x.mfa_verified ? " · verificata con secondo fattore" : ""}</small></div>
      <Btn kind="sm ghost" onClick={() => { setErr(null); setConfirm({ one: x }); }}>{x.current ? "Esci" : "Chiudi"}</Btn></div>)}</div>}
    <Modal open={!!confirm} onClose={() => setConfirm(null)} labelledBy="ss-title">
      <div className="modal-body">
        <h2 id="ss-title">{confirm && "all" in confirm ? "Chiudere le altre sessioni?" : "Chiudere la sessione?"}</h2>
        <p className="lead">{confirm && "all" in confirm ? "Su tutti gli altri browser dovrai accedere di nuovo. Questo browser resta collegato." : confirm && "one" in confirm && confirm.one.current ? "Uscirai da questo browser." : "Su quel browser dovrai accedere di nuovo."}</p>
        {err !== null && <ErrorState error={err} />}
      </div>
      <div className="modal-foot"><button type="button" className="pill-btn ghost" onClick={() => setConfirm(null)}>Annulla</button><button className="pill-btn danger" disabled={busy} onClick={go}>{busy ? "Chiusura…" : "Chiudi"}</button></div>
    </Modal>
  </div>;
}
export function device(ua = "") {
  const b = /Edg\//.test(ua) ? "Edge" : /Firefox\//.test(ua) ? "Firefox" : /Chrome\//.test(ua) ? "Chrome" : /Safari\//.test(ua) ? "Safari" : "Browser";
  const o = /iPhone|iPad/.test(ua) ? "iOS" : /Android/.test(ua) ? "Android" : /Mac OS X/.test(ua) ? "macOS" : /Windows/.test(ua) ? "Windows" : /Linux/.test(ua) ? "Linux" : "";
  return o ? `${b} su ${o}` : b;
}

/* ---------------- notifiche ---------------- */
const CAT: Record<string, string> = { SERVICE: "Servizio (lezioni, cambi, sicurezza)", MARKETING: "Comunicazioni promozionali" };
const CH: Record<string, string> = { IN_APP: "Nel portale", EMAIL: "Email" };
function Notifiche() {
  const toast = useToast(), pr = useLoad((signal) => get("/notifications/preferences", { signal }), []);
  const [busy, setBusy] = useState(""), [err, setErr] = useState<unknown>(null);
  async function toggle(p: S.NotificationPreferences["preferences"][number], enabled: boolean) {
    setBusy(p.category + p.channel); setErr(null);
    try { await put("/notifications/preferences", { preferences: [{ category: p.category, channel: p.channel, enabled }] }); pr.reload(); toast(enabled ? "Notifica attivata" : "Notifica disattivata"); }
    catch (x) { setErr(x); } finally { setBusy(""); }
  }
  return <div className="settings wide">
    {pr.error ? <ErrorState error={pr.error} onRetry={pr.reload} /> : !pr.data ? <ViewState kind="loading" /> : pr.data.preferences.map((p) => <div className="setting" key={p.category + p.channel}>
      <div><b>{CAT[p.category] || p.category} · {CH[p.channel] || p.channel}</b>
        <p>{p.mandatory ? "Obbligatoria: serve per il funzionamento del servizio." : !p.available ? "Non attiva in questo centro." : p.enabled ? "Attiva." : "Disattivata."}</p></div>
      {p.mandatory || !p.available ? <Tag tone="plain">{p.mandatory ? "Sempre attiva" : "Non disponibile"}</Tag>
        : <Check checked={p.enabled} onChange={(v) => { if (!busy) toggle(p, v); }}>{busy === p.category + p.channel ? "Salvataggio…" : p.enabled ? "Attiva" : "Disattivata"}</Check>}
    </div>)}
    {err !== null && <ErrorState error={err} />}
  </div>;
}

/* ---------------- calendario ICS ---------------- */
function Calendario() {
  const toast = useToast(), ft = useLoad((signal) => get("/calendar-feed-tokens", { signal }), []);
  const [label, setLabel] = useState(""), [busy, setBusy] = useState(false), [err, setErr] = useState<unknown>(null), [created, setCreated] = useState<S.FeedTokenCreated | null>(null), [revoke, setRevoke] = useState<S.FeedToken | null>(null);
  async function create(e: FormEvent) {
    e.preventDefault(); setBusy(true); setErr(null);
    try { setCreated(await post("/calendar-feed-tokens", { label: label.trim() }) as S.FeedTokenCreated); setLabel(""); ft.reload(); } catch (x) { setErr(x); } finally { setBusy(false); }
  }
  async function doRevoke() {
    if (!revoke) return; setBusy(true); setErr(null);
    try { await post("/calendar-feed-tokens/{pk}/revoke", undefined as never, { params: { pk: revoke.id } }); setRevoke(null); ft.reload(); toast("Link revocato: i calendari collegati smetteranno di aggiornarsi."); } catch (x) { setErr(x); } finally { setBusy(false); }
  }
  const url = created ? location.origin + created.feed_path : "";
  const active = (ft.data?.results || []).filter((x) => !x.revoked_at);
  return <div className="settings wide">
    <div className="setting" style={{ display: "block" }}>
      <b>Collega il tuo calendario</b>
      <p className="muted">Crea un link da aggiungere a Google Calendar, Apple Calendario o Outlook (“iscriviti a un calendario”). Contiene solo le tue lezioni pubblicate e si aggiorna da solo.</p>
      <form onSubmit={create} noValidate className="row-actions" style={{ alignItems: "flex-end" }}>
        <Field label="Nome del link" id="ft-label" optional hint="Per riconoscerlo, es. «Telefono»."><Input id="ft-label" value={label} maxLength={60} onChange={(e) => setLabel(e.target.value)} /></Field>
        <Btn kind="primary" type="submit" isle="plus" disabled={busy}>{busy && !revoke ? "Creo…" : "Crea link"}</Btn>
      </form>
      {err !== null && !revoke && (classify(err) === "stale" || (err instanceof ApiError && err.code === "TOKEN_LIMIT") ? <Notice kind="warn">{human(err).text}</Notice> : <ErrorState error={err} />)}
    </div>
    {ft.error ? <ErrorState error={ft.error} onRetry={ft.reload} /> : !ft.data ? <ViewState kind="loading" compact /> : active.length ? active.map((x) => <div className="setting" key={x.id}>
      <div><b>{x.label || "Link senza nome"}</b><p>Creato {when(x.created_at)} · {x.last_used_at ? `ultimo aggiornamento ${when(x.last_used_at)}` : "mai usato"}{x.expires_at ? ` · scade ${when(x.expires_at)}` : ""}</p></div>
      <Btn kind="ghost" onClick={() => { setErr(null); setRevoke(x); }}>Revoca</Btn></div>)
      : <ViewState kind="empty" title="Nessun link attivo">Crea un link per vedere le lezioni nel calendario del telefono.</ViewState>}
    <Modal open={!!created} onClose={() => setCreated(null)} labelledBy="ft-title">
      <div className="modal-body">
        <h2 id="ft-title">Il tuo link del calendario</h2>
        <Notice kind="warn" title="Lo vedi solo adesso">Chi ha questo link vede le tue lezioni: non condividerlo. Se lo perdi, revocalo e creane uno nuovo.</Notice>
        <div className="feed-url" style={{ marginTop: 12 }}><code>{url}</code><Btn kind="sm" onClick={() => copy(url).then(() => toast("Link copiato"), () => toast("Copia non riuscita: selezionalo e copialo a mano."))}>Copia</Btn></div>
      </div>
      <div className="modal-foot"><button className="pill-btn primary" onClick={() => setCreated(null)}>Fatto<Icon n="check" /></button></div>
    </Modal>
    <Modal open={!!revoke} onClose={() => setRevoke(null)} labelledBy="fr-title">
      <div className="modal-body"><h2 id="fr-title">Revocare il link?</h2><p className="lead">«{revoke?.label || "Link senza nome"}» smetterà di funzionare subito.</p>{err !== null && revoke && <ErrorState error={err} />}</div>
      <div className="modal-foot"><button type="button" className="pill-btn ghost" onClick={() => setRevoke(null)}>Annulla</button><button className="pill-btn danger" disabled={busy} onClick={doRevoke}>{busy ? "Revoca…" : "Revoca"}</button></div>
    </Modal>
  </div>;
}
