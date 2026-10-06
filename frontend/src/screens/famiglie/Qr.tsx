/** QR code d'accesso per il genitore presente in sede: link breve chiesto al server, disegnato in SVG. */
import { useCallback, useEffect, useMemo, useState } from "react";
import qrcode from "qrcode-generator";
import { Btn, Icon } from "../../ui/core";
import { send, writeError } from "../registry";

export function QrSvg({ text, size = 220 }: { text: string; size?: number }) {
  const path = useMemo(() => {
    const q = qrcode(0, "M"); q.addData(text); q.make();
    const n = q.getModuleCount(); let d = "";
    for (let r = 0; r < n; r++) for (let c = 0; c < n; c++) if (q.isDark(r, c)) d += `M${c + 4} ${r + 4}h1v1h-1z`;
    return { d, n: n + 8 };
  }, [text]);
  return <svg className="fm-qr-svg" viewBox={`0 0 ${path.n} ${path.n}`} width={size} height={size} role="img" aria-label="QR code per attivare l’accesso" shapeRendering="crispEdges">
    <rect width={path.n} height={path.n} fill="#fff" /><path d={path.d} fill="#111" />
  </svg>;
}

const left = (iso: string) => Math.max(0, Math.round((new Date(iso).getTime() - Date.now()) / 1000));

/** Pannello QR: si apre solo su richiesta, scade da solo e si può rigenerare. */
export function QrPanel({ invitationId, name, onClose }: { invitationId: string; name: string; onClose?: () => void }) {
  const [qr, setQr] = useState<{ url: string; expires_at: string } | null>(null), [err, setErr] = useState(""), [, tick] = useState(0);
  const load = useCallback(() => { setErr(""); setQr(null); send<{ url: string; expires_at: string }>("POST", `/registry/invitations/${invitationId}/qr`, {}).then(setQr).catch((e) => setErr(writeError(e))); }, [invitationId]);
  useEffect(load, [load]);
  useEffect(() => { const t = setInterval(() => tick((x) => x + 1), 1000); return () => clearInterval(t); }, []);
  const s = qr ? left(qr.expires_at) : 0, expired = qr && s === 0;
  return <div className="fm-qr" aria-live="polite">
    <div className="fm-qr-code">{qr && !expired ? <QrSvg text={qr.url} /> : <div className="fm-qr-ph">{err ? <Icon n="x" /> : expired ? <Icon n="clock" /> : <span className="fm-spin" aria-label="Preparo il QR code" />}</div>}</div>
    <div className="fm-qr-txt">
      <b>Fai inquadrare il codice a {name.split(" ")[0] || "il genitore"}</b>
      <ol><li>Apre la fotocamera del telefono e tocca il link.</li><li>Sceglie una password.</li><li>Entra subito nella sua pagina.</li></ol>
      {err ? <p className="fm-qr-err">{err}</p> : qr && <p className={"fm-qr-time" + (expired ? " off" : "")}>{expired ? "Il codice è scaduto." : `Valido ancora ${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")} · l’invito via email resta valido`}</p>}
      <div className="fm-qr-act">{(expired || err) && <Btn kind="primary sm" onClick={load}>Genera un nuovo codice</Btn>}{onClose && <Btn kind="sm ghost" onClick={onClose}>Nascondi</Btn>}</div>
    </div>
  </div>;
}
