import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class CoreConfig(AppConfig):
    name = 'core'

    def ready(self):
        from django.db.models.signals import post_save, pre_save
        from core.models import log_model_changes, log_status_changes

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

        # RBAC + SoD cache-invalidation hooks — every Role / SoDRule /
        # PermissionDefinition write fans out an
        # ``invalidate_permission_cache`` call for every affected user
        # so changes take effect on the very next request without any
        # restart or session refresh.
        try:
            from core.signals import connect_rbac_signals
            connect_rbac_signals()
        except Exception as exc:  # pragma: no cover — defensive
            logger.warning("core: RBAC signals not connected: %s", exc)

        # V18 — register the audit-log PII coverage system check
        # (``core.W001``). Importing the module is enough — the check
        # is registered via the @register decorator at import time.
        try:
            import core.checks  # noqa: F401
        except Exception as exc:  # pragma: no cover — defensive
            logger.warning(
                "core: audit-log PII coverage check not registered: %s", exc
            )
