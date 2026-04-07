import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class ProductionConfig(AppConfig):
    name = 'production'

    def ready(self):
        from django.apps import apps
        optional_deps = {
            'accounting': 'GL posting for production orders',
            'inventory': 'Material issue/receipt stock updates',
            'quality': 'QC inspection triggers',
        }
        for mod, features in optional_deps.items():
            if apps.is_installed(mod):
                logger.debug("production: optional module '%s' available (%s)", mod, features)
            else:
                logger.info("production: optional module '%s' not installed — %s disabled", mod, features)
