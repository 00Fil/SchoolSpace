import "./lumen/index.css";
import "./app.css";
import { Component, ReactNode, useCallback, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { api, ApiError } from "./api";
import { get, onSessionEvent, post } from "./api/client";
import { AuthCard, ContextPicker, InviteAccept, Login, MfaSetup, MfaVerify, RecoveryCodes, ResetConfirm, ResetRequest, SessionEnded } from "./auth/Auth";
import type { S } from "./api/schema.gen";
import { publicPage, Step, takePendingInvite, tokenFromHash } from "./auth/flow";
import { human } from "./messages";
import { initPrefs } from "./ui/prefs";
import { Btn, Notice, Skeleton, Sprite } from "./ui/core";
import { ToastHost, useToast } from "./ui/layers";
import { classify, ErrorState } from "./ui/states";
import { useRoute } from "./ui/route";
import { DataProvider, Me, useData } from "./app/data";
import Shell, { sectionsFor } from "./app/Shell";
import Panoramica from "./screens/Panoramica";
import Agenda from "./screens/Agenda";
import Settimana from "./screens/Settimana";
import Studenti from "./screens/Studenti";
import Disponibilita from "./screens/Disponibilita";
import Richieste from "./screens/Richieste";
import Percorsi from "./screens/Percorsi";
import Materie from "./screens/Materie";
import Proposte from "./screens/Proposte";
import Pianificazione from "./screens/Pianificazione";
import PianoMensile from "./screens/PianoMensile";
import OrariCentro from "./screens/OrariCentro";
import Impegni from "./screens/Impegni";
import Conferme from "./portal/Conferme";
import Laboratorio from "./screens/Laboratorio";
import Decisioni from "./screens/Decisioni";
import Impostazioni from "./screens/Impostazioni";
import Famiglie from "./screens/Famiglie";
import TutorScreen from "./screens/Tutor";
import Utenti from "./screens/Utenti";
import Configurazione from "./screens/Configurazione";
import PortalHome from "./portal/PortalHome";
import Profilo from "./portal/Profilo";
import MieiDati from "./portal/MieiDati";
import Privacy from "./screens/Privacy";
import Cambi from "./portal/Cambi";
import Presenze from "./portal/Presenze";
import PresaVisione from "./portal/PresaVisione";
import Operativita from "./screens/Operativita";
import Statistiche from "./screens/Statistiche";

initPrefs();

const SCREENS: Record<string, () => ReactNode> = {
  panoramica: () => <Panoramica />, statistiche: () => <Statistiche />, agenda: () => <Agenda />, settimana: () => <Settimana />, studenti: () => <Studenti />, disponibilita: () => <Disponibilita />,
  richieste: () => <Richieste />, percorsi: () => <Percorsi />, materie: () => <Materie />, proposte: () => <Proposte />, pianificazione: () => <PianoMensile />, "pianificazione-avanzata": () => <Pianificazione />, apertura: () => <OrariCentro />, impegni: () => <Impegni />, conferme: () => <Conferme />, laboratorio: () => <Laboratorio />,
  decisioni: () => <Decisioni />, impostazioni: () => <Impostazioni />,
  anagrafica: () => <Famiglie />, tutor: () => <TutorScreen />, utenti: () => <Utenti />, configurazione: () => <Configurazione />,
  profilo: () => <Profilo />, dati: () => <MieiDati />, cambi: () => <Cambi />, presenze: () => <Presenze />, orari: () => <PresaVisione />, operativita: () => <Operativita />, privacy: () => <Privacy />,
};

/** Aiuto in linea per le schermate del centro (GAP-G09); i portali lo mostrano in testata. */
function Screens() {
  const d = useData(), r = useRoute(); const [err, setErr] = useState<unknown>(null);
  const load = useCallback(() => { setErr(null); d.refresh().catch((e) => setErr(e)); }, [d.refresh]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(load, [load]);
  // v0.9.5: per il centro «Studenti» non esiste più; i vecchi link aprono la scheda del figlio in Famiglie.
  useEffect(() => { if (d.center && r.name === "studenti") location.replace("#/anagrafica" + (r.q.toString() ? "?" + r.q.toString() : "")); }, [d.center, r]);
  const allowed = r.name === "impostazioni" || sectionsFor(d.center, d.me.roles).some((s) => s.key === r.name);
  const key = allowed && SCREENS[r.name] ? r.name : "panoramica";
  return <Shell>
    {err !== null && <div style={{ marginBottom: 14 }}><ErrorState error={err} onRetry={load} title={classify(err) === "error" ? "Non riesco a caricare i dati" : undefined} /></div>}
    <ScreenBoundary key={key}>{key === "panoramica" && !d.center ? <PortalHome /> : SCREENS[key]()}</ScreenBoundary>
  </Shell>;
}

/** Un errore imprevisto in una schermata non deve mai lasciare la pagina bianca. */
class ScreenBoundary extends Component<{ children: ReactNode }, { error: unknown }> {
  state = { error: null as unknown };
  static getDerivedStateFromError(error: unknown) { return { error }; }
  componentDidCatch(error: unknown) { console.error(error); }
  render() {
    if (this.state.error === null) return this.props.children;
    return <Notice kind="bad" title="Questa schermata non si è caricata correttamente" action={<Btn kind="sm" onClick={() => this.setState({ error: null })}>Riprova</Btn>}>Gli altri dati non sono stati toccati. Puoi riprovare o tornare alla <a href="#/panoramica">panoramica</a>.</Notice>;
  }
}

type Phase = { kind: "boot" } | { kind: "auth"; step: Step; notice?: string } | { kind: "reset"; token: string } | { kind: "invite"; token: string } | { kind: "app" } | { kind: "forgot" } | { kind: "ended" } | { kind: "error"; error: unknown };

async function loadMe(): Promise<Me> {
  const me = await api<Me>("/me");
  if (!me || typeof me !== "object" || !Array.isArray(me.roles)) throw new ApiError(502, "Risposta del server non valida.", "UNEXPECTED_RESPONSE");
  const ctx = await get("/auth/context", { quiet: true }).catch(() => null);
  return { ...me, contexts: ctx?.contexts || [], context: ctx?.context ?? null };
}

function App() {
  const toast = useToast();
  const [me, setMe] = useState<Me | null>(null);
  const [phase, setPhase] = useState<Phase>(() => {
    const page = publicPage(location.pathname);
    if (!page) return { kind: "boot" };
    // Il token sta nel frammento: lo leggiamo e lo togliamo subito dall'indirizzo (niente cronologia/referrer).
    const token = tokenFromHash(location.hash);
    history.replaceState(null, "", "/");
    return page === "reset" ? { kind: "reset", token } : { kind: "invite", token };
  });
  const [stepUp, setStepUp] = useState(false);

  /** Dopo un errore di sessione: decide fra login, scelta del ruolo e verifica MFA. */
  const route = useCallback(async (e: unknown, notice?: string): Promise<Phase> => {
    if (e instanceof ApiError && e.code === "CONTEXT_REQUIRED") {
      const ctx = await get("/auth/context", { quiet: true });
      return { kind: "auth", step: { kind: "context", contexts: ctx.contexts, current: ctx.context } };
    }
    if (e instanceof ApiError && e.code === "MFA_REQUIRED") {
      const st = await get("/auth/mfa", { quiet: true });
      return { kind: "auth", step: { kind: st.enrolled ? "mfa-verify" : "mfa-setup" } };
    }
    if (e instanceof ApiError && (e.status === 403 || e.status === 401)) return { kind: "auth", step: { kind: "login" }, notice };
    return { kind: "error", error: e };
  }, []);

  const finish = useCallback(async () => {
    try {
      const m = await loadMe(); setMe(m); setPhase({ kind: "app" }); setStepUp(false);
      const pending = takePendingInvite();
      if (pending) post("/invitations/accept", { token: pending }).then(() => { toast("Invito accettato: il nuovo ruolo è attivo."); return loadMe().then(setMe); }).catch((x) => toast(human(x).text));
    } catch (e) { setPhase(await route(e).catch((x) => ({ kind: "error", error: x }) as Phase)); }
  }, [route, toast]);

  const boot = useCallback(() => {
    setPhase({ kind: "boot" });
    api("/auth/csrf").then(finish).catch((e) => setPhase({ kind: "error", error: e }));
  }, [finish]);
  useEffect(() => { if (phase.kind === "boot") boot(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Eventi globali del client API (GAP-G04): revoca, contesto, step-up MFA.
  useEffect(() => onSessionEvent(async (ev) => {
    if (ev.type === "context-required") { setPhase(await route(new ApiError(409, "", "CONTEXT_REQUIRED"))); return; }
    if (ev.type === "mfa-required") { setStepUp(true); setPhase(await route(new ApiError(403, "", "MFA_REQUIRED"))); return; }
    // 401/403: la sessione esiste ancora? Se /me fallisce, l'accesso è stato revocato o è scaduto.
    try { const m = await loadMe(); setMe(m); }
    catch { setMe(null); setPhase({ kind: "ended" }); }
  }), [route]);

  const toLogin = (notice?: string) => setPhase({ kind: "auth", step: { kind: "login" }, notice });
  const onStep = (s: Step) => { if (s.kind === "done") finish(); else setPhase({ kind: "auth", step: s }); };
  const restart = (msg?: string) => { api("/auth/logout", { method: "POST" }).catch(() => undefined).finally(() => toLogin(msg)); };

  if (phase.kind === "error") return <main className="login-page" id="main"><section className="module login-card"><Notice kind="bad" title="Server non raggiungibile" action={<Btn kind="sm" onClick={boot}>Riprova</Btn>}>{human(phase.error).text}</Notice></section></main>;
  if (phase.kind === "boot") return <main className="login-page" id="main" aria-busy="true"><section className="module login-card"><Skeleton rows={3} /></section></main>;
  if (phase.kind === "reset") return <ResetConfirm token={phase.token} onDone={(msg) => toLogin(msg || undefined)} />;
  if (phase.kind === "invite") return <InviteGate token={phase.token} onDone={(msg) => { if (msg) toast(msg); boot(); }} onLogin={toLogin} />;
  if (phase.kind === "ended") return <SessionEnded onLogin={() => toLogin()} />;
  if (phase.kind === "auth") {
    const s = phase.step;
    if (s.kind === "mfa-verify") return <MfaVerify stepUp={stepUp && !!me} onStep={onStep} onRestart={restart} />;
    if (s.kind === "mfa-setup") return <MfaSetup onStep={onStep} onRestart={restart} />;
    if (s.kind === "recovery-codes") return <RecoveryCodes codes={s.codes} onContinue={() => onStep(s.then)} />;
    if (s.kind === "context") return <ContextPicker contexts={s.contexts} current={s.current} onDone={() => finish()} onCancel={me ? () => setPhase({ kind: "app" }) : () => restart()} />;
    if (s.kind === "login") return <Login onStep={onStep} onForgot={() => setPhase({ kind: "forgot" })} notice={phase.notice ? <Notice kind="info">{phase.notice}</Notice> : undefined} />;
  }
  if (phase.kind === "forgot") return <ResetRequest onBack={() => toLogin()} />;
  if (!me) return <Login onStep={onStep} onForgot={() => setPhase({ kind: "forgot" })} />;
  if (!me.roles.length) return <NoRole onSignOut={() => restart()} />;
  return <DataProvider key={me.id + ":" + me.roles.join(",")} me={me}
    onSignOut={() => { setMe(null); history.replaceState(null, "", location.pathname); toLogin(); }}
    onSwitchContext={me.contexts && me.contexts.length > 1 ? () => setPhase({ kind: "auth", step: { kind: "context", contexts: me.contexts as S.Role[], current: me.context ?? null } }) : undefined}>
    <Screens /></DataProvider>;
}

function InviteGate({ token, onDone, onLogin }: { token: string; onDone: (msg: string) => void; onLogin: (msg: string) => void }) {
  const [signedIn, setSignedIn] = useState<boolean | null>(null);
  useEffect(() => { api("/auth/csrf").then(() => api("/me")).then(() => setSignedIn(true), () => setSignedIn(false)); }, []);
  if (signedIn === null) return <main className="login-page" id="main" aria-busy="true"><section className="module login-card"><Skeleton rows={3} /></section></main>;
  return <InviteAccept token={token} signedIn={signedIn} onDone={onDone} onLogin={onLogin} />;
}

function NoRole({ onSignOut }: { onSignOut: () => void }) {
  return <AuthCard title="Nessun ruolo attivo" id="h-norole" lead="Il tuo account esiste, ma al momento non ha autorizzazioni attive: il centro può averle revocate o non ancora confermate.">
    <Notice kind="info">Contatta il centro se pensi sia un errore. Nessun dato è visibile finché un ruolo non viene riattivato.</Notice>
    <Btn kind="primary" className="login-btn" isle="arrow" onClick={onSignOut}>Esci</Btn>
  </AuthCard>;
}

createRoot(document.getElementById("root")!).render(<><Sprite /><ToastHost><App /></ToastHost></>);
