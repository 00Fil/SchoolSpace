import { ReactNode, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { get, post } from "../api/client";
import type { S } from "../api/schema.gen";
import { isMac, plural } from "../format";
import { Avatar, Icon, IconName, Tag } from "../ui/core";
import { layersOpen, Modal, Pop, useToast } from "../ui/layers";
import { getPrefs, resolved, setTheme, usePrefs, viewTransition } from "../ui/prefs";
import { go, useRoute } from "../ui/route";
import { useData } from "./data";
import { ENV_LABEL, TECH_ADMIN } from "../env";
import { loadPending, Pending } from "../portal/data";
import { LessonPrefill, Req, RequestModal } from "../screens/requestForms";
import { ReviewModal } from "../screens/RequestReview";

/** «Nuova lezione» da qualunque punto (barra in alto, scorciatoia N, trascinamento in
 *  agenda): apre il modulo originale delle richieste, eventualmente precompilato. */
export const openNewLesson = (prefill?: LessonPrefill) => dispatchEvent(new CustomEvent("new-lesson", { detail: prefill || null }));
/** Apre la verifica delle lezioni inserite dal motore per una richiesta. */
export const openReview = (id: string) => dispatchEvent(new CustomEvent("request-review", { detail: id }));
/** Apre la verifica se la richiesta salvata/approvata è in attesa di verifica. */
export const reviewIfNeeded = (r: Pick<Req, "id" | "planning_state">) => { if (r.planning_state === "REVIEW") openReview(r.id); return r.planning_state === "REVIEW"; };
/** Dopo una modifica al calendario fatta fuori dall'agenda (es. lezione creata). */
export const calendarChanged = () => dispatchEvent(new Event("calendar:changed"));

/** Modulo «Nuova lezione» + verifica: salvata la richiesta, il motore la colloca e si
 *  apre subito l'elenco delle lezioni da verificare. */
function LessonHost() {
  const toast = useToast(), d = useData();
  const [open, setOpen] = useState(false), [prefill, setPrefill] = useState<LessonPrefill | null>(null), [review, setReview] = useState<string | null>(null);
  useEffect(() => {
    const f = (e: Event) => { setPrefill((e as CustomEvent<LessonPrefill | null>).detail); setOpen(true); };
    const r = (e: Event) => setReview((e as CustomEvent<string>).detail);
    addEventListener("new-lesson", f); addEventListener("request-review", r);
    return () => { removeEventListener("new-lesson", f); removeEventListener("request-review", r); };
  }, []);
  return <>
    <RequestModal open={open} prefill={prefill} onClose={() => setOpen(false)}
      onSaved={async (req) => { setOpen(false); await d.refresh(); if (req.planning_state === "REVIEW") setReview(req.id); else toast("Richiesta salvata."); }} />
    <ReviewModal id={review} onClose={() => { setReview(null); void d.refresh(); }}
      onDone={(msg, date) => { setReview(null); calendarChanged(); toast(msg, date ? { action: "Apri l’agenda", onAction: () => go("agenda", { d: date }) } : undefined); }} />
  </>;
}

export type Section = { key: string; label: string; icon: IconName; center?: boolean; portal?: boolean; title: string; roles?: string[]; tech?: boolean };
export { TECH_ADMIN };
/** Tutte le schermate raggiungibili. Il menu non le elenca una per una: le raggruppa in aree (HUBS). */
export const SECTIONS: Section[] = [
  { key: "panoramica", label: "Oggi", icon: "home", title: "Panoramica" },
  { key: "statistiche", label: "Statistiche", icon: "chart", center: true, title: "Statistiche" },
  { key: "agenda", label: "Agenda", icon: "cal", center: true, title: "Agenda del centro" },
  { key: "pianificazione", label: "Pianificazione", icon: "spark", center: true, title: "Pianificazione mensile" },
  { key: "pianificazione-avanzata", label: "Motore settimanale", icon: "spark", center: true, title: "Pianificazione settimanale (tecnica)", tech: true },
  { key: "proposte", label: "Calcolo semplice", icon: "spark", center: true, title: "Genera l’orario", tech: true },
  { key: "operativita", label: "Da gestire", icon: "bell", center: true, title: "Da gestire" },
  // Per il centro i figli si gestiscono dentro Famiglie (v0.9.5); i portali tengono «Studenti».
  { key: "studenti", label: "Studenti", icon: "users", portal: true, title: "Studenti" },
  { key: "anagrafica", label: "Famiglie", icon: "users", center: true, title: "Famiglie" },
  { key: "tutor", label: "Tutor", icon: "user", center: true, title: "Tutor" },
  { key: "impegni", label: "Impegni", icon: "clock", title: "Impegni" },
  { key: "disponibilita", label: "Disponibilità", icon: "clock", title: "Disponibilità", tech: true },
  { key: "percorsi", label: "Percorsi", icon: "clip", title: "Percorsi" },
  { key: "richieste", label: "Richieste didattiche", icon: "book", title: "Richieste didattiche" },
  { key: "materie", label: "Materie", icon: "book", center: true, title: "Materie" },
  { key: "apertura", label: "Orari e chiusure", icon: "clock", center: true, title: "Orari e chiusure" },
  { key: "configurazione", label: "Anno e aule", icon: "gear", center: true, title: "Anno scolastico e aule" },
  { key: "utenti", label: "Utenti e ruoli", icon: "gear", center: true, title: "Utenti e ruoli" },
  { key: "privacy", label: "Privacy", icon: "check", center: true, title: "Privacy" },
  { key: "laboratorio", label: "Laboratorio", icon: "spark", center: true, title: "Laboratorio", tech: true },
  { key: "decisioni", label: "Decisioni", icon: "check", center: true, title: "Decisioni di progetto", tech: true },
  { key: "settimana", label: "Calendario", icon: "cal", portal: true, title: "Le mie lezioni" },
  { key: "cambi", label: "Richieste di cambio", icon: "send", portal: true, title: "Richieste di cambio" },
  { key: "conferme", label: "Da confermare", icon: "check", portal: true, title: "Lezioni da confermare" },
  { key: "orari", label: "Orari da confermare", icon: "check", portal: true, roles: ["TUTOR"], title: "Orari da confermare" },
  { key: "presenze", label: "Presenze", icon: "clipf", portal: true, roles: ["TUTOR"], title: "Presenze" },
  { key: "profilo", label: "Fasce e assenze", icon: "user", portal: true, title: "Disponibilità e assenze" },
  { key: "dati", label: "I miei dati", icon: "user", portal: true, title: "I miei dati" },
];
const SETTINGS: Section = { key: "impostazioni", label: "Impostazioni", icon: "gear", title: "Impostazioni" };
/** Sezioni per ruolo: il centro vede la gestione, i portali le proprie viste. */
export const sectionsFor = (center: boolean, roles: string[] = []) => SECTIONS
  .filter((s) => (center ? !s.portal : !s.center) && (!s.tech || TECH_ADMIN) && (!s.roles || s.roles.some((r) => roles.includes(r))))
  .map((s) => (s.key === "profilo" ? (roles.includes("GUARDIAN") ? { ...s, label: "Figli", title: "Figli" } : { ...s, label: "Riepilogo" })
    : s.key === "disponibilita" && !center ? { ...s, label: "Fasce settimanali" }
    : s.key === "richieste" && !center ? { ...s, label: "Richieste di lezioni", title: "Richieste di lezioni" } : s));

/** Aree del menu: ogni voce raccoglie schermate affini, mostrate come schede in cima alla pagina. */
export type Hub = { key: string; label: string; icon: IconName; tabs: string[]; center?: boolean; portal?: boolean };
const HUBS: Hub[] = [
  { key: "home", label: "Panoramica", icon: "home", tabs: ["panoramica", "statistiche"] },
  // Centro
  { key: "calendario", label: "Calendario", icon: "cal", center: true, tabs: ["agenda", "pianificazione", "pianificazione-avanzata", "proposte"] },
  { key: "gestire", label: "Da gestire", icon: "bell", center: true, tabs: ["operativita"] },
  { key: "persone", label: "Persone", icon: "users", center: true, tabs: ["anagrafica", "tutor", "impegni", "disponibilita"] },
  { key: "didattica", label: "Didattica", icon: "book", center: true, tabs: ["richieste", "percorsi", "materie"] },
  { key: "centro", label: "Centro", icon: "gear", center: true, tabs: ["apertura", "configurazione", "utenti", "privacy", "laboratorio", "decisioni"] },
  // Portali (famiglie, studenti, tutor)
  { key: "lezioni", label: "Lezioni", icon: "cal", portal: true, tabs: ["settimana", "conferme", "cambi", "orari", "presenze"] },
  { key: "disp", label: "Impegni", icon: "clock", portal: true, tabs: ["impegni", "profilo", "disponibilita"] },
  { key: "studio", label: "Studio", icon: "book", portal: true, tabs: ["studenti", "richieste", "percorsi"] },
  { key: "dati", label: "I miei dati", icon: "user", portal: true, tabs: ["dati"] },
];
export type HubView = Hub & { sections: Section[] };
/** Aree visibili al ruolo, con le sole schede autorizzate; le aree vuote spariscono. */
export function hubsFor(center: boolean, roles: string[] = []): HubView[] {
  const secs = sectionsFor(center, roles);
  return HUBS.filter((h) => (center ? !h.portal : !h.center))
    .map((h) => ({ ...h, sections: h.tabs.map((k) => secs.find((s) => s.key === k)).filter((s): s is Section => !!s) }))
    .filter((h) => h.sections.length > 0);
}
export const hubOf = (hubs: HubView[], key: string) => hubs.find((h) => h.sections.some((s) => s.key === key));

function usePuck(nav: React.RefObject<HTMLElement | null>, axis: "x" | "y", dep: string) {
  useLayoutEffect(() => {
    const place = () => {
      const n = nav.current; if (!n) return;
      const puck = n.querySelector<HTMLElement>(".puck"), a = n.querySelector<HTMLElement>("[aria-current]");
      if (!puck) return;
      if (!a) { puck.style.opacity = "0"; return; }
      puck.style.opacity = "1";
      puck.style.transform = axis === "y" ? `translateY(${a.offsetTop}px)` : `translateX(${a.offsetLeft}px)`;
    };
    // le voci del menu dipendono dai dati (ruoli, contatori): riposiziona quando cambiano o si ridimensionano
    place(); const raf = requestAnimationFrame(place); addEventListener("resize", place);
    const n = nav.current, ro = typeof ResizeObserver !== "undefined" && n ? new ResizeObserver(place) : null, mo = n ? new MutationObserver(place) : null;
    if (n) { ro?.observe(n); mo?.observe(n, { subtree: true, childList: true, attributes: true, attributeFilter: ["aria-current"] }); }
    document.fonts?.ready.then(place).catch(() => undefined);
    return () => { cancelAnimationFrame(raf); removeEventListener("resize", place); ro?.disconnect(); mo?.disconnect(); };
  }, [dep, axis, nav]);
}

type Note = { id: string; title: string; sub: string; who: string; run: () => void };
/** Cose da fare nei portali (conferme, presenze, deleghe): vivono nella campanella, non in dashboard. */
function usePortalTodo(on: boolean, roles: string[]) {
  const [s, set] = useState<{ p: Pending | null; o: S.PortalOverview | null }>({ p: null, o: null });
  useEffect(() => {
    if (!on) return;
    let live = true;
    const load = () => Promise.all([loadPending(roles).catch(() => null), get("/portal/overview", { quiet: true }).catch(() => null)]).then(([p, o]) => live && set({ p, o }));
    load(); const t = setInterval(() => { if (document.visibilityState === "visible") load(); }, 120000);
    return () => { live = false; clearInterval(t); };
  }, [on, roles.join(",")]); // eslint-disable-line react-hooks/exhaustive-deps
  return s;
}
function useNotes(): Note[] {
  const d = useData();
  const pt = usePortalTodo(!d.center, d.me.roles);
  return useMemo(() => {
    const n: Note[] = [];
    if (!d.center) {
      const { p, o } = pt;
      if (p?.confirm) n.push({ id: "conf-" + p.confirm, who: "!", title: plural(p.confirm, "modifica da confermare", "modifiche da confermare"), sub: "Proposte dal tutor e accolte dal centro", run: () => go("cambi") });
      if (p?.acks) n.push({ id: "acks-" + p.acks, who: "O", title: plural(p.acks, "orario da confermare", "orari da confermare"), sub: "Nuove lezioni assegnate dal centro", run: () => go("orari") });
      const att = o?.tutor?.week?.attendance_pending || 0;
      if (att) n.push({ id: "att-" + att, who: "P", title: plural(att, "presenza da registrare", "presenze da registrare"), sub: "Lezioni concluse", run: () => go("presenze") });
      for (const c of o?.children || []) if (c.reconfirmation && c.relation === "GUARDIAN") n.push({ id: "rec-" + c.student_id + c.reconfirmation, who: "R", title: `Delega da riconfermare: ${c.display_name.split(/\s+/)[0]}`, sub: `Entro il ${c.reconfirmation.split("-").reverse().join("/")}`, run: () => go("profilo", { s: c.student_id }) });
      if (o?.open_change_requests) n.push({ id: "cr-" + o.open_change_requests, who: "C", title: plural(o.open_change_requests, "richiesta di cambio in attesa", "richieste di cambio in attesa"), sub: "Il centro ti risponderà con una notifica", run: () => go("cambi") });
    }
    const drafts = d.rules.filter((r) => r.status === "DRAFT").length;
    if (drafts) n.push({ id: "drafts-" + drafts, who: "D", title: d.center ? `${plural(drafts, "disponibilità", "disponibilità")} da approvare` : `${plural(drafts, "disponibilità", "disponibilità")} in attesa del centro`, sub: d.center ? "Verificale prima di generare una proposta" : "Il centro le verificherà prima di usarle", run: () => go("disponibilita", { f: "DRAFT" }) });
    const open = d.decisions.filter((x) => x.status === "OPEN").length;
    if (open && TECH_ADMIN) n.push({ id: "dec-" + open, who: "D?", title: `${plural(open, "decisione aperta", "decisioni aperte")}`, sub: "Bloccano l’uso operativo del gestionale", run: () => go("decisioni") });
    if (d.readiness && !d.readiness.ready) n.push({ id: "ready-" + (d.readiness.blockers?.length ?? 0), who: "!", title: "Pianificazione non ancora pronta", sub: plural((d.readiness.blockers?.length ?? 0), "requisito da completare", "requisiti da completare"), run: () => go("pianificazione") });
    return n;
  }, [d.rules, d.decisions, d.readiness, d.center, pt]);
}
/** Notifiche interne reali (s3): conteggio non lette, lettura singola e totale. */
type Notif = S.Notification;
function useInbox(open: boolean) {
  const [page, setPage] = useState<S.NotificationPage | null>(null), [err, setErr] = useState(false);
  const load = useCallback(() => get("/notifications", { quiet: true }).then((p) => { setPage(p); setErr(false); }, () => setErr(true)), []);
  useEffect(() => { load(); const t = setInterval(() => { if (document.visibilityState === "visible") load(); }, 60000); return () => clearInterval(t); }, [load]);
  useEffect(() => { if (open) load(); }, [open, load]);
  const read = async (n: Notif) => { if (n.read_at) return; await post("/notifications/{pk}/read", undefined as never, { params: { pk: n.id }, quiet: true }).catch(() => undefined); load(); };
  const readAll = async () => { await post("/notifications/read-all", undefined as never, { quiet: true }).catch(() => undefined); load(); };
  return { items: page?.results || [], unread: page?.unread_count || 0, pending: page?.pending_email_deliveries || 0, err, read, readAll, loaded: !!page };
}
const ago = (iso: string) => {
  const m = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (m < 1) return "adesso"; if (m < 60) return `${m} min fa`; const h = Math.round(m / 60); if (h < 24) return `${h} h fa`;
  return new Intl.DateTimeFormat("it-IT", { day: "numeric", month: "short", timeZone: "Europe/Rome" }).format(new Date(iso));
};
const READ = "ripetizioni-read";
const readSet = () => { try { return new Set<string>(JSON.parse(localStorage.getItem(READ) || "[]")); } catch { return new Set<string>(); } };

export default function Shell({ children }: { children: ReactNode }) {
  const d = useData(), r = useRoute(), toast = useToast(); usePrefs();
  const secs = sectionsFor(d.center, d.me.roles);
  const all = [...secs, SETTINGS];
  const cur = all.find((s) => s.key === r.name) || secs[0];
  const hubs = hubsFor(d.center, d.me.roles), hub = hubOf(hubs, cur.key);
  const rail = useRef<HTMLElement>(null), tab = useRef<HTMLElement>(null);
  usePuck(rail, "y", hub?.key || cur.key); usePuck(tab, "x", hub?.key || cur.key);
  const [cmd, setCmd] = useState(false), [bell, setBell] = useState<HTMLElement | null>(null), [meOpen, setMeOpen] = useState<HTMLElement | null>(null);
  const notes = useNotes(); const [read, setRead] = useState(readSet);
  const inbox = useInbox(!!bell);
  const unread = inbox.unread + notes.filter((n) => !read.has(n.id)).length;
  const markRead = (ids: string[]) => { const s = new Set(read); ids.forEach((i) => s.add(i)); setRead(s); localStorage.setItem(READ, JSON.stringify([...s])); };
  const prevKey = useRef(cur.key), centerRef = useRef(d.center); centerRef.current = d.center;
  useEffect(() => {
    document.title = `${cur.title} · Centro ripetizioni`;
    if (prevKey.current !== cur.key) { scrollTo({ top: 0 }); document.getElementById("main")?.focus({ preventScroll: true }); prevKey.current = cur.key; }
  }, [cur.key, cur.title]);
  useEffect(() => {
    const f = (e: KeyboardEvent) => {
      const a = document.activeElement as HTMLElement | null;
      const typing = !!a && (/INPUT|TEXTAREA|SELECT/.test(a.tagName) || a.isContentEditable);
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); if (!layersOpen()) setCmd(true); return; }
      if (typing || layersOpen() || e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === "/") { e.preventDefault(); setCmd(true); }
      else if (e.key.toLowerCase() === "n" && centerRef.current) { e.preventDefault(); openNewLesson(); }
    };
    addEventListener("keydown", f); return () => removeEventListener("keydown", f);
  }, []);
  const nav = (key: string) => (e: React.MouseEvent) => { e.preventDefault(); if (key === cur.key) return; viewTransition(() => go(key)); };
  const themeBtn = useRef<HTMLButtonElement>(null);
  const dark = resolved(getPrefs().theme) === "dark";
  const tabs = hubs.slice(0, 4);
  return <>
    <a className="skip" href="#main">Vai al contenuto</a>
    {d.center && <LessonHost />}
    <div className="frame">
      <aside className="rail" aria-label="Sezioni">
        <a className="logo raised" href="#/panoramica" onClick={nav("panoramica")} aria-label="Centro ripetizioni, panoramica"><span className="bars"><i style={{ height: 12 }} /><i style={{ height: 20 }} /><i style={{ height: 16 }} /></span></a>
        <nav ref={rail}>
          <span className="puck" aria-hidden="true" />
          {hubs.map((h) => <a key={h.key} className="circle raised tip" href={"#/" + h.sections[0].key} onClick={nav(h.sections[0].key)} data-tip={h.label} aria-label={h.label} aria-current={h.key === hub?.key ? "page" : undefined}><Icon n={h.icon} /></a>)}
        </nav>
        <a className="circle raised tip" href="#/impostazioni" onClick={nav("impostazioni")} data-tip="Impostazioni" aria-label="Impostazioni" aria-current={cur.key === "impostazioni" ? "page" : undefined}><Icon n="gear" /></a>
      </aside>
      <div className="content">
        <header className="topbar">
          <button className="search-trigger raised" onClick={() => setCmd(true)} aria-label="Cerca sezioni, studenti e azioni" aria-keyshortcuts="Control+K Meta+K"><Icon n="search" /><span>Cerca sezioni, studenti, azioni…</span><kbd>{isMac ? "⌘ K" : "Ctrl K"}</kbd></button>
          <span className="spacer" />
          <div className="tb-group">
            {ENV_LABEL && <span className="env-tag"><Tag tone="amber">{ENV_LABEL}</Tag></span>}
            {d.center && <button className="pill-btn raised island cta" onClick={() => openNewLesson()} aria-label="Nuova lezione" aria-keyshortcuts="N"><span className="lbl" aria-hidden="true">Nuova lezione</span><span className="isle" aria-hidden="true"><Icon n="plus" /></span></button>}
          </div>
          <div className="tb-group">
            <button ref={themeBtn} className="circle raised theme" aria-label={dark ? "Passa al tema chiaro" : "Passa al tema scuro"} onClick={() => setTheme(dark ? "light" : "dark", themeBtn.current?.getBoundingClientRect())}><Icon n={dark ? "sun" : "moon"} /></button>
            <button className="circle raised bell" aria-label={unread ? `Notifiche, ${unread} da leggere` : "Notifiche"} aria-haspopup="dialog" aria-expanded={false} onClick={(e) => setBell(bell ? null : e.currentTarget)}><Icon n="bell" /><span className={"dot" + (unread ? " on" : "")} /></button>
            <button className="me-btn" aria-label={`${d.me.name}, account`} aria-haspopup="dialog" aria-expanded={false} onClick={(e) => setMeOpen(meOpen ? null : e.currentTarget)}><Avatar name={d.me.name} /></button>
          </div>
        </header>
        <main id="main" tabIndex={-1}>
          {hub && hub.sections.length > 1 && <nav className="hub-tabs" aria-label={hub.label}>
            {hub.sections.map((s) => <a key={s.key} href={"#/" + s.key} onClick={nav(s.key)} aria-current={s.key === cur.key ? "page" : undefined}>{s.label}</a>)}
          </nav>}
          <div className="view" key={cur.key}>{children}</div>
        </main>
      </div>
    </div>
    <nav className="tabbar" aria-label="Sezioni" ref={tab}>
      <span className="puck" aria-hidden="true" />
      {tabs.map((h) => <a key={h.key} href={"#/" + h.sections[0].key} onClick={nav(h.sections[0].key)} aria-label={h.label} aria-current={h.key === hub?.key ? "page" : undefined}><Icon n={h.icon} /></a>)}
      <a href="#" onClick={(e) => { e.preventDefault(); setCmd(true); }} aria-label="Tutte le sezioni e la ricerca" aria-current={tabs.some((t) => t.key === hub?.key) ? undefined : "page"}><Icon n="search" /></a>
    </nav>
    <Pop open={!!bell} anchor={bell} onClose={() => setBell(null)} label="Notifiche">
      <h2>Notifiche {unread > 0 && <button onClick={() => { inbox.readAll(); markRead(notes.map((n) => n.id)); }}>Segna tutte come lette</button>}</h2>
      <div className="pop-list" aria-live="polite">
        {inbox.err && <div className="fine" style={{ padding: "8px" }}>Notifiche non disponibili al momento.</div>}
        {inbox.items.slice(0, 8).map((n) => <button key={n.id} className={"pop-item note-item" + (n.read_at ? "" : " unread")} onClick={() => { inbox.read(n); setBell(null); openRef(n.subject_ref, n.kind, d.center); }}>
          <span className={`av t${(n.kind.length % 5) + 1}`} aria-hidden="true"><Icon n="bell" size={16} /></span><div><b>{n.title}</b><small>{n.body ? n.body.slice(0, 120) : ""}{n.body ? " · " : ""}{ago(n.created_at)}{n.read_at ? "" : " · da leggere"}</small></div>
        </button>)}
        {notes.length > 0 && <h3 className="pop-sub">Da fare</h3>}
        {notes.map((n) => <button key={n.id} className="pop-item" onClick={() => { markRead([n.id]); setBell(null); n.run(); }}>
          <span className={`av t${n.id.length % 5 + 1}`} aria-hidden="true">{n.who}</span><div><b>{n.title}</b><small>{n.sub}</small></div><span className={"ud" + (read.has(n.id) ? " read" : "")} />
        </button>)}
        {!inbox.items.length && !notes.length && <div className="empty" style={{ padding: "24px 8px" }}><b>Nessuna novità</b>Qui trovi le notifiche del centro e ciò che richiede la tua attenzione.</div>}
        {inbox.pending > 0 && <div className="fine" style={{ padding: "8px" }}>{plural(inbox.pending, "email in uscita", "email in uscita")}: le trovi anche qui.</div>}
      </div>
      <div style={{ padding: "6px 8px 2px" }}><button className="link-btn" onClick={() => { setBell(null); go("impostazioni", { t: "notifiche" }); }}>Preferenze di notifica</button></div>
    </Pop>
    <Pop open={!!meOpen} anchor={meOpen} onClose={() => setMeOpen(null)} label="Account">
      <div className="me-card"><Avatar name={d.me.name} size={48} /><div><b>{d.me.name}</b><small>{d.me.roles.map(roleName).join(", ") || "Nessun ruolo attivo"}</small></div></div>
      <div className="pop-list">
        {d.switchContext && <button className="pop-item" onClick={() => { setMeOpen(null); d.switchContext!(); }}><span className="ic-sm"><Icon n="users" /></span><div><b>Cambia ruolo</b><small>Ora: {d.me.roles.map(roleName).join(", ")}</small></div></button>}
        <button className="pop-item" onClick={() => { setMeOpen(null); go("impostazioni"); }}><span className="ic-sm"><Icon n="gear" /></span><div><b>Impostazioni</b><small>Sicurezza, notifiche, calendario, tema</small></div></button>
        <button className="pop-item" onClick={() => { setMeOpen(null); d.signOut().catch(() => toast("Uscita non riuscita. Riprova.")); }}><span className="ic-sm"><Icon n="arrow" /></span><div><b>Esci</b><small>Chiude la sessione su questo browser</small></div></button>
      </div>
    </Pop>
    <CommandPalette open={cmd} onClose={() => setCmd(false)} sections={all} />
  </>;
}
/** Dove porta una notifica: la lezione nella settimana/agenda o le richieste di cambio. */
function openRef(ref: string, kind: string, center: boolean) {
  if (kind.startsWith("change_request")) { go(center ? "agenda" : "cambi"); return; }
  if (ref.startsWith("autoplan-confirmation:")) { go(center ? "pianificazione" : "conferme"); return; }
  if (ref.startsWith("lesson-change:")) { go(center ? "agenda" : "conferme"); return; }
  if (ref.startsWith("lesson:")) { go(center ? "agenda" : "settimana"); return; }
}
export const roleName = (r: string) => ({ CENTER: "Centro", TUTOR: "Tutor", GUARDIAN: "Tutore legale", STUDENT: "Studente" } as Record<string, string>)[r] || r;

