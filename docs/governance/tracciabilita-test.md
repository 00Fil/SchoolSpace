# Matrice di tracciabilità requisiti → test (FR / H / T / NFR)

| Campo | Valore |
|---|---|
| Stato | **BOZZA** — analisi manuale della suite; da trasformare in marcatori automatici controllati in CI (G1) |
| Versione | 0.1 — 2026-10-02, branch `s7-conformita` (baseline v0.7 + merge di `main` con lo stream s4-privacy) |
| GAP | **GAP-A04** (matrice di tracciabilità), GAP-M04 |
| Gate | G1 (matrice in CI), poi ogni gate |
| Responsabile | QA (R), architect (A) — [DA COMPILARE] |
| Riferimenti | Paper §2.1 (FR), §6.3 (H), §12.2 (T01–T42), §12.4 (tracciabilità); guida sez4-requisiti |

## 1. Metodo
- Fonte: `backend/tests/` (16 moduli). Elenco delle funzioni estratto con AST; numero dei casi da `pytest --collect-only`.
- Ogni test è stato letto per nome, parametri e asserzioni ed etichettato con i requisiti che **verifica direttamente**
  (non quelli solo attraversati). Etichette: `Txx`, `FRxx`, `Hxx`, `NFRxx`, `OBJ` (obiettivi), `D07`/`D09`, `PG` (eseguito solo su
  PostgreSQL), `GOV` (guardie di governance/flag sperimentali).
- Stato del caso T: 🟢 l'asserzione del paper è verificata; 🟡 verificata in parte o solo su PostgreSQL non eseguito; 🔴 nessun test.
- Limite: su SQLite i test PG sono skipped; per il paper "una fase non passa con un test critico non eseguito", quindi T18/T19
  e i trigger contano solo dopo la CI PostgreSQL (GAP-J05). I test degli stream s1, s2, s3, s8 non ancora integrati in `main`
  non sono inclusi: **rigenerare la matrice dopo ogni merge**.

## 2. Riepilogo quantitativo

| Modulo | Funzioni di test | Casi raccolti (con parametrize) |
|---|---|---|
| `test_api.py` | 21 | 27 |
| `test_calendar.py` | 34 | 47 |
| `test_database_planning.py` | 35 | 61 |
| `test_families_api.py` | 12 | 12 |
| `test_intervals.py` | 10 | 11 |
| `test_parentali.py` | 32 | 35 |
| `test_planning_api.py` | 6 | 6 |
| `test_planning_contracts.py` | 2 | 2 |
| `test_portals.py` | 6 | 6 |
| `test_privacy_exports.py` | 7 | 7 |
| `test_privacy_import.py` | 9 | 9 |
| `test_privacy_majority.py` | 7 | 7 |
| `test_privacy_postgres.py` | 6 | 7 |
| `test_privacy_retention.py` | 12 | 12 |
| `test_privacy_rights.py` | 9 | 9 |
| `test_solver.py` | 43 | 58 |
| **Totale** | **251** | **316** |

Test PostgreSQL-only (skipped su SQLite): 7 funzioni, 12 casi. Test di governance/flag (GOV): 9.

Copertura del catalogo T01–T42 su questo branch: **25 coperti, 11 parziali, 6 assenti** (stima della guida per la v0.7: 26 / 8 / 8).

## 3. Matrice T01–T42 → test

