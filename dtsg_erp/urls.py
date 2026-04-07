"""
URL configuration for dtsg_erp project.

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
from django.contrib import admin
from django.urls import path, include

v1_patterns = [
    path('accounting/', include('accounting.urls')),
    path('budget/', include('budget.urls')),
    path('procurement/', include('procurement.urls')),
    path('inventory/', include('inventory.urls')),
    path('service/', include('service.urls')),
    path('sales/', include('sales.urls')),
    path('workflow/', include('workflow.urls')),
    path('hrm/', include('hrm.urls')),
    path('core/', include('core.urls')),
    path('tenants/', include('tenants.urls')),
    path('quality/', include('quality.urls')),
    path('production/', include('production.urls')),
    path('superadmin/', include('superadmin.urls')),
    path('integrations/', include('integrations.urls')),
]

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/', include((v1_patterns, 'v1'))),
    # Backward compat — remove after all clients migrate to /api/v1/
    path('api/', include(v1_patterns)),
]
