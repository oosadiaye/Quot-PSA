# Lint Baseline — Quot PSE

**Measured**: after P1-T3 ruff auto-fix, start of Phase 1 Task 3.

## Current state

**247 remaining findings** across `accounting`, `budget`, `procurement`, `core`.
Down from **2,194** before Phase 1 started (89% reduction).

| Code | Count | Description | Action |
|---|---:|---|---|
| E402 | 35 | Module-level import not at top of file | Usually deliberate (lazy imports in models); acceptable |
| F841 | 25 | Local variable assigned but unused | Clean up case-by-case |
| F821 | 14 | **Undefined name** | **Investigate — potential bug** |
| F403 | 11 | Star-import from module — unable to resolve names | `accounting/models/__init__.py` re-exports; acceptable with noqa |
| F405 | 0 | (Cleared — dropped off after --unsafe-fixes) | |
| E741 | 10 | Ambiguous variable name (l/O/I) | Rename per PEP 8 |
| F811 | 5 | Redefined while unused | Remove duplicates |
| E701 | 4 | Multiple statements on one line (colon) | Split |
| E722 | 1 | Bare `except:` | Replace with `except Exception:` |
| F401 | 1 | Unused import | Remove or `# noqa` |
| F601 | 1 | Dict with duplicate keys | Fix typo |

## Ratchet policy

1. **CI gate set to advisory (`continue-on-error: true`)** until the count
   drops to zero. The gate logs findings but does not fail the build.
2. **No regression** — every PR must not increase the total count.
3. **Priority order**:
   - P0 (investigate this week): 14 × F821 undefined-name — potential bugs
   - P1 (next month): E722 bare-except, F601 duplicate-key, F811 redefines
   - P2 (cleanup backlog): F841 unused-var, E741 ambiguous-name
   - P3 (acceptable or noqa): E402, F403, F405
4. **Target**: 0 findings by the time Phase 7 documentation ships. Flip the
   gate from `continue-on-error: true` to strict at that point.

## Reproduce

```bash
python -m ruff check accounting budget procurement core \
  --select E,F,W --ignore E501 --statistics
```

## Auto-fix (safe)

```bash
python -m ruff check accounting budget procurement core \
  --select E,F,W --ignore E501 --fix
# Then, after manual review:
python -m ruff check accounting budget procurement core \
  --select W --ignore E501 --fix --unsafe-fixes
```