| T | Scenario | Stato | Funzioni (casi) | Test | Nota |
|---|---|---|---|---|---|
| T01 | Tutor non abilitato | 🟢 coperto | 3 (3) | `solver::test_dated_skill_must_cover_whole_lesson`, `solver::test_independent_validator_checks_skill_from_raw_snapshot`, `solver::test_unqualified_tutor_no_assignments` |  |
| T02 | 90 min in finestra da 60 | 🟢 coperto | 1 (1) | `solver::test_ninety_minutes_do_not_fit_sixty` |  |
| T03 | Gruppo, membro indisponibile | 🟢 coperto | 2 (2) | `intervals::test_intersection_all_participants`, `solver::test_all_group_participants_intersection` |  |
| T04 | Gruppo di tre in presenza | 🟢 coperto | 2 (2) | `parentali::test_physical_group_of_three_rejected`, `solver::test_group_three_not_split_in_presence` |  |
| T05 | Quarta lezione con tre spazi | 🟢 coperto | 1 (1) | `solver::test_four_simultaneous_lessons_cannot_use_three_spaces` |  |
| T06 | Tutor online+presenza sovrapposti | 🟢 coperto | 1 (1) | `solver::test_same_tutor_collision_across_modalities` |  |
| T07 | Studente in due gruppi | 🟢 coperto | 1 (1) | `solver::test_same_student_collision_across_groups_and_tutors` |  |
| T08 | Online dal tutor in sede | 🟢 coperto | 1 (1) | `solver::test_online_tutor_in_center_requires_configured_space` |  |
| T09 | Chiusura su apertura | 🟢 coperto | 4 (4) | `intervals::test_removal_prevails`, `solver::test_closure_overrides_service`, `solver::test_mode_specific_closure_does_not_close_online`, `solver::test_resource_specific_closure` |  |
| T10 | Disponibilità UNKNOWN | 🟢 coperto | 8 (10) | `api::test_readiness_not_fake`, `database_planning::test_draft_rule_approval_unblocks_bridge`, `database_planning::test_required_configuration_missing`, `intervals::test_declared_none`, `intervals::test_unknown_blocks`, `solver::test_missing_availability_is_blocked_not_infeasible`, `solver::test_none_is_not_unrestricted`, `solver::test_unreferenced_unknown_tutor_does_not_block` |  |
| T11 | Indicazioni incompatibili di due tutori | 🟡 parziale | 1 (1) | `database_planning::test_conflicting_family_data_blocks` | Blocco del preflight testato; manca la pratica di risoluzione (ConflictCase, s2) |
| T12 | DST 21/28 ottobre 2026 | 🟡 parziale | 4 (5) | `database_planning::test_autumn_dst_week_is_169_hours`, `database_planning::test_spring_dst_week_is_167_hours`, `intervals::test_dst_invalid_or_ambiguous`, `intervals::test_dst_local_hour_stable` | DST testato su settimane e ore locali; manca il caso letterale 21 e 28 ottobre 2026 16:00 → UTC 14/15 |
| T13 | EXDATE e run ripetuto | 🟡 parziale | 0 (0) | — | Non duplicazione delle lezioni pubblicate sì; EXDATE assente (LessonSeries, s2) |
| T14 | Questa e successive | 🔴 assente | 1 (1) | `calendar::test_existing_lesson_started_cannot_be_changed` | Solo il blocco delle lezioni iniziate; nessuna segmentazione di serie (s2) |
| T15 | Limite giornaliero in minuti | 🟢 coperto | 2 (2) | `solver::test_daily_load_in_minutes`, `solver::test_weekly_load_in_minutes` |  |
| T16 | Transizione remoto/sede | 🟢 coperto | 1 (1) | `solver::test_transition_not_instant_and_pause_not_double_counted` |  |
| T17 | Import ripetuto | 🟢 coperto | 9 (9) | `privacy_import::test_command_and_api`, `privacy_import::test_conflict_when_student_key_changes_family`, `privacy_import::test_dry_run_writes_nothing_and_never_invites`, `privacy_import::test_execute_is_idempotent`, `privacy_import::test_header_and_version_checks`, `privacy_import::test_invites_only_on_execute_with_flag_and_once`, `privacy_import::test_unverified_links_get_no_invites`, `privacy_import::test_validation_errors_block_everything`, `privacy_import::test_versioned_template_file_matches_definition` | Coperto dai test s4 (dry-run senza inviti, idempotenza); manca la rigenerazione della domanda dopo import |
| T18 | Due piani stessa revisione | 🟢 coperto | 4 (7) | `calendar::test_concurrent_publications_single_commit`, `calendar::test_publish_guards_no_writes`, `calendar::test_second_plan_same_revision_becomes_stale`, `calendar::test_stale_plan_after_input_change` | Il caso concorrente reale è PG-only (skipped su SQLite) |
| T19 | Spostamenti concorrenti | 🟡 parziale | 3 (3) | `calendar::test_concurrent_cancellation_single_version_change`, `calendar::test_move_collision_never_changes_calendar`, `calendar::test_postgres_exclusion_rejects_raw_collision` | Constraint DB e cancellazioni concorrenti solo su PostgreSQL (skipped); su SQLite solo collisione sequenziale |
| T20 | Replay stesso comando | 🟢 coperto | 6 (6) | `calendar::test_api_missing_publish_key`, `calendar::test_api_publish_replay_and_plan_state`, `calendar::test_replay_exact_response_single_effect`, `database_planning::test_duplicate_worker_delivery_single_attempt`, `database_planning::test_replay_returns_same_run_without_duplicate_demand`, `parentali::test_exact_replay_returns_original_even_after_version_changed` |  |
| T21 | Stessa chiave, body diverso | 🟢 coperto | 3 (3) | `calendar::test_same_key_different_body_rejected`, `database_planning::test_key_body_mismatch`, `parentali::test_same_key_different_body_conflicts` |  |
| T22 | Crash dopo commit prima di accodare | 🔴 assente | 0 (0) | — | Outbox non presente su questo branch (stream s3) |
| T23 | Delivery ambigua | 🔴 assente | 0 (0) | — | Stream s3 |
| T24 | ID altrui in liste/dettaglio/FK/export/link | 🟡 parziale | 21 (25) | `api::test_anonymous_denied`, `api::test_family_is_not_access_scope`, `api::test_governance_center_only`, `api::test_readonly_guardian_cannot_write`, `api::test_student_only_self`, `api::test_tutor_only_own_availability`, `api::test_unauthorized_foreign_key`, `calendar::test_family_cannot_read_experimental_calendar`, `database_planning::test_family_denied`, `families_api::test_non_center_cannot_use_registry`, `parentali::test_family_summary_only_own_child`, `parentali::test_group_request_does_not_leak_other_participants`, `parentali::test_guardian_cannot_manage_cohort_or_derive`, `planning_api::test_simulation_center_only`, `portals::test_guardian_sees_children_and_hides_other_names`, `portals::test_my_lessons_guards`, `portals::test_student_sees_only_own_lessons`, `portals::test_tutor_sees_only_own_lessons`, `privacy_exports::test_wrong_audience_bad_token_and_expiry_are_denied_and_audited`, `privacy_retention::test_retention_api_permissions_and_flow`, `privacy_rights::test_request_api_validation_and_permissions` | Liste, dettaglio, FK diretti, export protetti; mancano FK annidate su tutte le relazioni, link video, ICS (GAP-B08, s1/s3) |
| T25 | Delega revocata con sessione valida | 🟢 coperto | 10 (10) | `api::test_expired_guardian_link`, `api::test_inactive_user_scope_empty`, `api::test_revocation_immediate`, `api::test_role_revocation_removes_scope`, `calendar::test_stale_actor_object_cannot_cancel_after_revocation`, `database_planning::test_actor_revoked`, `families_api::test_guardian_link_create_verify_revoke_controls_scope`, `families_api::test_student_deactivation_disables_student_account`, `parentali::test_revocation_hides_whole_path`, `portals::test_revoked_link_and_roleless_account_see_nothing` |  |
| T26 | Parziale con mandatory scoperta | 🟢 coperto | 3 (3) | `calendar::test_partial_acceptance_cannot_override_mandatory`, `calendar::test_partial_requires_exact_acceptance_and_reason`, `solver::test_mandatory_cannot_be_dropped_for_higher_priority_optional` |  |
| T27 | Ricerca senza prova | 🟢 coperto | 5 (6) | `database_planning::test_successful_job_is_not_mathematical_success`, `solver::test_budget_expires_after_proven_level_keeps_valid_incumbent`, `solver::test_candidate_limit_blocks_without_false_impossibility`, `solver::test_feasible_level_stops_without_claiming_lower_optimality`, `solver::test_unknown_is_not_infeasible` |  |
| T28 | Modello invalido | 🟢 coperto | 4 (9) | `database_planning::test_no_silent_relaxation`, `database_planning::test_technical_failure_does_not_expose_exception`, `solver::test_family_or_curriculum_constraint_not_silently_relaxed`, `solver::test_invalid_model_is_technical_failure` |  |
| T29 | Soluzione manomessa | 🟢 coperto | 8 (11) | `calendar::test_independent_validator_rejects_before_creation`, `calendar::test_plan_result_integrity`, `calendar::test_snapshot_revalidated_not_trusting_assignment_status`, `solver::test_independent_validator_checks_skill_from_raw_snapshot`, `solver::test_independent_validator_detects_malformed_duration`, `solver::test_independent_validator_detects_overlap_and_missing_mandatory`, `solver::test_validation_failure_discards_solver_output`, `solver::test_validator_handles_malformed_result_without_crashing` |  |
| T30 | Presenze in gruppo | 🔴 assente | 0 (0) | — | Attendance non presente su questo branch (stream s2) |
| T31 | Coorte e curriculum | 🟡 parziale | 3 (3) | `parentali::test_complete_program_generates_canonical_requests`, `parentali::test_individual_and_group_same_subject_not_double_counted`, `parentali::test_sequential_blocks_do_not_sum_weekly_minutes` | Monte minuti senza doppio conteggio sì; riconciliazione con presenze no |
| T32 | Restore precedente a revoca | 🟡 parziale | 3 (3) | `privacy_retention::test_executed_run_goes_to_external_ledger`, `privacy_rights::test_restore_reconciliation_reapplies_erasure_and_revocation`, `privacy_rights::test_tampered_ledger_blocks_reconciliation` | Riconciliazione da ledger testata (s4); manca la prova di restore reale e il controllo dell'outbox |
| T33 | 390 px, zoom, tastiera, screen reader | 🔴 assente | 0 (0) | — | Nessun test backend; evidenza axe nel frontend, verifica manuale assente |
| T34 | Benchmark 20 run | 🔴 assente | 0 (0) | — | Stream s8 |
| T35 | Enum sconosciuti, campi extra, timestamp naive | 🟢 coperto | 15 (43) | `api::test_invalid_payload_rejected`, `calendar::test_api_publish_closed_payload`, `database_planning::test_closure_requires_explicit_offset_and_minute`, `database_planning::test_config_strict_fields`, `database_planning::test_configuration_root_array_rejected`, `database_planning::test_invalid_idempotency_key`, `database_planning::test_monday_required`, `intervals::test_naive_rejected`, `parentali::test_derive_payload_strict`, `planning_api::test_example_is_synthetic_and_schema_closed`, `planning_contracts::test_output_fixture_and_live_solver_match_result_contract`, `planning_contracts::test_runtime_input_schema_matches_documented_fixture`, `privacy_import::test_header_and_version_checks`, `solver::test_invalid_or_unsupported_dto_rejected`, `solver::test_nonfinite_budget_rejected` |  |
| T36 | Fine = inizio successivo | 🟢 coperto | 3 (3) | `intervals::test_adjacent_merged`, `intervals::test_boundary_not_overlap`, `solver::test_adjacent_lessons_zero_pause_allowed_and_pause_enforced` |  |
| T37 | Cambi membri nel futuro | 🟡 parziale | 1 (1) | `parentali::test_dated_membership_change_requires_segmentation` | Segmentazione richiesta; manca la rivalidazione delle unità future con partecipanti storici invariati |
| T38 | Durata fuori catalogo | 🟡 parziale | 2 (14) | `solver::test_independent_validator_detects_malformed_duration`, `solver::test_invalid_or_unsupported_dto_rejected` | DTO rifiuta 75 min; catalogo non persistente (GAP-C01) |
| T39 | Input modificati dopo lo snapshot | 🟢 coperto | 8 (17) | `calendar::test_stale_plan_after_input_change`, `database_planning::test_change_during_search_returns_stale_plan`, `database_planning::test_expected_revision_rejected_before_writes`, `database_planning::test_revision_tracks_source_mutations`, `database_planning::test_snapshot_immutable`, `database_planning::test_snapshot_integrity_checked_before_search`, `database_planning::test_stale_queued_job_never_solves`, `solver::test_input_not_mutated_and_hash_stable` |  |
| T40 | Cancellazione e recupero ripetuti | 🟡 parziale | 3 (3) | `calendar::test_cancel_frees_only_own_bookings_retains_history`, `calendar::test_cancel_reopens_same_canonical_unit`, `calendar::test_concurrent_cancellation_single_version_change` | Cancellazione e riapertura della stessa unità sì; RecoveryObligation assente (s2) |
| T41 | Nuova assenza su lezione pubblicata | 🟡 parziale | 1 (1) | `calendar::test_unavailable_published_lesson_never_disappears` | La lezione non sparisce; nessuna pratica aperta (s2) |
| T42 | Audit/export con segreti artificiali | 🟢 coperto | 8 (8) | `families_api::test_invitation_single_use_and_secret_never_audited`, `privacy_exports::test_api_download_revoke_and_listing`, `privacy_exports::test_file_is_private_and_only_hashes_stored`, `privacy_exports::test_integrity_check`, `privacy_exports::test_single_use_download_then_file_removed`, `privacy_exports::test_wrong_audience_bad_token_and_expiry_are_denied_and_audited`, `privacy_retention::test_redaction_of_synthetic_secrets`, `privacy_rights::test_access_export_json_and_csv` | Coperto dai test s4 (redazione, export protetti) |

