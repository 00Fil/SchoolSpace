import { hm, parseHm, rome, romeISO } from "../format";
import { Check, Combo, ComboItem, DateField, Field, Input, SegCtl, Wheel } from "../ui/controls";

/** Moduli strutturati per la configurazione di prova: il JSON resta solo come modalità avanzata. */
type Ref = "tutor" | "student" | "subject" | "resource";
export type F = { k: string; label: string; t: "text" | "int" | "num" | "bool" | "date" | "time" | "dt" | "enum" | "ref" | "list"; opts?: [string, string][]; ref?: Ref; nullable?: boolean; hint?: string; min?: number };
const MODE: [string, string][] = [["IN_PERSON", "In presenza"], ["ONLINE", "Online"]];
const LOC: [string, string][] = [["ON_SITE", "In sede"], ["REMOTE", "Da remoto"]];
const WD: [string, string][] = ["Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom"].map((l, i) => [String(i), l]);
const WHO: F[] = [{ k: "student", label: "Studente", t: "ref", ref: "student", nullable: true, hint: "Indica uno studente oppure un tutor, non entrambi." }, { k: "tutor", label: "Tutor", t: "ref", ref: "tutor", nullable: true }];
export const SCHEMA: Record<string, F[]> = {
  "planning-policies": [
    { k: "name", label: "Nome", t: "text" },
    { k: "budget_seconds", label: "Tempo massimo di ricerca (secondi)", t: "num", min: 1 },
    { k: "partial_week_rule", label: "Settimana parziale", t: "enum", opts: [["BLOCK", "Blocca"], ["INCLUDE_ACTIVE_DATES", "Date attive"]] },
    { k: "online_onsite_requires_space", label: "Online dalla sede richiede uno spazio", t: "bool" },
    { k: "video_channels_required", label: "Canale video obbligatorio online", t: "bool" },
    { k: "approved_for_exploration", label: "Approvata per l’esplorazione (non è approvazione G1)", t: "bool" },
    { k: "unsupported_constraints", label: "Vincoli non supportati", t: "list", hint: "Separati da virgola. Se presenti, la generazione si blocca." },
  ],
  "tutor-skills": [
    { k: "tutor", label: "Tutor", t: "ref", ref: "tutor" }, { k: "subject", label: "Materia", t: "ref", ref: "subject" },
    { k: "level", label: "Livello", t: "text", hint: "Deve coincidere con il livello del percorso." }, { k: "mode", label: "Modalità", t: "enum", opts: MODE },
    { k: "valid_from", label: "Valida dal", t: "date" }, { k: "valid_until", label: "Valida fino al", t: "date" }, { k: "approved", label: "Approvata", t: "bool" },
  ],
  "tutor-operating-policies": [
    { k: "tutor", label: "Tutor", t: "ref", ref: "tutor" },
    { k: "daily_limit_minutes", label: "Limite giornaliero (minuti)", t: "int", min: 0 }, { k: "weekly_limit_minutes", label: "Limite settimanale (minuti)", t: "int", min: 0 },
    { k: "pause_minutes", label: "Pausa tra lezioni (minuti)", t: "int", min: 0 },
    { k: "site_to_remote_minutes", label: "Dalla sede a remoto (minuti)", t: "int", min: 0 }, { k: "remote_to_site_minutes", label: "Da remoto alla sede (minuti)", t: "int", min: 0 },
  ],
  "service-windows": [
    { k: "weekday", label: "Giorno", t: "enum", opts: WD }, { k: "mode", label: "Modalità", t: "enum", opts: MODE }, { k: "location", label: "Luogo", t: "enum", opts: LOC },
    { k: "start_time", label: "Apertura", t: "time" }, { k: "end_time", label: "Chiusura", t: "time" },
    { k: "period_start", label: "Dal", t: "date" }, { k: "period_end", label: "Al", t: "date" },
    { k: "resource", label: "Solo per la risorsa", t: "ref", ref: "resource", nullable: true, hint: "Vuoto: vale per tutto il centro." },
  ],
  "resource-timings": [
    { k: "resource", label: "Risorsa", t: "ref", ref: "resource" }, { k: "buffer_minutes", label: "Margine dopo l’uso (minuti)", t: "int", min: 0 },
    { k: "inherit_service_windows", label: "Segue le aperture del centro", t: "bool" },
  ],
  closures: [
    { k: "start_at", label: "Inizio", t: "dt" }, { k: "end_at", label: "Fine", t: "dt" },
    { k: "mode", label: "Vale per", t: "enum", opts: [["ALL", "Tutte"], ...MODE] },
    { k: "resource", label: "Solo per la risorsa", t: "ref", ref: "resource", nullable: true }, { k: "reason", label: "Descrizione", t: "text", hint: "Facoltativa, senza dati personali.", nullable: true },
  ],
  "availability-declarations": [...WHO, { k: "state", label: "Stato dei dati", t: "enum", opts: [["APPROVED", "Approvati"], ["DECLARED_NONE", "Nessuna disponibilità"], ["UNKNOWN", "Incompleti"]] }],
  "availability-exceptions": [
    ...WHO, { k: "kind", label: "Tipo", t: "enum", opts: [["ADD_AVAILABLE", "Aggiunge"], ["REMOVE_AVAILABLE", "Toglie"]] },
    { k: "start_at", label: "Inizio", t: "dt" }, { k: "end_at", label: "Fine", t: "dt" },
    { k: "mode", label: "Modalità", t: "enum", opts: MODE }, { k: "location", label: "Luogo", t: "enum", opts: LOC },
  ],
  "availability-conflicts": [...WHO, { k: "reason", label: "Indicazione da verificare", t: "text", hint: "Senza dati personali." }, { k: "open", label: "Ancora aperto", t: "bool" }],
};
export type Refs = Record<Ref, ComboItem[]>;
const TIMES = Array.from({ length: 97 }, (_, i) => ({ v: i * 15, label: i === 96 ? "24:00" : hm(i * 15) }));
const snap = (m: number) => Math.min(1440, Math.max(0, Math.round(m / 15) * 15));

