import { useEffect, useRef, useState } from "react";
import { createRoot, Root } from "react-dom/client";
import { BASE, csrfToken, request } from "../api/client";
import { hm, rome } from "../format";
import { Icon } from "../ui/core";

/** v0.10 · Videolezione integrata (Jitsi Meet self-hosted).
 *  Un clic su «Entra nella lezione»: la stanza si apre dentro il gestionale, con nome già
 *  impostato e senza schermata intermedia. Una sola intestazione (questa): Jitsi riceve
 *  `embed_url`, che nasconde materia e timer della stanza. Mentre è aperta si invia un
 *  segnale al minuto per precompilare le presenze (il tutor conferma sempre). */
export type Meeting = {
  lesson_id: string; version: number; join_url: string; expires_at: string;
  provider?: "jitsi"; embed?: boolean; embed_url?: string; starts_at?: string; origin?: string;
  room?: string; display_name?: string; moderator?: boolean; subject?: string;
};

const HEARTBEAT_MS = 60_000, SLOW_MS = 15_000, EXIT_MS = 320;
const reduced = () => typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
let root: Root | null = null, host: HTMLDivElement | null = null;

function presence(id: string, event: "join" | "heartbeat" | "leave", keepalive = false) {
  if (keepalive) {
    // Chiusura della scheda: fetch keepalive (sendBeacon non porta l'header CSRF).
    try { void fetch(`${BASE}/occurrences/${id}/meeting/presence`, { method: "POST", keepalive: true, credentials: "same-origin", headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() }, body: JSON.stringify({ event }) }); } catch { /* best effort */ }
    return;
  }
  request("POST", `/occurrences/${id}/meeting/presence`, { body: { event }, quiet: true }).catch(() => undefined);
}

/** Stato temporale della lezione, aggiornato ogni 15 secondi. */
function useClock(startIso: string | undefined, endIso: string) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 15_000); return () => clearInterval(t); }, []);
  const end = new Date(endIso).getTime(), start = startIso ? new Date(startIso).getTime() : end - 3_600_000;
  const left = Math.max(0, Math.round((end - now) / 60_000)), toStart = Math.round((start - now) / 60_000);
  const progress = Math.min(1, Math.max(0, (now - start) / Math.max(1, end - start)));
  const label = toStart > 0 ? `Inizia tra ${toStart} min` : left > 0 ? `Termina tra ${left} min` : "Tempo terminato";
  const tone = toStart > 0 ? "wait" : left <= 5 ? "warn" : "live";
  return { label, tone, progress };
}

const Bars = () => <span className="vr-bars" aria-hidden="true"><i /><i /><i /></span>;

