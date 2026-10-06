/** P1 «Utenti e ruoli» (T3): gestori e tutor del centro, inviti, revoca ruolo, reset MFA, chiusura sessioni. */
import { FormEvent, useState } from "react";
import { Btn, Empty, Notice, PageHead, Skeleton, Tag } from "../ui/core";
import { Field, Input } from "../ui/controls";
import { Modal, useToast } from "../ui/layers";
import { ErrorState } from "../ui/states";
import { useData } from "../app/data";
import { INVITE_STATUS, send, useList, writeError } from "./registry";

type User = { id: string; name: string; email: string; is_active: boolean; roles: string[]; mfa_required: boolean; last_login: string | null };
type Inv = { id: string; email: string; role: string; status: string; expires_at: string | null };
type Act = { kind: "invite" } | { kind: "revoke"; user: User; role: string } | { kind: "mfa"; user: User } | { kind: "sessions"; user: User };
const ROLE: Record<string, string> = { CENTER: "Gestore", TUTOR: "Tutor" };

export default function Utenti() {
  const d = useData();
  const users = useList<User>("/identity/center-users"), invs = useList<Inv>("/identity/center-invitations?status=SENT");
  const [act, setAct] = useState<Act | null>(null);
  const toast = useToast();
  const me = (d.me as { id?: string }).id;
  return <section className="module planner" aria-labelledby="h-ut">
    <PageHead id="h-ut" title="Utenti e ruoli">
      <Btn kind="primary" isle="plus" onClick={() => setAct({ kind: "invite" })}>Invita un gestore</Btn>
    </PageHead>
    <Notice kind="info">I tutor si invitano dalla loro scheda in <b>Tutor</b>, così l’account resta collegato alle competenze e alle lezioni.</Notice>
    <div className="list-wrap" style={{ marginTop: 12 }}>
      {users.error ? <ErrorState error={users.error} onRetry={users.reload} /> : !users.data ? <Skeleton />
        : users.data.length ? <table className="list"><thead><tr><th scope="col">Persona</th><th scope="col">Ruoli</th><th scope="col" className="hide-m">Ultimo accesso</th><th scope="col"><span className="sr">Azioni</span></th></tr></thead>
          <tbody>{users.data.map((u) => <tr key={u.id}>
            <td><b>{u.name || u.email}</b><br /><small className="muted">{u.email}</small></td>
            <td>{u.roles.map((r) => <Tag key={r} tone={r === "CENTER" ? "violet" : "blue"}>{ROLE[r] || r}</Tag>)}{!u.is_active && <Tag>Disattivato</Tag>}</td>
            <td className="hide-m">{u.last_login ? new Date(u.last_login).toLocaleString("it-IT") : <span className="muted">Mai</span>}</td>
            <td><span className="toolbar">
              {u.roles.map((r) => (u.id !== me || r !== "CENTER") && <Btn key={r} kind="ghost" onClick={() => setAct({ kind: "revoke", user: u, role: r })}>Revoca {ROLE[r]?.toLowerCase()}</Btn>)}
              {u.id !== me && <Btn kind="ghost" onClick={() => setAct({ kind: "mfa", user: u })}>Azzera MFA</Btn>}
              <Btn kind="ghost" onClick={() => setAct({ kind: "sessions", user: u })}>Chiudi sessioni</Btn>
            </span></td></tr>)}</tbody></table>
        : <Empty title="Nessun utente del centro" />}
    </div>
    <h3>Inviti in attesa</h3>
    {invs.error ? <ErrorState error={invs.error} onRetry={invs.reload} /> : !invs.data ? <Skeleton rows={2} /> : invs.data.length ? <div className="mini-list">{invs.data.map((i) => <div key={i.id} className="mini"><span><b>{i.email}</b><small>{ROLE[i.role]} · {INVITE_STATUS[i.status]}{i.expires_at ? " · scade il " + new Date(i.expires_at).toLocaleDateString("it-IT") : ""}</small></span></div>)}</div> : <p className="muted">Nessun invito in attesa.</p>}
    {act && <ActModal act={act} onClose={() => setAct(null)} onDone={(m) => { setAct(null); toast(m); users.reload(); invs.reload(); }} />}
  </section>;
}

function ActModal({ act, onClose, onDone }: { act: Act; onClose: () => void; onDone: (m: string) => void }) {
  const [email, setEmail] = useState(""), [err, setErr] = useState(""), [busy, setBusy] = useState(false);
  const title = { invite: "Invita un gestore", revoke: "Revoca ruolo", mfa: "Azzera la MFA", sessions: "Chiudi tutte le sessioni" }[act.kind];
  async function submit(e: FormEvent) {
    e.preventDefault(); setBusy(true); setErr("");
    try {
      if (act.kind === "invite") { await send("POST", "/identity/center-invitations", { email, role: "CENTER" }); onDone("Invito inviato"); }
      else if (act.kind === "revoke") { await send("POST", `/identity/center-users/${act.user.id}/revoke-role`, { role: act.role }); onDone("Ruolo revocato"); }
      else if (act.kind === "mfa") { await send("POST", `/identity/accounts/${act.user.id}/mfa/reset`, {}); onDone("MFA azzerata: la persona la riconfigurerà al prossimo accesso"); }
      else { await send("POST", `/identity/accounts/${act.user.id}/sessions/revoke-all`, {}); onDone("Sessioni chiuse"); }
    } catch (e2) { setErr(writeError(e2)); }
    setBusy(false);
  }
  return <Modal open onClose={onClose} labelledBy="m-ut"><form className="modal-body" onSubmit={submit}>
    <h2 id="m-ut">{title}</h2>
    {err && <Notice kind="bad">{err}</Notice>}
    {act.kind === "invite" && <><Field label="Email" id="u-email"><Input id="u-email" type="email" required value={email} onChange={(e) => setEmail(e.target.value)} /></Field></>}
    {act.kind === "revoke" && <p>{act.user.email} perderà subito il ruolo di {ROLE[act.role]?.toLowerCase()}. Deve sempre restare almeno un gestore.</p>}
    {act.kind === "mfa" && <p>Le sessioni di {act.user.email} verranno chiuse e dovrà configurare di nuovo l’app di autenticazione.</p>}
    {act.kind === "sessions" && <p>{act.user.email} verrà disconnesso da tutti i dispositivi.</p>}
    <div className="modal-foot"><Btn type="button" kind="ghost" onClick={onClose}>Annulla</Btn><Btn type="submit" kind={act.kind === "invite" ? "primary" : "danger"} disabled={busy}>Conferma</Btn></div>
  </form></Modal>;
}
