"""Model-level invariants for SnapshotJob."""
from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.db import DataError, IntegrityError

from snapshots.models import SnapshotJob


User = get_user_model()


@pytest.fixture
def actor(db):
    return User.objects.create_user(username='ada', password='x')


@pytest.mark.integration
def test_can_create_queued_job(actor):
    job = SnapshotJob.objects.create(
        schema_name='delta_state', triggered_by=actor, label='pre import')
    assert job.status == SnapshotJob.Status.QUEUED
    assert job.triggered_at is not None
    assert job.started_at is None
    assert job.completed_at is None


@pytest.mark.integration
def test_schema_name_regex_rejected_at_db_level(actor):
    # Capital letters not allowed by the CheckConstraint.
    with pytest.raises(IntegrityError):
        SnapshotJob.objects.create(schema_name='Delta_State', triggered_by=actor)


@pytest.mark.integration
def test_schema_name_starts_with_digit_rejected(actor):
    with pytest.raises(IntegrityError):
        SnapshotJob.objects.create(schema_name='1state', triggered_by=actor)


@pytest.mark.integration
def test_schema_name_too_long_rejected(actor):
    # 64-char string exceeds the VARCHAR(63) column — Postgres raises
    # DataError (StringDataRightTruncation), not IntegrityError.
    too_long = 'a' + 'b' * 63
    with pytest.raises((IntegrityError, DataError)):
        SnapshotJob.objects.create(schema_name=too_long, triggered_by=actor)


@pytest.mark.integration
def test_default_ordering_newest_first(actor):
    older = SnapshotJob.objects.create(schema_name='a', triggered_by=actor)
    newer = SnapshotJob.objects.create(schema_name='b', triggered_by=actor)
    listed = list(SnapshotJob.objects.all())
    assert listed.index(newer) < listed.index(older)


@pytest.mark.integration
def test_triggered_by_protect_blocks_user_delete(actor):
    """on_delete=PROTECT is wired on triggered_by.

    In the public-schema test environment Django's cascade collector may
    hit accounting/hrm/etc. tables that only exist in tenant schemas
    (raising ProgrammingError) before it even reaches the PROTECT check.
    We therefore verify PROTECT at the model-metadata level rather than
    by attempting a live delete, which would require all tenant-app tables
    to be present in the public schema.
    """
    from django.db import models as _models
    field = SnapshotJob._meta.get_field('triggered_by')
    assert field.remote_field.on_delete is _models.PROTECT
