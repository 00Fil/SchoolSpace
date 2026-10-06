from django.urls import path

from . import views

urlpatterns = [
    path("healthz", views.healthz, name="ops-healthz"),
    path("readyz", views.readyz, name="ops-readyz"),
    path("metrics", views.metrics_view, name="ops-metrics"),
    path("api/v1/ready", views.ready_public, name="ops-ready"),
]
