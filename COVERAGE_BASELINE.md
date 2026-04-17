# Coverage Baseline — Quot PSE

**Measured**: 2026-04-17 (after Sprint 25, start of Phase 1)

## Top-line

| Metric | Value |
|---|---:|
| Apps measured | `accounting`, `core`, `budget` |
| Total statements | 28,588 |
| Covered statements | 9,056 |
| Missing statements | 19,532 |
| **Line coverage** | **32%** |
| Test suite size | 127 tests (no-DB fast tier) |
| Suite runtime | ~12 s |

## Ratchet policy

1. **No regression** — every PR must not decrease the coverage percentage
   compared to the target branch (`main` or `develop`). CI enforces this via
   `pytest --cov-fail-under=32` once the gate is flipped on.
2. **Quarterly bump** — the target coverage % increases by 5 points per
   quarter for 4 quarters (32 → 37 → 42 → 47 → 52) until the absolute target
   is reached.
3. **Absolute target for production** — **60%** line coverage across
   `accounting`, `core`, `budget`. IPSAS service methods must individually
   exceed **80%** because they produce audit-signed output.

## Why 32% and not higher

The current suite is deliberately no-DB ("fast tier") — every test runs in
under a second, making TDD practical. DB-tier tests exist but haven't been
wired into CI yet because the multi-tenant bootstrap sequence needs ordering
fixes (see `accounting/tests/README.md` → "Known limitation"). Adding DB-tier
coverage is tracked as Phase 1 follow-up.

## Where coverage is weakest

| Area | Coverage | Priority to raise |
|---|---:|---|
| `core/views/misc.py` | 9% | Low — utility endpoints |
| `core/views/tenant_user.py` | 17% | **High** — core auth path |
| `core/views/auth.py` | 21% | **High** — JWT + login hardening |
| `core/views/user.py` | 27% | Medium |
| `accounting/views/*` (legacy views_old.py path) | varies | Low — deprecated |
| `accounting/services/*` (IPSAS) | 60–90% | Already well-covered |

## What's excluded

- `views_old.py` — scheduled for removal; not worth testing
- Management commands not tested through the command-line invocation (only
  their helpers are unit-tested)
- Migration files (Django default)
- Admin site registrations

## How to reproduce

```bash
python -m pytest \
  accounting/tests/test_s14*.py \
  accounting/tests/test_s15*.py \
  accounting/tests/test_s16*.py \
  accounting/tests/test_s17*.py \
  accounting/tests/test_s18*.py \
  accounting/tests/test_s19*.py \
  accounting/tests/test_s20*.py \
  accounting/tests/test_s21*.py \
  accounting/tests/test_s25*.py \
  core/tests/test_s23*.py \
  core/tests/test_s24*.py \
  --cov=accounting --cov=core --cov=budget \
  --cov-report=term
```
