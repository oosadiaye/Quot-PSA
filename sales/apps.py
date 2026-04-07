import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class SalesConfig(AppConfig):
    name = 'sales'

    def ready(self):
        from django.apps import apps
        optional_deps = {
            'accounting': 'GL posting, customer invoicing',
            'inventory': 'Stock reservation on order approval',
        }
        for mod, features in optional_deps.items():
            if apps.is_installed(mod):
                logger.debug("sales: optional module '%s' available (%s)", mod, features)
            else:
                logger.info("sales: optional module '%s' not installed — %s disabled", mod, features)
