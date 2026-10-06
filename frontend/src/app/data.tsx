import { createContext, ReactNode, useCallback, useContext, useState } from "react";
import { api, list } from "../api";

export type Me = { id: string; name: string; roles: string[]; tutor_id: string | null; own_tutor_id?: string | null; contexts?: string[]; context?: string | null };
export type Student = { id: string; display_name: string; level: string };
export type Tutor = { id: string; display_name: string };
export type Rule = { id: string; student: string | null; tutor: string | null; weekday: number; start_time: string; end_time: string; status: string; version: number; period_start?: string; period_end?: string; mode?: string; location?: string };
export type Decision = { code: string; title: string; status: string; proposed_default: string };
export type Resource = { id: string; name: string; student_capacity: number };
export type Request = { id: string; student: string | null; target_type: string; participant_ids: string[]; subject_name: string; duration_minutes: number; sessions_per_week: number; status?: string; student_name?: string };
export type Readiness = { ready: boolean; blockers: { code: string; reason: string }[] };

type Data = { me: Me; center: boolean; students: Student[]; tutors: Tutor[]; rules: Rule[]; requests: Request[]; decisions: Decision[]; resources: Resource[]; readiness: Readiness | null; loaded: boolean; refresh: () => Promise<void>; signOut: () => Promise<void>; switchContext?: () => void };
const Ctx = createContext<Data | null>(null);
export const useData = () => useContext(Ctx)!;
export function DataProvider({ me, onSignOut, onSwitchContext, children }: { me: Me; onSignOut: () => void; onSwitchContext?: () => void; children: ReactNode }) {
  const center = me.roles.includes("CENTER");
  const [s, set] = useState({ students: [] as Student[], tutors: [] as Tutor[], rules: [] as Rule[], requests: [] as Request[], decisions: [] as Decision[], resources: [] as Resource[], readiness: null as Readiness | null, loaded: false });
  const refresh = useCallback(async () => {
    const [students, tutors, rules, requests] = await Promise.all([list<Student>("/students/"), list<Tutor>("/tutors/"), list<Rule>("/availability-rules/"), list<Request>("/teaching-requests/")]);
    let extra = { decisions: [] as Decision[], resources: [] as Resource[], readiness: null as Readiness | null };
    if (center) {
      const [decisions, resources, readiness] = await Promise.all([list<Decision>("/decisions/"), list<Resource>("/resources/"), api<Readiness>("/planning/readiness")]);
      extra = { decisions, resources, readiness };
    }
    set({ students, tutors, rules, requests, ...extra, loaded: true });
  }, [center]);
  const signOut = useCallback(async () => { await api("/auth/logout", { method: "POST" }); onSignOut(); }, [onSignOut]);
  return <Ctx.Provider value={{ me, center, ...s, refresh, signOut, switchContext: onSwitchContext }}>{children}</Ctx.Provider>;
}
export const subjectName = (d: Pick<Data, "students" | "tutors">, r: { student: string | null; tutor: string | null }) =>
  d.students.find((x) => x.id === r.student)?.display_name || d.tutors.find((x) => x.id === r.tutor)?.display_name || "Persona autorizzata";
