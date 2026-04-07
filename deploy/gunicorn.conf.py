"""
Gunicorn configuration for DTSG ERP — Phase 1.

Start: gunicorn dtsg_erp.wsgi:application -c deploy/gunicorn.conf.py
"""

import multiprocessing
import os

# Bind
bind = os.getenv('GUNICORN_BIND', '0.0.0.0:8000')

# Workers: 2-4 × CPU cores for I/O-bound Django apps
# Each worker holds its own DB connection pool via CONN_MAX_AGE
workers = int(os.getenv('GUNICORN_WORKERS', multiprocessing.cpu_count() * 2 + 1))

# Threads per worker: enables concurrent requests within a single worker
# This is important for django-tenants where schema switching is per-connection
threads = int(os.getenv('GUNICORN_THREADS', '4'))

# Worker class: 'gthread' for threaded workers (best for Django + DB)
worker_class = 'gthread'

# Timeouts
timeout = 120  # Kill workers that hang >2 min
graceful_timeout = 30
keepalive = 5

# Max requests before worker restart (prevents memory leaks)
max_requests = 1000
max_requests_jitter = 100

# Logging
accesslog = '-'
errorlog = '-'
loglevel = os.getenv('GUNICORN_LOG_LEVEL', 'info')

# Preload app for faster worker spawns and shared memory
preload_app = True

# Security
limit_request_line = 8190
limit_request_fields = 100
limit_request_field_size = 8190
