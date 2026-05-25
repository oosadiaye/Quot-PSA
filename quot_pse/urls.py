"""
URL configuration for quot_pse project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include

v1_patterns = [
    # ─── Quot PSE: Nigeria Government IFMIS API ───────────────────────
    path('accounting/', include('accounting.urls')),
    path('budget/', include('budget.urls')),
    path('procurement/', include('procurement.urls')),
    path('inventory/', include('inventory.urls')),
    path('workflow/', include('workflow.urls')),
    path('hrm/', include('hrm.urls')),
    path('my/', include('hrm.urls_portal')),
    path('core/', include('core.urls')),
    path('tenants/', include('tenants.urls')),
    path('superadmin/', include('superadmin.urls')),
    path('contracts/', include('contracts.urls', namespace='contracts')),
]

from core.views.health import healthz, readyz          # P3-T3
from core.views.metrics import prometheus_metrics       # P3-T4

# P7-T1 — OpenAPI 3.1 schema + interactive docs.
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
    SpectacularRedocView,
)

urlpatterns = [
    # P3-T3 — liveness + readiness probes. No auth, no prefix, so k8s
    # probes can hit them from the pod network without credentials.
    path('healthz', healthz, name='healthz'),
    path('readyz',  readyz,  name='readyz'),
    # P3-T4 — Prometheus metrics scrape target. Same no-auth rationale;
    # restrict at the load balancer or via an IP allow-list in prod.
    path('metrics', prometheus_metrics, name='prometheus-metrics'),

    path('admin/', admin.site.urls),

    # P7-T1 — OpenAPI 3.1 schema + Swagger/ReDoc UIs.
    path('api/schema/',      SpectacularAPIView.as_view(),                           name='schema'),
    path('api/docs/',        SpectacularSwaggerView.as_view(url_name='schema'),      name='swagger-ui'),
    path('api/redoc/',       SpectacularRedocView.as_view(url_name='schema'),        name='redoc'),

    path('api/v1/', include((v1_patterns, 'v1'))),
    # Backward compat — remove after all clients migrate to /api/v1/
    path('api/', include(v1_patterns)),
]

# ── Media serving in development ─────────────────────────────────────
# Without this helper, every URL returned by ``ImageField.url`` /
# ``FileField.url`` (e.g. /media/warrants/printout_settings/signatures/
# governor.png) would 404 in dev — files write to disk fine, but Django
# only serves them when the URLconf is wired explicitly. In production,
# Nginx / S3 / CDN serves /media/ directly and this no-ops because
# ``static()`` returns [] when DEBUG is False.
#
# Why this matters for the warrant-printout page:
#   • Upload signature → backend writes file → response includes _url
#   • Frontend swaps <img src="blob:..."> for <img src="/media/...">
#   • Without this helper, the second src 404s → image disappears
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