## 4. Matrice FR01–FR24 → test

| FR | T prescritti (paper §12.4) | Funzioni marcate direttamente | Casi | T prescritti senza copertura piena |
|---|---|---|---|---|
| FR01 | T24, T25 | 15 | 15 | T24 |
| FR02 | T24, T25 | 10 | 10 | T24 |
| FR03 | T01 | 2 | 2 | — |
| FR04 | T04, T05 | 3 | 3 | — |
| FR05 | T09–T11 | 7 | 10 | T11 |
| FR06 | T09–T11 | 12 | 18 | T11 |
| FR07 | T26 | 3 | 3 | — |
| FR08 | T03, T04, T30, T37 | 8 | 8 | T30, T37 |
| FR09 | T02, T38 | 2 | 14 | T38 |
| FR10 | T12–T14 | 5 | 6 | T12, T13, T14 |
| FR11 | T27, T39 | 19 | 29 | — |
| FR12 | T05–T08, T16, T19 | 8 | 12 | T19 |
| FR13 | T27, T28 | 4 | 5 | — |
| FR14 | T24 | 2 | 3 | T24 |
| FR15 | T18–T21, T39 | 13 | 18 | T19 |
| FR16 | T19, T36 | 5 | 8 | T19 |
| FR17 | T14, T40, T41 | 5 | 8 | T14, T40, T41 |
| FR18 | T14, T40, T41 | 1 | 1 | T14, T40, T41 |
| FR19 | T24, T33 | 10 | 10 | T24, T33 |
| FR20 | T22, T23 | 0 | 0 | T22, T23 |
| FR21 | T30 | 0 | 0 | T30 |
| FR22 | T31 | 21 | 24 | T31 |
| FR23 | T17, T20, T32, T42 | 14 | 15 | T32 |
| FR24 | T17, T20, T32, T42 | 25 | 25 | T32 |

