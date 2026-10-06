from django.conf import settings
from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from api import views
from api import paths
from api import planning
from api import planning_data
from api import calendar
from api import calendar_ops  # s2-calendario
from api import lesson_slots  # v0.9.8
from api import availability_effective  # s2-calendario
from api import school_year  # P2
from api import communications  # s3-comunicazioni
from api import teaching_requests  # v0.9.4
from api import planning_overview  # v0.9.4

router = DefaultRouter()
for prefix, view in [
    ("students", views.StudentsView),
    ("tutors", views.TutorsView),
    ("resources", views.ResourcesView),
    ("teaching-requests", teaching_requests.RequestsView),
    ("availability-rules", views.AvailabilityView),
    ("decisions", views.DecisionsView),
    ("subjects", paths.SubjectsView),
    ("learning-paths", paths.PathsView),
    ("path-enrollments", paths.EnrollmentsView),
    ("teaching-groups", paths.GroupsView),
    ("group-memberships", paths.MembershipsView),
    ("curriculum-blocks", paths.BlocksView),
]:
    router.register(prefix, view, basename=prefix)
for prefix, model in planning_data.CONFIG_MODELS.items():
    router.register(prefix, planning_data.config_view(model), basename=prefix)
router.register("schedule-runs", planning_data.RunView, basename="schedule-runs")
router.register("schedule-plans", planning_data.PlanView, basename="schedule-plans")
urlpatterns = [
    # --- s1-sicurezza: auth, MFA, inviti, sessioni ---
    path("api/v1/", include("api.auth")),
    path("", include("apps.ops.urls")),  # s5-infra: healthz/readyz/metrics/ready
    path("api/v1/calendar/capabilities", calendar.capabilities),
    path("api/v1/planning/overview", planning_overview.planning_overview),
    path("api/v1/calendar/", calendar.CalendarView.as_view()),
    path("api/v1/my/lessons", calendar.my_lessons),
    path("api/v1/schedule-plans/<uuid:pk>/publish/", calendar.publish),
    path("api/v1/occurrences/<uuid:pk>/reschedule/", calendar.move),
    path("api/v1/occurrences/<uuid:pk>/cancel/", calendar.cancel),
    path("api/v1/occurrences/<uuid:pk>/propose-change/", calendar.propose_change),
    path("api/v1/lesson-changes/", calendar.lesson_changes),
    path("api/v1/lesson-changes/<uuid:pk>/<str:action>/", calendar.lesson_change_action),
    path("api/v1/occurrences/<uuid:pk>/reschedule-options/", calendar.move_options),
    # --- s2-calendario ---
    path("api/v1/occurrences/swap/", calendar_ops.swap),
    path("api/v1/occurrences/<uuid:pk>/move/", calendar_ops.move),
    path("api/v1/occurrences/<uuid:pk>/modify/", calendar_ops.modify),
    path("api/v1/occurrences/<uuid:pk>/substitutes/", calendar_ops.substitutes),
    path("api/v1/occurrences/<uuid:pk>/recovery/", calendar_ops.recovery),
    path("api/v1/occurrences/<uuid:pk>/attendance/", calendar_ops.attendance),
    path("api/v1/occurrences/<uuid:pk>/complete/", calendar_ops.complete),
    path(
        "api/v1/occurrences/<uuid:pk>/admin-correction/", calendar_ops.admin_correction
    ),
    path("api/v1/recovery-obligations/", calendar_ops.recovery_list),
    path("api/v1/recovery-obligations/<uuid:pk>/makeup/", calendar_ops.makeup),
    path("api/v1/recovery-obligations/<uuid:pk>/options/", lesson_slots.recovery_options),
    path("api/v1/lessons/options/", lesson_slots.lesson_options),
    path("api/v1/lessons/", lesson_slots.lesson_create),
    path("api/v1/recovery-obligations/<uuid:pk>/waive/", calendar_ops.waive),
    path("api/v1/lesson-series/", calendar_ops.series_collection),
    path("api/v1/lesson-series/<uuid:pk>/", calendar_ops.series_detail),
    path("api/v1/lesson-series/<uuid:pk>/exdate/", calendar_ops.series_exdate),
    path("api/v1/lesson-series/<uuid:pk>/override/", calendar_ops.series_override),
    path("api/v1/lesson-series/<uuid:pk>/split/", calendar_ops.series_split),
    path("api/v1/conflict-cases/", calendar_ops.conflict_list),
    path("api/v1/conflict-cases/detect/", calendar_ops.conflict_detect),
    path("api/v1/conflict-cases/<uuid:pk>/resolve/", calendar_ops.conflict_resolve),
    path("api/v1/change-requests/", calendar_ops.change_requests),
    path("api/v1/change-requests/<uuid:pk>/decide/", calendar_ops.change_decide),
    path("api/v1/change-requests/<uuid:pk>/withdraw/", calendar_ops.change_withdraw),
    path(
        "api/v1/change-requests/<uuid:pk>/guardian-confirm/",
        calendar_ops.change_guardian_confirm,
    ),
    path(
        "api/v1/change-requests/<uuid:pk>/tutor-confirm/",
        calendar_ops.change_tutor_confirm,
    ),
    path("api/v1/schedule-plans/<uuid:pk>/validate/", calendar_ops.plan_validate),
    path("api/v1/schedule-plans/<uuid:pk>/reject/", calendar_ops.plan_reject),
    path("api/v1/schedule-plans/<uuid:pk>/lifecycle/", calendar_ops.plan_lifecycle),
    path("api/v1/calendar/horizon/", calendar_ops.horizon),
    path("api/v1/availability/effective", availability_effective.effective),
    # --- fine s2-calendario ---
    # --- s3-comunicazioni ---
    path("api/v1/notifications", communications.notifications),
    path("api/v1/notifications/read-all", communications.notifications_read_all),
    path("api/v1/notifications/preferences", communications.notification_preferences),
    path("api/v1/notifications/<uuid:pk>/read", communications.notification_read),
    path("api/v1/calendar-feed-tokens", communications.feed_tokens),
    path(
        "api/v1/calendar-feed-tokens/<uuid:pk>/revoke", communications.feed_token_revoke
    ),
    path("api/v1/calendar.ics", communications.calendar_ics),
    path("api/v1/occurrences/<uuid:pk>/meeting", communications.meeting),
    path(
        "api/v1/occurrences/<uuid:pk>/meeting/presence",
        communications.meeting_presence,
    ),  # v0.10 videolezioni
    path("api/v1/communications/status", communications.communications_status),
    path("api/v1/communications/deliveries", communications.deliveries_problems),
    path(
        "api/v1/communications/deliveries/<uuid:pk>/resolve",
        communications.delivery_resolve,
    ),
    # --- fine s3-comunicazioni ---
    # --- s1-sicurezza: admin disattivabile in produzione (GAP-I06) ---
    *([path("admin/", admin.site.urls)] if settings.IDENTITY_ADMIN_ENABLED else []),
    path("api/v1/health", views.health),
    path("api/v1/auth/csrf", views.csrf),
    path("api/v1/me", views.me),
    path("api/v1/planning/readiness", views.readiness),
    # --- P2: anno scolastico, orari da griglia, approvazione disponibilità in blocco ---
    path("api/v1/planning/school-years", school_year.years),
    path("api/v1/planning/school-years/current", school_year.current_year),
    path("api/v1/planning/school-years/<uuid:pk>", school_year.year_detail),
    path("api/v1/planning/school-years/<uuid:pk>/periods", school_year.year_periods),
    path("api/v1/planning/study-periods/<uuid:pk>", school_year.period_detail),
    path("api/v1/planning/study-periods/<uuid:pk>/delete", school_year.period_delete),
    path("api/v1/planning/service-windows/replace", school_year.service_windows_replace),
    path("api/v1/availability/bulk-review", school_year.availability_bulk_review),
    path("api/v1/schedule-runs", planning_data.create_run),
    path("api/v1/planning/data-readiness", planning_data.data_readiness),
    path("api/v1/planning/example", planning.example),
    path("api/v1/planning/simulate", planning.simulation),
    path("api/v1/", include(router.urls)),
]

