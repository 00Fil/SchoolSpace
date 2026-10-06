/**
 * Schermate di accesso (s1): login email, verifica in due passaggi (TOTP o codice di
 * recupero), attivazione MFA con QR, codici di recupero mostrati una volta, scelta del
 * contesto, reimpostazione password e accettazione invito. Nessun dialog nativo.
 */
import { FormEvent, ReactNode, useEffect, useRef, useState } from "react";
import { ApiError, get, post } from "../api/client";
import type { S } from "../api/schema.gen";
import { human } from "../messages";
import { Btn, Icon, Notice, Skeleton, Tag, Tech } from "../ui/core";
import { Check, Choices, Field, Input } from "../ui/controls";
import { useToast } from "../ui/layers";
import { Help } from "../ui/help";
import { ENV_LABEL } from "../env";
import { cleanCode, CONTEXT_LABEL, isTotp, nextStep, passwordHints, savePendingInvite, Step } from "./flow";

export function AuthCard({ title, lead, children, foot, id = "h-auth", tag }: { title: string; lead?: ReactNode; children: ReactNode; foot?: ReactNode; id?: string; tag?: string }) {
  useEffect(() => { document.title = `${title} · Centro ripetizioni`; }, [title]);
  return <main className="login-page" id="main">
    <section className="module login-card" aria-labelledby={id}>
      <div className="login-top"><span className="logo raised" aria-hidden="true"><span className="bars"><i style={{ height: 12 }} /><i style={{ height: 20 }} /><i style={{ height: 16 }} /></span></span>{(tag || ENV_LABEL) && <Tag tone="amber">{tag || ENV_LABEL}</Tag>}</div>
      <h1 className="h-display" id={id}>{title}</h1>
      {lead && <p className="muted login-lead">{lead}</p>}
      {children}
      {foot && <div className="login-foot">{foot}</div>}
    </section>
  </main>;
}
const Submit = ({ busy, children, busyText }: { busy: boolean; children: ReactNode; busyText: string }) =>
  <button className="pill-btn primary island login-btn" disabled={busy} aria-busy={busy}>{busy ? busyText : children}<span className="isle"><Icon n="arrow" /></span></button>;
const LinkBtn = ({ onClick, children }: { onClick: () => void; children: ReactNode }) => <button type="button" className="link-btn" onClick={onClick}>{children}</button>;

/* ---------------- login ---------------- */
export function Login({ onStep, onForgot, notice }: { onStep: (s: Step) => void; onForgot: () => void; notice?: ReactNode }) {
  const [busy, setBusy] = useState(false), [err, setErr] = useState<unknown>(null), [bad, setBad] = useState<{ e?: boolean; p?: boolean }>({});
  async function submit(ev: FormEvent<HTMLFormElement>) {
    ev.preventDefault();
    const f = new FormData(ev.currentTarget), email = String(f.get("email") || "").trim(), password = String(f.get("password") || "");
    const b = { e: !email || !email.includes("@"), p: !password }; setBad(b);
    if (b.e || b.p) { (ev.currentTarget.elements.namedItem(b.e ? "email" : "password") as HTMLElement).focus(); return; }
    setBusy(true); setErr(null);
    try { await get("/auth/csrf"); onStep(nextStep(await post("/auth/login", { email, password }))); }
    catch (x) { setErr(x); } finally { setBusy(false); }
  }
  return <AuthCard title="Bentornato." id="h-login" lead="Accedi con l’email registrata dal centro.">
    {notice}
    <form onSubmit={submit} noValidate>
      <Field label="Email" id="l-email" error={bad.e && "Scrivi l’indirizzo email completo."}><Input id="l-email" name="email" type="email" inputMode="email" autoComplete="username" autoFocus aria-invalid={bad.e || undefined} onInput={() => setBad({ ...bad, e: false })} /></Field>
      <Field label="Password" id="l-pass" error={bad.p && "Scrivi la password."}><Input id="l-pass" name="password" type="password" autoComplete="current-password" aria-invalid={bad.p || undefined} onInput={() => setBad({ ...bad, p: false })} /></Field>
      {err !== null && <ErrorNotice error={err} />}
      <Submit busy={busy} busyText="Accesso in corso…">Accedi</Submit>
    </form>
    <p className="login-foot"><LinkBtn onClick={onForgot}>Password dimenticata?</LinkBtn></p>
    <p className="login-foot">L’account lo crea il centro con un invito via email. Non esistono credenziali predefinite.</p>
    <Help topic="login" />
  </AuthCard>;
}
function ErrorNotice({ error }: { error: unknown }) {
  const h = human(error);
  return <Notice kind="bad">{h.text}{h.detail && <Tech>{h.detail}</Tech>}</Notice>;
}

