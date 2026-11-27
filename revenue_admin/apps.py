from django.apps import AppConfig


class RevenueAdminConfig(AppConfig):
    name = 'revenue_admin'
    verbose_name = 'Revenue Administration (IGR)'

    def ready(self):
        from . import receivers  # noqa: F401  (connects the collection → arrears link)
