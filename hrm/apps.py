from django.apps import AppConfig


class HrmConfig(AppConfig):
    name = 'hrm'

    def ready(self):
        # Register data-tagged system checks (run via:
        # ``python manage.py check --tag=database``).
        from hrm import checks  # noqa: F401
