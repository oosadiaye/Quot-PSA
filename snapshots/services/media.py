"""Walk every FileField/ImageField in a schema and copy referenced files.

We iterate model instances rather than walking the filesystem so that
files orphaned by deletion (row gone, file still on disk) are excluded
from the snapshot. Bounded: you can only copy what a row references.
"""
from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Iterator

from django.apps import apps
from django.conf import settings
from django.db.models import FileField
from django_tenants.utils import schema_context


logger = logging.getLogger(__name__)


def _iter_file_fields() -> Iterator[tuple[type, FileField]]:
    """Yield (model_class, field) for every FileField on every concrete model."""
    for model in apps.get_models():
        if model._meta.abstract or model._meta.proxy:
            continue
        for field in model._meta.get_fields():
            if isinstance(field, FileField):
                yield model, field


def _copy_one(rel_path: str, media_root: Path, destination: Path) -> bool:
    """Copy ``media_root/rel_path`` to ``destination/rel_path``.

    Returns True on success, False if the source did not exist."""
    src = media_root / rel_path
    if not src.exists() or not src.is_file():
        logger.warning('snapshots.media: referenced file missing on disk: %s', src)
        return False
    dst = destination / rel_path
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return True


def collect_referenced_media(
    *,
    schema_name: str,
    destination: Path,
    media_root: Path | None = None,
) -> list[str]:
    """Inside ``schema_name``, copy every FileField-referenced file under
    ``destination``. Returns the list of relative paths copied."""
    media_root = media_root or Path(settings.MEDIA_ROOT)
    if not media_root.exists():
        return []
    destination.mkdir(parents=True, exist_ok=True)
    copied: list[str] = []

    with schema_context(schema_name):
        for model, field in _iter_file_fields():
            field_name = field.name
            queryset = model._default_manager.exclude(
                **{f'{field_name}__isnull': True}
            ).exclude(**{f'{field_name}__exact': ''})
            for instance in queryset.only(field_name).iterator(chunk_size=500):
                file_value = getattr(instance, field_name, None)
                if not file_value:
                    continue
                rel = str(file_value).lstrip('/')
                if _copy_one(rel, media_root, destination):
                    copied.append(rel)
    return copied
