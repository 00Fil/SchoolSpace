import { ApiError } from "./api/client";
export type Tone = "blue" | "green" | "amber" | "red" | "violet" | "plain";
/** Etichette umane degli stati interni: il codice resta nei dettagli tecnici. */
export const STATE: Record<string, [string, Tone]> = {
  DRAFT: ["Bozza", "amber"], APPROVED: ["Approvata", "green"], REVOKED: ["Revocata", "plain"],
  PUBLISHED: ["Pubblicata", "blue"], CANCELLED: ["Cancellata", "plain"],
  QUEUED: ["In coda", "plain"], RUNNING: ["In elaborazione", "blue"], SUCCEEDED: ["Completato", "green"], FAILED: ["Non riuscito", "red"],
  CANCEL_REQUESTED: ["Annullamento richiesto", "amber"],
  VALIDATED: ["Validata", "green"], REJECTED: ["Respinta", "red"], PUBLISHED_EXPERIMENTAL: ["Pubblicata", "blue"], SUPERSEDED: ["Superata", "plain"],
  OPEN: ["Aperta", "amber"], DECIDED: ["Decisa", "green"], DEFERRED: ["Rinviata", "plain"], CLOSED: ["Chiusa", "green"],
  OPTIMAL: ["Ottimale", "green"], FEASIBLE: ["Valida", "blue"], INFEASIBLE: ["Impossibile", "red"], UNKNOWN: ["Non conclusiva", "amber"],
  BLOCKED: ["Bloccata", "amber"], MODEL_INVALID: ["Dati non validi", "red"], VALIDATION_FAILED: ["Non superata", "red"],
  PASSED: ["Superata", "green"], NOT_RUN: ["Non eseguita", "plain"],
};
export const stateOf = (s: string): [string, Tone] => STATE[s] || [s.charAt(0) + s.slice(1).toLowerCase().replace(/_/g, " "), "plain"];
export const MODE: Record<string, string> = { IN_PERSON: "In presenza", ONLINE: "Online" };
export const LOCATION: Record<string, string> = { ON_SITE: "In sede", REMOTE: "Da remoto" };
const CODES: Record<string, string> = {
  VERSION_CONFLICT: "Qualcuno ha modificato questi dati nel frattempo. Ricarica e riprova.",
  DATA_CONFLICT: "I dati sono cambiati durante l’operazione. Ricarica e riprova.",
  BOOKING_CONFLICT: "Lo spazio, il tutor o uno studente è già occupato in quell’orario. Non è stato salvato nulla.",
  INVALID_CREDENTIALS: "Email o password non corrette.",
  INVALID_CODE: "Il codice non è valido o è già stato usato. Controlla l’ora del telefono e usa il codice nuovo.",
  MFA_SESSION_EXPIRED: "Il tempo per la verifica è scaduto. Accedi di nuovo.",
  MFA_ALREADY_ENROLLED: "La verifica in due passaggi è già attiva su questo account.",
  MFA_REQUIRED: "Per continuare serve la verifica in due passaggi.",
  CONTEXT_REQUIRED: "Scegli con quale ruolo vuoi operare.",
  CONTEXT_NOT_GRANTED: "Questo ruolo non è più disponibile per il tuo account.",
  INVALID_TOKEN: "Il link non è valido, è scaduto o è già stato usato. Chiedine uno nuovo al centro.",
  LOGIN_REQUIRED: "Hai già un account: accedi con la tua password e poi riapri il link dell’invito.",
  PASSWORD_REQUIRED: "Scegli una password per il nuovo account.",
  WEAK_PASSWORD: "La password è troppo debole.",
  NOT_AUTHENTICATED: "La sessione è terminata. Accedi di nuovo.",
  NOT_FOUND: "Questi dati non sono disponibili per il tuo account.",
  TOKEN_LIMIT: "Hai già il numero massimo di link del calendario. Revocane uno prima di crearne un altro.",
  STUDENT_REQUIRED: "Indica lo studente a cui si riferisce la richiesta.",
  PROPOSAL_INVALID: "L’orario proposto non è valido.",
  PREFERENCE_MANDATORY: "Questa notifica è obbligatoria e non si può disattivare.",
  RATE_LIMITED: "Troppi tentativi ravvicinati. Attendi qualche minuto e riprova.",
  POSTGRES_REQUIRED: "Questa funzione non è disponibile al momento. Contatta l’assistenza del centro.",
  FEATURE_DISABLED: "Questa funzione non è attiva. Contatta l’assistenza del centro.",
  DEVELOPMENT_ONLY: "Questa funzione non è disponibile.",
  SIMULATION_BUSY: "C’è già una simulazione in corso. Riprova tra poco.",
  INVALID_PAYLOAD: "Alcuni dati non sono validi. Controlla i campi e riprova.",
  IMPLEMENTATION_PENDING: "Questa funzione non è ancora disponibile.",
  SAME_WEEK_REQUIRED: "Una lezione si può spostare solo all’interno della stessa settimana.",
  PAST_LESSON: "La lezione è già iniziata o passata: non si può modificare.",
  LESSON_NOT_ACTIVE: "La lezione non è più attiva.",
  REASON_REQUIRED: "Scrivi il motivo dell’operazione.",
  PARTIAL_ACCEPTANCE_REQUIRED: "Devi accettare esplicitamente le unità non soddisfatte.",
  PARTIAL_REASON_REQUIRED: "Per una pubblicazione parziale serve il motivo.",
  EXPERIMENTAL_CONFIRMATION: "Serve una conferma esplicita prima di pubblicare.",
  SNAPSHOT_CHANGED: "I dati sono cambiati dopo la proposta: generane una nuova.",
  STALE_INPUT: "La proposta si basa su dati non più attuali: generane una nuova.",
  ALREADY_PUBLISHED: "Questa proposta è già stata pubblicata.",
  PLAN_NOT_VALIDATED: "La proposta non è stata validata e non si può pubblicare.",
  IDEMPOTENCY_CONFLICT: "La stessa operazione è stata già inviata con dati diversi. Ricarica la pagina.",
  CURRICULUM_FROZEN: "Il programma è congelato dopo la derivazione delle richieste.",
  CALENDAR_VALIDATION_FAILED: "Il controllo del calendario non ha permesso l’operazione. Nulla è cambiato.",
  TRANSITION_CONFLICT: "L’operazione non è possibile nello stato attuale.",
  FORBIDDEN: "Non hai i permessi per questa operazione.",
  IDEMPOTENCY_KEY_REQUIRED: "Richiesta incompleta: ricarica la pagina e riprova.",
  LESSON_NOT_STARTED: "Le presenze si registrano dall’inizio della lezione.",
  ATTENDANCE_WINDOW_CLOSED: "Il periodo per registrare le presenze di questa lezione è chiuso: contatta il centro.",
};
/** Codici del validatore indipendente → motivo leggibile (spostamenti e opzioni). */
export const VIOLATION: Record<string, string> = {
  TUTOR_AVAILABILITY: "il tutor non è disponibile in quell’orario",
  STUDENT_AVAILABILITY: "uno studente non è disponibile in quell’orario",
  SERVICE_CLOSED: "il centro è chiuso in quell’orario",
  RESOURCE_AVAILABILITY: "lo spazio o il canale video non è disponibile",
  CLOSURE: "c’è una chiusura programmata",
  RESOURCE_OVERLAP: "tutor, studente o spazio sono già occupati",
  TUTOR_BUSY: "il tutor ha già un’altra lezione",
  STUDENT_BUSY: "lo studente ha già un’altra lezione",
  NO_ROOM: "nessuna aula libera con posti sufficienti",
  TRANSITION_OR_PAUSE: "manca la pausa o il tempo di spostamento del tutor",
  DAILY_LOAD: "si supera il limite giornaliero del tutor",
  WEEKLY_LOAD: "si supera il limite settimanale del tutor",
  DURATION_OR_WINDOW: "la lezione esce dalla finestra consentita",
  CROSS_LOCAL_MIDNIGHT: "la lezione supererebbe la mezzanotte",
  UNQUALIFIED_TUTOR: "il tutor non è abilitato per questa materia",
  SPACE_REQUIRED: "serve uno spazio in sede",
  SPACE_CAPACITY: "lo spazio non ha posti sufficienti",
  VIDEO_REQUIRED: "serve un canale video",
  ONLINE_CAPACITY: "il canale online non ha posti sufficienti",
  LOCK_CHANGED: "la lezione è bloccata in questa proposta",
  ILLEGAL_OPTION: "combinazione di modalità e luogo non ammessa",
  PAST_LESSON: "l’orario è già passato",
  SAME_WEEK_REQUIRED: "è fuori dalla settimana della lezione",
  CALENDAR_VALIDATION_FAILED: "il calendario attuale ha già un’incoerenza da risolvere",
};
const ORDER = Object.keys(VIOLATION);
/** Motivi in ordine di utilità per chi sposta: prima persone, poi centro e risorse. */
export const reasons = (codes: string[]) => [...codes].sort((a, b) => (ORDER.indexOf(a) + 1 || 99) - (ORDER.indexOf(b) + 1 || 99)).map((c) => VIOLATION[c] || c.toLowerCase().replace(/_/g, " "));
export function violationsOf(e: unknown): string[] {
  const d = e instanceof ApiError && e.data && typeof e.data === "object" ? (e.data as { violations?: unknown }).violations : null;
  return Array.isArray(d) ? d.filter((x): x is string => typeof x === "string") : [];
}
export type Human = { text: string; code: string; detail: string; retry: boolean };
export function human(e: unknown): Human {
  if (e instanceof ApiError) {
    const code = e.code || (e.status === 409 ? "VERSION_CONFLICT" : e.status === 403 ? "FORBIDDEN" : "");
    let text = CODES[code] || "";
    // rettifiche del calendario del mese (v0.9.11): il server spiega già cosa non va
    if (e.message && /rettific/i.test(e.message) && !e.message.startsWith("{")) text = e.message;
    if (!text && e.status === 403) text = CODES.FORBIDDEN;
    if (!text && e.status === 0) text = "Connessione al server non riuscita. Puoi riprovare: la stessa operazione non verrà duplicata.";
    if (!text) text = e.message && !e.message.startsWith("{") ? e.message : "Operazione non riuscita.";
    const why = reasons(violationsOf(e));
    if (why.length) text += ` Motivo: ${why.join("; ")}.`;
    const errs = e.data && typeof e.data === "object" ? (e.data as { errors?: unknown }).errors : null;
    if (Array.isArray(errs) && errs.length) text += " " + errs.filter((x) => typeof x === "string").join(" ");
    if (code === "RATE_LIMITED" && e.retryAfter) text = `Troppi tentativi ravvicinati. Riprova tra ${e.retryAfter < 120 ? e.retryAfter + " secondi" : Math.ceil(e.retryAfter / 60) + " minuti"}.`;
    return { text, code, detail: `HTTP ${e.status}${code ? " · " + code : ""}${e.message && e.message !== text ? " · " + e.message : ""}`, retry: e.status === 0 || e.status >= 500 };
  }
  const m = e instanceof Error ? e.message : String(e);
  return { text: m.includes("JSON") ? "Il testo JSON non è valido. Controlla virgole e parentesi." : m, code: "", detail: m, retry: false };
}