function Room({ m, onClose }: { m: Meeting; onClose: () => void }) {
  const [loaded, setLoaded] = useState(false), [slow, setSlow] = useState(false), [ask, setAsk] = useState(false), [leaving, setLeaving] = useState(false);
  const exitBtn = useRef<HTMLButtonElement>(null), stayBtn = useRef<HTMLButtonElement>(null);
  const clock = useClock(m.starts_at, m.expires_at);
  const src = m.embed_url || m.join_url;

  const close = () => { if (leaving) return; setLeaving(true); setTimeout(onClose, reduced() ? 0 : EXIT_MS); };
  useEffect(() => {
    presence(m.lesson_id, "join");
    const beat = setInterval(() => presence(m.lesson_id, "heartbeat"), HEARTBEAT_MS);
    const bye = () => presence(m.lesson_id, "leave", true);
    window.addEventListener("pagehide", bye);
    const prev = document.body.style.overflow; document.body.style.overflow = "hidden";
    return () => { clearInterval(beat); window.removeEventListener("pagehide", bye); presence(m.lesson_id, "leave"); document.body.style.overflow = prev; };
  }, [m.lesson_id]);
  useEffect(() => { if (loaded) return; const t = setTimeout(() => setSlow(true), SLOW_MS); return () => clearTimeout(t); }, [loaded]);
  useEffect(() => {
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") { e.preventDefault(); setAsk((a) => !a); } };
    window.addEventListener("keydown", key); return () => window.removeEventListener("keydown", key);
  }, []);
  useEffect(() => { (ask ? stayBtn : exitBtn).current?.focus(); }, [ask]);

  return <div className={"vroom" + (leaving ? " is-leaving" : "")} data-theme="dark" role="dialog" aria-modal="true" aria-labelledby="vr-title">
    <header className="vr-head">
      <div className="vr-id">
        <span className="vr-logo"><Bars /></span>
        <div className="vr-text">
          <h2 id="vr-title">{m.subject || "Videolezione"}</h2>
          <p className="vr-meta">
            <span className={"vr-state " + clock.tone} aria-live="polite">{clock.label}</span>
            <span className="vr-sep vr-m" aria-hidden="true" />
            <span className="vr-m">{m.display_name}</span>
            {m.moderator && <span className="vr-badge">Moderatore</span>}
            <span className="vr-sep vr-m" aria-hidden="true" />
            <span className="vr-m">fino alle {hm(rome(m.expires_at).min)}</span>
          </p>
        </div>
      </div>
      <div className="vr-actions">
        <a className="vr-btn ghost" href={m.join_url} target="_blank" rel="noopener noreferrer" onClick={onClose} title="Apri in una nuova scheda">
          <Icon n="arrow" size={18} /><span className="vr-m">Nuova scheda</span></a>
        <div className="vr-exit">
          <button ref={exitBtn} type="button" className="vr-btn danger" aria-expanded={ask} aria-controls="vr-confirm" onClick={() => setAsk(!ask)}>
            <Icon n="x" size={18} /><span>Esci</span></button>
          {ask && <div className="vr-confirm" id="vr-confirm" role="alertdialog" aria-labelledby="vr-confirm-t" aria-describedby="vr-confirm-d">
            <b id="vr-confirm-t">Uscire dalla videolezione?</b>
            <p id="vr-confirm-d">Puoi rientrare fino alle {hm(rome(m.expires_at).min)}.</p>
            <div className="vr-confirm-acts">
              <button ref={stayBtn} type="button" className="vr-btn ghost" onClick={() => setAsk(false)}>Resta</button>
              <button type="button" className="vr-btn danger solid" onClick={close}>Esci</button>
            </div>
          </div>}
        </div>
      </div>
      <span className="vr-progress" aria-hidden="true"><i style={{ transform: `scaleX(${clock.progress})` }} /></span>
    </header>
    <div className={"vr-stage" + (loaded ? " is-live" : "")}>
      <div className="vr-wait" aria-hidden={loaded}>
        <span className="vr-logo lg"><Bars /></span>
        <b>Collegamento alla stanza</b>
        <p>Quando il browser lo chiede, consenti camera e microfono.</p>
        {slow && <p className="vr-slow">Ci vuole più del solito. <a href={m.join_url} target="_blank" rel="noopener noreferrer" onClick={onClose}>Apri in una nuova scheda</a></p>}
      </div>
      <iframe className="vr-frame" title={`Videolezione ${m.subject || ""}`} src={src} onLoad={() => setLoaded(true)}
        allow="camera; microphone; display-capture; fullscreen; autoplay; clipboard-write" referrerPolicy="no-referrer" />
    </div>
  </div>;
}

function unmount() { root?.unmount(); host?.remove(); root = null; host = null; }

/** Apre la lezione: integrata se il server lo consente, altrimenti in una nuova scheda. */
export function openMeeting(m: Meeting): boolean {
  if (m.provider === "jitsi" && m.embed !== false) {
    unmount();
    host = document.createElement("div"); document.body.appendChild(host);
    root = createRoot(host); root.render(<Room m={m} onClose={unmount} />);
    return true;
  }
  return !!window.open(m.join_url, "_blank", "noopener,noreferrer") || (window.location.assign(m.join_url), true);
}

/** Recupera il link autorizzato e apre la stanza. Gli errori restano al chiamante. */
export async function joinLesson(id: string) {
  const m = await request<Meeting>("GET", `/occurrences/${id}/meeting`);
  openMeeting(m);
  return m;
}
