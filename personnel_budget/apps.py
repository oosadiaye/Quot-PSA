from django.apps import AppConfig


class PersonnelBudgetConfig(AppConfig):
    name = 'personnel_budget'
    verbose_name = 'Establishment & Personnel Cost Control'

    def ready(self):
        from . import receivers  # noqa: F401  (connects the payroll budget gate)
