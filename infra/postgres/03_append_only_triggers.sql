-- GENERATO da apps/governance/pg_append_only.py: non modificare a mano.
-- Trigger anti-modifica per audit e snapshot (GAP-E08). Idempotente.
BEGIN;
CREATE OR REPLACE FUNCTION app_append_only_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE owner_name name;
BEGIN
  SELECT pg_get_userbyid(c.relowner) INTO owner_name FROM pg_class c WHERE c.oid = TG_RELID;
  IF coalesce(current_setting('app.audit_maintenance', true), '') = 'on'
     AND pg_has_role(current_user, owner_name, 'MEMBER') THEN
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
  END IF;
  IF TG_OP = 'TRUNCATE' AND current_database() LIKE 'test\_%' THEN
    RETURN NULL;
  END IF;
  RAISE EXCEPTION 'Tabella append-only %: % non consentito', TG_TABLE_NAME, TG_OP
    USING ERRCODE = '42501';
END $$;

DROP TRIGGER IF EXISTS lesson_calendar_calendaraudit_append_only ON lesson_calendar_calendaraudit;
CREATE TRIGGER lesson_calendar_calendaraudit_append_only BEFORE UPDATE OR DELETE ON lesson_calendar_calendaraudit
  FOR EACH ROW EXECUTE FUNCTION app_append_only_guard();
DROP TRIGGER IF EXISTS lesson_calendar_calendaraudit_append_only_truncate ON lesson_calendar_calendaraudit;
CREATE TRIGGER lesson_calendar_calendaraudit_append_only_truncate BEFORE TRUNCATE ON lesson_calendar_calendaraudit
  FOR EACH STATEMENT EXECUTE FUNCTION app_append_only_guard();

DROP TRIGGER IF EXISTS governance_pathauditevent_append_only ON governance_pathauditevent;
CREATE TRIGGER governance_pathauditevent_append_only BEFORE UPDATE OR DELETE ON governance_pathauditevent
  FOR EACH ROW EXECUTE FUNCTION app_append_only_guard();
DROP TRIGGER IF EXISTS governance_pathauditevent_append_only_truncate ON governance_pathauditevent;
CREATE TRIGGER governance_pathauditevent_append_only_truncate BEFORE TRUNCATE ON governance_pathauditevent
  FOR EACH STATEMENT EXECUTE FUNCTION app_append_only_guard();

DROP TRIGGER IF EXISTS scheduling_planningaudit_append_only ON scheduling_planningaudit;
CREATE TRIGGER scheduling_planningaudit_append_only BEFORE UPDATE OR DELETE ON scheduling_planningaudit
  FOR EACH ROW EXECUTE FUNCTION app_append_only_guard();
DROP TRIGGER IF EXISTS scheduling_planningaudit_append_only_truncate ON scheduling_planningaudit;
CREATE TRIGGER scheduling_planningaudit_append_only_truncate BEFORE TRUNCATE ON scheduling_planningaudit
  FOR EACH STATEMENT EXECUTE FUNCTION app_append_only_guard();

DROP TRIGGER IF EXISTS scheduling_planningsnapshot_append_only ON scheduling_planningsnapshot;
CREATE TRIGGER scheduling_planningsnapshot_append_only BEFORE UPDATE OR DELETE ON scheduling_planningsnapshot
  FOR EACH ROW EXECUTE FUNCTION app_append_only_guard();
DROP TRIGGER IF EXISTS scheduling_planningsnapshot_append_only_truncate ON scheduling_planningsnapshot;
CREATE TRIGGER scheduling_planningsnapshot_append_only_truncate BEFORE TRUNCATE ON scheduling_planningsnapshot
  FOR EACH STATEMENT EXECUTE FUNCTION app_append_only_guard();

DROP TRIGGER IF EXISTS governance_auditevent_append_only ON governance_auditevent;
CREATE TRIGGER governance_auditevent_append_only BEFORE UPDATE OR DELETE ON governance_auditevent
  FOR EACH ROW EXECUTE FUNCTION app_append_only_guard();
DROP TRIGGER IF EXISTS governance_auditevent_append_only_truncate ON governance_auditevent;
CREATE TRIGGER governance_auditevent_append_only_truncate BEFORE TRUNCATE ON governance_auditevent
  FOR EACH STATEMENT EXECUTE FUNCTION app_append_only_guard();

DROP TRIGGER IF EXISTS privacy_retentionrun_append_only ON privacy_retentionrun;
CREATE TRIGGER privacy_retentionrun_append_only BEFORE UPDATE OR DELETE ON privacy_retentionrun
  FOR EACH ROW EXECUTE FUNCTION app_append_only_guard();
DROP TRIGGER IF EXISTS privacy_retentionrun_append_only_truncate ON privacy_retentionrun;
CREATE TRIGGER privacy_retentionrun_append_only_truncate BEFORE TRUNCATE ON privacy_retentionrun
  FOR EACH STATEMENT EXECUTE FUNCTION app_append_only_guard();

DROP TRIGGER IF EXISTS identity_identityauditevent_append_only ON identity_identityauditevent;
CREATE TRIGGER identity_identityauditevent_append_only BEFORE UPDATE OR DELETE ON identity_identityauditevent
  FOR EACH ROW EXECUTE FUNCTION app_append_only_guard();
DROP TRIGGER IF EXISTS identity_identityauditevent_append_only_truncate ON identity_identityauditevent;
CREATE TRIGGER identity_identityauditevent_append_only_truncate BEFORE TRUNCATE ON identity_identityauditevent
  FOR EACH STATEMENT EXECUTE FUNCTION app_append_only_guard();
DROP TRIGGER IF EXISTS identity_audit_no_update ON identity_identityauditevent;
COMMIT;
