from django.apps import AppConfig


class AccountingConfig(AppConfig):
    name = 'accounting'

    def ready(self):
        """Register signal receivers at startup.

        Importing ``accounting.signals`` attaches the centralised
        BudgetCheckRule enforcement + expenditure roll-up to every
        JournalHeader save, so that every posting path in the system
        goes through the same gate regardless of the call-site.

        ``coa_to_ncoa`` mirrors every ``Account`` create / update into the
        corresponding NCoA ``EconomicSegment`` row, so the two layers stay
        in lockstep without any manual sync step. See
        ``accounting/services/coa_to_ncoa_sync.py`` for the mapping rules.

        ``ncoa_to_legacy`` is the opposite direction: every NCoA segment
        create / update auto-creates the matching legacy
        MDA / Fund / Function / Program / Geo row and attaches the
        ``legacy_*`` bridge. Required because Journal/Voucher/Asset forms
        still query the legacy endpoints — without this signal, freshly
        imported NCoA segments produce empty dropdowns until someone
        runs ``backfill_legacy_dims``.
        """
        from accounting.signals import budget_enforcement
        budget_enforcement._connect_signals()

        from accounting.signals import coa_to_ncoa  # noqa: F401 — attaches receiver
        coa_to_ncoa._connect_signals()

        from accounting.signals import ncoa_to_legacy  # noqa: F401 — attaches receivers
        ncoa_to_legacy._connect_signals()
