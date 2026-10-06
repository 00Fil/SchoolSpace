/** Famiglie v0.9.5: tipi, stati leggibili e utilità condivise da elenco, pagina e moduli. */
import type { Tone } from "../../messages";

export type Invitation = { id: string; email: string; student: string | null; family: string | null; status: string; relationship: string | null; relation_verified_at: string | null; expires_at: string | null; accepted_at: string | null; send_count: number; version: number };
export type Link = { id: string; student: string; guardian_name: string; guardian_email: string; relationship: string | null; verified: boolean; active: boolean; can_manage_availability: boolean; version: number };
export type Perms = { can_manage_availability: boolean; can_receive_notifications: boolean; can_request_changes: boolean };
export type GStatus = "ACTIVE" | "INVITED" | "TO_VERIFY" | "EXPIRED" | "NO_INVITE";
export type Guardian = {
  id: string | null; legacy: boolean; family: string; name: string; email: string; phone: string; relationship: string | null;
  permissions: Perms | null; status: GStatus; invitation: Invitation | null; invitations?: Invitation[]; account: string | null;
  students: string[]; links: Link[]; version: number | null;
};
export type Child = { id: string; family: string; display_name: string; level: string; active: boolean; has_account: boolean; birth_date: string | null; version: number };
export type Family = { id: string; reference: string; contact_name: string; contact_email: string; contact_phone: string; students: string[]; children: Child[]; guardians: Guardian[]; version: number };

export const RELS: [string, string][] = [["PARENT", "Genitore"], ["LEGAL_GUARDIAN", "Tutore legale"], ["DELEGATE", "Delegato"]];
export const relText = (r: string | null) => RELS.find((x) => x[0] === r)?.[1] || "Genitore";

/** Stato del genitore/tutore in parole: etichetta, tono pieno e cosa fare. */
export const G_STATUS: Record<GStatus, [string, Tone, string]> = {
  ACTIVE: ["Accesso attivo", "green", "Entra nel portale e vede i figli collegati."],
  INVITED: ["Invito inviato", "blue", "Non ha ancora attivato l’accesso: puoi mostrargli il QR code."],
  TO_VERIFY: ["Da verificare", "amber", "Conferma la relazione con il figlio per inviare l’invito."],
  EXPIRED: ["Invito scaduto", "red", "Invia di nuovo l’invito."],
  NO_INVITE: ["Senza invito", "red", "Crea un nuovo invito per dargli l’accesso."],
};

export const guardianName = (g: Guardian) => g.name || g.email;
export const guardianKey = (g: Guardian) => g.id || "legacy:" + g.email;

/** Lo stato più urgente della famiglia, per il bollino della scheda. */
export function familyState(f: Family): [string, Tone] {
  const gs = f.guardians;
  if (!gs.length) return ["Manca un genitore", "red"];
  if (gs.some((g) => g.status === "TO_VERIFY")) return ["Da verificare", "amber"];
  if (gs.some((g) => g.status === "EXPIRED" || g.status === "NO_INVITE")) return ["Invito scaduto", "red"];
  if (!gs.some((g) => g.status === "ACTIVE")) return ["Invito inviato", "blue"];
  if (!f.children.length) return ["Nessun figlio", "amber"];
  return ["Tutto attivo", "green"];
}

export const surnameOf = (name: string) => { const p = name.trim().split(/\s+/); return p.length > 1 ? p[p.length - 1] : ""; };
