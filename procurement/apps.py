import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class ProcurementConfig(AppConfig):
    name = 'procurement'

    def ready(self):
        import procurement.signals  # noqa: F401 — register signal handlers

        # Log availability of optional cross-module dependencies at startup
        from django.apps import apps
        optional_deps = {
            'accounting': 'GL posting, budget checks',
            'quality': 'QC inspection on GRN',
            'inventory': 'Stock movement on GRN',
        }
        for mod, features in optional_deps.items():
            if apps.is_installed(mod):
                logger.debug("procurement: optional module '%s' available (%s)", mod, features)
            else:
                logger.info("procurement: optional module '%s' not installed — %s disabled", mod, features)
