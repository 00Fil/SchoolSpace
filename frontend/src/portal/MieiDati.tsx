import { useEffect, useState } from "react";
import { api, csrfToken } from "../api";
import { dateLong, rome } from "../format";
import { human } from "../messages";
import { Btn, Notice, PageHead, Skeleton, Tag } from "../ui/core";
import { Field, SegCtl } from "../ui/controls";
import { Modal, useToast } from "../ui/layers";
import { Help } from "../ui/help";

/** P5 · «I miei dati»: informativa, consenso dello studente, export personale, richieste (artt. 15-21). */
type Subject = { type: "ACCOUNT" | "STUDENT"; id: string; label: string };
type Req = { id: string; kind: string; subject_id: string; status: string; received_at: string; due_at: string };
type Exp = { id: string; created_at: string; expires_at: string; available: boolean; token?: string; filename: string };
type Data = { notice_version: string; role: string; subjects: Subject[]; consent: null | { adult_confirmed: boolean; consent_at: string | null; reconfirmations?: { link_id: string; guardian: string; due_at: string | null }[] }; requests: Req[]; exports: Exp[] };
const KIND: Record<string, string> = { ACCESS: "Copia dei dati", PORTABILITY: "Portabilità", RECTIFICATION: "Correzione", ERASURE: "Cancellazione", RESTRICTION: "Limitazione", OBJECTION: "Opposizione" };
const STATUS: Record<string, [string, "amber" | "green" | "plain" | "blue"]> = { RECEIVED: ["Ricevuta", "blue"], VERIFIED: ["In lavorazione", "amber"], EXTENDED: ["Prorogata", "amber"], COMPLETED: ["Evasa", "green"], REJECTED: ["Respinta", "plain"] };
const day = (iso: string) => dateLong(rome(iso).date);
const csrf = () => String(csrfToken() || "");

