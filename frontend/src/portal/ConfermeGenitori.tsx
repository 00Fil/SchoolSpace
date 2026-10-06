import { useEffect, useState } from "react";
import { api } from "../api";
import { dayLabel, hm, rome } from "../format";
import { human } from "../messages";
import { Btn, Notice, Skeleton } from "../ui/core";
import { Field, TextArea } from "../ui/controls";
import { Modal, useToast } from "../ui/layers";

/** P5 · DC-CONFERMA-GENITORI: le modifiche proposte dal tutor e accolte dal centro le confermano i genitori. */
type Row = { id: string; reason: string; version: number; awaiting: string | null; lesson_start_at: string | null; proposal: { note?: string } };
const at = (iso: string | null) => { if (!iso) return ""; const r = rome(iso); return `${dayLabel(r.date)} alle ${hm(r.min)}`; };

export default function ConfermeGenitori() {
  const toast = useToast();
  const [rows, setRows] = useState<Row[] | null>(null), [err, setErr] = useState(""), [act, setAct] = useState<{ row: Row; ok: boolean } | null>(null), [reason, setReason] = useState(""), [busy, setBusy] = useState(false);
  const load = () => api<{ results: Row[] }>("/change-requests/?state=SUBMITTED").then((r) => { setRows(r.results.filter((x) => x.awaiting === "GUARDIANS")); setErr(""); }).catch((e) => { setRows([]); setErr(human(e).text); });
  useEffect(() => { load(); }, []);
  if (!rows) return <Skeleton rows={2} />;
  if (!rows.length && !err) return null;
  async function send() {
    setBusy(true);
    try {
      await api(`/change-requests/${act!.row.id}/guardian-confirm/`, { method: "POST", headers: { "Idempotency-Key": crypto.randomUUID() }, body: JSON.stringify({ expected_version: act!.row.version, decision: act!.ok ? "CONFIRM" : "REJECT", reason: reason.trim() }) });
      toast(act!.ok ? "Conferma inviata al centro." : "Rifiuto registrato: il tutor viene avvisato."); setAct(null); await load();
    } catch (e) { const h = human(e); setErr(h.code === "VERSION_CONFLICT" || h.code === "CHANGE_NOT_AWAITING_GUARDIANS" ? "La richiesta è cambiata nel frattempo: ricarico l’elenco." : h.text); setAct(null); await load(); }
    finally { setBusy(false); }
  }
  return <section aria-labelledby="cg-title" className="module" style={{ marginBottom: 20 }}>
    <h2 id="cg-title" className="m-title">Modifiche proposte dal tutor</h2>
    
    {err && <Notice kind="bad">{err}</Notice>}
    {rows.map((r) => <div className="card" key={r.id} style={{ marginBottom: 10 }}>
      <b>Lezione del {at(r.lesson_start_at)}</b>
      <p>Proposta del tutor: {r.proposal.note || r.reason}</p>
      <div className="controls"><Btn kind="primary" onClick={() => { setAct({ row: r, ok: true }); setReason("Per noi va bene"); }}>Va bene</Btn>
        <Btn onClick={() => { setAct({ row: r, ok: false }); setReason("Non possiamo con questa modifica"); }}>Non va bene</Btn></div>
    </div>)}
    <Modal open={!!act} onClose={() => setAct(null)} labelledBy="cg-m"><div className="modal-body">
      <h2 id="cg-m">{act?.ok ? "Confermate la modifica?" : "Rifiutate la modifica?"}</h2>
    </div><div className="modal-foot"><button type="button" className="pill-btn ghost" onClick={() => setAct(null)}>Annulla</button>
      <Btn kind="primary" disabled={busy} onClick={send}>{busy ? "Invio…" : act?.ok ? "Confermo" : "Rifiuto"}</Btn></div></Modal>
  </section>;
}
