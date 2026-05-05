"""Django system checks for the tenants app.

Surfaces production-misconfiguration risks during ``manage.py check``
so deploys fail fast instead of silently falling back to placeholder
values that produce broken tenant URLs at runtime.
"""
from django.conf import settings
from django.core.checks import Warning as DjangoWarning, register


@register()
def tenant_subdomain_base_configured(app_configs, **kwargs):
    """Warn when ``TENANT_SUBDOMAIN_BASE`` is missing in non-DEBUG.

    ``Client.subdomain`` falls back to ``'dtsg.test'`` when the
    setting is unset — fine for local dev but produces a
    non-resolvable URL in production. The warning shows up under
    ``manage.py check --deploy`` so a release pipeline that runs
    deploy checks catches the misconfig.
    """
    issues = []
    base = getattr(settings, 'TENANT_SUBDOMAIN_BASE', None)
    if not base and not settings.DEBUG:
        issues.append(
            DjangoWarning(
                'TENANT_SUBDOMAIN_BASE is not configured. Tenant '
                'subdomains will fall back to the placeholder '
                "'dtsg.test', which is non-routable. Set "
                'TENANT_SUBDOMAIN_BASE in settings (e.g., '
                "'erp.example.gov').",
                id='tenants.W001',
            )
        )
    return issues
