import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class CoreConfig(AppConfig):
    name = 'core'

    def ready(self):
        from django.db.models.signals import post_save, pre_save
        from core.models import AuditBaseModel, log_model_changes, log_status_changes

        # Connect audit logging signals for all AuditBaseModel subclasses.
        # Using dispatch_uid prevents duplicate connections on app reload.
        post_save.connect(
            log_model_changes,
            dispatch_uid='core_audit_log_model_changes',
        )
        pre_save.connect(
            log_status_changes,
            dispatch_uid='core_audit_log_status_changes',
        )
        logger.debug("core: audit logging signals connected")