## 5. Vincoli H01–H12 e obiettivi

| H | Funzioni | Test |
|---|---|---|
| H01 | 0 | — |
| H02 | 2 | `solver::test_dated_skill_must_cover_whole_lesson`, `solver::test_unqualified_tutor_no_assignments` |
| H03 | 2 | `solver::test_all_group_participants_intersection`, `solver::test_ninety_minutes_do_not_fit_sixty` |
| H04 | 2 | `solver::test_same_student_collision_across_groups_and_tutors`, `solver::test_same_tutor_collision_across_modalities` |
| H05 | 2 | `solver::test_group_three_not_split_in_presence`, `solver::test_online_group_capacity_separate_and_remote_no_space` |
| H06 | 3 | `solver::test_cleanup_buffer_occupies_space`, `solver::test_four_simultaneous_lessons_cannot_use_three_spaces`, `solver::test_online_tutor_in_center_requires_configured_space` |
| H07 | 1 | `solver::test_exclusive_video_channels_parallelism` |
| H08 | 4 | `calendar::test_published_lessons_reconciled_locked_not_duplicated`, `solver::test_conflicting_locks_not_silently_moved`, `solver::test_illegal_lock_blocks_before_solving`, `solver::test_locked_assignment_preserved_even_if_optional` |
| H09 | 2 | `calendar::test_partial_acceptance_cannot_override_mandatory`, `solver::test_mandatory_cannot_be_dropped_for_higher_priority_optional` |
| H10 | 3 | `solver::test_adjacent_lessons_zero_pause_allowed_and_pause_enforced`, `solver::test_daily_load_in_minutes`, `solver::test_weekly_load_in_minutes` |
| H11 | 3 | `database_planning::test_no_silent_relaxation`, `solver::test_family_or_curriculum_constraint_not_silently_relaxed`, `solver::test_transition_not_instant_and_pause_not_double_counted` |
| H12 | 0 | — |
| OBJ | 2 | `solver::test_lexicographic_priority_above_lower_beneficiary_count`, `solver::test_same_priority_counts_minutes_per_beneficiary` |

H01 (una alternativa per unità) è verificato implicitamente dal validatore (`T29`) e da `test_real_cp_sat_demo_valid_complete`; H12 non ha test (non implementato). OBJ = vettore lessicografico: coperti solo U_P0–U_P2.

## 6. NFR e decisioni

| Voce | Funzioni | Test |
|---|---|---|
| NFR01 | 6 | `api::test_database_xor_constraint`, `calendar::test_failure_mid_batch_rolls_back_all_effects`, `calendar::test_postgres_trigger_rejects_corruption`, `parentali::test_minute_database_constraint`, `parentali::test_target_database_xor_constraint`, `solver::test_real_cp_sat_demo_valid_complete` |
| NFR04 | 4 | `planning_api::test_busy_simulation_returns_retry_after`, `solver::test_budget_expires_after_proven_level_keeps_valid_incumbent`, `solver::test_candidate_limit_blocks_without_false_impossibility`, `solver::test_feasible_level_stops_without_claiming_lower_optimality` |
| NFR06 | 4 | `api::test_login_requires_csrf`, `api::test_provisional_login_disabled_in_production`, `api::test_session_login_and_logout`, `privacy_postgres::test_role_scripts_cover_least_privilege` |
| NFR08 | 2 | `api::test_seed_idempotent`, `privacy_postgres::test_generated_trigger_script_is_in_sync` |
| D07 | 7 | `privacy_majority::test_adult_student_reconfirms_or_declines`, `privacy_majority::test_api_and_command`, `privacy_majority::test_flags_without_silent_revocation`, `privacy_majority::test_majority_date_handles_leap_day`, `privacy_majority::test_minor_not_flagged`, `privacy_majority::test_overdue_report_only_by_default`, `privacy_majority::test_overdue_suspend_is_audited` |
| D09 | 13 | `privacy_exports::test_orphan_files_are_swept`, `privacy_exports::test_retention_purges_expired_files`, `privacy_postgres::test_postgres_owner_maintenance_mode_allows_governed_minimization`, `privacy_retention::test_audit_minimization_after_approval`, `privacy_retention::test_command_defaults_to_dry_run`, `privacy_retention::test_default_matrix_is_seeded_as_to_be_approved`, `privacy_retention::test_dry_run_counts_without_changes_and_signs_receipt`, `privacy_retention::test_executed_run_goes_to_external_ledger`, `privacy_retention::test_execution_requires_approval`, `privacy_retention::test_invitations_purge_keeps_pending_valid`, `privacy_retention::test_policy_update_resets_approval_and_validates`, `privacy_retention::test_retention_api_permissions_and_flow`, `privacy_retention::test_revoked_accounts_are_minimized` |

