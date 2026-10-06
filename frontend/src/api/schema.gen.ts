/* eslint-disable */
// GENERATO da frontend/scripts/gen-api.py a partire da contracts/openapi.yaml.
// Non modificare a mano: rigenera con `npm run gen:api` (verifica in CI con `npm run check:api`).
// Contratto: Gestionale ripetizioni — subset sperimentale 0.7.0

export namespace S {
  export type Health = {
    status: string;
    release: string;
    production_ready: boolean;
  };
  export type Me = {
    id: string;
    name: string;
    roles: Array<"CENTER" | "TUTOR" | "GUARDIAN" | "STUDENT">;
    tutor_id: string | null;
    experimental: boolean;
  };
  export type Student = {
    id: string;
    display_name: string;
    level: string;
    active: boolean;
    version: number;
  };
  export type Tutor = {
    id: string;
    display_name: string;
    version: number;
  };
  export type Resource = {
    id: string;
    name: string;
    kind: "SPACE" | "VIDEO_CHANNEL";
    student_capacity: number | null;
    active: boolean;
    version: number;
  };
  export type TeachingRequest = {
    id: string;
    student: string | null;
    subject_name: string;
    duration_minutes: 60 | 90 | 120;
    sessions_per_week: number;
    period_start: string;
    period_end: string;
    version: number;
    target_type: "STUDENT" | "GROUP";
    participant_ids: Array<string>;
    mode: "" | "IN_PERSON" | "ONLINE";
    kind?: "SINGLE" | "SERIES" | "WEEKLY";
    fixed_time?: string | null;
    planning_state?: "" | "REVIEW" | "DONE";
    completed_at?: string | null;
    group_label?: string;
    participant_names?: Array<string>;
  };
  export type Decision = {
    id: string;
    code: "D01" | "D02" | "D03" | "D04" | "D05" | "D06" | "D07" | "D08" | "D09";
    title: string;
    proposed_default: string;
    status: "OPEN" | "PROPOSED" | "APPROVED";
    owner: string;
    outcome: string;
    approved_at: string | null;
    version: number;
  };
  export type Readiness = {
    ready: false;
    gate: "G1";
    blockers: Array<{
      code: string;
      reason: string;
    }>;
    release: string;
  };
  export type Detail = {
    detail: string;
  };
  export type Login = {
    username: string;
    password: string;
  };
  export type Unavailable = {
    code: "NOT_IMPLEMENTED";
    message: string;
  };
  export type AvailabilityCreate = {
    tutor?: string | null;
    student?: string | null;
    weekday: number;
    start_time: string;
    end_time: string;
    period_start: string;
    period_end: string;
    timezone?: string;
    mode: "IN_PERSON" | "ONLINE";
    location: "ON_SITE" | "REMOTE";
  };
  export type Availability = {
    id: string;
    tutor: string | null;
    student: string | null;
    weekday: number;
    start_time: string;
    end_time: string;
    period_start: string;
    period_end: string;
    timezone: string;
    mode: "IN_PERSON" | "ONLINE";
    location: "ON_SITE" | "REMOTE";
    status: "DRAFT" | "APPROVED" | "REVOKED";
    version: number;
  };
  export type PageStudent = {
    count: number;
    next: string | null;
    previous: string | null;
    results: Array<S.Student>;
  };
  export type PageTutor = {
    count: number;
    next: string | null;
    previous: string | null;
    results: Array<S.Tutor>;
  };
  export type ResourceWrite = {
    name?: string;
    kind?: "SPACE" | "VIDEO_CHANNEL";
    student_capacity?: number | null;
    active?: boolean;
  };
  export type PageResource = {
    count: number;
    next: string | null;
    previous: string | null;
    results: Array<S.Resource>;
  };
  export type PageTeachingRequest = {
    count: number;
    next: string | null;
    previous: string | null;
    results: Array<S.TeachingRequest>;
  };
  export type PageAvailability = {
    count: number;
    next: string | null;
    previous: string | null;
    results: Array<S.Availability>;
  };
  export type PageDecision = {
    count: number;
    next: string | null;
    previous: string | null;
    results: Array<S.Decision>;
  };
  export type Subject = {
    id: string;
    name: string;
    description?: string;
    active?: boolean;
    version: number;
  };
  export type SubjectCreate = {
    name: string;
    description?: string;
    active?: boolean;
  };
  export type PageSubject = {
    count: number;
    next: string | null;
    previous: string | null;
    results: Array<S.Subject>;
  };
  export type LearningPath = {
    id: string;
    title: string;
    kind: "HOME_EDUCATION" | "TUTORING";
    academic_year: string;
    level: string;
    period_start: string;
    period_end: string;
    required_subjects: Array<string>;
    curriculum_version: number;
    version: number;
  };
  export type LearningPathCreate = {
    title: string;
    kind: "HOME_EDUCATION" | "TUTORING";
    academic_year: string;
    level: string;
    period_start: string;
    period_end: string;
    required_subjects: Array<string>;
  };
  export type PageLearningPath = {
    count: number;
    next: string | null;
    previous: string | null;
    results: Array<S.LearningPath>;
  };
  export type PathEnrollment = {
    id: string;
    path: string;
    student: string;
    student_name: string;
    period_start: string;
    period_end: string;
    active: boolean;
    version: number;
  };
  export type PathEnrollmentCreate = {
    path: string;
    student: string;
    period_start: string;
    period_end: string;
    active?: boolean;
  };
  export type PagePathEnrollment = {
    count: number;
    next: string | null;
    previous: string | null;
    results: Array<S.PathEnrollment>;
  };
  export type TeachingGroup = {
    id: string;
    path: string;
    name: string;
    subject: string;
    online_capacity: number | null;
    approved: boolean;
    version: number;
  };
  export type TeachingGroupCreate = {
    path: string;
    name: string;
    subject: string;
    online_capacity?: number | null;
    approved?: boolean;
  };
  export type PageTeachingGroup = {
    count: number;
    next: string | null;
    previous: string | null;
    results: Array<S.TeachingGroup>;
  };
  export type GroupMembership = {
    id: string;
    group: string;
    student: string;
    period_start: string;
    period_end: string;
    version: number;
  };
  export type GroupMembershipCreate = {
    group: string;
    student: string;
    period_start: string;
    period_end: string;
  };
  export type PageGroupMembership = {
    count: number;
    next: string | null;
    previous: string | null;
    results: Array<S.GroupMembership>;
  };
  export type CurriculumBlock = {
    id: string;
    path: string;
    subject: string;
    subject_name: string;
    objective: string;
    student: string | null;
    group: string | null;
    period_start: string;
    period_end: string;
    minutes_per_week: number;
    duration_minutes: 60 | 90 | 120;
    sessions_per_week: number;
    mode: "IN_PERSON" | "ONLINE";
    priority: "P0" | "P1" | "P2";
    mandatory: boolean;
    version: number;
  };
  export type CurriculumBlockCreate = {
    path: string;
    subject: string;
    objective: string;
    student?: string | null;
    group?: string | null;
    period_start: string;
    period_end: string;
    minutes_per_week: number;
    duration_minutes: 60 | 90 | 120;
    sessions_per_week: number;
    mode: "IN_PERSON" | "ONLINE";
    priority: "P0" | "P1" | "P2";
    mandatory: boolean;
  };
  export type PageCurriculumBlock = {
    count: number;
    next: string | null;
    previous: string | null;
    results: Array<S.CurriculumBlock>;
  };
  export type CurriculumSummary = {
    path_id: string;
    version: number;
    measure: "required_weekly_minutes_by_period";
    students: Array<{
      student_id: string;
      student_name: string;
      subjects: Array<{
        subject_id: string;
        subject_name: string;
        covered_full_period: boolean;
        segments: Array<{
          period_start: string;
          period_end: string;
          required_minutes_per_week: number;
          overlap: boolean;
        }>;
        validation_codes: Array<string>;
        scheduled_minutes: null;
        attended_minutes: null;
      }>;
    }>;
    calendar_available: false;
  };
  export type DeriveReceipt = {
    path_id: string;
    created: number;
    request_ids: Array<string>;
    version: number;
    calendar_changed: false;
  };
  export type PlanningInput = {
    schema_version: "0.4";
    policy_version: string;
    epoch: string;
    timezone: "Europe/Rome";
    horizon_days: number;
    grid_minutes: 15;
    duration_catalog: Array<60 | 90 | 120>;
    mode: "STRICT" | "COVERAGE";
    budget_seconds: number;
    online_onsite_requires_space: boolean;
    video_channels_required: boolean;
    objective_order: Array<unknown>;
    unsupported_constraints: Array<string>;
    students: Array<{
      id: string;
      availability_state: "APPROVED" | "APPROVED_UNRESTRICTED" | "DECLARED_NONE" | "UNKNOWN";
      availability: Array<{
        mode: "IN_PERSON" | "ONLINE";
        start: number;
        end: number;
      }>;
    }>;
    tutors: Array<{
      id: string;
      availability_state: "APPROVED" | "APPROVED_UNRESTRICTED" | "DECLARED_NONE" | "UNKNOWN";
      availability: Array<{
        mode: "IN_PERSON" | "ONLINE";
        location: "ON_SITE" | "REMOTE";
        start: number;
        end: number;
      }>;
      skills: Array<{
        subject: string;
        level: string;
        mode: "IN_PERSON" | "ONLINE";
        start: number;
        end: number;
      }>;
      daily_limit_minutes: number;
      weekly_limit_minutes: number;
      pause_minutes: number;
      transition_minutes: {
        ON_SITE: {
          ON_SITE: number;
          REMOTE: number;
        };
        REMOTE: {
          ON_SITE: number;
          REMOTE: number;
        };
      };
    }>;
    resources: Array<{
      id: string;
      kind: "SPACE" | "VIDEO_CHANNEL";
      student_capacity: (number | null);
      buffer_minutes: number;
      availability: Array<{
        start: number;
        end: number;
      }>;
    }>;
    service_windows: Array<{
      mode: "IN_PERSON" | "ONLINE";
      location: "ON_SITE" | "REMOTE";
      start: number;
      end: number;
    }>;
    closures: Array<{
      mode: "ALL" | "IN_PERSON" | "ONLINE";
      resource_id: (string | null);
      start: number;
      end: number;
    }>;
    units: Array<{
      demand_key: string;
      type: "INDIVIDUAL" | "GROUP";
      subject: string;
      level: string;
      participants: Array<string>;
      duration_minutes: number;
      priority: "P0" | "P1" | "P2";
      mandatory: boolean;
      allowed_modes: Array<"IN_PERSON" | "ONLINE">;
      allowed_tutors: Array<string>;
      online_capacity: (number | null);
      earliest_start: number;
      latest_end: number;
      locked_assignment: ({
        demand_key: string;
        tutor_id: string;
        mode: "IN_PERSON" | "ONLINE";
        location: "ON_SITE" | "REMOTE";
        space_id: (string | null);
        video_id: (string | null);
        start: number;
        end: number;
      } | null);
    }>;
    allow_cross_local_midnight: false;
    student_buffer_minutes: 0;
    horizon_minutes: number;
  };
  export type SimulatedAssignment = {
    demand_key: string;
    tutor_id: string;
    mode: "IN_PERSON" | "ONLINE";
    location: "ON_SITE" | "REMOTE";
    space_id: (string | null);
    video_id: (string | null);
    start: number;
    end: number;
  };
  export type SimulationResult = {
    schema_version: "0.4";
    build_version: string;
    execution_mode: "IN_PROCESS_DTO";
    objective_scope: "COVERAGE_P0_P1_P2_ONLY";
    publishable: false;
    calendar_changed: false;
    epoch: string;
    timezone: "Europe/Rome";
    input_hash: string;
    policy_version: string;
    solver_version: string;
    solver_status: "OPTIMAL" | "FEASIBLE" | "INFEASIBLE" | "UNKNOWN" | "MODEL_INVALID" | "BLOCKED" | "VALIDATION_FAILED";
    assignments: Array<S.SimulatedAssignment>;
    unassigned: Array<{
      demand_key: string;
      priority: string;
      mandatory: boolean;
      reason_codes: Array<string>;
    }>;
    optimality_proven_levels: Array<"P0" | "P1" | "P2">;
    validation: {
      status: "PASSED" | "FAILED" | "NOT_RUN";
      violations: Array<{
        code: string;
        demand_key: string;
      }>;
    };
    is_complete: boolean;
    diagnostics: Array<{
      code: string;
      message: string;
    }>;
    statistics: {
      wall_time_seconds: number;
      candidate_count?: number;
    };
    termination_reason?: string;
    objective_values?: {
      [key: string]: number;
    };
    empty_domain_diagnostics?: Array<{
      demand_key: string;
      reason_codes: Array<string>;
    }>;
  };
  export type TutorSkill = {
    id: string;
    created_at: string;
    updated_at: string;
    version: number;
    level: string;
    mode: "IN_PERSON" | "ONLINE";
    valid_from: string;
    valid_until: string;
    approved: boolean;
    tutor: string;
    subject: string;
  };
  export type TutorSkillCreate = {
    level: string;
    mode: "IN_PERSON" | "ONLINE";
    valid_from: string;
    valid_until: string;
    approved?: boolean;
    tutor: string;
    subject: string;
  };
  export type TutorSkillPatch = {
    level?: string;
    mode?: "IN_PERSON" | "ONLINE";
    valid_from?: string;
    valid_until?: string;
    approved?: boolean;
    tutor?: string;
    subject?: string;
    expected_version: number;
  };
  export type TutorOperatingPolicy = {
    id: string;
    created_at: string;
    updated_at: string;
    version: number;
    daily_limit_minutes: number;
    weekly_limit_minutes: number;
    pause_minutes: number;
    site_to_remote_minutes: number;
    remote_to_site_minutes: number;
    tutor: string;
  };
  export type TutorOperatingPolicyCreate = {
    daily_limit_minutes: number;
    weekly_limit_minutes: number;
    pause_minutes: number;
    site_to_remote_minutes: number;
    remote_to_site_minutes: number;
    tutor: string;
  };
  export type TutorOperatingPolicyPatch = {
    daily_limit_minutes?: number;
    weekly_limit_minutes?: number;
    pause_minutes?: number;
    site_to_remote_minutes?: number;
    remote_to_site_minutes?: number;
    tutor?: string;
    expected_version: number;
  };
  export type ResourceTiming = {
    id: string;
    created_at: string;
    updated_at: string;
    version: number;
    buffer_minutes: number;
    inherit_service_windows: boolean;
    resource: string;
  };
  export type ResourceTimingCreate = {
    buffer_minutes: number;
    inherit_service_windows: boolean;
    resource: string;
  };
  export type ResourceTimingPatch = {
    buffer_minutes?: number;
    inherit_service_windows?: boolean;
    resource?: string;
    expected_version: number;
  };
  export type ServiceWindow = {
    id: string;
    created_at: string;
    updated_at: string;
    version: number;
    mode: "IN_PERSON" | "ONLINE";
    location: "ON_SITE" | "REMOTE";
    weekday: number;
    start_time: string;
    end_time: string;
    period_start: string;
    period_end: string;
    resource: string | null;
  };
  export type ServiceWindowCreate = {
    mode: "IN_PERSON" | "ONLINE";
    location: "ON_SITE" | "REMOTE";
    weekday: number;
    start_time: string;
    end_time: string;
    period_start: string;
    period_end: string;
    resource?: string | null;
  };
  export type ServiceWindowPatch = {
    mode?: "IN_PERSON" | "ONLINE";
    location?: "ON_SITE" | "REMOTE";
    weekday?: number;
    start_time?: string;
    end_time?: string;
    period_start?: string;
    period_end?: string;
    resource?: string | null;
    expected_version: number;
  };
  export type Closure = {
    id: string;
    created_at: string;
    updated_at: string;
    version: number;
    start_at: string;
    end_at: string;
    mode: "ALL" | "IN_PERSON" | "ONLINE";
    reason: string;
    resource: string | null;
  };
  export type ClosureCreate = {
    start_at: string;
    end_at: string;
    mode: "ALL" | "IN_PERSON" | "ONLINE";
    reason: string;
    resource?: string | null;
  };
  export type ClosurePatch = {
    start_at?: string;
    end_at?: string;
    mode?: "ALL" | "IN_PERSON" | "ONLINE";
    reason?: string;
    resource?: string | null;
    expected_version: number;
  };
  export type PlanningPolicy = {
    id: string;
    created_at: string;
    updated_at: string;
    version: number;
    name: string;
    budget_seconds: number;
    online_onsite_requires_space: boolean;
    video_channels_required: boolean;
    partial_week_rule: "BLOCK" | "INCLUDE_ACTIVE_DATES";
    unsupported_constraints: Array<string>;
    approved_for_exploration: boolean;
  };
  export type PlanningPolicyCreate = {
    name: string;
    budget_seconds: number;
    online_onsite_requires_space: boolean;
    video_channels_required: boolean;
    partial_week_rule: "BLOCK" | "INCLUDE_ACTIVE_DATES";
    unsupported_constraints: Array<string>;
    approved_for_exploration: boolean;
  };
  export type PlanningPolicyPatch = {
    name?: string;
    budget_seconds?: number;
    online_onsite_requires_space?: boolean;
    video_channels_required?: boolean;
    partial_week_rule?: "BLOCK" | "INCLUDE_ACTIVE_DATES";
    unsupported_constraints?: Array<string>;
    approved_for_exploration?: boolean;
    expected_version: number;
  };
  export type AvailabilityDeclaration = {
    id: string;
    created_at: string;
    updated_at: string;
    version: number;
    state: "APPROVED" | "DECLARED_NONE" | "UNKNOWN";
    tutor: string | null;
    student: string | null;
  };
  export type AvailabilityDeclarationCreate = {
    state: "APPROVED" | "DECLARED_NONE" | "UNKNOWN";
    tutor?: string | null;
    student?: string | null;
  };
  export type AvailabilityDeclarationPatch = {
    state?: "APPROVED" | "DECLARED_NONE" | "UNKNOWN";
    tutor?: string | null;
    student?: string | null;
    expected_version: number;
  };
  export type AvailabilityException = {
    id: string;
    created_at: string;
    updated_at: string;
    version: number;
    start_at: string;
    end_at: string;
    mode: "IN_PERSON" | "ONLINE";
    location: "ON_SITE" | "REMOTE";
    kind: "ADD_AVAILABLE" | "REMOVE_AVAILABLE";
    tutor: string | null;
    student: string | null;
  };
  export type AvailabilityExceptionCreate = {
    start_at: string;
    end_at: string;
    mode: "IN_PERSON" | "ONLINE";
    location: "ON_SITE" | "REMOTE";
    kind: "ADD_AVAILABLE" | "REMOVE_AVAILABLE";
    tutor?: string | null;
    student?: string | null;
  };
  export type AvailabilityExceptionPatch = {
    start_at?: string;
    end_at?: string;
    mode?: "IN_PERSON" | "ONLINE";
    location?: "ON_SITE" | "REMOTE";
    kind?: "ADD_AVAILABLE" | "REMOVE_AVAILABLE";
    tutor?: string | null;
    student?: string | null;
    expected_version: number;
  };
  export type AvailabilityConflict = {
    id: string;
    created_at: string;
    updated_at: string;
    version: number;
    reason: string;
    open: boolean;
    tutor: string | null;
    student: string | null;
  };
  export type AvailabilityConflictCreate = {
    reason: string;
    open: boolean;
    tutor?: string | null;
    student?: string | null;
  };
  export type AvailabilityConflictPatch = {
    reason?: string;
    open?: boolean;
    tutor?: string | null;
    student?: string | null;
    expected_version: number;
  };
  export type TutorSkillPage = {
    count: number;
    next: string | null;
    previous: string | null;
    results: Array<S.TutorSkill>;
  };
  export type TutorOperatingPolicyPage = {
    count: number;
    next: string | null;
    previous: string | null;
    results: Array<S.TutorOperatingPolicy>;
  };
  export type ResourceTimingPage = {
    count: number;
    next: string | null;
    previous: string | null;
    results: Array<S.ResourceTiming>;
  };
  export type ServiceWindowPage = {
    count: number;
    next: string | null;
    previous: string | null;
    results: Array<S.ServiceWindow>;
  };
  export type ClosurePage = {
    count: number;
    next: string | null;
    previous: string | null;
    results: Array<S.Closure>;
  };
  export type PlanningPolicyPage = {
    count: number;
    next: string | null;
    previous: string | null;
    results: Array<S.PlanningPolicy>;
  };
  export type AvailabilityDeclarationPage = {
    count: number;
    next: string | null;
    previous: string | null;
    results: Array<S.AvailabilityDeclaration>;
  };
  export type AvailabilityExceptionPage = {
    count: number;
    next: string | null;
    previous: string | null;
    results: Array<S.AvailabilityException>;
  };
  export type AvailabilityConflictPage = {
    count: number;
    next: string | null;
    previous: string | null;
    results: Array<S.AvailabilityConflict>;
  };
  export type DatabaseRunCommand = {
    policy_id: string;
    horizon_start: string;
    expected_revision: number;
    mode: "STRICT" | "COVERAGE";
  };
  export type DatabaseQueuedRun = {
    run_id: string;
    snapshot_id: string;
    status: "QUEUED";
    revision: number;
    poll_url: string;
    publishable: false;
  };
  export type DatabaseRun = {
    id: string;
    status: "QUEUED" | "RUNNING" | "SUCCEEDED" | "FAILED" | "CANCELLED";
    phase: string;
    snapshot_id?: string;
    snapshot_revision?: number;
    stale: boolean;
    publishable: false;
    dispatch_status?: "PENDING" | "SENT";
    attempts?: number;
    cancel_requested?: boolean;
    error_code?: string;
    result: (S.SimulationResult | null);
    created_at?: string | null;
    started_at?: string | null;
    finished_at?: string | null;
    heartbeat_at?: string | null;
  };
  export type DatabasePlan = {
    id?: string;
    run?: string;
    state?: "VALIDATED" | "STALE" | "PUBLISHED_EXPERIMENTAL";
    assignments?: Array<S.SimulatedAssignment>;
    result_hash?: string;
    created_at?: string;
    publishable?: false;
    version?: 1;
    snapshot_revision?: number;
    publication_id?: string | null;
    experimental_publish_available?: boolean;
  };
  export type DatabaseReadiness = {
    ready: boolean;
    revision: number;
    unit_count?: number;
    horizon_minutes?: number;
    issues: Array<{
      code?: string;
      message?: string;
    }>;
    publishable: false;
    scope?: string;
  };
  export type DatabaseRunPage = {
    count: number;
    next: string | null;
    previous: string | null;
    results: Array<S.DatabaseRun>;
  };
  export type DatabasePlanPage = {
    count: number;
    next: string | null;
    previous: string | null;
    results: Array<S.DatabasePlan>;
  };
  export type AvailabilityReview = {
    expected_version: number;
    reason: string;
  };
  export type ExperimentalPublishCommand = {
    expected_version: number;
    expected_revision: number;
    accept_unassigned_demand_keys: Array<string>;
    reason: string;
    confirm_experimental: boolean;
  };
  export type ExperimentalCancelCommand = {
    expected_version: number;
    reason: string;
  };
  export type ExperimentalMoveCommand = {
    expected_version: number;
    reason: string;
    start_at: string;
  };
  export type ExperimentalPublicationResponse = {
    publication_id: string;
    created_lesson_ids: Array<string>;
    kept_lesson_ids: Array<string>;
    revision: number;
    experimental: true;
    notifications_sent: false;
  };
  export type ExperimentalChangeResponse = {
    id: string;
    version: number;
    state: "PUBLISHED" | "CANCELLED";
    start_at: string;
    end_at: string;
    revision: number;
    experimental: true;
    notifications_sent: false;
    recovery_created: false;
  };
  export type CalendarCapabilities = {
    enabled: boolean;
    reason_code: string;
    database: string;
    production_enabled: false;
    notifications_enabled: false;
    sqlite_test_override: boolean;
  };
  export type CalendarLesson = {
    id: string;
    version: number;
    state: "PUBLISHED" | "CANCELLED";
    demand_key: string;
    start_at: string;
    end_at: string;
    tutor: string;
    tutor_name: string;
    subject: string;
    subject_name: string;
    mode: "IN_PERSON" | "ONLINE";
    location: "ON_SITE" | "REMOTE";
    space: string | null;
    video: string | null;
    participants: Array<{
      student_id: string;
      name: string;
    }>;
    experimental: true;
  };
  export type CalendarPage = {
    count: number;
    next: string | null;
    previous: string | null;
    results: Array<S.CalendarLesson>;
    revision: number;
    experimental: true;
  };
  export type DeliveryStatus = "PENDING" | "SENDING" | "SENT" | "AMBIGUOUS" | "DEAD" | "SKIPPED" | "CANCELLED" | "REVOKED" | "EXPIRED";
  export type Notification = {
    id: string;
    kind: string;
    category: "SERVICE" | "MARKETING";
    title: string;
    body: string;
    subject_ref: string;
    created_at: string;
    read_at: string | null;
  };
  export type NotificationPage = {
    count: number;
    next: string | null;
    previous: string | null;
    results: Array<S.Notification>;
    unread_count: number;
    pending_email_deliveries: number;
  };
  export type PreferenceItem = {
    category: "SERVICE" | "MARKETING";
    channel: "IN_APP" | "EMAIL";
    enabled: boolean;
  };
  export type NotificationPreferences = {
    preferences: Array<{
      category: "SERVICE" | "MARKETING";
      channel: "IN_APP" | "EMAIL";
      enabled: boolean;
      mandatory: boolean;
      available: boolean;
    }>;
  };
  export type CalendarFeedToken = {
    id: string;
    label: string;
    created_at: string;
    expires_at: string | null;
    revoked_at: string | null;
    last_used_at: string | null;
  };
  export type MeetingLink = {
    lesson_id: string;
    version: number;
    join_url: string;
    expires_at: string;
    provider?: "jitsi";
    embed?: boolean;
    embed_url?: string;
    starts_at?: string;
    origin?: string;
    room?: string;
    display_name?: string;
    moderator?: boolean;
    subject?: string;
  };
  export type MeetingPresenceSummary = {
    lesson_id: string;
    lesson_minutes: number;
    tutor_minutes: number;
    students: Array<{
      student_id: string;
      name: string;
      joined: boolean;
      minutes: number;
    }>;
  };
  export type CommunicationsStatus = {
    counts: {
      [key: string]: {
        [key: string]: number;
      };
    };
    oldest_pending_seconds: number | null;
    dead_letter: number;
    ambiguous: number;
    email_backend: "sink" | "smtp" | "api";
    environment: "development" | "test" | "staging" | "production";
  };
  export type Role = "CENTER" | "TUTOR" | "GUARDIAN" | "STUDENT";
  export type FeedToken = {
    id: string;
    label: string;
    created_at: string;
    expires_at: string | null;
    revoked_at: string | null;
    last_used_at: string | null;
  };
  export type FeedTokenCreated = (S.FeedToken & {
    token: string;
    feed_path: string;
  });
  export type LoginCommand = {
    email: string;
    password: string;
  };
  export type LoginResult = {
    detail?: string;
    mfa_required: boolean;
    mfa_enrolled?: boolean;
    id?: string;
    contexts?: Array<S.Role>;
    context?: string | null;
    context_required?: boolean;
    recovery_codes?: Array<string>;
  };
  export type MfaStatus = {
    required: boolean;
    enrolled: boolean;
    verified: boolean;
    recovery_codes_remaining: number;
  };
  export type MfaSetup = {
    secret: string;
    otpauth_uri: string;
    qr_svg: string;
  };
  export type MfaCode = {
    code: string;
  };
  export type MfaVerify = {
    code?: string;
    recovery_code?: string;
  };
  export type MfaConfirmResult = (S.LoginResult);
  export type AuthContext = {
    id: string;
    contexts: Array<S.Role>;
    context: string | null;
  };
  export type UserSession = {
    id: string;
    current?: boolean;
    created_at?: string;
    last_seen_at?: string | null;
    user_agent?: string;
    mfa_verified?: boolean;
  };
  export type ChangeRequest = {
    id: string;
    lesson_id: string;
    kind: "CANCEL" | "RESCHEDULE" | "ABSENCE" | "OTHER";
    proposal?: {
      [key: string]: unknown;
    };
    origin?: "CENTER" | "TUTOR" | "GUARDIAN" | "STUDENT";
    student_id?: string | null;
    reason?: string;
    state: "SUBMITTED" | "ACCEPTED" | "REJECTED" | "WITHDRAWN";
    resolution_note?: string;
    version: number;
    created_at?: string | null;
  };
  export type ChangeRequestCommand = {
    lesson_id: string;
    kind: "CANCEL" | "RESCHEDULE" | "ABSENCE" | "OTHER";
    reason: string;
    proposal?: {
      start_at?: string;
    };
    student_id?: string | null;
  };
  export type AttendanceStatus = "PRESENT" | "ABSENT" | "JUSTIFIED" | "NOT_RECORDED";
  export type AttendanceSummary = {
    lesson_id: string;
    lesson_state?: string;
    lesson_version: number;
    entries: Array<{
      student_id: string;
      status: S.AttendanceStatus;
      minutes?: number | null;
      version?: number;
      recorded?: boolean;
    }>;
    counts?: {
      [key: string]: number;
    };
    experimental?: boolean;
  };
  export type AttendanceCommand = {
    expected_version: number;
    entries: Array<{
      student_id: string;
      status: S.AttendanceStatus;
      minutes?: number | null;
    }>;
    reason?: string;
  };
  export type EffectiveAvailability = {
    subject?: {
      kind?: string;
      id?: string;
    };
    from?: string;
    until?: string;
    timezone?: string;
    declaration_state?: string;
    ready: boolean;
    windows: Array<{
      mode?: string;
      location?: string;
      start_at?: string;
      end_at?: string;
      local_start?: string;
      local_end?: string;
      minutes?: number;
      within_service_minutes?: number;
    }>;
    exceptions?: Array<S.PortalException>;
    problems?: Array<{
      code?: string;
      severity?: string;
      message?: string;
    }>;
  };
  export type PortalAvailabilityCounts = {
    approved: number;
    draft: number;
    revoked: number;
    exceptions_upcoming: number;
  };
  export type PortalChild = {
    student_id: string;
    display_name: string;
    level: string;
    relation: "SELF" | "GUARDIAN";
    permissions: {
      can_view: boolean;
      can_manage_availability: boolean;
      can_request_changes: boolean;
      can_receive_notifications: boolean;
    };
    read_only: boolean;
    reconfirmation: string | null;
    availability: S.PortalAvailabilityCounts;
    week: (null | {
      lessons: number;
      cancelled: number;
      minutes: number;
      next_lesson_at: string | null;
    });
    open_change_requests: number;
  };
  export type PortalTutor = {
    tutor_id: string;
    display_name: string;
    limits: {
      daily_limit_minutes?: number;
      weekly_limit_minutes?: number;
      pause_minutes?: number;
    } | null;
    availability: S.PortalAvailabilityCounts;
    week: {
      lessons: number;
      scheduled_minutes: number;
      completed_minutes: number;
      cancelled_minutes: number;
      by_day: Array<{
        date: string;
        minutes: number;
      }>;
      attendance_pending: number;
    } | null;
  };
  export type PortalOverview = {
    context: string | null;
    roles: Array<S.Role>;
    week: {
      from: string;
      until: string;
    };
    timezone: "Europe/Rome";
    calendar_enabled: boolean;
    children: Array<S.PortalChild>;
    tutor: (null | S.PortalTutor);
    open_change_requests: number;
    policies: {
      student_can_request_changes: boolean;
      decision: string;
      status: string;
    };
    generated_at: string;
  };
  export type PortalException = {
    id: string;
    kind: "ADD_AVAILABLE" | "REMOVE_AVAILABLE";
    mode: "IN_PERSON" | "ONLINE";
    location: "ON_SITE" | "REMOTE";
    start_at: string;
    end_at: string;
  };
  export type CursorPageMeta = {
    next?: string | null;
    previous?: string | null;
  };
  export type PortalExceptionPage = {
    next: string | null;
    previous: string | null;
    results: Array<S.PortalException>;
  };
  export type PortalAttendanceItem = {
    lesson_id: string;
    version: number;
    start_at: string;
    end_at: string;
    subject_name: string;
    participants: Array<{
      student_id: string;
      name: string;
    }>;
  };
  export type PortalAttendancePage = {
    next: string | null;
    previous: string | null;
    results: Array<S.PortalAttendanceItem>;
  };
}

