"""P6-T3 — Locust load-test harness for Quot PSE.

Models a mixed public-sector workload:
  * 70 % read traffic (dashboards, reports, list-pages)
  * 20 % write-light (search, filter, bookmark)
  * 10 % heavy (open an IPSAS report, export Excel)

Run a local smoke test (no UI):
    pip install locust
    locust -f loadtests/load/locustfile.py --headless \\
        -u 100 -r 10 --run-time 5m \\
        --host https://tenant-demo.quotpse.local

Target: 100 concurrent users × 10 req/s per user.
Exit criteria (see loadtests/load/README.md):
    p50 < 200 ms, p95 < 1 s, error-rate < 0.5 %.
"""
from __future__ import annotations

import os
import random

from locust import HttpUser, between, task


# ─────────────────────────── auth helpers ────────────────────────────

class QuotPSEUser(HttpUser):
    """Base class — performs JWT login on start and re-authenticates on 401."""

    wait_time = between(1, 3)      # each simulated user pauses 1–3 s between tasks
    abstract = True

    def on_start(self):
        self.token: str | None = None
        self.login()

    def login(self) -> None:
        email = os.getenv('LOCUST_EMAIL', 'loadtest@quotpse.local')
        password = os.getenv('LOCUST_PASSWORD', 'loadtest-pwd')
        with self.client.post(
            '/api/auth/login/',
            json={'email': email, 'password': password},
            catch_response=True,
            name='/api/auth/login/',
        ) as r:
            if r.status_code == 200:
                data = r.json()
                self.token = data.get('access') or data.get('token')
                self.client.headers.update({'Authorization': f'Bearer {self.token}'})
                r.success()
            else:
                r.failure(f'Login failed — {r.status_code}')


# ─────────────────────────── workloads ───────────────────────────────

class ReadHeavyUser(QuotPSEUser):
    """Represents a finance officer refreshing dashboards + opening reports."""
    weight = 7

    @task(3)
    def dashboard(self):
        self.client.get('/api/accounting/dashboard/')

    @task(3)
    def journal_list(self):
        self.client.get('/api/accounting/journals/?page=1&page_size=25')

    @task(2)
    def appropriations(self):
        self.client.get('/api/budget/appropriations/?page=1&page_size=25',
                        name='/api/budget/appropriations/')

    @task(1)
    def notification_count(self):
        self.client.get('/api/core/notifications/unread_count/')

    @task(1)
    def vendor_invoices(self):
        status = random.choice(['Draft', 'Posted', 'Paid'])
        self.client.get(
            f'/api/accounting/vendor-invoices/?status={status}&page=1',
            name='/api/accounting/vendor-invoices/?status=[status]',
        )


class WriteLightUser(QuotPSEUser):
    """Represents a user filtering + searching — no DB writes yet."""
    weight = 2

    @task
    def search_accounts(self):
        term = random.choice(['cash', 'revenue', 'salary', 'capital'])
        self.client.get(
            f'/api/accounting/accounts/?search={term}',
            name='/api/accounting/accounts/?search=[term]',
        )

    @task
    def filter_journals_by_date(self):
        self.client.get(
            '/api/accounting/journals/?posting_date_after=2026-01-01'
            '&posting_date_before=2026-03-31',
            name='/api/accounting/journals/?date_range',
        )


class ReportUser(QuotPSEUser):
    """Represents the Accountant-General opening the heavy IPSAS reports."""
    weight = 1

    @task
    def sofp(self):
        self.client.get(
            '/api/accounting/reports/financial-position/?period=2026-Q1',
            name='/api/accounting/reports/financial-position/',
        )

    @task
    def sofperf(self):
        self.client.get(
            '/api/accounting/reports/financial-performance/?period=2026-Q1',
            name='/api/accounting/reports/financial-performance/',
        )

    @task
    def budget_vs_actual(self):
        self.client.get(
            '/api/accounting/reports/budget-vs-actual/?fiscal_year=2026',
            name='/api/accounting/reports/budget-vs-actual/',
        )