NFR02, NFR03, NFR05, NFR07: nessun test automatico nel backend (carico, prestazioni UI, restore, accessibilità manuale).

## 7. Indice completo test → etichette


### `tests/test_api.py`

| Test | Casi | Etichette |
|---|---|---|
| `test_anonymous_denied` | 1 | T24 FR01 |
| `test_family_is_not_access_scope` | 1 | T24 FR01 FR02 |
| `test_revocation_immediate` | 1 | T25 FR01 |
| `test_unauthorized_foreign_key` | 1 | T24 FR19 |
| `test_guardian_creates_only_draft` | 1 | FR06 |
| `test_invalid_payload_rejected` | 7 | T35 FR06 |
| `test_readonly_guardian_cannot_write` | 1 | T24 FR02 |
| `test_role_revocation_removes_scope` | 1 | T25 FR01 |
| `test_tutor_only_own_availability` | 1 | T24 FR06 |
| `test_readiness_not_fake` | 1 | T10 FR06 |
| `test_seed_idempotent` | 1 | FR04 NFR08 |
| `test_database_xor_constraint` | 1 | FR06 NFR01 |
| `test_login_requires_csrf` | 1 | NFR06 |
| `test_session_login_and_logout` | 1 | FR01 NFR06 |
| `test_provisional_login_disabled_in_production` | 1 | NFR06 |
| `test_expired_guardian_link` | 1 | T25 FR02 |
| `test_unverified_guardian_link` | 1 | FR01 FR02 |
| `test_student_only_self` | 1 | T24 FR19 |
| `test_governance_center_only` | 1 | T24 |
| `test_g1_flag_does_not_implement_solver` | 1 | GOV |
| `test_inactive_user_scope_empty` | 1 | T25 FR01 |

### `tests/test_calendar.py`

| Test | Casi | Etichette |
|---|---|---|
| `test_atomic_six_lessons_all_bookings` | 1 | FR15 FR12 |
| `test_replay_exact_response_single_effect` | 1 | T20 FR15 |
| `test_same_key_different_body_rejected` | 1 | T21 FR15 |
| `test_publish_guards_no_writes` | 4 | T18 FR15 |
| `test_stale_plan_after_input_change` | 1 | T39 T18 FR15 |
| `test_snapshot_revalidated_not_trusting_assignment_status` | 1 | T29 FR15 |
| `test_plan_result_integrity` | 1 | T29 FR11 |
| `test_failure_mid_batch_rolls_back_all_effects` | 1 | FR15 NFR01 |
| `test_independent_validator_rejects_before_creation` | 1 | T29 FR12 |
| `test_second_plan_same_revision_becomes_stale` | 1 | T18 FR15 |
| `test_published_lessons_reconciled_locked_not_duplicated` | 1 | H08 FR15 |
| `test_unavailable_published_lesson_never_disappears` | 1 | T41 FR18 |
| `test_cancel_frees_only_own_bookings_retains_history` | 1 | T40 FR17 |
| `test_cancel_reopens_same_canonical_unit` | 1 | T40 FR17 |
| `test_move_keeps_identity_and_moves_bookings_atomically` | 1 | FR16 |
| `test_invalid_change_rollback` | 4 | FR16 FR17 |
| `test_move_collision_never_changes_calendar` | 1 | T19 FR16 |
| `test_move_rejection_reports_specific_codes` | 1 | FR16 |
| `test_reschedule_options_read_only` | 1 | FR16 |
| `test_existing_lesson_started_cannot_be_changed` | 1 | FR17 T14 |
| `test_family_cannot_read_experimental_calendar` | 2 | T24 FR14 |
| `test_calendar_api_range_and_revision` | 1 | FR19 |
| `test_api_publish_replay_and_plan_state` | 1 | T20 FR15 |
| `test_api_publish_closed_payload` | 3 | T35 FR15 |
| `test_api_missing_publish_key` | 1 | T20 FR15 |
| `test_normal_sqlite_publication_disabled` | 1 | GOV |
| `test_production_calendar_guard` | 1 | GOV |
| `test_postgres_exclusion_rejects_raw_collision` | 1 | T19 FR12 PG |
| `test_postgres_trigger_rejects_corruption` | 5 | FR12 NFR01 PG |
| `test_concurrent_publications_single_commit` | 1 | T18 FR15 PG |
| `test_partial_requires_exact_acceptance_and_reason` | 1 | T26 FR07 |
| `test_partial_acceptance_cannot_override_mandatory` | 1 | T26 H09 |
| `test_stale_actor_object_cannot_cancel_after_revocation` | 1 | T25 FR17 |
| `test_concurrent_cancellation_single_version_change` | 1 | T19 T40 PG |

### `tests/test_database_planning.py`