/* ---------------- verifica in due passaggi ---------------- */
export function MfaVerify({ onStep, onRestart, stepUp }: { onStep: (s: Step) => void; onRestart: (msg?: string) => void; stepUp?: boolean }) {
  const [recovery, setRecovery] = useState(false), [busy, setBusy] = useState(false), [err, setErr] = useState<unknown>(null), [bad, setBad] = useState("");
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => { input.current?.focus(); }, [recovery]);
  async function submit(ev: FormEvent<HTMLFormElement>) {
    ev.preventDefault();
    const v = cleanCode(input.current?.value || "");
    if (!recovery && !isTotp(v)) { setBad("Il codice è di 6 cifre."); input.current?.focus(); return; }
    if (recovery && v.length < 6) { setBad("Scrivi il codice di recupero completo."); input.current?.focus(); return; }
    setBusy(true); setErr(null); setBad("");
    try { onStep(nextStep(await post("/auth/mfa/verify", recovery ? { recovery_code: v } : { code: v }) as S.LoginResult)); }
    catch (x) {
      if (x instanceof ApiError && x.code === "MFA_SESSION_EXPIRED") { onRestart(human(x).text); return; }
      if (x instanceof ApiError && x.code === "INVALID_CODE") { setBad(human(x).text); if (input.current) input.current.value = ""; input.current?.focus(); }
      else setErr(x);
    } finally { setBusy(false); }
  }
  return <AuthCard title="Verifica in due passaggi" id="h-mfa" lead={stepUp ? "Per questa operazione il centro chiede di confermare la tua identità." : "Apri l’app di autenticazione sul telefono e scrivi il codice di 6 cifre."}>
    <form onSubmit={submit} noValidate>
      {recovery
        ? <Field label="Codice di recupero" id="m-rec" error={bad} hint="Ogni codice di recupero vale una sola volta."><Input ref={input} key="rec" id="m-rec" name="recovery" autoComplete="off" aria-invalid={!!bad || undefined} onInput={() => setBad("")} /></Field>
        : <Field label="Codice dell’app" id="m-code" error={bad}><Input ref={input} key="totp" id="m-code" name="code" inputMode="numeric" autoComplete="one-time-code" maxLength={7} pattern="[0-9 ]*" aria-invalid={!!bad || undefined} onInput={() => setBad("")} /></Field>}
      {err !== null && <ErrorNotice error={err} />}
      <Submit busy={busy} busyText="Verifica in corso…">Verifica</Submit>
    </form>
    <p className="login-foot"><LinkBtn onClick={() => { setRecovery(!recovery); setBad(""); }}>{recovery ? "Usa il codice dell’app" : "Non hai il telefono? Usa un codice di recupero"}</LinkBtn></p>
    {!stepUp && <p className="login-foot"><LinkBtn onClick={() => onRestart()}>Accedi con un altro account</LinkBtn></p>}
    <Help topic="login" />
  </AuthCard>;
}

