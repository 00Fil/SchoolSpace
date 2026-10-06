"""s2-calendario: estende la protezione PostgreSQL (vedi 0002).

- calendar_assert_lesson: COMPLETED conserva le prenotazioni ed è verificata come PUBLISHED;
  una lezione di recupero (recovery_id) usa partecipanti e minuti dell'obbligo, che
  devono essere un sottoinsieme dell'unità canonica d'origine.
- lezioni COMPLETED immutabili nei campi operativi (trigger BEFORE UPDATE).
- CalendarAudit e AttendanceRevision append-only anche contro SQL diretto.
Su SQLite non installa nulla (pattern di 0002); i test PG sono marcati skip.
"""

import importlib
from django.db import migrations

_v1 = importlib.import_module("apps.calendar.migrations.0002_postgres_protection").SQL
ORIGINAL_FUNCTION = _v1[
    _v1.index("CREATE FUNCTION calendar_assert_lesson") : _v1.index(
        "CREATE FUNCTION calendar_check_trigger"
    )
].replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1)


def _v2_function():
    sql = ORIGINAL_FUNCTION
    replacements = [
        (
            "needs_space boolean; needs_video boolean; expected_students text[]; actual_students text[];",
            "needs_space boolean; needs_video boolean; expected_students text[]; actual_students text[];\n"
            " rec_minutes integer; rec_participants jsonb; rec_demand uuid;",
        ),
        (
            "IF l.state <> 'PUBLISHED' THEN",
            "IF l.state NOT IN ('PUBLISHED','COMPLETED') THEN",
        ),
        (
            "IF unit IS NULL OR (unit->>'subject')<>l.subject_id::text OR\n"
            "    l.end_at-l.start_at<>make_interval(mins=>(unit->>'duration_minutes')::integer) OR",
            "IF l.recovery_id IS NOT NULL THEN\n"
            "   SELECT minutes_remaining, participants, demand_id INTO rec_minutes, rec_participants, rec_demand\n"
            "   FROM lesson_calendar_recoveryobligation WHERE id=l.recovery_id;\n"
            "   IF rec_demand IS DISTINCT FROM l.demand_id OR unit IS NULL OR NOT ((unit->'participants') @> rec_participants) THEN\n"
            "     RAISE EXCEPTION 'Makeup lesson inconsistent with recovery obligation' USING ERRCODE='23514';\n"
            "   END IF;\n"
            " END IF;\n"
            " IF unit IS NULL OR (unit->>'subject')<>l.subject_id::text OR\n"
            "    l.end_at-l.start_at<>make_interval(mins=>COALESCE(rec_minutes,(unit->>'duration_minutes')::integer)) OR",
        ),
        (
            "SELECT array_agg(value ORDER BY value) INTO expected_students FROM jsonb_array_elements_text(unit->'participants');",
            "SELECT array_agg(value ORDER BY value) INTO expected_students FROM jsonb_array_elements_text(COALESCE(rec_participants, unit->'participants'));",
        ),
    ]
    for old, new in replacements:
        if old not in sql:
            raise RuntimeError("0002 function changed: cannot derive v2")
        sql = sql.replace(old, new, 1)
    return sql


SQL = (
    _v2_function()
    + """
CREATE OR REPLACE FUNCTION calendar_completed_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF OLD.state='COMPLETED' AND (NEW.state, NEW.start_at, NEW.end_at, NEW.tutor_id, NEW.mode, NEW.location,
     NEW.space_id, NEW.video_id, NEW.demand_id, NEW.tutor_occupied_until, NEW.completed_at)
   IS DISTINCT FROM (OLD.state, OLD.start_at, OLD.end_at, OLD.tutor_id, OLD.mode, OLD.location,
     OLD.space_id, OLD.video_id, OLD.demand_id, OLD.tutor_occupied_until, OLD.completed_at) THEN
  RAISE EXCEPTION 'Completed lesson is immutable' USING ERRCODE='23514';
 END IF; RETURN NEW;
END $$;
CREATE TRIGGER calendar_completed_immutable BEFORE UPDATE ON lesson_calendar_lessonoccurrence
 FOR EACH ROW EXECUTE FUNCTION calendar_completed_guard();
CREATE OR REPLACE FUNCTION calendar_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 RAISE EXCEPTION 'Append-only table %', TG_TABLE_NAME USING ERRCODE='23514';
END $$;
CREATE TRIGGER calendar_audit_append_only BEFORE UPDATE OR DELETE ON lesson_calendar_calendaraudit
 FOR EACH ROW EXECUTE FUNCTION calendar_append_only();
CREATE TRIGGER calendar_attendance_revision_append_only BEFORE UPDATE OR DELETE ON lesson_calendar_attendancerevision
 FOR EACH ROW EXECUTE FUNCTION calendar_append_only();
"""
)

REVERSE = (
    """
DROP TRIGGER IF EXISTS calendar_attendance_revision_append_only ON lesson_calendar_attendancerevision;
DROP TRIGGER IF EXISTS calendar_audit_append_only ON lesson_calendar_calendaraudit;
DROP FUNCTION IF EXISTS calendar_append_only();
DROP TRIGGER IF EXISTS calendar_completed_immutable ON lesson_calendar_lessonoccurrence;
DROP FUNCTION IF EXISTS calendar_completed_guard();
"""
    + ORIGINAL_FUNCTION
)


def install(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(SQL, params=None)


def remove(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(REVERSE, params=None)


class Migration(migrations.Migration):
    dependencies = [("lesson_calendar", "0004_series_recovery_attendance_conflicts")]
    operations = [migrations.RunPython(install, remove)]