| Test | Casi | Etichette |
|---|---|---|
| `test_bridge_materializes_six_minimized_units` | 1 | FR11 |
| `test_no_silent_relaxation` | 6 | T28 H11 |
| `test_required_configuration_missing` | 3 | T10 FR05 |
| `test_conflicting_family_data_blocks` | 1 | T11 FR06 |
| `test_monday_required` | 1 | T35 |
| `test_autumn_dst_week_is_169_hours` | 1 | T12 FR10 |
| `test_revision_tracks_source_mutations` | 4 | T39 FR11 |
| `test_snapshot_immutable` | 6 | T39 FR11 |
| `test_replay_returns_same_run_without_duplicate_demand` | 1 | T20 FR11 |
| `test_key_body_mismatch` | 1 | T21 |
| `test_invalid_idempotency_key` | 3 | T35 |
| `test_expected_revision_rejected_before_writes` | 1 | T39 |
| `test_stale_queued_job_never_solves` | 1 | T39 FR11 |
| `test_change_during_search_returns_stale_plan` | 1 | T39 FR11 |
| `test_duplicate_worker_delivery_single_attempt` | 1 | T20 FR11 |
| `test_cancel_queued_job_idempotent` | 1 | FR11 |
| `test_cancel_running_discards_result` | 1 | FR11 |
| `test_actor_revoked` | 1 | T25 |
| `test_broker_failure_leaves_durable_pending` | 1 | FR11 |
| `test_lease_reconciliation` | 2 | FR11 |
| `test_technical_failure_does_not_expose_exception` | 1 | T28 FR13 |
| `test_successful_job_is_not_mathematical_success` | 2 | T27 FR13 |
| `test_family_denied` | 4 | T24 |
| `test_api_run_poll_and_readiness` | 1 | FR11 |
| `test_config_version_guard` | 1 | FR11 |
| `test_availability_approval_version_and_author` | 1 | FR06 |
| `test_config_strict_fields` | 3 | T35 |
| `test_development_flag_blocks_new_jobs` | 1 | GOV |
| `test_snapshot_integrity_checked_before_search` | 2 | T39 FR11 |
| `test_draft_rule_approval_unblocks_bridge` | 1 | T10 FR06 |
| `test_spring_dst_week_is_167_hours` | 1 | T12 FR10 |
| `test_closure_requires_explicit_offset_and_minute` | 2 | T35 FR05 |
| `test_configuration_root_array_rejected` | 1 | T35 |
| `test_source_readiness_is_not_gate_approval` | 1 | GOV |
| `test_seed_default_week_is_multi_day_and_idempotent` | 1 | FR05 |

### `tests/test_families_api.py`

| Test | Casi | Etichette |
|---|---|---|
| `test_non_center_cannot_use_registry` | 1 | T24 FR02 |
| `test_family_and_student_lifecycle_is_audited` | 1 | FR02 FR23 |
| `test_guardian_link_create_verify_revoke_controls_scope` | 1 | T25 FR02 |
| `test_two_guardians_same_student_different_rights` | 1 | FR02 |
| `test_student_cannot_self_delegate` | 1 | FR01 |
| `test_invitation_single_use_and_secret_never_audited` | 1 | FR01 T42 |
| `test_expired_and_revoked_invitations` | 1 | FR01 |
| `test_new_invitation_supersedes_pending` | 1 | FR01 |
| `test_link_list_filters_and_detail` | 1 | FR02 |
| `test_student_deactivation_disables_student_account` | 1 | FR24 T25 |
| `test_admin_actions_are_audited` | 1 | FR23 |
| `test_guardian_link_rows_unique_active_per_pair` | 1 | FR02 |

### `tests/test_intervals.py`

| Test | Casi | Etichette |
|---|---|---|
| `test_adjacent_merged` | 1 | T36 |
| `test_removal_prevails` | 1 | T09 FR05 |
| `test_intersection_all_participants` | 1 | T03 FR08 |
| `test_boundary_not_overlap` | 1 | T36 FR12 |
| `test_unknown_blocks` | 1 | T10 FR06 |
| `test_declared_none` | 1 | T10 FR06 |
| `test_dst_local_hour_stable` | 1 | T12 FR10 |
| `test_dst_invalid_or_ambiguous` | 2 | T12 FR10 |
| `test_horizon_end_exclusive` | 1 | FR10 |
| `test_naive_rejected` | 1 | T35 |

### `tests/test_parentali.py`

| Test | Casi | Etichette |
|---|---|---|
| `test_complete_program_generates_canonical_requests` | 1 | T31 FR22 |
| `test_exact_replay_returns_original_even_after_version_changed` | 1 | T20 FR22 |
| `test_new_key_does_not_duplicate` | 1 | FR22 |
| `test_same_key_different_body_conflicts` | 1 | T21 FR22 |
| `test_stale_version_no_partial_writes` | 1 | FR22 |
| `test_missing_key_rejected` | 1 | FR22 |
| `test_derive_payload_strict` | 4 | T35 FR22 |
| `test_missing_subject_blocks_entire_derivation` | 1 | FR22 |
| `test_partial_period_not_complete_program` | 1 | FR22 |
| `test_individual_and_group_same_subject_not_double_counted` | 1 | T31 FR22 |
| `test_physical_group_of_three_rejected` | 1 | T04 FR08 |
| `test_online_capacity_must_be_explicit` | 1 | FR08 |
| `test_online_capacity_separate_from_physical` | 1 | FR08 |
| `test_group_must_be_approved` | 1 | FR08 |
| `test_dated_membership_change_requires_segmentation` | 1 | T37 FR08 |
| `test_short_enrollment_cannot_cover_block` | 1 | FR22 |
| `test_no_required_subjects_cannot_derive` | 1 | FR22 |
| `test_minute_database_constraint` | 1 | FR22 NFR01 |
| `test_target_database_xor_constraint` | 1 | FR22 NFR01 |
| `test_api_invalid_block_rolled_back` | 1 | FR22 |
| `test_program_frozen_after_derivation` | 1 | FR22 |
| `test_source_tampering_is_not_silently_overwritten` | 1 | FR22 |
| `test_family_summary_only_own_child` | 1 | T24 FR19 |
| `test_group_request_does_not_leak_other_participants` | 1 | T24 FR19 |
| `test_guardian_cannot_manage_cohort_or_derive` | 1 | T24 |
| `test_revocation_hides_whole_path` | 1 | T25 |
| `test_sequential_blocks_do_not_sum_weekly_minutes` | 1 | T31 FR22 |
| `test_create_path_requires_declared_subjects` | 1 | FR22 |
| `test_create_enrollment_touches_version_and_audit` | 1 | FR23 FR22 |
| `test_scope_clarification_does_not_sign_g1` | 1 | GOV |
| `test_optional_demo_is_idempotent_and_synthetic` | 1 | FR22 |
| `test_record_scope_does_not_downgrade_approved_decision` | 1 | GOV |

