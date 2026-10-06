export const LOC = "it-IT";
export const TZ = "Europe/Rome";
export const pad = (n: number) => String(n).padStart(2, "0");
export const cap = (s: string) => (s ? s.charAt(0).toUpperCase() + s.slice(1) : s);
const fDay = new Intl.DateTimeFormat(LOC, { weekday: "long", day: "numeric", month: "long", timeZone: "UTC" });
const fDayShort = new Intl.DateTimeFormat(LOC, { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" });
const fDM = new Intl.DateTimeFormat(LOC, { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });
const fMonthYear = new Intl.DateTimeFormat(LOC, { month: "long", year: "numeric", timeZone: "UTC" });
const fWdNarrow = new Intl.DateTimeFormat(LOC, { weekday: "narrow", timeZone: "UTC" });
const romeParts = new Intl.DateTimeFormat("en-CA", { timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
/** "YYYY-MM-DD" → Date a mezzogiorno UTC: aritmetica sui giorni senza effetti DST. */
export const parse = (d: string) => new Date(d + "T12:00:00Z");
export const iso = (d: Date) => d.toISOString().slice(0, 10);
export const addDays = (d: string, n: number) => iso(new Date(parse(d).getTime() + n * 86400000));
export const weekday = (d: string) => (parse(d).getUTCDay() + 6) % 7; // 0 = lunedì
export const mondayOf = (d: string) => addDays(d, -weekday(d));
export const addMonths = (ym: string, n: number) => { const [y, m] = ym.split("-").map(Number); const t = new Date(Date.UTC(y, m - 1 + n, 1, 12)); return iso(t).slice(0, 7); };
export const dayLabel = (d: string) => cap(fDay.format(parse(d)));
export const dayShort = (d: string) => cap(fDayShort.format(parse(d)).replace(".", ""));
export const dateLong = (d: string) => fDM.format(parse(d));
export const monthYear = (ym: string) => cap(fMonthYear.format(parse(ym + "-01")));
export const WD_NARROW = Array.from({ length: 7 }, (_, i) => cap(fWdNarrow.format(parse(addDays("2026-01-05", i)))));
export const WD_LONG = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"];
export const WD_SHORT = ["Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom"];
/** Data e minuto del giorno nel fuso del centro. */
export function rome(isoDateTime: string | Date) {
  const p = Object.fromEntries(romeParts.formatToParts(new Date(isoDateTime)).map((x) => [x.type, x.value]));
  return { date: `${p.year}-${p.month}-${p.day}`, min: Number(p.hour) * 60 + Number(p.minute) };
}
export const todayRome = () => rome(new Date()).date;
export const hm = (min: number) => `${pad(Math.floor(min / 60) % 24)}:${pad(min % 60)}`;
export const parseHm = (s: string) => { const [h, m] = s.split(":").map(Number); return h * 60 + (m || 0); };
export const timeOf = (isoDateTime: string) => hm(rome(isoDateTime).min);
export const rangeOf = (a: string, b: string) => `${timeOf(a)}–${timeOf(b)}`;
export function duration(min: number) {
  const h = Math.floor(min / 60), m = min % 60;
  if (!h) return `${m} min`;
  const hs = h === 1 ? "1 ora" : `${h} ore`;
  return m ? `${h} h ${pad(m)}` : hs;
}
/** Istante ISO con offset per un orario locale Europe/Rome (gestisce l’ora legale). */
const fOff = new Intl.DateTimeFormat("en-US", { timeZone: TZ, timeZoneName: "longOffset" });
function offsetAt(t: number) {
  const s = fOff.formatToParts(new Date(t)).find((p) => p.type === "timeZoneName")?.value || "GMT";
  const m = s.match(/GMT([+-])(\d{2}):?(\d{2})?/);
  return m ? (m[1] === "-" ? -1 : 1) * (Number(m[2]) * 60 + Number(m[3] || 0)) : 0;
}
export function romeISO(date: string, min: number) {
  const [y, mo, d] = date.split("-").map(Number);
  const local = Date.UTC(y, mo - 1, d, Math.floor(min / 60), min % 60);
  let off = offsetAt(local);
  off = offsetAt(local - off * 60000);
  const sign = off >= 0 ? "+" : "-";
  return `${date}T${hm(min)}:00${sign}${pad(Math.floor(Math.abs(off) / 60))}:${pad(Math.abs(off) % 60)}`;
}
export const num = (n: number) => new Intl.NumberFormat(LOC).format(n);
export const plural = (n: number, one: string, many: string) => `${num(n)} ${n === 1 ? one : many}`;
export function initials(name: string) {
  const w = name.replace(/[^\p{L}\p{N}\s]/gu, " ").split(/\s+/).filter(Boolean);
  return (w.length > 1 ? w[0][0] + w[w.length - 1][0] : (w[0] || "?").slice(0, 2)).toUpperCase();
}
export function tone(key: string) { let h = 2166136261; for (const c of key) { h ^= c.charCodeAt(0); h = Math.imul(h, 16777619); } return ((h >>> 0) % 5) + 1; }
export const shortId = (id: string) => id.slice(0, 8);
export const isMac = typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent);
