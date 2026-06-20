"""
Async report-export feature — end-to-end (additive surface).

Exercises the queue-and-poll flow against the real ``AsyncExportJob``
viewset using the project's tenant-schema test harness (see
``accounting/tests/conftest.py``):

1. ``POST /accounting/exports/`` creates a PENDING job and returns 202.
2. With Celery eager, ``run_async_export`` runs inline → job SUCCESS,
   ``file_size > 0``.
3. ``GET /accounting/exports/<id>/`` reflects SUCCESS.
4. ``GET /accounting/exports/<id>/download/`` streams a non-empty body.
5. A second user CANNOT see the first user's job (ownership scoping).

The payload uses ``fmt='html'`` — the simplest, dependency-light render
path — and is shaped like a report dict so ``ReportRenderer.render``
handles it cleanly. Amounts are strings, matching how ``JSONField``
round-trips Decimals (DjangoJSONEncoder), proving the stored payload
renders without modifying the renderer.

Run in CI under the django-tenants harness. If the tenant DB harness
cannot initialise locally, ``manage.py check`` + ``makemigrations
--check`` still validate the additive wiring.
"""
from __future__ import annotations

import tempfile

import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APIRequestFactory, force_authenticate

from accounting.models import AsyncExportJob
from accounting.views.async_export import AsyncExportJobViewSet


pytestmark = pytest.mark.django_db


# A small report dict shaped like an IPSAS statement. Amounts are
# STRINGS — exactly what JSONField gives back for Decimals — so this
# doubles as a Decimal-round-trip smoke test.
SAMPLE_PAYLOAD = {
    'title': 'Test',
    'period_label': '2026',
    'tenant_name': 'T',
    'revenue': {
        'items': [{'code': '1', 'name': 'Tax', 'amount': '100.00'}],
        'total': '100.00',
    },
}


def _user(username):
    User = get_user_model()
    user, _ = User.objects.get_or_create(
        username=username,
        defaults={'email': f'{username}@test.local'},
    )
    return user


def _create_job(factory, user):
    """POST /accounting/exports/ as ``user``; return the DRF response."""
    request = factory.post(
        '/api/accounting/exports/',
        {'label': 'Test Export', 'fmt': 'html', 'report_payload': SAMPLE_PAYLOAD},
        format='json',
    )
    force_authenticate(request, user=user)
    view = AsyncExportJobViewSet.as_view({'post': 'create'})
    return view(request)


@override_settings(
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_TASK_EAGER_PROPAGATES=True,
)
def test_create_runs_eagerly_and_download_succeeds(db):
    factory = APIRequestFactory()
    user = _user('exporter')

    with tempfile.TemporaryDirectory() as media_root:
        with override_settings(MEDIA_ROOT=media_root):
            # 1. POST → 202 with job id.
            create_resp = _create_job(factory, user)
            assert create_resp.status_code == 202
            job_id = create_resp.data['id']
            assert create_resp.data['status'] == AsyncExportJob.STATUS_PENDING

            # 2. Eager Celery ran the render inline → SUCCESS + bytes.
            job = AsyncExportJob.objects.get(pk=job_id)
            assert job.status == AsyncExportJob.STATUS_SUCCESS
            assert job.file_size > 0

            # 3. GET status reflects SUCCESS.
            status_req = factory.get(f'/api/accounting/exports/{job_id}/')
            force_authenticate(status_req, user=user)
            status_resp = AsyncExportJobViewSet.as_view(
                {'get': 'retrieve'}
            )(status_req, pk=job_id)
            assert status_resp.status_code == 200
            assert status_resp.data['status'] == 'SUCCESS'
            assert status_resp.data['file_size'] > 0

            # 4. GET download → 200 with a non-empty body.
            dl_req = factory.get(f'/api/accounting/exports/{job_id}/download/')
            force_authenticate(dl_req, user=user)
            dl_resp = AsyncExportJobViewSet.as_view(
                {'get': 'download'}
            )(dl_req, pk=job_id)
            assert dl_resp.status_code == 200
            body = b''.join(dl_resp.streaming_content)
            assert len(body) > 0
            assert b'Test' in body  # report title rendered into the HTML
            # Close the FileResponse so its file handle is released before
            # the temp MEDIA_ROOT is torn down — otherwise Windows raises
            # PermissionError (WinError 32) unlinking the still-open file.
            dl_resp.close()


@override_settings(
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_TASK_EAGER_PROPAGATES=True,
)
def test_other_user_cannot_see_or_download_job(db):
    factory = APIRequestFactory()
    owner = _user('owner')
    intruder = _user('intruder')

    with tempfile.TemporaryDirectory() as media_root:
        with override_settings(MEDIA_ROOT=media_root):
            create_resp = _create_job(factory, owner)
            job_id = create_resp.data['id']

            # Intruder polls the owner's job → 404 (scoped out, not leaked).
            status_req = factory.get(f'/api/accounting/exports/{job_id}/')
            force_authenticate(status_req, user=intruder)
            status_resp = AsyncExportJobViewSet.as_view(
                {'get': 'retrieve'}
            )(status_req, pk=job_id)
            assert status_resp.status_code == 404

            # Intruder tries to download → also 404.
            dl_req = factory.get(f'/api/accounting/exports/{job_id}/download/')
            force_authenticate(dl_req, user=intruder)
            dl_resp = AsyncExportJobViewSet.as_view(
                {'get': 'download'}
            )(dl_req, pk=job_id)
            assert dl_resp.status_code == 404


@override_settings(
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_TASK_EAGER_PROPAGATES=True,
)
def test_download_conflicts_while_not_ready(db):
    """A job that never succeeded returns 409 from /download/."""
    factory = APIRequestFactory()
    user = _user('pending-owner')

    # Build a job directly in a non-success state (bypass the task).
    job = AsyncExportJob.objects.create(
        label='Stuck', fmt='html', report_payload=SAMPLE_PAYLOAD,
        requested_by=user, status=AsyncExportJob.STATUS_FAILED,
        error='boom',
    )
    dl_req = factory.get(f'/api/accounting/exports/{job.pk}/download/')
    force_authenticate(dl_req, user=user)
    dl_resp = AsyncExportJobViewSet.as_view({'get': 'download'})(dl_req, pk=job.pk)
    assert dl_resp.status_code == 409
    assert dl_resp.data['status'] == 'FAILED'
