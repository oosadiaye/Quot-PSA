from django.apps import AppConfig


class WorkflowConfig(AppConfig):
    name = 'workflow'

    def ready(self):
        import workflow.signals  # noqa: F401
