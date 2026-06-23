from django.apps import AppConfig


class BudgetConfig(AppConfig):
    name = 'budget'

    def ready(self):
        import budget.signals  # noqa: F401 — registers workflow-dispatch receivers