type Item = { label: string; sub?: string; icon?: IconName; av?: string; run: () => void };
function CommandPalette({ open, onClose, sections }: { open: boolean; onClose: () => void; sections: Section[] }) {
  const d = useData(); const [q, setQ] = useState(""), [sel, setSel] = useState(0);
  useEffect(() => { if (open) { setQ(""); setSel(0); } }, [open]);
  const m = (s: string) => !q.trim() || s.toLowerCase().includes(q.trim().toLowerCase());
  const groups: [string, Item[]][] = [
    ["Azioni", [
      ...(d.center ? [{ label: "Nuova lezione", icon: "plus" as IconName, run: () => openNewLesson() }] : []),
      { label: "Nuovo impegno", icon: "clock" as IconName, run: () => go("impegni", { nuova: "1" }) },
      { label: "Cambia tema", icon: "moon" as IconName, run: () => setTheme(resolved(getPrefs().theme) === "dark" ? "light" : "dark") },
    ].filter((x) => m(x.label))],
    ["Sezioni", sections.filter((s) => m(s.label + " " + s.title)).map((s) => ({ label: s.label, icon: s.icon, run: () => viewTransition(() => go(s.key)) }))],
    ["Studenti", q.trim() ? d.students.filter((s) => m(s.display_name + " " + s.level)).slice(0, 6).map((s) => ({ label: s.display_name, sub: s.level || "Livello non indicato", av: s.display_name, run: () => go(d.center ? "anagrafica" : "studenti", { s: s.id }) })) : []],
  ].filter((g) => g[1].length) as [string, Item[]][];
  const items = groups.flatMap((g) => g[1]);
  const pick = (i: number) => { const it = items[i]; if (!it) return; onClose(); setTimeout(it.run, 40); };
  useEffect(() => { document.getElementById("opt-" + sel)?.scrollIntoView({ block: "nearest" }); }, [sel]);
  return <Modal open={open} onClose={onClose} className="cmd" label="Cerca">
    <div className="cmd-input"><Icon n="search" /><label className="sr" htmlFor="cmdQ">Cerca</label>
      <input id="cmdQ" autoFocus type="search" placeholder="Cerca sezioni, studenti o azioni…" autoComplete="off" spellCheck={false} role="combobox" aria-expanded="true" aria-controls="cmdRes" aria-activedescendant={items.length ? "opt-" + sel : undefined}
        value={q} onChange={(e) => { setQ(e.target.value); setSel(0); }}
        onKeyDown={(e) => { if (e.key === "ArrowDown") { e.preventDefault(); setSel(Math.min(items.length - 1, sel + 1)); } else if (e.key === "ArrowUp") { e.preventDefault(); setSel(Math.max(0, sel - 1)); } else if (e.key === "Enter") { e.preventDefault(); pick(sel); } }} />
      <kbd>Esc</kbd></div>
    <div className="cmd-res" id="cmdRes" role="listbox">{items.length ? groups.map(([h, arr]) => <div key={h}><h3>{h}</h3>{arr.map((it) => { const i = items.indexOf(it); return <button key={h + it.label} id={"opt-" + i} role="option" aria-selected={i === sel} className="pop-item" onMouseMove={() => setSel(i)} onClick={() => pick(i)}>
      {it.av ? <Avatar name={it.av} /> : <span className="ic"><Icon n={it.icon || "arrow"} /></span>}<div><b>{it.label}</b>{it.sub && <small>{it.sub}</small>}</div></button>; })}</div>)
      : <div className="empty"><b>Nessun risultato per “{q}”</b>Prova con il nome di una sezione o di uno studente.</div>}</div>
  </Modal>;
}
