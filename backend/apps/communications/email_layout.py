"""Struttura delle email HTML nello stile del centro (Lumen v5.2) — v0.10.

Ogni tipo di messaggio è descritto da una struttura fissa, resa da un unico layout
(``communications/email/layout.html``):

    intestazione (logo e nome del centro, etichetta colorata del tipo di messaggio)
    titolo e introduzione
    scheda «quando» (riquadro calendario: giorno, mese, orario; «prima» barrato)
    dettagli (materia, studenti, modalità, sede)
    avviso (riquadro colorato) e passi da seguire
    pulsante d'azione (+ link in chiaro per chi non vede il pulsante)
    piè di pagina (perché ricevi il messaggio, preferenze, non rispondere)

Vincoli: solo tabelle e stili in linea (compatibilità con Gmail/Outlook), nessuna
immagine o risorsa remota (niente tracciamento, logo disegnato in HTML), testo
sempre escapato dal template, link accettati solo se http(s). La versione testuale
resta l'alternativa ``text/plain`` dello stesso messaggio.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from django.conf import settings

ROME = ZoneInfo("Europe/Rome")
DAYS = ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì", "Sabato", "Domenica"]
MONTHS = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio",
          "agosto", "settembre", "ottobre", "novembre", "dicembre"]
MONTHS_SHORT = ["GEN", "FEB", "MAR", "APR", "MAG", "GIU", "LUG", "AGO", "SET", "OTT", "NOV", "DIC"]

# Token Lumen (frontend/src/lumen/tokens.css): tinta piena, sfondo tenue, inchiostro.
TONES = {
    "blue": {"solid": "#4F7CF7", "soft": "#DCE6FE", "ink": "#2449B8"},
    "violet": {"solid": "#8A6CF2", "soft": "#E7E0FD", "ink": "#5536C4"},
    "green": {"solid": "#3FA86F", "soft": "#DBF1E4", "ink": "#1F7A48"},
    "amber": {"solid": "#E0B33C", "soft": "#FDF0C8", "ink": "#6E5200"},
    "red": {"solid": "#D9534F", "soft": "#FBE3E2", "ink": "#9B2723"},
    "neutral": {"solid": "#7C808B", "soft": "#F1F2F5", "ink": "#5A5F6B"},
}


def _dt(value):
    if not value:
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return None
    return value.astimezone(ROME)


def _when(start, end=None, label=""):
    start, end = _dt(start), _dt(end)
    if start is None:
        return None
    time = f"{start:%H:%M}" + (f" – {end:%H:%M}" if end else "")
    minutes = int((end - start).total_seconds() // 60) if end else 0
    return {
        "label": label,
        "weekday": DAYS[start.weekday()],
        "day": start.day,
        "month": MONTHS_SHORT[start.month - 1],
        "date": f"{DAYS[start.weekday()]} {start.day} {MONTHS[start.month - 1]} {start.year}",
        "time": time,
        "duration": f"{minutes} min" if minutes > 0 else "",
    }


def _safe_url(value):
    value = (value or "").strip()
    return value if value.startswith(("https://", "http://")) else ""


def _cap(text):
    return text[:1].upper() + text[1:] if text else ""


def _details(ctx):
    rows = [("Materia", ctx.get("subject_name", ""))]
    if ctx.get("student_names"):
        many = "," in ctx["student_names"]
        rows.append(("Studenti" if many else "Studente", ctx["student_names"]))
    mode = _cap(ctx.get("mode_text", ""))
    if mode and ctx.get("location_text"):
        mode = f"{mode}, {ctx['location_text']}"
    rows.append(("Modalità", mode))
    return [{"label": k, "value": v} for k, v in rows if v]


def _portal_cta(ctx, label="Apri il calendario"):
    url = _safe_url(ctx.get("portal_url"))
    return {"label": label, "url": url} if url else None


def _for(ctx):
    return f" per {ctx['student_names']}" if ctx.get("student_names") else ""


def _online_notice(ctx, text):
    return {"tone": "blue", "title": "Lezione online", "text": text} if ctx.get("mode") == "ONLINE" else None


def _published(ctx):
    minutes = getattr(settings, "COMMUNICATIONS_MEETING_OPEN_MINUTES_BEFORE", 15)
    return {
        "tone": "blue",
        "badge": "Nuova lezione",
        "title": f"Lezione di {ctx.get('subject_name', '')} in calendario",
        "intro": f"È stata pubblicata una nuova lezione{_for(ctx)}. La trovi già nel calendario del portale.",
        "when": [_when(ctx.get("start_at"), ctx.get("end_at"))],
        "notice": _online_notice(
            ctx,
            f"Il collegamento si apre dal portale {minutes} minuti prima dell'inizio. "
            "Per sicurezza il link non viene inviato via email.",
        ),
        "cta": _portal_cta(ctx),
    }


def _rescheduled(ctx):
    return {
        "tone": "amber",
        "badge": "Lezione spostata",
        "title": f"La lezione di {ctx.get('subject_name', '')} cambia orario",
        "intro": f"La lezione{_for(ctx)} è stata spostata. Ecco il nuovo orario.",
        "previous": _when(ctx.get("previous_start_at"), ctx.get("previous_end_at"), "Prima"),
        "when": [_when(ctx.get("start_at"), ctx.get("end_at"), "Ora")],
        "notice": _online_notice(ctx, "Il link per il collegamento resta disponibile solo nel portale."),
        "cta": _portal_cta(ctx),
    }


def _cancelled(ctx):
    return {
        "tone": "red",
        "badge": "Lezione annullata",
        "title": f"Lezione di {ctx.get('subject_name', '')} annullata",
        "intro": f"La lezione{_for(ctx)} prevista per questo orario è stata annullata.",
        "previous": _when(ctx.get("start_at"), ctx.get("end_at"), "Annullata"),
        "notice": {"tone": "neutral", "title": "Recuperi",
                   "text": "Eventuali recuperi saranno pubblicati nel portale: riceverai un avviso."},
        "cta": _portal_cta(ctx),
    }


def _change_requested(ctx):
    return {
        "tone": "violet",
        "badge": "Da confermare",
        "title": f"Nuovo orario proposto per {ctx.get('subject_name', '')}",
        "intro": f"Il centro propone di spostare la lezione{_for(ctx)}. Serve la tua risposta.",
        "previous": _when(ctx.get("previous_start_at"), ctx.get("previous_end_at"), "Attuale"),
        "when": [_when(ctx.get("start_at"), ctx.get("end_at"), "Proposta")],
        "steps": [
            "Apri la sezione «Da confermare» del portale.",
            "Accetta o rifiuta la proposta.",
            "Finché tutti gli interessati non confermano, resta l'orario attuale.",
        ],
        "cta": _portal_cta(ctx, "Rispondi alla proposta"),
    }


def _change_answered(ctx):
    outcome = ctx.get("outcome")
    subject = ctx.get("subject_name", "")
    resolution = (ctx.get("resolution") or "").strip()
    if outcome == "APPLIED":
        return {
            "tone": "green",
            "badge": "Modifica confermata",
            "title": "Nuovo orario confermato",
            "intro": f"Tutti gli interessati hanno accettato: la lezione di {subject} ha il nuovo orario.",
            "when": [_when(ctx.get("start_at"), ctx.get("end_at"), "Nuovo orario")],
            "cta": _portal_cta(ctx),
        }
    rejected = outcome == "REJECTED"
    return {
        "tone": "red" if rejected else "amber",
        "badge": "Modifica rifiutata" if rejected else "Modifica non applicata",
        "title": f"La lezione di {subject} resta all'orario precedente",
        "intro": (
            "La modifica proposta è stata rifiutata."
            if rejected
            else "La modifica è stata accettata da tutti, ma non si è potuta applicare."
        ),
        "when": [_when(ctx.get("start_at"), ctx.get("end_at"), "Orario proposto")],
        "notice": {"tone": "neutral", "title": "Motivo", "text": resolution} if resolution else None,
        "steps": ["Puoi proporre un altro orario dall'Agenda del portale."] if rejected else [],
        "cta": _portal_cta(ctx, "Apri l'Agenda"),
    }


def _autoplan(ctx):
    labels = ctx.get("commitment_labels") or ""
    overlap = f"«{labels}»" if labels else "un impegno che hai indicato"
    return {
        "tone": "violet",
        "badge": "Da confermare",
        "title": f"Confermi la lezione di {ctx.get('subject_name', '')}?",
        "intro": f"Il centro ha riservato una lezione{_for(ctx)}. Prima di confermarla serve il tuo via libera.",
        "when": [_when(ctx.get("start_at"), ctx.get("end_at"))],
        "notice": {
            "tone": "amber",
            "title": "Sovrapposizione",
            "text": f"Si sovrappone di {ctx.get('overflow_minutes', '')} minuti a {overlap}.",
        },
        "steps": [
            "Apri la sezione «Da confermare» del portale.",
            "Accetta la lezione oppure rifiutala.",
            "Se rifiuti, il centro cercherà un altro orario.",
        ],
        "cta": _portal_cta(ctx, "Conferma o rifiuta"),
    }


def _invitation(ctx):
    center = ctx.get("center_name", "")
    return {
        "tone": "blue",
        "badge": "Invito",
        "title": f"Benvenuto in {center}",
        "intro": "Sei stato invitato ad accedere al gestionale del centro: lezioni, calendario "
                 "e comunicazioni in un unico posto.",
        "cta": {"label": "Attiva l'accesso", "url": _safe_url(ctx.get("link"))},
        "fallback_link": True,
        "notice": {
            "tone": "neutral",
            "title": "Link personale",
            "text": f"Vale una sola volta e scade tra {ctx.get('hours', '')} ore. "
                    "Se non ti aspettavi questo messaggio, ignoralo.",
        },
    }


def _password_reset(ctx):
    return {
        "tone": "blue",
        "badge": "Sicurezza",
        "title": "Reimposta la password",
        "intro": "Abbiamo ricevuto una richiesta di reimpostazione della password del tuo account.",
        "cta": {"label": "Scegli una nuova password", "url": _safe_url(ctx.get("link"))},
        "fallback_link": True,
        "notice": {
            "tone": "amber",
            "title": "Non sei stato tu?",
            "text": f"Ignora questo messaggio: la password non cambia. Il link vale "
                    f"{ctx.get('minutes', '')} minuti e si può usare una sola volta.",
        },
    }


def _generic(ctx):
    return {
        "tone": "blue",
        "badge": "Aggiornamento",
        "title": "C'è un aggiornamento per te",
        "intro": "Trovi tutti i dettagli nel portale del centro.",
        "cta": _portal_cta(ctx, "Apri il portale"),
    }


BUILDERS = {
    "lesson.published": _published,
    "lesson.rescheduled": _rescheduled,
    "lesson.cancelled": _cancelled,
    "lesson.change_requested": _change_requested,
    "lesson.change_answered": _change_answered,
    "autoplan.confirmation_requested": _autoplan,
    "identity.invitation": _invitation,
    "identity.password_reset": _password_reset,
}
LESSON_TYPES = {"lesson.published", "lesson.rescheduled", "lesson.cancelled",
                "lesson.change_requested", "lesson.change_answered",
                "autoplan.confirmation_requested"}


def build(event_type, ctx, preheader=""):
    spec = BUILDERS.get(event_type, _generic)(ctx)
    spec["when"] = [w for w in spec.get("when") or [] if w]
    spec.setdefault("previous", None)
    spec.setdefault("notice", None)
    spec.setdefault("steps", [])
    spec["details"] = _details(ctx) if event_type in LESSON_TYPES else []
    cta = spec.get("cta")
    spec["cta"] = cta if cta and cta.get("url") else None
    spec["palette"] = TONES[spec["tone"]]
    if spec["notice"]:
        spec["notice"]["palette"] = TONES[spec["notice"].get("tone", "neutral")]
    spec["preheader"] = preheader or spec["intro"]
    return spec
