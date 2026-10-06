/**
 * Su mobile le tabelle diventano schede impilate (vedi app.css «liste su mobile»): ogni cella
 * mostra l'intestazione della sua colonna come etichetta. Qui copiamo il testo dei <th> di
 * <thead> nell'attributo data-label delle celle, per tutte le tabelle presenti e future.
 */
export function labelTables(root: ParentNode = document) {
  root.querySelectorAll<HTMLTableElement>("table").forEach((t) => {
    const head = t.tHead?.rows[t.tHead.rows.length - 1]; if (!head) return;
    const names: string[] = [];
    for (const th of Array.from(head.cells)) for (let i = 0; i < (th.colSpan || 1); i++) names.push((th.textContent || "").trim());
    for (const body of Array.from(t.tBodies)) for (const tr of Array.from(body.rows)) {
      let i = 0;
      for (const c of Array.from(tr.cells)) {
        const n = names[i] || ""; if (c.dataset.label !== n) c.dataset.label = n;
        i += c.colSpan || 1;
      }
    }
  });
}
export function watchTables() {
  if (typeof MutationObserver === "undefined") return;
  let raf = 0;
  const run = () => { raf = 0; labelTables(); };
  new MutationObserver(() => { if (!raf) raf = requestAnimationFrame(run); }).observe(document.body, { childList: true, subtree: true, characterData: true });
  run();
}
