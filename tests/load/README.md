# Load Testing — Quot PSE

Locust-based load harness. See `locustfile.py`.

## Install

```bash
pip install locust==2.27.0
```

## Smoke run (5 minutes, 100 users)

```bash
export LOCUST_EMAIL=loadtest@quotpse.local
export LOCUST_PASSWORD=loadtest-pwd

locust -f tests/load/locustfile.py --headless \
    -u 100 -r 10 --run-time 5m \
    --host https://tenant-demo.quotpse.local \
    --csv reports/load_$(date +%Y%m%d_%H%M)
```

Parameters:
- `-u 100` — 100 concurrent simulated users
- `-r 10`  — ramp up at 10 new users / sec
- `--run-time 5m`
- `--csv` — writes `_stats.csv`, `_failures.csv`, `_stats_history.csv`

## Acceptance thresholds

| Metric | Target | Fail |
|--------|--------|------|
| p50 latency | < 200 ms | > 500 ms |
| p95 latency | < 1 s | > 3 s |
| error-rate  | < 0.5 % | > 2 % |
| RPS steady  | ≥ 200 | < 100 |

If any row fails, open `docs/PERFORMANCE_AUDIT.md` and add the offending endpoint to the index audit backlog.

## Workload shape

- **70 %** read-heavy (dashboard, list pages, notification bell)
- **20 %** write-light (search, filtered listings)
- **10 %** heavy reports (SoFP, SoFPerf, Budget vs Actual)

## Seeding test data

Load-test tenants need a stable dataset. Before a run:

```bash
./manage.py tenant_command seed_demo_gl     --schema=demo --count=500
./manage.py tenant_command seed_demo_registers --schema=demo --count=200
./manage.py tenant_command resync_appropriation_totals --schema=demo
```

## Results log

Keep per-run summaries in `docs/LOAD_TEST_RESULTS.md` with date, git SHA, and the verdict (`PASS` / `FAIL`).
