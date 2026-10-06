/** Orari suggeriti dal motore (v0.9.8): un elenco per giorno, già filtrato su aperture,
 *  chiusure, impegni di tutor e studenti, lezioni e aule occupate. */
import { dayLabel, rangeOf } from "../format";

export type Slot = { date: string; start_at: string; end_at: string; tutor_id: string; tutor_name: string; space_id: string | null; space_name?: string | null; same_tutor?: boolean };
export const slotKey = (s: Pick<Slot, "start_at" | "tutor_id">) => `${s.start_at}|${s.tutor_id}`;

export function SlotPicker({ slots, value, onPick, showTutor = true, empty }: { slots: Slot[] | null; value: string; onPick: (s: Slot) => void; showTutor?: boolean; empty?: string }) {
  if (!slots) return <div className="sp-loading" aria-busy="true"><span /><span /><span /></div>;
  if (!slots.length) return <p className="sp-empty">{empty || "Nessun orario libero per tutte le persone coinvolte in questo periodo."}</p>;
  const days = [...new Set(slots.map((s) => s.date))];
  return <div className="sp" role="radiogroup" aria-label="Orari proposti">
    {days.map((d) => <div key={d} className="sp-day">
      <span className="sp-date">{dayLabel(d)}</span>
      <div className="sp-opts">{slots.filter((s) => s.date === d).map((s) => {
        const k = slotKey(s), on = k === value;
        return <button key={k} type="button" role="radio" aria-checked={on} className={"sp-opt" + (on ? " on" : "")} onClick={() => onPick(s)}>
          <b>{rangeOf(s.start_at, s.end_at)}</b>
          {showTutor && <small>{s.tutor_name}{s.space_name ? ` · ${s.space_name}` : ""}</small>}
        </button>;
      })}</div>
    </div>)}
  </div>;
}
