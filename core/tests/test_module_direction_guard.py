"""Existing apps must never import the optional modules (the 'with or without' contract, rule 1).

The optional modules may depend on the core apps; the core apps must stay unaware of them, so a tenant can run with any
module switched off or not installed. A violation is fixed by turning the import into a signal or a string reference,
never by loosening this test.
"""
import pathlib
import re

OPTIONAL = [
    "budget_prep", "personnel_budget", "cash_planning", "catalogue", "egp", "revenue_admin", "debt",
    "staff_advances", "fleet", "legal", "disclosure", "internal_audit", "transparency", "results", "integrations",
]
CORE = ["budget", "procurement", "accounting", "hrm", "contracts", "inventory"]
ROOT = pathlib.Path(__file__).resolve().parents[2]
IMPORT = re.compile(r"^\s*(?:from|import)\s+(?:%s)\b" % "|".join(OPTIONAL), re.M)
SKIP_DIRS = {"migrations", "tests", "venv", ".venv", "__pycache__", "node_modules"}


def _core_sources():
    for app in CORE:
        for path in (ROOT / app).rglob("*.py"):
            if SKIP_DIRS.isdisjoint(path.parts):
                yield path


def test_core_apps_do_not_import_optional_modules():
    offenders = sorted({
        f"{path.relative_to(ROOT)}: {m.group(0).strip()}"
        for path in _core_sources()
        for m in IMPORT.finditer(path.read_text(encoding="utf-8", errors="ignore"))
    })
    assert offenders == [], "core apps import optional modules:\n" + "\n".join(offenders)


def test_guard_actually_scans_files():
    """A guard that scans nothing passes forever; make sure it sees the core apps."""
    assert sum(1 for _ in _core_sources()) > 100
