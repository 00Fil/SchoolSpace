import { api } from "../api";
/** Lezione vista da tutor, tutore legale o studente: nomi di altri partecipanti nascosti dal server. */
export type MyLesson = { id: string; state: string; start_at: string; end_at: string; subject_name: string; tutor_name: string; mode: string; location: string; space_name: string | null; as_tutor: boolean; participants: { student_id: string; name: string }[]; other_participants: number };
export const loadMine = (from: string, until: string) => api<{ results: MyLesson[] }>(`/my/lessons?from=${from}&until=${until}`).then((r) => r.results);
