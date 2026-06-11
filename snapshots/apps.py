"""Django app configuration for the snapshots feature."""
from __future__ import annotations

from django.apps import AppConfig
from django.core.checks import register


class SnapshotsConfig(AppConfig):
    name = 'snapshots'
    default_auto_field = 'django.db.models.BigAutoField'

    def ready(self) -> None:
        from .checks import check_snapshot_kek
        register(check_snapshot_kek)
