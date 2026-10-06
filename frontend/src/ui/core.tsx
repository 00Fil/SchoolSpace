import { ReactNode, useState } from "react";
import sprite from "../lumen/icons.svg?raw";
import { initials, tone } from "../format";
import { stateOf, Tone } from "../messages";
import { TECH_ADMIN } from "../env";

export type IconName = "home" | "cal" | "users" | "user" | "book" | "clip" | "chart" | "wallet" | "spark" | "gear" | "search" | "bell" | "plus" | "filter" | "arrow" | "chev" | "left" | "right" | "x" | "check" | "clock" | "send" | "clipf" | "mic" | "sun" | "moon" | "download" | "move" | "qr" | "mail" | "phone" | "video" | "pin";
export const Sprite = () => <div hidden dangerouslySetInnerHTML={{ __html: sprite }} />;
export const Icon = ({ n, size }: { n: IconName; size?: number }) => (
  <svg className="i" aria-hidden="true" style={size ? { width: size, height: size } : undefined}><use href={"#" + n} /></svg>
);
export const Avatar = ({ name, size, k }: { name: string; size?: number; k?: string }) => (
  <span className={`av t${tone(k || name)}`} aria-hidden="true" style={size ? { width: size, height: size, fontSize: Math.round(size * 0.36) } : undefined}>{initials(name)}</span>
);
export function Stack({ names, max = 3 }: { names: string[]; max?: number }) {
  return <span className="stack">{names.slice(0, max).map((n) => <Avatar key={n} name={n} />)}{names.length > max && <span className="av more" aria-hidden="true">+{names.length - max}</span>}</span>;
}
export const Tag = ({ tone: t = "plain", children }: { tone?: Tone; children: ReactNode }) => <span className={"tag " + t}>{children}</span>;
export function State({ s }: { s: string }) { const [label, t] = stateOf(s); return <Tag tone={t}>{label}</Tag>; }
export const Empty = ({ title, children }: { title: string; children?: ReactNode }) => <div className="empty"><b>{title}</b>{children}</div>;
export function Stat({ label, value, note }: { label: string; value: ReactNode; note?: ReactNode }) {
  return <div className="stat"><small>{label}</small><b>{value}</b>{note && <div className="note">{note}</div>}</div>;
}
/** Dettagli tecnici (codici, ID, hash, revisioni): solo per l'amministrazione tecnica, mai in produzione. */
export function Tech({ children, label = "Dettagli tecnici" }: { children: ReactNode; label?: string }) {
  const [open, setOpen] = useState(false);
  if (!TECH_ADMIN) return null;
  return <div className={"tech" + (open ? " open" : "")}>
    <button type="button" className="tech-btn" aria-expanded={open} onClick={() => setOpen(!open)}>{label}<Icon n="chev" size={16} /></button>
    {open && <div className="tech-body reveal">{children}</div>}
  </div>;
}
export function Notice({ kind = "info", title, children, action }: { kind?: "info" | "ok" | "warn" | "bad"; title?: ReactNode; children?: ReactNode; action?: ReactNode }) {
  return <div className={"notice " + kind} role={kind === "bad" ? "alert" : "status"}>
    <div>{title && <b>{title}</b>}{children}</div>{action}
  </div>;
}
export function PageHead({ title, lead, id, children }: { title: string; lead?: ReactNode; id: string; children?: ReactNode }) {
  return <div className="page-head"><div><h1 className="h-display" id={id}>{title}</h1>{lead && <p>{lead}</p>}</div>{children && <div className="toolbar">{children}</div>}</div>;
}
export function Skeleton({ rows = 4 }: { rows?: number }) {
  return <div className="skel-wrap" role="status" aria-label="Caricamento in corso">{Array.from({ length: rows }, (_, i) => <span key={i} className="skel" style={{ animationDelay: i * 90 + "ms" }} />)}</div>;
}
export const Btn = ({ kind = "raised", icon, isle, children, ...p }: React.ButtonHTMLAttributes<HTMLButtonElement> & { kind?: string; icon?: IconName; isle?: IconName }) => (
  <button type="button" {...p} className={`pill-btn ${kind}${isle ? " island" : ""} ${p.className || ""}`.trim()}>
    {icon && <Icon n={icon} />}{children}{isle && <span className="isle"><Icon n={isle} /></span>}
  </button>
);
export const Circle = ({ icon, label, kind = "raised", ...p }: React.ButtonHTMLAttributes<HTMLButtonElement> & { icon: IconName; label: string; kind?: string }) => (
  <button type="button" aria-label={label} {...p} className={`circle ${kind} ${p.className || ""}`.trim()}><Icon n={icon} /></button>
);
