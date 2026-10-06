/** Testi di aiuto in linea: un pulsante «Come funziona» per ogni schermata. */
import { useId, useState } from "react";
import { HELP } from "../help";
import { Icon } from "./core";

export function Help({ topic }: { topic: keyof typeof HELP }) {
  const [open, setOpen] = useState(false), id = useId();
  const h = HELP[topic];
  return <div className={"help" + (open ? " open" : "")}>
    <button type="button" className="tech-btn" aria-expanded={open} aria-controls={id} onClick={() => setOpen(!open)}>
      <Icon n="book" size={16} />Come funziona<Icon n="chev" size={16} />
    </button>
    {open && <div id={id} className="help-body reveal" role="region" aria-label={`Aiuto: ${h.title}`}>
      <b>{h.title}</b>
      <ul>{h.points.map((p) => <li key={p}>{p}</li>)}</ul>
    </div>}
  </div>;
}