export interface Paths {
  "/health": {
    get: {
      query: Record<string, never>;
      body: never;
      response: S.Health;
    };
  };
  "/auth/csrf": {
    get: {
      query: Record<string, never>;
      body: never;
      response: S.Detail;
    };
  };
  "/auth/login": {
    post: {
      query: Record<string, never>;
      body: S.LoginCommand;
      response: S.LoginResult;
    };
  };
  "/auth/logout": {
    post: {
      query: Record<string, never>;
      body: never;
      response: S.Detail;
    };
  };
  "/me": {
    get: {
      query: Record<string, never>;
      body: never;
      response: S.Me;
    };
  };
  "/planning/readiness": {
    get: {
      query: Record<string, never>;
      body: never;
      response: S.Readiness;
    };
  };
  "/schedule-runs": {
    post: {
      query: Record<string, never>;
      body: S.DatabaseRunCommand;
      response: S.DatabaseQueuedRun;
    };
  };
  "/students/": {
    get: {
      query: { page?: number };
      body: never;
      response: S.PageStudent;
    };
  };
  "/students/{id}/": {
    get: {
      query: Record<string, never>;
      body: never;
      response: S.Student;
    };
  };
  "/tutors/": {
    get: {
      query: { page?: number };
      body: never;
      response: S.PageTutor;
    };
  };
  "/tutors/{id}/": {
    get: {
      query: Record<string, never>;
      body: never;
      response: S.Tutor;
    };
  };
  "/resources/": {
    get: {
      query: { page?: number };
      body: never;
      response: S.PageResource;
    };
    post: {
      query: Record<string, never>;
      body: S.ResourceWrite;
      response: S.Resource;
    };
  };
  "/resources/{id}/": {
    get: {
      query: Record<string, never>;
      body: never;
      response: S.Resource;
    };
    patch: {
      query: Record<string, never>;
      body: (S.ResourceWrite & {
        expected_version?: number;
      });
      response: S.Resource;
    };
  };
  "/teaching-requests/": {
    get: {
      query: { page?: number };
      body: never;
      response: S.PageTeachingRequest;
    };
  };
  "/teaching-requests/{id}/": {
    get: {
      query: Record<string, never>;
      body: never;
      response: S.TeachingRequest;
    };
  };
  "/availability-rules/": {
    get: {
      query: { page?: number };
      body: never;
      response: S.PageAvailability;
    };
    post: {
      query: Record<string, never>;
      body: S.AvailabilityCreate;
      response: S.Availability;
    };
  };
  "/availability-rules/{id}/": {
    get: {
      query: Record<string, never>;
      body: never;
      response: S.Availability;
    };
  };
  "/decisions/": {
    get: {
      query: { page?: number };
      body: never;
      response: S.PageDecision;
    };
  };
  "/decisions/{id}/": {
    get: {
      query: Record<string, never>;
      body: never;
      response: S.Decision;
    };
  };
  "/subjects/": {
    get: {
      query: { page?: number };
      body: never;
      response: S.PageSubject;
    };
    post: {
      query: Record<string, never>;
      body: S.SubjectCreate;
      response: S.Subject;
    };
  };
  "/subjects/{id}/": {
    get: {
      query: Record<string, never>;
      body: never;
      response: S.Subject;
    };
    patch: {
      query: Record<string, never>;
      body: S.SubjectCreate;
      response: S.Subject;
    };
    delete: {
      query: Record<string, never>;
      body: never;
      response: unknown;
    };
  };
  "/subjects/overview/": {
    get: {
      query: Record<string, never>;
      body: never;
      response: {
        results?: Array<{
          [key: string]: unknown;
        }>;
      };
    };
  };
  "/planner/setup": {
    get: {
      query: Record<string, never>;
      body: never;
      response: {
        [key: string]: unknown;
      };
    };
  };
  "/planner/opening-hours": {
    get: {
      query: Record<string, never>;
      body: never;
      response: {
        [key: string]: unknown;
      };
    };
    put: {
      query: Record<string, never>;
      body: {
        [key: string]: unknown;
      };
      response: {
        [key: string]: unknown;
      };
    };
  };
  "/planner/closures": {
    post: {
      query: Record<string, never>;
      body: {
        [key: string]: unknown;
      };
      response: {
        [key: string]: unknown;
      };
    };
  };
  "/planner/closures/{id}": {
    delete: {
      query: Record<string, never>;
      body: never;
      response: unknown;
    };
  };
  "/commitments": {
    get: {
      query: Record<string, never>;
      body: never;
      response: {
        [key: string]: unknown;
      };
    };
    post: {
      query: Record<string, never>;
      body: {
        [key: string]: unknown;
      };
      response: {
        [key: string]: unknown;
      };
    };
  };
  "/commitments/{id}": {
    patch: {
      query: Record<string, never>;
      body: {
        [key: string]: unknown;
      };
      response: {
        [key: string]: unknown;
      };
    };
    delete: {
      query: Record<string, never>;
      body: never;
      response: unknown;
    };
  };
  "/planner/plans": {
    get: {
      query: Record<string, never>;
      body: never;
      response: {
        [key: string]: unknown;
      };
    };
    post: {
      query: Record<string, never>;
      body: {
        [key: string]: unknown;
      };
      response: {
        [key: string]: unknown;
      };
    };
  };
  "/planner/plans/{id}": {
    get: {
      query: Record<string, never>;
      body: never;
      response: {
        [key: string]: unknown;
      };
    };
  };
  "/planner/plans/{id}/publish": {
    post: {
      query: Record<string, never>;
      body: never;
      response: {
        [key: string]: unknown;
      };
    };
  };
  "/planner/plans/{id}/discard": {
    post: {
      query: Record<string, never>;
      body: never;
      response: {
        [key: string]: unknown;
      };
    };
  };
  "/planner/lessons/{id}/remove": {
    post: {
      query: Record<string, never>;
      body: never;
      response: {
        [key: string]: unknown;
      };
    };
  };
  "/planner/confirmations": {
    get: {
      query: Record<string, never>;
      body: never;
      response: {
        [key: string]: unknown;
      };
    };
  };
  "/planner/confirmations/{id}/answer": {
    post: {
      query: Record<string, never>;
      body: {
        [key: string]: unknown;
      };
      response: {
        [key: string]: unknown;
      };
    };
  };
  "/learning-paths/": {
    get: {
      query: { page?: number };
      body: never;
      response: S.PageLearningPath;
    };
    post: {
      query: Record<string, never>;
      body: S.LearningPathCreate;
      response: S.LearningPath;
    };
  };
  "/learning-paths/{id}/": {
    get: {
      query: Record<string, never>;
      body: never;
      response: S.LearningPath;
    };
  };
  "/path-enrollments/": {
    get: {
      query: { page?: number };
      body: never;
      response: S.PagePathEnrollment;
    };
    post: {
      query: Record<string, never>;
      body: S.PathEnrollmentCreate;
      response: S.PathEnrollment;
    };
  };
  "/path-enrollments/{id}/": {
    get: {
      query: Record<string, never>;
      body: never;
      response: S.PathEnrollment;
    };
  };
  "/teaching-groups/": {
    get: {
      query: { page?: number };
      body: never;
      response: S.PageTeachingGroup;
    };
    post: {
      query: Record<string, never>;
      body: S.TeachingGroupCreate;
      response: S.TeachingGroup;
    };
  };
  "/teaching-groups/{id}/": {
    get: {
      query: Record<string, never>;
      body: never;
      response: S.TeachingGroup;
    };
  };
  "/group-memberships/": {
    get: {
      query: { page?: number };
      body: never;
      response: S.PageGroupMembership;
    };
    post: {
      query: Record<string, never>;
      body: S.GroupMembershipCreate;
      response: S.GroupMembership;
    };
  };
  "/group-memberships/{id}/": {
    get: {
      query: Record<string, never>;
      body: never;
      response: S.GroupMembership;
    };
  };
  "/curriculum-blocks/": {
    get: {
      query: { page?: number };
      body: never;
      response: S.PageCurriculumBlock;
    };
    post: {
      query: Record<string, never>;
      body: S.CurriculumBlockCreate;
      response: S.CurriculumBlock;
    };
  };
  "/curriculum-blocks/{id}/": {
    get: {
      query: Record<string, never>;
      body: never;
      response: S.CurriculumBlock;
    };
  };
  "/learning-paths/{id}/curriculum-summary/": {
    get: {
      query: Record<string, never>;
      body: never;
      response: S.CurriculumSummary;
    };
  };
  "/learning-paths/{id}/derive-requests/": {
    post: {
      query: Record<string, never>;
      body: {
        expected_version: number;
      };
      response: S.DeriveReceipt;
    };
  };
  "/planning/example": {
    get: {
      query: Record<string, never>;
      body: never;
      response: S.PlanningInput;
    };
  };
  "/planning/simulate": {
    post: {
      query: Record<string, never>;
      body: S.PlanningInput;
      response: S.SimulationResult;
    };
  };
  "/tutor-skills/": {
    get: {
      query: Record<string, never>;
      body: never;
      response: S.TutorSkillPage;
    };
    post: {
      query: Record<string, never>;
      body: S.TutorSkillCreate;
      response: S.TutorSkill;
    };
  };
  "/tutor-skills/{id}/": {
    get: {
      query: Record<string, never>;
      body: never;
      response: S.TutorSkill;
    };
    patch: {
      query: Record<string, never>;
      body: S.TutorSkillPatch;
      response: S.TutorSkill;
    };
  };
  "/tutor-operating-policies/": {
    get: {
      query: Record<string, never>;
      body: never;
      response: S.TutorOperatingPolicyPage;
    };
    post: {
      query: Record<string, never>;
      body: S.TutorOperatingPolicyCreate;
      response: S.TutorOperatingPolicy;
    };
  };
  "/tutor-operating-policies/{id}/": {
    get: {
      query: Record<string, never>;
      body: never;
      response: S.TutorOperatingPolicy;
    };
    patch: {
      query: Record<string, never>;
      body: S.TutorOperatingPolicyPatch;
      response: S.TutorOperatingPolicy;
    };
  };
  "/resource-timings/": {
    get: {
      query: Record<string, never>;
      body: never;
      response: S.ResourceTimingPage;
    };
    post: {
      query: Record<string, never>;
      body: S.ResourceTimingCreate;
      response: S.ResourceTiming;
    };
  };
  "/resource-timings/{id}/": {
    get: {
      query: Record<string, never>;
      body: never;
      response: S.ResourceTiming;
    };
    patch: {
      query: Record<string, never>;
      body: S.ResourceTimingPatch;
      response: S.ResourceTiming;
    };
  };
  "/service-windows/": {
    get: {
      query: Record<string, never>;
      body: never;
      response: S.ServiceWindowPage;
    };
    post: {
      query: Record<string, never>;
      body: S.ServiceWindowCreate;
      response: S.ServiceWindow;
    };
  };
  "/service-windows/{id}/": {
    get: {
      query: Record<string, never>;
      body: never;
      response: S.ServiceWindow;
    };
    patch: {
      query: Record<string, never>;
      body: S.ServiceWindowPatch;
      response: S.ServiceWindow;
    };
  };
  "/closures/": {
    get: {
      query: Record<string, never>;
      body: never;
      response: S.ClosurePage;
    };
    post: {
      query: Record<string, never>;
      body: S.ClosureCreate;
      response: S.Closure;
    };
  };
  "/closures/{id}/": {
    get: {
      query: Record<string, never>;
      body: never;
      response: S.Closure;
    };
    patch: {
      query: Record<string, never>;
      body: S.ClosurePatch;
      response: S.Closure;
    };
  };
  "/planning-policies/": {
    get: {
      query: Record<string, never>;
      body: never;
      response: S.PlanningPolicyPage;
    };
    post: {
      query: Record<string, never>;
      body: S.PlanningPolicyCreate;
      response: S.PlanningPolicy;
    };
  };
  "/planning-policies/{id}/": {
    get: {
      query: Record<string, never>;
      body: never;
      response: S.PlanningPolicy;
    };
    patch: {
      query: Record<string, never>;
      body: S.PlanningPolicyPatch;
      response: S.PlanningPolicy;
    };
  };
  "/availability-declarations/": {
    get: {
      query: Record<string, never>;
      body: never;
      response: S.AvailabilityDeclarationPage;
    };
    post: {
      query: Record<string, never>;
      body: S.AvailabilityDeclarationCreate;
      response: S.AvailabilityDeclaration;
    };
  };
  "/availability-declarations/{id}/": {
    get: {
      query: Record<string, never>;
      body: never;
      response: S.AvailabilityDeclaration;
    };
    patch: {
      query: Record<string, never>;
      body: S.AvailabilityDeclarationPatch;
      response: S.AvailabilityDeclaration;
    };
  };
  "/availability-exceptions/": {
    get: {
      query: Record<string, never>;
      body: never;
      response: S.AvailabilityExceptionPage;
    };
    post: {
      query: Record<string, never>;
      body: S.AvailabilityExceptionCreate;
      response: S.AvailabilityException;
    };
  };
  "/availability-exceptions/{id}/": {
    get: {
      query: Record<string, never>;
      body: never;
      response: S.AvailabilityException;
    };
    patch: {
      query: Record<string, never>;
      body: S.AvailabilityExceptionPatch;
      response: S.AvailabilityException;
    };
  };
  "/availability-conflicts/": {
    get: {
      query: Record<string, never>;
      body: never;
      response: S.AvailabilityConflictPage;
    };
    post: {
      query: Record<string, never>;
      body: S.AvailabilityConflictCreate;
      response: S.AvailabilityConflict;
    };
  };
  "/availability-conflicts/{id}/": {
    get: {
      query: Record<string, never>;
      body: never;
      response: S.AvailabilityConflict;
    };
    patch: {
      query: Record<string, never>;
      body: S.AvailabilityConflictPatch;
      response: S.AvailabilityConflict;
    };
  };
  "/schedule-runs/": {
    get: {
      query: Record<string, never>;
      body: never;
      response: S.DatabaseRunPage;
    };
  };
  "/schedule-runs/{id}/": {
    get: {
      query: Record<string, never>;
      body: never;
      response: S.DatabaseRun;
    };
  };
  "/schedule-plans/": {
    get: {
      query: Record<string, never>;
      body: never;
      response: S.DatabasePlanPage;
    };
  };
  "/schedule-plans/{id}/": {
    get: {
      query: Record<string, never>;
      body: never;
      response: S.DatabasePlan;
    };
  };
  "/schedule-runs/{id}/cancel/": {
    post: {
      query: Record<string, never>;
      body: never;
      response: S.DatabaseRun;
    };
  };
  "/planning/data-readiness": {
    get: {
      query: { policy_id: string; horizon_start: string; mode?: "STRICT" | "COVERAGE" };
      body: never;
      response: S.DatabaseReadiness;
    };
  };
  "/availability-rules/{id}/approve/": {
    post: {
      query: Record<string, never>;
      body: S.AvailabilityReview;
      response: unknown;
    };
  };
  "/availability-rules/{id}/revoke/": {
    post: {
      query: Record<string, never>;
      body: S.AvailabilityReview;
      response: unknown;
    };
  };
  "/schedule-plans/{pk}/publish/": {
    post: {
      query: Record<string, never>;
      body: S.ExperimentalPublishCommand;
      response: S.ExperimentalPublicationResponse;
    };
  };
  "/occurrences/{pk}/reschedule/": {
    post: {
      query: Record<string, never>;
      body: S.ExperimentalMoveCommand;
      response: S.ExperimentalChangeResponse;
    };
  };
  "/occurrences/{pk}/cancel/": {
    post: {
      query: Record<string, never>;
      body: S.ExperimentalCancelCommand;
      response: S.ExperimentalChangeResponse;
    };
  };
  "/occurrences/{pk}/reschedule-options/": {
    get: {
      query: { date: string };
      body: never;
      response: {
        lesson_id: string;
        version: number;
        date: string;
        current_start_at: string;
        experimental: boolean;
        options: Array<{
          start_at: string;
          ok: boolean;
          codes: Array<string>;
        }>;
      };
    };
  };
  "/my/lessons": {
    get: {
      query: { from: string; until: string };
      body: never;
      response: {
        experimental?: boolean;
        results?: Array<{
          id?: string;
          state?: "PUBLISHED" | "CANCELLED";
          start_at?: string;
          end_at?: string;
          subject_name?: string;
          tutor_name?: string;
          mode?: string;
          location?: string;
          space_name?: string | null;
          as_tutor?: boolean;
          other_participants?: number;
          participants?: Array<{
            student_id?: string;
            name?: string;
          }>;
        }>;
      };
    };
  };
  "/calendar/capabilities": {
    get: {
      query: Record<string, never>;
      body: never;
      response: S.CalendarCapabilities;
    };
  };
  "/calendar/": {
    get: {
      query: { from: string; until: string; page?: number };
      body: never;
      response: S.CalendarPage;
    };
  };
  "/notifications": {
    get: {
      query: { unread?: "0" | "1"; category?: "SERVICE" | "MARKETING"; page?: number };
      body: never;
      response: S.NotificationPage;
    };
  };
  "/notifications/{pk}/read": {
    post: {
      query: Record<string, never>;
      body: never;
      response: S.Notification;
    };
  };
  "/notifications/read-all": {
    post: {
      query: Record<string, never>;
      body: never;
      response: {
        marked_read: number;
      };
    };
  };
  "/notifications/preferences": {
    get: {
      query: Record<string, never>;
      body: never;
      response: S.NotificationPreferences;
    };
    put: {
      query: Record<string, never>;
      body: {
        preferences: Array<S.PreferenceItem>;
      };
      response: S.NotificationPreferences;
    };
  };
  "/calendar-feed-tokens": {
    get: {
      query: Record<string, never>;
      body: never;
      response: {
        results: Array<S.CalendarFeedToken>;
      };
    };
    post: {
      query: Record<string, never>;
      body: {
        label?: string;
      };
      response: (S.CalendarFeedToken & {
        token: string;
        feed_path: string;
      });
    };
  };
  "/calendar-feed-tokens/{pk}/revoke": {
    post: {
      query: Record<string, never>;
      body: never;
      response: S.CalendarFeedToken;
    };
  };
  "/calendar.ics": {
    get: {
      query: { token: string };
      body: never;
      response: unknown;
    };
  };
  "/occurrences/{pk}/meeting": {
    get: {
      query: Record<string, never>;
      body: never;
      response: S.MeetingLink;
    };
  };
  "/occurrences/{pk}/meeting/presence": {
    get: {
      query: Record<string, never>;
      body: never;
      response: S.MeetingPresenceSummary;
    };
    post: {
      query: Record<string, never>;
      body: {
        event: "join" | "heartbeat" | "leave";
      };
      response: {
        ok: boolean;
        seconds: number;
      };
    };
  };
  "/communications/status": {
    get: {
      query: Record<string, never>;
      body: never;
      response: S.CommunicationsStatus;
    };
  };
  "/communications/deliveries/{pk}/resolve": {
    post: {
      query: Record<string, never>;
      body: {
        resolution: "MARK_SENT" | "RETRY" | "ABANDON";
        reason: string;
      };
      response: {
        id: string;
        status: S.DeliveryStatus;
        attempts: number;
      };
    };
  };
  "/auth/mfa": {
    get: {
      query: Record<string, never>;
      body: never;
      response: S.MfaStatus;
    };
  };
  "/auth/mfa/setup": {
    post: {
      query: Record<string, never>;
      body: Record<string, never>;
      response: S.MfaSetup;
    };
  };
  "/auth/mfa/confirm": {
    post: {
      query: Record<string, never>;
      body: S.MfaCode;
      response: S.MfaConfirmResult;
    };
  };
  "/auth/mfa/verify": {
    post: {
      query: Record<string, never>;
      body: S.MfaVerify;
      response: S.LoginResult;
    };
  };
  "/auth/mfa/recovery-codes": {
    post: {
      query: Record<string, never>;
      body: S.MfaCode;
      response: {
        recovery_codes: Array<string>;
      };
    };
  };
  "/auth/password-reset": {
    post: {
      query: Record<string, never>;
      body: {
        email: string;
      };
      response: S.Detail;
    };
  };
  "/auth/password-reset/confirm": {
    post: {
      query: Record<string, never>;
      body: {
        token: string;
        password: string;
      };
      response: S.Detail;
    };
  };
  "/auth/password-change": {
    post: {
      query: Record<string, never>;
      body: {
        current_password: string;
        new_password: string;
      };
      response: S.Detail;
    };
  };
  "/auth/sessions": {
    get: {
      query: Record<string, never>;
      body: never;
      response: {
        results: Array<S.UserSession>;
      };
    };
  };
  "/auth/sessions/{id}/revoke": {
    post: {
      query: Record<string, never>;
      body: never;
      response: S.Detail;
    };
  };
  "/auth/sessions/revoke-all": {
    post: {
      query: Record<string, never>;
      body: {
        include_current?: boolean;
      };
      response: {
        detail?: string;
        revoked: number;
      };
    };
  };
  "/auth/context": {
    get: {
      query: Record<string, never>;
      body: never;
      response: S.AuthContext;
    };
    post: {
      query: Record<string, never>;
      body: {
        context: S.Role;
      };
      response: S.AuthContext;
    };
  };
  "/invitations/accept": {
    post: {
      query: Record<string, never>;
      body: {
        token: string;
        password?: string;
      };
      response: S.Detail;
    };
  };
  "/change-requests/": {
    get: {
      query: { state?: "SUBMITTED" | "ACCEPTED" | "REJECTED" | "WITHDRAWN" };
      body: never;
      response: {
        results: Array<S.ChangeRequest>;
        experimental?: boolean;
      };
    };
    post: {
      query: Record<string, never>;
      body: S.ChangeRequestCommand;
      response: {
        [key: string]: unknown;
      };
    };
  };
  "/change-requests/{pk}/withdraw/": {
    post: {
      query: Record<string, never>;
      body: {
        expected_version: number;
        reason: string;
      };
      response: {
        [key: string]: unknown;
      };
    };
  };
  "/occurrences/{pk}/attendance/": {
    get: {
      query: Record<string, never>;
      body: never;
      response: S.AttendanceSummary;
    };
    post: {
      query: Record<string, never>;
      body: S.AttendanceCommand;
      response: {
        [key: string]: unknown;
      };
    };
  };
  "/availability/effective": {
    get: {
      query: { student?: string; tutor?: string; from: string; until: string };
      body: never;
      response: S.EffectiveAvailability;
    };
  };
  "/portal/overview": {
    get: {
      query: { week?: string };
      body: never;
      response: S.PortalOverview;
    };
  };
  "/portal/availability-exceptions": {
    get: {
      query: { student?: string; tutor?: string; cursor?: string; page_size?: number; past?: "0" | "1" };
      body: never;
      response: S.PortalExceptionPage;
    };
  };
  "/portal/attendance-pending": {
    get: {
      query: { cursor?: string };
      body: never;
      response: S.PortalAttendancePage;
    };
  };
  "/teaching-requests/{id}/planning": {
    get: {
      query: Record<string, never>;
      body: never;
      response: {
        [key: string]: unknown;
      };
    };
  };
  "/teaching-requests/{id}/planning/rerun": {
    post: {
      query: Record<string, never>;
      body: {
        month?: string;
      };
      response: {
        [key: string]: unknown;
      };
    };
  };
  "/teaching-requests/{id}/planning/options": {
    post: {
      query: Record<string, never>;
      body: {
        [key: string]: unknown;
      };
      response: {
        [key: string]: unknown;
      };
    };
  };
  "/teaching-requests/{id}/planning/lessons": {
    post: {
      query: Record<string, never>;
      body: {
        [key: string]: unknown;
      };
      response: {
        [key: string]: unknown;
      };
    };
  };
  "/teaching-requests/{id}/planning/complete": {
    post: {
      query: Record<string, never>;
      body: {
        [key: string]: unknown;
      };
      response: {
        [key: string]: unknown;
      };
    };
  };
  "/planner/calendar-months/{month}": {
    get: {
      query: Record<string, never>;
      body: never;
      response: {
        [key: string]: unknown;
      };
    };
  };
  "/planner/calendar-months/{month}/publish": {
    post: {
      query: Record<string, never>;
      body: {
        [key: string]: unknown;
      };
      response: {
        [key: string]: unknown;
      };
    };
  };
  "/planner/corrections": {
    post: {
      query: Record<string, never>;
      body: {
        [key: string]: unknown;
      };
      response: {
        [key: string]: unknown;
      };
    };
  };
  "/planner/corrections/{id}/discard": {
    post: {
      query: Record<string, never>;
      body: {
        [key: string]: unknown;
      };
      response: {
        [key: string]: unknown;
      };
    };
  };
  "/planner/corrections/{id}/publish": {
    post: {
      query: Record<string, never>;
      body: {
        [key: string]: unknown;
      };
      response: {
        [key: string]: unknown;
      };
    };
  };
  "/planner/request-lessons/{id}/move": {
    post: {
      query: Record<string, never>;
      body: {
        [key: string]: unknown;
      };
      response: {
        [key: string]: unknown;
      };
    };
  };
  "/planner/request-lessons/{id}/remove": {
    post: {
      query: Record<string, never>;
      body: {
        [key: string]: unknown;
      };
      response: {
        [key: string]: unknown;
      };
    };
  };
}

