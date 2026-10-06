import { api } from "../api";
export type Lesson = { series?: string | null; recurrence_key?: string | null; video?: string | null; id: string; version: number; state: string; demand_key?: string; start_at: string; end_at: string; tutor: string; tutor_name: string; subject: string; subject_name: string; mode: string; location: string; space: string | null; participants: { student_id: string; name: string }[];
  /** Modifica di orario/durata proposta con il drag & drop, in attesa di tutor e famiglie. */
  time_change?: TimeChange | null };
export type TimeChange = { id: string; start_at: string; end_at: string; answers: { party: "TUTOR" | "STUDENT"; who: string; status: "PENDING" | "ACCEPTED" | "REJECTED" }[] };
export type Cap = { enabled: boolean; reason_code: string; database: string; production_enabled: boolean };
export async function loadLessons(from: string, until: string) {
  let path: string | null = `/calendar/?from=${from}&until=${until}`;
  let seen: number | null = null; const rows: Lesson[] = [];
  while (path) {
    const page: { revision: number; results: Lesson[]; next: string | null } = await api(path);
    if (seen !== null && seen !== page.revision) throw Error("Il calendario è cambiato durante la lettura. Aggiorna la vista.");
    seen = page.revision; rows.push(...page.results);
    if (page.next) {
      const next = new URL(page.next, window.location.origin);
      if (next.origin !== window.location.origin || !next.pathname.startsWith("/api/v1/calendar/")) throw Error("Paginazione calendario fuori origine");
      path = next.pathname.slice("/api/v1".length) + next.search;
    } else path = null;
  }
  return { lessons: rows, revision: seen };
}
