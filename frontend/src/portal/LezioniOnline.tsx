import { useEffect, useState } from "react";
import { ApiError } from "../api";
import { joinLesson } from "./VideoRoom";
import { addDays, dayShort, hm, rome, todayRome } from "../format";
import { human } from "../messages";
import { Btn, Notice } from "../ui/core";
import { loadMine, MyLesson } from "../app/myApi";

/** P5 · link delle lezioni online nei portali (si apre poco prima e durante la lezione). */
export default function LezioniOnline() {
  const [rows, setRows] = useState<MyLesson[]>([]), [msg, setMsg] = useState<Record<string, string>>({});
  useEffect(() => { const t = todayRome(); loadMine(t, addDays(t, 7)).then((r) => setRows(r.filter((l) => l.mode === "ONLINE" && l.state === "PUBLISHED" && new Date(l.end_at).getTime() > Date.now()).slice(0, 3))).catch(() => setRows([])); }, []);
  if (!rows.length) return null;
  async function join(l: MyLesson) {
    try { await joinLesson(l.id); setMsg({ ...msg, [l.id]: "" }); }
    catch (e) { const h = human(e), d = ((e instanceof ApiError ? e.data : null) || {}) as { opens_at?: string };
      setMsg({ ...msg, [l.id]: h.code === "MEETING_NOT_OPEN" && d.opens_at ? `Il link si apre alle ${hm(rome(d.opens_at).min)}.` : h.code === "MEETING_NOT_CONFIGURED" ? "La videolezione non è ancora attiva: contatta il centro." : h.text }); }
  }
  return <section aria-labelledby="h-online" style={{ marginBottom: 18 }}>
    <h2 className="m-title" id="h-online">Lezioni online in arrivo</h2>
    <div className="list-rows">{rows.map((l) => <div className="list-row" key={l.id}>
      <div><b>{dayShort(rome(l.start_at).date)} {hm(rome(l.start_at).min)} · {l.subject_name}</b><small>con {l.tutor_name}</small>{msg[l.id] && <Notice kind="info">{msg[l.id]}</Notice>}</div>
      <Btn kind="sm" onClick={() => join(l)}>Entra nella lezione</Btn></div>)}</div>
  </section>;
}
