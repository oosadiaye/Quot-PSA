# Quot PSE — Operator Runbook

Owner: Platform SRE  ·  On-call: `#quotpse-oncall`  ·  Last reviewed: 2026-04-17

This runbook lists the scenarios an operator is most likely to hit. Each
entry gives: **symptoms → triage → remediation → verification**. Use it
as a checklist; don't improvise during an incident.

---

## 0. Prerequisites

- SSH access to the Quot PSE application servers
- `kubectl` context pointing at the production cluster
- `psql` access to the primary (via IAM role)
- Secrets in `~/.config/quotpse/.env` (never commit)

Every command in this doc assumes the env file is sourced:

```bash
set -a; source ~/.config/quotpse/.env; set +a
```

---

## 1. Service is down — `/readyz` failing

**Symptoms:** 5xx from all endpoints; `readyz` returns 503.

**Triage:**
```bash
kubectl -n quotpse get pods
kubectl -n quotpse logs -l app=web --tail=200 | grep -E 'ERROR|CRITICAL'
curl -s https://api.quotpse.ng/readyz | jq
```

**Remediation:**
- DB connection failure → §2
- Redis outage → §3
- Migrations pending → `kubectl exec deploy/web -- ./manage.py migrate_schemas --executor=multiprocessing`
- OOM / 137 exits → bump the web deployment memory request by 50 % and `rollout restart`

**Verification:** `/readyz` returns 200 for 3 consecutive polls.

---

## 2. Database fail-over / replication lag

**Symptoms:** slow writes, timeouts on `POST /api/accounting/journals/post`.

**Triage:**
```bash
psql $DATABASE_URL -c "SELECT now() - pg_last_xact_replay_timestamp() AS lag;"
psql $DATABASE_URL -c "SELECT state, count(*) FROM pg_stat_activity GROUP BY 1;"
```

**Remediation:**
- Lag > 60 s: drain the read-replica from the app's `replica` alias:
  `unset DB_REPLICA_HOST && kubectl rollout restart deploy/web`
- Primary stalled: invoke managed fail-over via cloud console. Record the
  fail-over event in `#incidents` with start/end timestamps.

**Verification:** lag back under 5 s; `/readyz` green; a journal posts.

---

## 3. Redis / cache layer outage

**Symptoms:** slow report loads but no 5xx (report cache fails open, §P6-T4).

**Triage:**
```bash
kubectl -n quotpse exec deploy/web -- python -c "
from django.core.cache import cache; print(cache.get('health', 'MISS'))
"
```

**Remediation:**
- Restart the Redis master
- If persistence corruption suspected, failover to the replica and replay
- Sessions are resilient (`SESSION_ENGINE='db'` via fallback automatically)

**Verification:** `cache.set('health', 'ok')` round-trips.

---

## 4. Tenant onboarding

Follow [docs/RUNBOOK_ONBOARD_TENANT.md](RUNBOOK_ONBOARD_TENANT.md).
Key steps in brief: create `Client` + `Domain`, run `migrate_schemas --tenant`, seed NCoA, create the Accountant-General user.

---

## 5. Tenant off-boarding (decommission)

```bash
./manage.py tenant_command dumpdata --schema=<schema> -o /tmp/<schema>_final.json
./manage.py drop_schema --schema=<schema>   # custom mgmt command; irreversible
```

Archive the JSON dump and the last `pg_dump` to cold storage for 7 years
(IPSAS retention minimum).

---

## 6. Journal posting blocked — "period closed"

**Symptoms:** 400 with `Cannot post to period … status is: CLOSED`.

**Triage:** confirm the period status in the Period Close admin.

**Remediation:**
- Legitimate back-dated entry → the Accountant-General issues a
  **DualControlOverride** via the AdminConsole; override reason is audited.
- Mistake → correct the `posting_date` to the current open period and re-post.

**Verification:** the journal posts; the override (if used) appears in the
Override Audit page with both approver signatures.

---

## 7. Budget-availability failure on PO approval

**Symptoms:** procurement workflow stalls; `commitments.create_commitment_for_po`
raises `BudgetExceededError`.

**Triage:**
```sql
SELECT a.id, a.amount_approved, a.cached_total_committed, a.cached_total_expended
FROM budget_appropriation a
WHERE a.id = <appropriation_id>;
```