export const OPERATIONS = {
  addRequestPlanningLesson: ["POST", "/teaching-requests/{id}/planning/lessons"],
  answerAutoPlanConfirmation: ["POST", "/planner/confirmations/{id}/answer"],
  approveAvailability: ["POST", "/availability-rules/{id}/approve/"],
  attendanceGet: ["GET", "/occurrences/{pk}/attendance/"],
  attendanceRecord: ["POST", "/occurrences/{pk}/attendance/"],
  authContextGet: ["GET", "/auth/context"],
  authContextSet: ["POST", "/auth/context"],
  authMfaConfirm: ["POST", "/auth/mfa/confirm"],
  authMfaRecoveryCodes: ["POST", "/auth/mfa/recovery-codes"],
  authMfaSetup: ["POST", "/auth/mfa/setup"],
  authMfaStatus: ["GET", "/auth/mfa"],
  authMfaVerify: ["POST", "/auth/mfa/verify"],
  authPasswordChange: ["POST", "/auth/password-change"],
  authPasswordReset: ["POST", "/auth/password-reset"],
  authPasswordResetConfirm: ["POST", "/auth/password-reset/confirm"],
  authSessionRevoke: ["POST", "/auth/sessions/{id}/revoke"],
  authSessions: ["GET", "/auth/sessions"],
  authSessionsRevokeAll: ["POST", "/auth/sessions/revoke-all"],
  availabilityEffective: ["GET", "/availability/effective"],
  cancelDatabaseRun: ["POST", "/schedule-runs/{id}/cancel/"],
  cancelExperimentalLesson: ["POST", "/occurrences/{pk}/cancel/"],
  changeRequestWithdraw: ["POST", "/change-requests/{pk}/withdraw/"],
  changeRequestsList: ["GET", "/change-requests/"],
  changeRequestsSubmit: ["POST", "/change-requests/"],
  completeRequestPlanning: ["POST", "/teaching-requests/{id}/planning/complete"],
  createAvailabilityConflict: ["POST", "/availability-conflicts/"],
  createAvailabilityDeclaration: ["POST", "/availability-declarations/"],
  createAvailabilityDraft: ["POST", "/availability-rules/"],
  createAvailabilityException: ["POST", "/availability-exceptions/"],
  createCalendarCorrection: ["POST", "/planner/corrections"],
  createCalendarFeedToken: ["POST", "/calendar-feed-tokens"],
  createClosure: ["POST", "/closures/"],
  createCommitments: ["POST", "/commitments"],
  createCurriculumBlock: ["POST", "/curriculum-blocks/"],
  createGroupMembership: ["POST", "/group-memberships/"],
  createLearningPath: ["POST", "/learning-paths/"],
  createPathEnrollment: ["POST", "/path-enrollments/"],
  createPlannerClosure: ["POST", "/planner/closures"],
  createPlanningPolicy: ["POST", "/planning-policies/"],
  createResource: ["POST", "/resources/"],
  createResourceTiming: ["POST", "/resource-timings/"],
  createServiceWindow: ["POST", "/service-windows/"],
  createSubject: ["POST", "/subjects/"],
  createTeachingGroup: ["POST", "/teaching-groups/"],
  createTutorOperatingPolicy: ["POST", "/tutor-operating-policies/"],
  createTutorSkill: ["POST", "/tutor-skills/"],
  csrf: ["GET", "/auth/csrf"],
  curriculumSummary: ["GET", "/learning-paths/{id}/curriculum-summary/"],
  databaseReadiness: ["GET", "/planning/data-readiness"],
  deleteCommitment: ["DELETE", "/commitments/{id}"],
  deletePlannerClosure: ["DELETE", "/planner/closures/{id}"],
  deleteSubject: ["DELETE", "/subjects/{id}/"],
  deriveCurriculumRequests: ["POST", "/learning-paths/{id}/derive-requests/"],
  discardAutoPlan: ["POST", "/planner/plans/{id}/discard"],
  discardCalendarCorrection: ["POST", "/planner/corrections/{id}/discard"],
  generateMonthPlan: ["POST", "/planner/plans"],
  getAutoPlan: ["GET", "/planner/plans/{id}"],
  getCalendarCapabilities: ["GET", "/calendar/capabilities"],
  getCalendarMonth: ["GET", "/planner/calendar-months/{month}"],
  getCommunicationsStatus: ["GET", "/communications/status"],
  getDatabasePlan: ["GET", "/schedule-plans/{id}/"],
  getDatabaseRun: ["GET", "/schedule-runs/{id}/"],
  getExperimentalCalendar: ["GET", "/calendar/"],
  getMeetingPresence: ["GET", "/occurrences/{pk}/meeting/presence"],
  getMonthPlanning: ["GET", "/planner/plans"],
  getMyLessons: ["GET", "/my/lessons"],
  getNotificationPreferences: ["GET", "/notifications/preferences"],
  getOccurrenceMeeting: ["GET", "/occurrences/{pk}/meeting"],
  getOpeningHours: ["GET", "/planner/opening-hours"],
  getPersonalCalendarIcs: ["GET", "/calendar.ics"],
  getPlannerSetup: ["GET", "/planner/setup"],
  getRequestPlanning: ["GET", "/teaching-requests/{id}/planning"],
  getRescheduleOptions: ["GET", "/occurrences/{pk}/reschedule-options/"],
  health: ["GET", "/health"],
  invitationAccept: ["POST", "/invitations/accept"],
  listAutoPlanConfirmations: ["GET", "/planner/confirmations"],
  listAvailability: ["GET", "/availability-rules/"],
  listAvailabilityConflict: ["GET", "/availability-conflicts/"],
  listAvailabilityDeclaration: ["GET", "/availability-declarations/"],
  listAvailabilityException: ["GET", "/availability-exceptions/"],
  listCalendarFeedTokens: ["GET", "/calendar-feed-tokens"],
  listClosure: ["GET", "/closures/"],
  listCommitments: ["GET", "/commitments"],
  listCurriculumBlock: ["GET", "/curriculum-blocks/"],
  listDatabasePlan: ["GET", "/schedule-plans/"],
  listDatabaseRun: ["GET", "/schedule-runs/"],
  listDecision: ["GET", "/decisions/"],
  listGroupMembership: ["GET", "/group-memberships/"],
  listLearningPath: ["GET", "/learning-paths/"],
  listNotifications: ["GET", "/notifications"],
  listPathEnrollment: ["GET", "/path-enrollments/"],
  listPlanningPolicy: ["GET", "/planning-policies/"],
  listResource: ["GET", "/resources/"],
  listResourceTiming: ["GET", "/resource-timings/"],
  listServiceWindow: ["GET", "/service-windows/"],
  listStudent: ["GET", "/students/"],
  listSubject: ["GET", "/subjects/"],
  listTeachingGroup: ["GET", "/teaching-groups/"],
  listTeachingRequest: ["GET", "/teaching-requests/"],
  listTutor: ["GET", "/tutors/"],
  listTutorOperatingPolicy: ["GET", "/tutor-operating-policies/"],
  listTutorSkill: ["GET", "/tutor-skills/"],
  login: ["POST", "/auth/login"],
  logout: ["POST", "/auth/logout"],
  markAllNotificationsRead: ["POST", "/notifications/read-all"],
  markNotificationRead: ["POST", "/notifications/{pk}/read"],
  me: ["GET", "/me"],
  moveExperimentalLesson: ["POST", "/occurrences/{pk}/reschedule/"],
  moveRequestPlanningLesson: ["POST", "/planner/request-lessons/{id}/move"],
  patchAvailabilityConflict: ["PATCH", "/availability-conflicts/{id}/"],
  patchAvailabilityDeclaration: ["PATCH", "/availability-declarations/{id}/"],
  patchAvailabilityException: ["PATCH", "/availability-exceptions/{id}/"],
  patchClosure: ["PATCH", "/closures/{id}/"],
  patchPlanningPolicy: ["PATCH", "/planning-policies/{id}/"],
  patchResourceTiming: ["PATCH", "/resource-timings/{id}/"],
  patchServiceWindow: ["PATCH", "/service-windows/{id}/"],
  patchTutorOperatingPolicy: ["PATCH", "/tutor-operating-policies/{id}/"],
  patchTutorSkill: ["PATCH", "/tutor-skills/{id}/"],
  planningReadiness: ["GET", "/planning/readiness"],
  portalAttendancePending: ["GET", "/portal/attendance-pending"],
  portalAvailabilityExceptions: ["GET", "/portal/availability-exceptions"],
  portalOverview: ["GET", "/portal/overview"],
  postMeetingPresence: ["POST", "/occurrences/{pk}/meeting/presence"],
  publishAutoPlan: ["POST", "/planner/plans/{id}/publish"],
  publishCalendarCorrection: ["POST", "/planner/corrections/{id}/publish"],
  publishCalendarMonth: ["POST", "/planner/calendar-months/{month}/publish"],
  publishExperimentalPlan: ["POST", "/schedule-plans/{pk}/publish/"],
  putOpeningHours: ["PUT", "/planner/opening-hours"],
  queueDatabaseRun: ["POST", "/schedule-runs"],
  removeAutoPlanLesson: ["POST", "/planner/lessons/{id}/remove"],
  removeRequestPlanningLesson: ["POST", "/planner/request-lessons/{id}/remove"],
  requestPlanningOptions: ["POST", "/teaching-requests/{id}/planning/options"],
  rerunRequestPlanning: ["POST", "/teaching-requests/{id}/planning/rerun"],
  resolveDelivery: ["POST", "/communications/deliveries/{pk}/resolve"],
  retrieveAvailability: ["GET", "/availability-rules/{id}/"],
  retrieveAvailabilityConflict: ["GET", "/availability-conflicts/{id}/"],
  retrieveAvailabilityDeclaration: ["GET", "/availability-declarations/{id}/"],
  retrieveAvailabilityException: ["GET", "/availability-exceptions/{id}/"],
  retrieveClosure: ["GET", "/closures/{id}/"],
  retrieveCurriculumBlock: ["GET", "/curriculum-blocks/{id}/"],
  retrieveDecision: ["GET", "/decisions/{id}/"],
  retrieveGroupMembership: ["GET", "/group-memberships/{id}/"],
  retrieveLearningPath: ["GET", "/learning-paths/{id}/"],
  retrievePathEnrollment: ["GET", "/path-enrollments/{id}/"],
  retrievePlanningPolicy: ["GET", "/planning-policies/{id}/"],
  retrieveResource: ["GET", "/resources/{id}/"],
  retrieveResourceTiming: ["GET", "/resource-timings/{id}/"],
  retrieveServiceWindow: ["GET", "/service-windows/{id}/"],
  retrieveStudent: ["GET", "/students/{id}/"],
  retrieveSubject: ["GET", "/subjects/{id}/"],
  retrieveTeachingGroup: ["GET", "/teaching-groups/{id}/"],
  retrieveTeachingRequest: ["GET", "/teaching-requests/{id}/"],
  retrieveTutor: ["GET", "/tutors/{id}/"],
  retrieveTutorOperatingPolicy: ["GET", "/tutor-operating-policies/{id}/"],
  retrieveTutorSkill: ["GET", "/tutor-skills/{id}/"],
  revokeAvailability: ["POST", "/availability-rules/{id}/revoke/"],
  revokeCalendarFeedToken: ["POST", "/calendar-feed-tokens/{pk}/revoke"],
  simulateSyntheticPlanning: ["POST", "/planning/simulate"],
  subjectsOverview: ["GET", "/subjects/overview/"],
  syntheticPlanningExample: ["GET", "/planning/example"],
  updateCommitment: ["PATCH", "/commitments/{id}"],
  updateNotificationPreferences: ["PUT", "/notifications/preferences"],
  updateResource: ["PATCH", "/resources/{id}/"],
  updateSubject: ["PATCH", "/subjects/{id}/"],
} as const;

export type PathsWith<M extends string> = { [P in keyof Paths]: M extends keyof Paths[P] ? P : never }[keyof Paths];