### `tests/test_planning_api.py`

| Test | Casi | Etichette |
|---|---|---|
| `test_simulation_api_real_solver_no_database_writes` | 1 | FR14 |
| `test_example_is_synthetic_and_schema_closed` | 1 | T35 |
| `test_simulation_center_only` | 1 | T24 |
| `test_simulation_disabled_outside_development` | 1 | GOV |
| `test_busy_simulation_returns_retry_after` | 1 | NFR04 |
| `test_operation_jobs_still_not_implemented` | 1 | GOV |

### `tests/test_planning_contracts.py`

| Test | Casi | Etichette |
|---|---|---|
| `test_runtime_input_schema_matches_documented_fixture` | 1 | T35 FR11 |
| `test_output_fixture_and_live_solver_match_result_contract` | 1 | T35 FR11 |

### `tests/test_portals.py`

| Test | Casi | Etichette |
|---|---|---|
| `test_seed_portal_accounts_are_unusable_and_idempotent` | 1 | FR01 |
| `test_tutor_sees_only_own_lessons` | 1 | T24 FR19 |
| `test_guardian_sees_children_and_hides_other_names` | 1 | T24 FR19 |
| `test_student_sees_only_own_lessons` | 1 | T24 FR19 |
| `test_revoked_link_and_roleless_account_see_nothing` | 1 | T25 FR19 |
| `test_my_lessons_guards` | 1 | T24 FR19 |

### `tests/test_privacy_exports.py`

| Test | Casi | Etichette |
|---|---|---|
| `test_file_is_private_and_only_hashes_stored` | 1 | T42 FR24 |
| `test_single_use_download_then_file_removed` | 1 | T42 FR24 |
| `test_wrong_audience_bad_token_and_expiry_are_denied_and_audited` | 1 | T42 T24 FR24 |
| `test_integrity_check` | 1 | T42 FR24 |
| `test_api_download_revoke_and_listing` | 1 | T42 FR24 |
| `test_retention_purges_expired_files` | 1 | FR24 D09 |
| `test_orphan_files_are_swept` | 1 | FR24 D09 |

### `tests/test_privacy_import.py`

| Test | Casi | Etichette |
|---|---|---|
| `test_versioned_template_file_matches_definition` | 1 | T17 FR24 |
| `test_dry_run_writes_nothing_and_never_invites` | 1 | T17 FR24 |
| `test_execute_is_idempotent` | 1 | T17 FR24 |
| `test_invites_only_on_execute_with_flag_and_once` | 1 | T17 FR24 |
| `test_unverified_links_get_no_invites` | 1 | T17 FR01 |
| `test_validation_errors_block_everything` | 1 | T17 FR24 |
| `test_header_and_version_checks` | 1 | T17 T35 |
| `test_conflict_when_student_key_changes_family` | 1 | T17 FR24 |
| `test_command_and_api` | 1 | T17 FR24 |

### `tests/test_privacy_majority.py`

| Test | Casi | Etichette |
|---|---|---|
| `test_majority_date_handles_leap_day` | 1 | D07 |
| `test_minor_not_flagged` | 1 | D07 |
| `test_flags_without_silent_revocation` | 1 | D07 FR01 |
| `test_overdue_report_only_by_default` | 1 | D07 |
| `test_overdue_suspend_is_audited` | 1 | D07 FR23 |
| `test_adult_student_reconfirms_or_declines` | 1 | D07 FR01 |
| `test_api_and_command` | 1 | D07 |

### `tests/test_privacy_postgres.py`

| Test | Casi | Etichette |
|---|---|---|
| `test_generated_trigger_script_is_in_sync` | 1 | FR23 NFR08 |
| `test_table_names_match_models` | 1 | FR23 |
| `test_role_scripts_cover_least_privilege` | 1 | FR23 NFR06 |
| `test_postgres_trigger_blocks_raw_modification` | 2 | FR23 PG |
| `test_postgres_triggers_installed_on_all_tables` | 1 | FR23 PG |
| `test_postgres_owner_maintenance_mode_allows_governed_minimization` | 1 | FR23 D09 PG |

### `tests/test_privacy_retention.py`

| Test | Casi | Etichette |
|---|---|---|
| `test_default_matrix_is_seeded_as_to_be_approved` | 1 | D09 |
| `test_dry_run_counts_without_changes_and_signs_receipt` | 1 | D09 FR24 |
| `test_execution_requires_approval` | 1 | D09 |
| `test_executed_run_goes_to_external_ledger` | 1 | D09 T32 |
| `test_policy_update_resets_approval_and_validates` | 1 | D09 |
| `test_retention_api_permissions_and_flow` | 1 | D09 T24 |
| `test_invitations_purge_keeps_pending_valid` | 1 | D09 |
| `test_revoked_accounts_are_minimized` | 1 | D09 FR24 |
| `test_audit_minimization_after_approval` | 1 | D09 FR23 |
| `test_command_defaults_to_dry_run` | 1 | D09 |
| `test_audit_event_is_append_only` | 1 | FR23 |
| `test_redaction_of_synthetic_secrets` | 1 | T42 FR23 |

### `tests/test_privacy_rights.py`

| Test | Casi | Etichette |
|---|---|---|
| `test_request_register_deadlines_and_extension` | 1 | FR24 |
| `test_access_export_json_and_csv` | 1 | FR24 T42 |
| `test_portability_requires_json_and_account_export` | 1 | FR24 |
| `test_rectification_is_audited` | 1 | FR24 FR23 |
| `test_erasure_anonymizes_and_register_survives` | 1 | FR24 |
| `test_restore_reconciliation_reapplies_erasure_and_revocation` | 1 | T32 FR24 |
| `test_tampered_ledger_blocks_reconciliation` | 1 | T32 |
| `test_manual_close_and_reject` | 1 | FR24 |
| `test_request_api_validation_and_permissions` | 1 | FR24 T24 |

