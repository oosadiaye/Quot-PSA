"""Print how deeply each optional module is wired into the application (tracked files only).

Run from the repository root:  python scripts/module_matrix.py
Columns: backend test files, then how many non-test source files mention the ledger, workflow, MDA scoping or signals.
A module with 0 tests, or with no ledger/workflow/signal mentions, is a register without behaviour yet.
"""
import subprocess

APPS = [
    "budget_prep", "personnel_budget", "cash_planning", "catalogue", "egp", "revenue_admin", "debt",
    "staff_advances", "fleet", "legal", "disclosure", "internal_audit", "transparency", "results", "integrations",
]
MARKS = {
    "ledger": ("JournalHeader", "JournalLine", "post_journal"),
    "workflow": ("workflow", "approval"),
    "mda": ("mda", "administrative"),
    "signals": ("receiver", "signals"),
}


def tracked_python(app: str) -> list[str]:
    out = subprocess.run(["git", "ls-files", app], capture_output=True, text=True, check=True).stdout.split()
    return [p for p in out if p.endswith(".py") and "/migrations/" not in p]


def mentions(path: str, words: tuple[str, ...]) -> bool:
    try:
        text = open(path, encoding="utf-8").read().lower()
    except OSError:
        return False
    return any(w.lower() in text for w in words)


def main() -> None:
    print(f"{'app':18}{'tests':>6}" + "".join(f"{k:>10}" for k in MARKS))
    for app in APPS:
        files = tracked_python(app)
        tests = sum(1 for f in files if "/tests/" in f and f.rsplit("/", 1)[-1].startswith("test_"))
        sources = [f for f in files if "/tests/" not in f]
        cells = "".join(f"{sum(mentions(f, words) for f in sources):>10}" for words in MARKS.values())
        print(f"{app:18}{tests:>6}{cells}")


if __name__ == "__main__":
    main()
