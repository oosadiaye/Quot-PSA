"""Accounting signals — centralised side-effects for model lifecycle events.

Importing this module registers every signal. `AccountingConfig.ready()`
imports it so Django discovers the receivers at startup.
"""
from . import budget_enforcement  # noqa: F401