/* ---------------- attivazione MFA ---------------- */
export function MfaSetup({ onStep, onRestart }: { onStep: (s: Step) => void; onRestart: (msg?: string) => void }) {
  const [setup, setSetup] = useState<S.MfaSetup | null>(null), [loadErr, setLoadErr] = useState<unknown>(null);
  const [busy, setBusy] = useState(false), [bad, setBad] = useState(""), [err, setErr] = useState<unknown>(null);
  const toast = useToast(); const input = useRef<HTMLInputElement>(null);
  const load = () => {
    setLoadErr(null); setSetup(null);
    post("/auth/mfa/setup", {} as never).then((r) => setSetup(r as S.MfaSetup)).catch((x) => {
      if (x instanceof ApiError && x.code === "MFA_SESSION_EXPIRED") onRestart(human(x).text); else setLoadErr(x);
    });
  };
  useEffect(load, []); // eslint-disable-line react-hooks/exhaustive-deps
  async function submit(ev: FormEvent<HTMLFormElement>) {
    ev.preventDefault();
    const v = cleanCode(input.current?.value || "");
    if (!isTotp(v)) { setBad("Il codice è di 6 cifre."); input.current?.focus(); return; }
    setBusy(true); setErr(null); setBad("");
    try { onStep(nextStep(await post("/auth/mfa/confirm", { code: v }) as S.LoginResult)); }
    catch (x) {
      if (x instanceof ApiError && x.code === "MFA_SESSION_EXPIRED") { onRestart(human(x).text); return; }
      if (x instanceof ApiError && x.code === "INVALID_CODE") { setBad(human(x).text); input.current?.focus(); } else setErr(x);
    } finally { setBusy(false); }
  }
  const secret = setup?.secret.replace(/(.{4})/g, "$1 ").trim() || "";
  return <AuthCard title="Attiva la verifica in due passaggi" id="h-mfa-setup" lead="Il tuo ruolo richiede un secondo fattore. Serve un’app di autenticazione (per esempio quella del telefono che genera codici a 6 cifre).">
    {loadErr !== null ? <Notice kind="bad" title="Non riesco a preparare l’attivazione" action={<Btn kind="sm" onClick={load}>Riprova</Btn>}>{human(loadErr).text}</Notice>
      : !setup ? <Skeleton rows={4} /> : <>
        <ol className="steps">
          <li>Inquadra il codice QR con l’app.
            <div className="qr"><img src={setup.qr_svg} alt="Codice QR da inquadrare con l’app di autenticazione" width={184} height={184} /></div>
          </li>
          <li>Se non puoi inquadrarlo, inserisci a mano questa chiave:
            <div className="secret"><code aria-label={`Chiave: ${setup.secret.split("").join(" ")}`}>{secret}</code>
              <Btn kind="sm" onClick={() => copy(setup.secret).then(() => toast("Chiave copiata"), () => toast("Copia non riuscita: selezionala e copiala a mano."))}>Copia</Btn></div>
          </li>
          <li>Scrivi il codice di 6 cifre che compare nell’app.</li>
        </ol>
        <form onSubmit={submit} noValidate>
          <Field label="Codice dell’app" id="ms-code" error={bad}><Input ref={input} id="ms-code" name="code" inputMode="numeric" autoComplete="one-time-code" maxLength={7} aria-invalid={!!bad || undefined} onInput={() => setBad("")} /></Field>
          {err !== null && <ErrorNotice error={err} />}
          <Submit busy={busy} busyText="Attivazione…">Attiva</Submit>
        </form>
      </>}
    <p className="login-foot"><LinkBtn onClick={() => onRestart()}>Annulla e torna all’accesso</LinkBtn></p>
  </AuthCard>;
}
export function copy(text: string) {
  if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) return navigator.clipboard.writeText(text);
  return Promise.reject(new Error("clipboard"));
}
export function downloadText(name: string, text: string) {
  const url = URL.createObjectURL(new Blob([text], { type: "text/plain;charset=utf-8" }));
  const a = document.createElement("a"); a.href = url; a.download = name; document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** Codici di recupero: mostrati una sola volta, si prosegue solo confermando di averli salvati. */
export function RecoveryCodes({ codes, onContinue, embedded }: { codes: string[]; onContinue: () => void; embedded?: boolean }) {
  const [saved, setSaved] = useState(false), toast = useToast();
  const text = "Codici di recupero — Centro ripetizioni\nOgni codice vale una sola volta.\n\n" + codes.join("\n") + "\n";
  const body = <>
    <Notice kind="warn" title="Li vedi solo adesso">Conservali in un posto sicuro, separato dal telefono. Ognuno vale una volta sola se perdi l’accesso all’app.</Notice>
    <ol className="codes" aria-label="Codici di recupero">{codes.map((c) => <li key={c}><code>{c}</code></li>)}</ol>
    <div className="row-actions">
      <Btn kind="sm" onClick={() => copy(codes.join("\n")).then(() => toast("Codici copiati"), () => toast("Copia non riuscita: scaricali come file."))}>Copia</Btn>
      <Btn kind="sm" icon="download" onClick={() => downloadText("codici-recupero.txt", text)}>Scarica .txt</Btn>
    </div>
    <Check checked={saved} onChange={setSaved}>Li ho salvati in un posto sicuro</Check>
    <Btn kind="primary" className="login-btn" isle="arrow" disabled={!saved} onClick={onContinue}>Continua</Btn>
  </>;
  if (embedded) return body;
  return <AuthCard title="Salva i codici di recupero" id="h-codes" lead="La verifica in due passaggi è attiva.">{body}</AuthCard>;
}

/* ---------------- contesto ---------------- */
export function ContextPicker({ contexts, current, onDone, onCancel }: { contexts: S.Role[]; current: string | null; onDone: (ctx: S.AuthContext) => void; onCancel?: () => void }) {
  const [v, setV] = useState(current || ""), [busy, setBusy] = useState(false), [err, setErr] = useState<unknown>(null), [bad, setBad] = useState(false);
  async function submit(ev: FormEvent) {
    ev.preventDefault();
    if (!v) { setBad(true); return; }
    setBusy(true); setErr(null);
    try { onDone(await post("/auth/context", { context: v as S.Role })); } catch (x) { setErr(x); } finally { setBusy(false); }
  }
  return <AuthCard title="Con quale ruolo entri?" id="h-ctx" lead="Il tuo account ha più ruoli. Vedrai solo i dati e le funzioni del ruolo scelto; puoi cambiarlo dal menu dell’account.">
    <form onSubmit={submit} noValidate>
      <Choices label="Ruolo" name="context" value={v} onChange={(x) => { setV(x); setBad(false); }} options={contexts.map((c) => ({ v: c, label: CONTEXT_LABEL[c]?.label || c, sub: CONTEXT_LABEL[c]?.sub }))} />
      {bad && <p className="err" role="alert">Scegli un ruolo per continuare.</p>}
      {err !== null && <ErrorNotice error={err} />}
      <Submit busy={busy} busyText="Un momento…">Continua</Submit>
    </form>
    {onCancel && <p className="login-foot"><LinkBtn onClick={onCancel}>Esci</LinkBtn></p>}
  </AuthCard>;
}

/* ---------------- reimpostazione password ---------------- */
export function ResetRequest({ onBack }: { onBack: () => void }) {
  const [sent, setSent] = useState(""), [busy, setBusy] = useState(false), [err, setErr] = useState<unknown>(null), [bad, setBad] = useState(false);
  async function submit(ev: FormEvent<HTMLFormElement>) {
    ev.preventDefault();
    const email = String(new FormData(ev.currentTarget).get("email") || "").trim();
    if (!email.includes("@")) { setBad(true); return; }
    setBusy(true); setErr(null);
    try { await get("/auth/csrf"); await post("/auth/password-reset", { email }); setSent(email); } catch (x) { setErr(x); } finally { setBusy(false); }
  }
  if (sent) return <AuthCard title="Controlla la posta" id="h-reset-sent" lead={<>Se <b>{sent}</b> è registrato, riceverai un link per scegliere una nuova password. Il link vale poco tempo e una sola volta.</>}>
    <Notice kind="info">Non arriva nulla? Controlla lo spam o chiedi al centro di verificare l’indirizzo. Per sicurezza non indichiamo se l’email esiste.</Notice>
    <Btn kind="primary" className="login-btn" isle="arrow" onClick={onBack}>Torna all’accesso</Btn>
  </AuthCard>;
  return <AuthCard title="Password dimenticata" id="h-reset" lead="Scrivi l’email del tuo account: ti mandiamo un link per sceglierne una nuova.">
    <form onSubmit={submit} noValidate>
      <Field label="Email" id="r-email" error={bad && "Scrivi l’indirizzo email completo."}><Input id="r-email" name="email" type="email" inputMode="email" autoComplete="username" autoFocus onInput={() => setBad(false)} /></Field>
      {err !== null && <ErrorNotice error={err} />}
      <Submit busy={busy} busyText="Invio…">Invia il link</Submit>
    </form>
    <p className="login-foot"><LinkBtn onClick={onBack}>Torna all’accesso</LinkBtn></p>
  </AuthCard>;
}

function NewPassword({ email = "", busy, err, onSubmit, cta, busyText }: { email?: string; busy: boolean; err: unknown; onSubmit: (pw: string) => void; cta: string; busyText: string }) {
  const [pw, setPw] = useState(""), [pw2, setPw2] = useState(""), [tried, setTried] = useState(false);
  const hints = passwordHints(pw, email), mismatch = pw2 !== pw;
  const serverErrs = err instanceof ApiError && err.code === "WEAK_PASSWORD" && Array.isArray((err.data as { errors?: string[] })?.errors) ? (err.data as { errors: string[] }).errors : [];
  return <form noValidate onSubmit={(e) => { e.preventDefault(); setTried(true); if (!pw || hints.length || mismatch) return; onSubmit(pw); }}>
    <Field label="Nuova password" id="np-1" error={(tried && (!pw ? "Scegli una password." : hints[0])) || (serverErrs.length ? serverErrs.join(" ") : false)} hint="Almeno 12 caratteri; meglio una frase che ricordi facilmente.">
      <Input id="np-1" type="password" autoComplete="new-password" autoFocus value={pw} onChange={(e) => setPw(e.target.value)} aria-invalid={(tried && (!pw || hints.length > 0)) || serverErrs.length > 0 || undefined} /></Field>
    <Field label="Ripeti la password" id="np-2" error={tried && mismatch && "Le due password non coincidono."}>
      <Input id="np-2" type="password" autoComplete="new-password" value={pw2} onChange={(e) => setPw2(e.target.value)} aria-invalid={(tried && mismatch) || undefined} /></Field>
    {err !== null && !serverErrs.length && <ErrorNotice error={err} />}
    <Submit busy={busy} busyText={busyText}>{cta}</Submit>
  </form>;
}

export function ResetConfirm({ token, onDone }: { token: string; onDone: (msg: string) => void }) {
  const [busy, setBusy] = useState(false), [err, setErr] = useState<unknown>(null), [forgot, setForgot] = useState(false);
  if (forgot) return <ResetRequest onBack={() => onDone("")} />;
  if (!token || (err instanceof ApiError && err.code === "INVALID_TOKEN")) return <AuthCard title="Link non valido" id="h-reset-bad" lead="Il link per reimpostare la password è scaduto, è già stato usato oppure è incompleto.">
    <Btn kind="primary" className="login-btn" isle="arrow" onClick={() => setForgot(true)}>Chiedi un nuovo link</Btn>
    <p className="login-foot"><LinkBtn onClick={() => onDone("")}>Torna all’accesso</LinkBtn></p>
  </AuthCard>;
  return <AuthCard title="Scegli una nuova password" id="h-reset-new" lead="Dopo il salvataggio, le sessioni aperte sugli altri dispositivi vengono chiuse.">
    <NewPassword busy={busy} err={err} cta="Salva la password" busyText="Salvataggio…" onSubmit={async (password) => {
      setBusy(true); setErr(null);
      try { await get("/auth/csrf"); await post("/auth/password-reset/confirm", { token, password }); onDone("Password aggiornata. Accedi con la nuova password."); }
      catch (x) { setErr(x); } finally { setBusy(false); }
    }} />
  </AuthCard>;
}

/* ---------------- invito ---------------- */
export function InviteAccept({ token, signedIn, onDone, onLogin }: { token: string; signedIn: boolean; onDone: (msg: string) => void; onLogin: (msg: string) => void }) {
  const [busy, setBusy] = useState(false), [err, setErr] = useState<unknown>(null);
  async function accept(password?: string) {
    setBusy(true); setErr(null);
    try { await get("/auth/csrf"); const res = await post("/invitations/accept", password ? { token, password } : { token }) as { signed_in?: boolean } | undefined; onDone(signedIn ? "Invito accettato: il nuovo ruolo è attivo." : res?.signed_in ? "Benvenuto! Il tuo account è attivo." : "Account attivato. Accedi con la tua email e la password appena scelta."); }
    catch (x) {
      if (x instanceof ApiError && x.code === "LOGIN_REQUIRED") { savePendingInvite(token); onLogin("Hai già un account: accedi e l’invito verrà attivato subito dopo."); return; }
      setErr(x);
    } finally { setBusy(false); }
  }
  if (!token || (err instanceof ApiError && err.code === "INVALID_TOKEN")) return <AuthCard title="Invito non valido" id="h-inv-bad" lead="Il link dell’invito è scaduto, è già stato usato oppure è incompleto. Chiedi al centro di inviarne uno nuovo.">
    <Btn kind="primary" className="login-btn" isle="arrow" onClick={() => onDone("")}>Vai all’accesso</Btn>
  </AuthCard>;
  if (signedIn) return <AuthCard title="Accetta l’invito" id="h-inv" lead="L’invito verrà collegato all’account con cui hai già effettuato l’accesso.">
    {err !== null && <ErrorNotice error={err} />}
    <Btn kind="primary" className="login-btn" isle="arrow" disabled={busy} onClick={() => accept()}>{busy ? "Attivazione…" : "Accetta l’invito"}</Btn>
    <p className="login-foot"><LinkBtn onClick={() => onDone("")}>Non ora</LinkBtn></p>
  </AuthCard>;
  return <AuthCard title="Benvenuto nel centro" id="h-inv" lead="Scegli una password per attivare il tuo account. Se hai già un account con questa email, ti chiederemo di accedere.">
    <NewPassword busy={busy} err={err} cta="Attiva l’account" busyText="Attivazione…" onSubmit={(pw) => accept(pw)} />
    <p className="login-foot"><LinkBtn onClick={() => { savePendingInvite(token); onLogin("Accedi: l’invito verrà attivato subito dopo."); }}>Ho già un account</LinkBtn></p>
    <Help topic="famiglia" />
  </AuthCard>;
}

/** Sessione terminata o revocata altrove (GAP-G04). */
export function SessionEnded({ onLogin }: { onLogin: () => void }) {
  return <AuthCard title="Accesso non più disponibile" id="h-ended" lead="La sessione è terminata: è scaduta, è stata chiusa da un altro dispositivo oppure il centro ha modificato le autorizzazioni.">
    <Notice kind="info">Nessuna modifica in corso è stata salvata a metà. Accedi di nuovo per continuare.</Notice>
    <Btn kind="primary" className="login-btn" isle="arrow" onClick={onLogin}>Accedi di nuovo</Btn>
  </AuthCard>;
}
