from django.apps import AppConfig


class DimensionsConfig(AppConfig):
    name = 'dimensions'
    verbose_name = 'Custom Dimensions'

    def ready(self):
        from django.db.models.signals import post_delete

        from accounting.models import JournalLine
        from .receivers import drop_tags_of_deleted_line

        post_delete.connect(drop_tags_of_deleted_line, sender=JournalLine, dispatch_uid='dimensions_drop_line_tags')