/** Errori di compilazione lato client (il server resta l’autorità). */
export function missing(kind: string, v: Record<string, unknown>) {
  return (SCHEMA[kind] || []).filter((f) => !f.nullable && f.t !== "bool" && f.t !== "list" && (v[f.k] === undefined || v[f.k] === null || v[f.k] === "" || v[f.k] === "UUID")).map((f) => f.k);
}

export function ConfigForm({ kind, value, onChange, refs, bad }: { kind: string; value: Record<string, unknown>; onChange: (v: Record<string, unknown>) => void; refs: Refs; bad: string[] }) {
  const set = (k: string, x: unknown) => onChange({ ...value, [k]: x });
  return <div className="cfg-form">{(SCHEMA[kind] || []).map((f) => {
    const id = `cf-${f.k}`, v = value[f.k], err = bad.includes(f.k) ? "Campo obbligatorio" : undefined;
    if (f.t === "bool") return <div key={f.k} className="cfg-wide"><Check checked={!!v} onChange={(x) => set(f.k, x)}>{f.label}</Check></div>;
    let control;
    if (f.t === "enum") control = <div className="seg-scroll"><SegCtl label={f.label} value={String(v ?? f.opts![0][0])} options={f.opts!} onChange={(x) => set(f.k, f.k === "weekday" ? Number(x) : x)} /></div>;
    else if (f.t === "ref") {
      const items = refs[f.ref!] || [], cur = items.find((x) => x.id === v) || null;
      control = <Combo id={id} value={cur} items={items} invalid={!!err} placeholder={f.nullable ? "Nessuno (facoltativo)" : "Cerca per nome…"} onPick={(x) => set(f.k, x ? x.id : f.nullable ? null : "")} />;
    } else if (f.t === "date") control = <DateField id={id} label={f.label} value={typeof v === "string" ? v.slice(0, 10) : ""} onChange={(x) => set(f.k, x)} />;
    else if (f.t === "time") {
      const m = typeof v === "string" && v ? snap(parseHm(v)) : 600;
      control = <div className="wheels one"><div className="wheel-col"><Wheel label={f.label} items={TIMES} value={m} onChange={(x) => set(f.k, x === 1440 ? "23:59" : hm(x))} /></div></div>;
    } else if (f.t === "dt") {
      const r = typeof v === "string" && v ? rome(v) : null, date = r?.date || "", m = r ? snap(r.min) : 600;
      control = <div className="cfg-dt"><DateField id={id} label={`${f.label}, giorno`} value={date} onChange={(x) => set(f.k, romeISO(x, m))} />
        <div className="wheels one"><div className="wheel-col"><Wheel label={`${f.label}, ora`} items={TIMES.slice(0, 96)} value={Math.min(m, 1425)} onChange={(x) => date && set(f.k, romeISO(date, x))} /></div></div></div>;
    } else if (f.t === "list") control = <Input id={id} value={Array.isArray(v) ? v.join(", ") : ""} onChange={(e) => set(f.k, e.target.value.split(",").map((s) => s.trim()).filter(Boolean))} />;
    else control = <Input id={id} inputMode={f.t === "text" ? undefined : "decimal"} aria-invalid={!!err || undefined} value={v === undefined || v === null ? "" : String(v)} maxLength={f.t === "text" ? 200 : 8}
      onChange={(e) => { const s = e.target.value; set(f.k, f.t === "text" ? s : s === "" ? "" : f.t === "int" ? (Number.isInteger(+s) ? +s : s) : (Number.isFinite(+s) ? +s : s)); }} />;
    const wide = f.t === "dt" || f.t === "enum";
    const labelled = f.t !== "time" && f.t !== "enum";
    return <div key={f.k} className={wide ? "cfg-wide" : ""}><Field label={f.label} id={labelled ? id : undefined} hint={f.hint} error={err}>{control}</Field></div>;
  })}</div>;
}