### `tests/test_solver.py`

| Test | Casi | Etichette |
|---|---|---|
| `test_real_cp_sat_demo_valid_complete` | 1 | FR11 NFR01 |
| `test_input_not_mutated_and_hash_stable` | 1 | T39 FR11 |
| `test_invalid_or_unsupported_dto_rejected` | 13 | T35 T38 FR09 |
| `test_missing_availability_is_blocked_not_infeasible` | 1 | T10 FR06 |
| `test_unreferenced_unknown_tutor_does_not_block` | 1 | T10 |
| `test_none_is_not_unrestricted` | 1 | T10 FR06 |
| `test_family_or_curriculum_constraint_not_silently_relaxed` | 1 | T28 H11 |
| `test_unqualified_tutor_no_assignments` | 1 | T01 FR03 H02 |
| `test_dated_skill_must_cover_whole_lesson` | 1 | T01 FR03 H02 |
| `test_ninety_minutes_do_not_fit_sixty` | 1 | T02 FR09 H03 |
| `test_all_group_participants_intersection` | 1 | T03 FR08 H03 |
| `test_group_three_not_split_in_presence` | 1 | T04 FR04 H05 |
| `test_online_group_capacity_separate_and_remote_no_space` | 1 | FR08 H05 |
| `test_four_simultaneous_lessons_cannot_use_three_spaces` | 1 | T05 FR04 H06 |
| `test_same_tutor_collision_across_modalities` | 1 | T06 FR12 H04 |
| `test_same_student_collision_across_groups_and_tutors` | 1 | T07 FR12 H04 |
| `test_closure_overrides_service` | 1 | T09 FR05 |
| `test_resource_specific_closure` | 1 | T09 FR05 |
| `test_mode_specific_closure_does_not_close_online` | 1 | T09 FR05 |
| `test_adjacent_lessons_zero_pause_allowed_and_pause_enforced` | 1 | T36 H10 |
| `test_cleanup_buffer_occupies_space` | 1 | H06 |
| `test_transition_not_instant_and_pause_not_double_counted` | 1 | T16 H11 |
| `test_daily_load_in_minutes` | 1 | T15 H10 |
| `test_weekly_load_in_minutes` | 1 | T15 H10 |
| `test_online_tutor_in_center_requires_configured_space` | 1 | T08 H06 |
| `test_exclusive_video_channels_parallelism` | 1 | H07 |
| `test_lexicographic_priority_above_lower_beneficiary_count` | 1 | FR07 OBJ |
| `test_same_priority_counts_minutes_per_beneficiary` | 1 | FR07 OBJ |
| `test_mandatory_cannot_be_dropped_for_higher_priority_optional` | 1 | T26 H09 |
| `test_locked_assignment_preserved_even_if_optional` | 1 | H08 |
| `test_illegal_lock_blocks_before_solving` | 1 | H08 |
| `test_conflicting_locks_not_silently_moved` | 1 | H08 |
| `test_unknown_is_not_infeasible` | 1 | T27 FR13 |
| `test_invalid_model_is_technical_failure` | 1 | T28 FR13 |
| `test_candidate_limit_blocks_without_false_impossibility` | 1 | T27 NFR04 |
| `test_independent_validator_detects_malformed_duration` | 1 | T29 T38 |
| `test_independent_validator_checks_skill_from_raw_snapshot` | 1 | T29 T01 |
| `test_independent_validator_detects_overlap_and_missing_mandatory` | 1 | T29 FR12 |
| `test_validator_handles_malformed_result_without_crashing` | 4 | T29 |
| `test_validation_failure_discards_solver_output` | 1 | T29 |
| `test_nonfinite_budget_rejected` | 1 | T35 |
| `test_feasible_level_stops_without_claiming_lower_optimality` | 1 | T27 NFR04 |
| `test_budget_expires_after_proven_level_keeps_valid_incumbent` | 1 | T27 NFR04 |

## 8. Lacune principali (input per il piano G1–G5)
1. **Assenti**: T14 (questa e successive), T22/T23 (outbox, delivery ambigua), T30 (presenze), T33 (accessibilità manuale), T34 (benchmark) — dipendono dagli stream s2, s3, s6, s8.
2. **Solo PostgreSQL**: T18 concorrente, T19, trigger di integrità e append-only (`PG`): richiedono la CI reale (GAP-J05).
3. **Parziali di dominio**: T11 (pratica di conflitto), T13 (EXDATE), T37, T40, T41 (recuperi e pratiche, s2); T38 (catalogo durate persistente, GAP-C01); T31 (riconciliazione con presenze).
4. **Sicurezza**: T24 completo (FK annidate, link video, ICS; GAP-B08).
5. **Restore**: T32 ha la riconciliazione applicativa; manca la prova di restore misurata (GAP-L02).
6. **NFR02/03/05/07** senza test automatici.
7. **T12**: aggiungere il caso letterale del paper (21 e 28 ottobre 2026, 16:00 Europe/Rome → 14:00 e 15:00 UTC).

## 9. Proposta di automazione (da approvare; nessun codice modificato da questo stream)
1. Registrare in `backend/pytest.ini` un marcatore `req` e annotare i test: `@pytest.mark.req("T01", "FR03", "H02")`, partendo dalle etichette del §7.
2. Hook in `conftest.py` che, con `--req-report=path`, scrive un JSON `{test_id: [req...], outcome}` dopo la sessione.
3. Script CI che fallisce se: un ID T01–T42 dichiarato "coperto" nel file di baseline non ha test eseguiti e verdi nell'ambiente previsto (PG compresi); un test ha etichette sconosciute.
4. Archiviare il JSON in `docs/evidence/G<n>/` con commit e digest (GAP-M04) e rigenerare questa pagina dal JSON.