async function download(e: Exp) {
  const res = await fetch(`/api/v1/privacy/exports/${e.id}/download`, { method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() }, body: JSON.stringify({ token: e.token }) });
  if (!res.ok) throw new Error(res.status === 410 ? "Il file è scaduto o è già stato scaricato." : "Download non riuscito.");
  const url = URL.createObjectURL(await res.blob()), a = document.createElement("a");
  a.href = url; a.download = e.filename; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export default function MieiDati() {
  const toast = useToast();
  const [d, setD] = useState<Data | null>(null), [err, setErr] = useState(""), [fresh, setFresh] = useState<Exp | null>(null);
  const [who, setWho] = useState(""), [busy, setBusy] = useState(false), [ask, setAsk] = useState(""), [decline, setDecline] = useState("");
  const load = () => api<Data>("/me/data").then((x) => { setD(x); setWho((w) => w || x.subjects[0]?.id || ""); setErr(""); }).catch((e) => setErr(human(e).text));
  useEffect(() => { load(); }, []);
  const subject = d?.subjects.find((s) => s.id === who);
  async function exportNow() {
    if (!subject) return; setBusy(true);
    try { const e = await api<Exp>("/me/data/export", { method: "POST", body: JSON.stringify({ subject_type: subject.type, subject_id: subject.id }) }); setFresh(e); await load(); }
    catch (e) { const h = human(e); setErr(h.code === "EXPORT_RECENT" ? "Hai già un file pronto da scaricare: usalo prima di chiederne un altro." : h.text); } finally { setBusy(false); }
  }
  async function sendRequest() {
    if (!subject) return; setBusy(true);
    try { await api("/me/data/requests", { method: "POST", body: JSON.stringify({ kind: ask, subject_type: subject.type, subject_id: subject.id }) }); toast("Richiesta inviata al centro: risponde entro un mese."); setAsk(""); await load(); }
    catch (e) { const h = human(e); setErr(h.code === "REQUEST_ALREADY_OPEN" ? "C’è già una richiesta uguale in corso." : h.text); setAsk(""); } finally { setBusy(false); }
  }
  async function consent(granted: boolean) {
    setBusy(true);
    try { await api("/auth/student-consent", { method: "POST", body: JSON.stringify({ granted }) }); toast(granted ? "Consenso registrato." : "Consenso revocato."); await load(); }
    catch (e) { setErr(human(e).text); } finally { setBusy(false); }
  }
  async function reconfirm(id: string, yes: boolean) {
    setBusy(true);
    try {
      await api(`/registry/guardian-links/${id}/${yes ? "reconfirm" : "decline"}`, { method: "POST", body: JSON.stringify(yes ? { confirmation: "Confermata dallo studente nel portale", reason: "Riconferma alla maggiore età" } : { reason: "Lo studente maggiorenne non conferma la delega" }) });
      toast(yes ? "Delega confermata." : "Delega chiusa: il genitore non vede più le tue lezioni."); setDecline(""); await load();
    } catch (e) { setErr(human(e).text); setDecline(""); } finally { setBusy(false); }
  }
  const minorStudent = d?.role === "STUDENT" && !d.consent?.adult_confirmed;
  return <section className="module" aria-labelledby="h-dati">
    <PageHead id="h-dati" title="I miei dati" lead="Cosa conserva il centro, come scaricarlo e come chiedere correzioni o cancellazioni." />
    <div className="page-help"><Help topic="dati" /></div>
    {err && <Notice kind="bad" action={<Btn kind="sm" onClick={() => { setErr(""); load(); }}>Riprova</Btn>}>{err}</Notice>}
    {!d ? <Skeleton rows={4} /> : <>
      <h2 className="m-title">Informativa</h2>
      <p>Il centro tratta nome, contatti, lezioni, presenze e disponibilità solo per organizzare le lezioni. I dati non vengono venduti né usati per pubblicità. Puoi chiedere in ogni momento una copia, una correzione o la cancellazione: il centro risponde entro un mese.</p>
      <p className="fine">Versione dell’informativa: {d.notice_version}. Testo completo: chiedilo alla segreteria o leggi il manuale famiglie.</p>

      {d.consent && <div style={{ marginTop: 18 }}><h2 className="m-title">Accesso dei genitori</h2>
        {d.consent.adult_confirmed ? <>
          <p>Sei maggiorenne: i tuoi genitori vedono le tue lezioni solo se lo consenti.</p>
          <div className="controls"><Tag tone={d.consent.consent_at ? "green" : "plain"}>{d.consent.consent_at ? `Consentito dal ${day(d.consent.consent_at)}` : "Non consentito"}</Tag>
            <Btn kind="sm" disabled={busy} onClick={() => consent(!d.consent!.consent_at)}>{d.consent.consent_at ? "Revoca il consenso" : "Consenti l’accesso"}</Btn></div>
          {!!d.consent.reconfirmations?.length && <div style={{ marginTop: 12 }}><h3 className="m-title">Deleghe da riconfermare</h3>
            <p className="fine">Sei diventato maggiorenne: decidi tu se queste persone possono continuare a gestire le tue lezioni.</p>
            <div className="list-rows">{d.consent.reconfirmations.map((r) => <div className="list-row" key={r.link_id}>
              <div><b>{r.guardian}</b>{r.due_at && <small>entro il {day(r.due_at)}; poi la delega scade da sola</small>}</div>
              <div className="controls"><Btn kind="sm" disabled={busy} onClick={() => reconfirm(r.link_id, true)}>Confermo</Btn><Btn kind="sm" disabled={busy} onClick={() => setDecline(r.link_id)}>Non confermo</Btn></div></div>)}</div></div>}
        </> : <p className="muted">Finché sei minorenne il tuo accesso è in sola visione: lezioni e link delle lezioni online. Al compimento dei 18 anni il centro ti chiederà se i genitori possono continuare a vedere le tue lezioni.</p>}
      </div>}

      <h2 className="m-title" style={{ marginTop: 18 }}>Scarica o chiedi</h2>
      {d.subjects.length > 1 && <SegCtl label="Dati di" value={who} options={d.subjects.map((s) => [s.id, s.label])} onChange={setWho} />}
      <div className="controls" style={{ flexWrap: "wrap", gap: 8, marginTop: 10 }}>
        <Btn kind="primary" disabled={busy || !subject} onClick={exportNow}>{busy ? "Preparo…" : "Prepara la copia dei dati"}</Btn>
        {!minorStudent && ["RECTIFICATION", "ERASURE", "RESTRICTION", "OBJECTION"].map((k) => <Btn kind="sm" key={k} disabled={busy} onClick={() => setAsk(k)}>Chiedi {KIND[k].toLowerCase()}</Btn>)}
      </div>
      {fresh?.token && <Notice kind="ok" title="Copia pronta" action={<Btn kind="sm" onClick={() => download(fresh).then(() => { setFresh(null); load(); }).catch((e) => setErr(String(e.message || e)))}>Scarica</Btn>}>
        Il file si può scaricare una sola volta, entro il {day(fresh.expires_at)}. Contiene dati personali: conservalo con cura.</Notice>}

      <h2 className="m-title" style={{ marginTop: 18 }}>Le tue richieste</h2>
      {d.requests.length ? <div className="list-rows">{d.requests.map((r) => <div className="list-row" key={r.id}>
        <div><b>{KIND[r.kind] || r.kind}</b><small>{d.subjects.find((s) => s.id === r.subject_id)?.label || ""} · ricevuta il {day(r.received_at)}, risposta entro il {day(r.due_at)}</small></div>
        <Tag tone={(STATUS[r.status] || [r.status, "plain"])[1]}>{(STATUS[r.status] || [r.status])[0]}</Tag></div>)}</div>
        : <p className="muted">Nessuna richiesta.</p>}
    </>}
    <Modal open={!!ask} onClose={() => setAsk("")} labelledBy="md-ask"><div className="modal-body">
      <h2 id="md-ask">Chiedi {KIND[ask]?.toLowerCase()}</h2>
      <Field label="Dati di" id="md-who"><p id="md-who">{subject?.label}</p></Field>
      <p className="muted">{ask === "ERASURE" ? "Il centro cancella i dati non più necessari; alcuni (per esempio pagamenti e registri) vanno conservati per legge e te lo indicherà." : "Il centro ti contatta per i dettagli e risponde entro un mese."}</p>
    </div><div className="modal-foot"><button type="button" className="pill-btn ghost" onClick={() => setAsk("")}>Annulla</button><Btn kind="primary" disabled={busy} onClick={sendRequest}>Invia la richiesta</Btn></div></Modal>
    <Modal open={!!decline} onClose={() => setDecline("")} labelledBy="md-decline"><div className="modal-body">
      <h2 id="md-decline">Chiudere la delega?</h2>
      <p>Il genitore non vedrà più lezioni, presenze e disponibilità e non potrà chiedere cambi. Potrai chiedere al centro di riattivarla.</p>
    </div><div className="modal-foot"><button type="button" className="pill-btn ghost" onClick={() => setDecline("")}>Annulla</button><Btn kind="primary" disabled={busy} onClick={() => reconfirm(decline, false)}>Chiudi la delega</Btn></div></Modal>
  </section>;
}
