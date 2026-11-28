from .models import JOURNAL_LINE, DimensionTag


def drop_tags_of_deleted_line(sender, instance, **kwargs):
    """A draft journal's lines are recreated on every save, so the tags of a line that goes must go with it."""
    DimensionTag.objects.filter(record_type=JOURNAL_LINE, record_id=instance.pk).delete()