**Remediation:**
- Totals stale (>24 h old refresh) → run
  `./manage.py tenant_command resync_appropriation_totals --schema=<t>`
- Genuine over-commit → the user must secure a Supplementary Appropriation
  or a Virement; do **not** approve manually.

---

## 8. Notification fan-out silent

**Symptoms:** users report stale unread counts; bell never increments.

**Triage:**
```bash
kubectl -n quotpse exec deploy/celery-worker -- celery -A quot_pse inspect active
```

**Remediation:**
- Worker crashed → `kubectl rollout restart deploy/celery-worker`
- Broker disconnected → §3

**Verification:** `./manage.py send_test_email --to you@example.com` delivers.

---

## 9. Report cache serving stale data

**Symptoms:** a just-posted journal does not change the Statement of
Financial Position total on refresh.

**Triage:** check the `rpt_ns:*` generation counter in Redis:
```bash
redis-cli --scan --pattern 'dtsg:rpt_ns:*'
```

**Remediation:**
- The cache-bust hook should fire automatically. If it doesn't:
  `redis-cli DEL dtsg:rpt:v1:<schema>:sofp:*` (manual bust)
- Root-cause must be filed as a bug — automatic bust failing means
  cache invariants are broken.

---

## 10. Statutory XML rejected by FIRS / PENCOM

**Symptoms:** FIRS / PENCOM portal returns a schema-validation error after
upload of a Quot PSE-generated XML.

**Triage:**
```bash
./manage.py shell -c "
from accounting.services.statutory_xml import validate_xml
with open('/tmp/payload.xml','rb') as f: r = validate_xml(f.read(), 'firs_wht.xsd')
print(r.errors); print(r.warnings)
"
```

**Remediation:**
- `lxml not installed` warning → ensure `lxml` is in prod requirements;
  only the optional XSD content-validation step depends on it. Without it
  we only verify well-formedness.
- Real schema mismatch → treat as an S-bug; fix the exporter and re-file
  the return marked as `ReturnType=AMENDED`.

---

## 11. Nightly backup missed

**Symptoms:** `#quotpse-backups` channel reports no upload for a day.

**Triage:** check the cronjob on the backup host:
```bash
systemctl status quotpse-backup.timer
tail -100 /var/log/quotpse/backup.log
```

**Remediation:**
- Run the script manually: `bash scripts/backup.sh`
- Verify retention sweep: old dumps beyond 30 days are deleted and
  monthly ones kept. See the script header for the rotation policy.

**DR drill** cadence: quarterly; see [docs/DR_DRILL.md](DR_DRILL.md).

---

## 12. Load-test regression

Before a release, rerun the Locust harness (§P6-T3):

```bash
locust -f loadtests/load/locustfile.py --headless \
  -u 100 -r 10 --run-time 5m --host https://staging.quotpse.ng
```

Accept the build only if p50 < 200 ms, p95 < 1 s, err < 0.5 %. Record
the verdict in `docs/LOAD_TEST_RESULTS.md` (append, never overwrite).

---

## 13. Rollback

1. `kubectl rollout undo deploy/web deploy/celery-worker`
2. If a migration was shipped: run the reverse migration *only* after
   confirming it is reversible. Irreversible migrations (data backfills,
   column drops) must be rolled forward with a hotfix — never use
   `migrate <app> <older_tag>` on such revisions.
3. Post an incident update in `#incidents` with the rollback commit SHA
   and the change-window ticket.

---

## 14. Where to look for more

- **Architecture overview:** [INTEGRATION_ARCHITECTURE.md](../INTEGRATION_ARCHITECTURE.md)
- **Tenant onboarding:** [docs/RUNBOOK_ONBOARD_TENANT.md](RUNBOOK_ONBOARD_TENANT.md)
- **DR drill procedure:** [docs/DR_DRILL.md](DR_DRILL.md)
- **Performance audit:** [docs/PERFORMANCE_AUDIT.md](PERFORMANCE_AUDIT.md)
- **Load test harness:** [loadtests/load/README.md](../loadtests/load/README.md)
- **API reference (live):** <https://api.quotpse.ng/api/docs/>
