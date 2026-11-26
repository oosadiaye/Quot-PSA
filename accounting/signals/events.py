"""Events the accounting app announces so optional modules can react without accounting knowing they exist.

A receiver is called synchronously and may raise to refuse the action (``Signal.send`` lets exceptions through); that
is how an optional control, such as the payroll budget gate, can block a posting. With no receiver connected (the module
is not installed) nothing happens and the flow is exactly as it was before the module existed.
"""
from django.dispatch import Signal

# Sent just before a payroll run posts to the ledger.
# Provides: payroll_run (the run), total_gross (Decimal).
payroll_pre_post = Signal()

# Sent after a revenue collection has been posted to the ledger.
# Provides: collection (the RevenueCollection), journal (the posted JournalHeader).
# A receiver must not be needed for the ledger to be right: it is sent with ``send_robust`` and a failing listener is
# logged, never allowed to undo the posted journal.
revenue_collected = Signal()
