import { useEffect, useState } from "react";
import { api } from "../api";
import { human } from "../messages";
import { Btn, Notice } from "../ui/core";
import { Modal } from "../ui/layers";

/** P6 · C04: al primo accesso (e a ogni nuova versione) l'informativa va letta e confermata
 *  prima di usare il portale. Non si chiude senza conferma. */
export default function InformativaGate() {
  const [version, setVersion] = useState<string | null>(null), [busy, setBusy] = useState(false), [err, setErr] = useState("");
  useEffect(() => { api<{ notice_version: string; notice_acknowledged: boolean }>("/me/data").then((d) => { if (!d.notice_acknowledged) setVersion(d.notice_version); }).catch(() => {}); }, []);
  if (!version) return null;
  async function ack() {
    setBusy(true); setErr("");
    try { await api("/me/notice/acknowledge", { method: "POST", body: JSON.stringify({ version }) }); setVersion(null); }
    catch (e) { setErr(human(e).text); } finally { setBusy(false); }
  }
  return <Modal open onClose={() => {}} labelledBy="inf-h"><div className="modal-body">
    <h2 id="inf-h">Informativa sul trattamento dei dati</h2>
    <p>Il centro tratta i dati tuoi e, se sei genitore, dei tuoi figli solo per organizzare le lezioni, comunicare con la famiglia e adempiere agli obblighi di legge.</p>
    <ul>
      <li>Ogni persona vede solo i dati che le servono: gli altri partecipanti ai gruppi restano anonimi.</li>
      <li>I dati sono conservati per i tempi approvati dal centro e poi cancellati o anonimizzati.</li>
      <li>Puoi scaricare una copia dei tuoi dati e chiederne rettifica o cancellazione da «I miei dati».</li>
    </ul>
    <p>Il testo completo è in «I miei dati». Versione {version}.</p>
    {err && <Notice kind="bad">{err}</Notice>}
  </div><div className="modal-foot"><Btn kind="primary" disabled={busy} onClick={ack}>{busy ? "Attendi…" : "Ho letto l’informativa"}</Btn></div></Modal>;
}
