"""Walk every FileField/ImageField in a schema and copy referenced files.

We iterate model instances rather than walking the filesystem so that
files orphaned by deletion (row gone, file still on disk) are excluded
from the snapshot. Bounded: you can only copy what a row references.
"""
from __future__ import annotations

import logging
import shutil
from functools import lru_cache
from pathlib import Path
from typing import Iterator

from django.apps import apps
from django.conf import settings
from django.db.models import FileField
from django_tenants.utils import schema_context


logger = logging.getLogger(__name__)


def _is_unsafe_rel_path(rel_path: str) -> bool:
    """Quick first-line check: reject absolute paths and any path with .. components.

    The post-resolve containment check is the authoritative guard; this
    short-circuits the obvious cases without filesystem syscalls.
    """
    if not rel_path:
        return True
    p = Path(rel_path)
    if p.is_absolute():
        return True
    if '..' in p.parts:
        return True
    return False


@lru_cache(maxsize=1)
def _tenant_app_labels() -> frozenset[str]:
    """Return the set of app_labels that live in TENANT_APPS only.

    Computed once per process. We compare against ``model._meta.app_label``
    rather than dotted names to handle both 'core' and 'apps.core' shapes.
    """
    tenant_labels: set[str] = set()
    for dotted in getattr(settings, 'TENANT_APPS', []):
        try:
            tenant_labels.add(apps.get_app_config(dotted.split('.')[-1]).label)
        except LookupError:
            pass
    return frozenset(tenant_labels)


def _iter_file_fields() -> Iterator[tuple[type, FileField]]:
    """Yield (model_class, field) for every FileField on every concrete TENANT model.

    SHARED-app models are excluded: their rows are visible inside schema_context
    but contain cross-tenant data that doesn't belong in a single-tenant snapshot.
    """
    tenant_labels = _tenant_app_labels()
    for model in apps.get_models():
        if model._meta.abstract or model._meta.proxy:
            continue
        if model._meta.app_label not in tenant_labels:
            continue
        for field in model._meta.get_fields():
            if isinstance(field, FileField):
                yield model, field


def _copy_one(
    rel_path: str,
    media_root: Path,
    destination: Path,
    *,
    media_root_resolved: Path | None = None,
    destination_resolved: Path | None = None,
) -> bool:
    """Copy ``media_root/rel_path`` to ``destination/rel_path``.

    Returns True on success, False if the source did not exist or the path
    fails traversal validation. Optional pre-resolved roots avoid recomputing
    resolve() on every call when batching from collect_referenced_media.
    """
    if _is_unsafe_rel_path(rel_path):
        logger.warning('snapshots.media: refusing unsafe rel_path %r', rel_path)
        return False

    media_root_resolved = media_root_resolved or media_root.resolve()
    destination_resolved = destination_resolved or destination.resolve()
    src = (media_root / rel_path).resolve()
    dst_intended = (destination / rel_path).resolve()

    if not src.is_relative_to(media_root_resolved):
        logger.warning(
            'snapshots.media: refusing src outside media_root: %s', rel_path)
        return False
    if not dst_intended.is_relative_to(destination_resolved):
        logger.warning(
            'snapshots.media: refusing dst outside destination: %s', rel_path)
        return False

    if not src.exists() or not src.is_file():
        logger.warning('snapshots.media: referenced file missing on disk: %s', src)
        return False

    dst_intended.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst_intended)
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

    # Don't pre-create the destination; do it inside the schema block so that
    # on schema_context error no orphan directory is left behind.
    copied: list[str] = []
    media_root_resolved = media_root.resolve()
    seen: set[str] = set()

    with schema_context(schema_name):
        destination.mkdir(parents=True, exist_ok=True)
        destination_resolved = destination.resolve()

        for model, field in _iter_file_fields():
            field_name = field.name
            queryset = model._default_manager.exclude(
                **{f'{field_name}__isnull': True}
            ).exclude(**{f'{field_name}__exact': ''})
            for instance in queryset.only(field_name).iterator(chunk_size=500):
                file_value = getattr(instance, field_name, None)
                if not file_value:
                    continue
                rel = str(file_value).lstrip('/\\')
                if rel in seen:
                    continue
                if _copy_one(
                    rel, media_root, destination,
                    media_root_resolved=media_root_resolved,
                    destination_resolved=destination_resolved,
                ):
                    copied.append(rel)
                    seen.add(rel)
    return copied
