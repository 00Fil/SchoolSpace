import { Empty, PageHead, Skeleton, State, Tag } from "../ui/core";
import { useData } from "../app/data";

export default function Decisioni() {
  const d = useData(); const open = d.decisions.filter((x) => x.status === "OPEN").length;
  return <section className="module planner" aria-labelledby="h-dec">
    <PageHead id="h-dec" title="Decisioni di progetto" lead={open ? `${open} ancora aperte` : undefined} />
    {!d.loaded ? <Skeleton /> : d.decisions.length ? <div className="settings wide">{d.decisions.map((x) => <article key={x.code} className="setting decision">
      <div><div className="kind"><Tag tone="plain">{x.code}</Tag><State s={x.status} /></div><b>{x.title}</b><p>{x.proposed_default}</p></div>
    </article>)}</div> : <Empty title="Registro vuoto" />}
  </section>;
}