# --- s4-privacy ---
from api import families as s4_families, privacy as s4_privacy  # noqa: E402

urlpatterns += s4_families.urlpatterns() + s4_privacy.urlpatterns()

# --- P1 (guida v3.1): tutor (T2) e utenti del centro (T3) ---
from api import staff as p1_staff  # noqa: E402

urlpatterns += p1_staff.urlpatterns()

# --- s6-frontend: portali v2 di sola lettura ---
from api import portals_v2 as s6_portals  # noqa: E402

urlpatterns += s6_portals.urlpatterns()


# --- P3: presa visione e controproposte dei tutor ---
from api import acknowledgements  # noqa: E402

urlpatterns += [
    path("api/v1/schedule-acks", acknowledgements.collection),
    path("api/v1/schedule-acks/<uuid:pk>/acknowledge", acknowledgements.acknowledge),
    path("api/v1/schedule-acks/<uuid:pk>/counter", acknowledgements.counter),
    path("api/v1/schedule-acks/<uuid:pk>/decide", acknowledgements.decide),
]

from api import my_data as _my_data  # noqa: E402  P5 «I miei dati»

urlpatterns += _my_data.urlpatterns()

# --- v0.9.7: pianificatore mensile, impegni, conferme ---
from api import autoplanner  # noqa: E402

urlpatterns += autoplanner.urlpatterns()

from api import request_planning  # noqa: E402  v0.9.9: verifica delle lezioni di una richiesta

urlpatterns += request_planning.urlpatterns()

from api import calendar_months  # noqa: E402  v0.9.11: calendario pubblico del mese e rettifiche

urlpatterns += calendar_months.urlpatterns()
