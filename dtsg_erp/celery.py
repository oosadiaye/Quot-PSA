"""
Celery application configuration for DTSG ERP.

Phase 2: Async task processing for tenant schema creation,
heavy reports, bulk operations, and background maintenance.
"""

import os

from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dtsg_erp.settings')

app = Celery('dtsg_erp')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Debug task for verifying Celery connectivity."""
    print(f'Request: {self.request!r}')
