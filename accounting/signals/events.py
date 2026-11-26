"""Events the accounting app announces so optional modules can react without accounting knowing they exist.

A receiver is called synchronously and may raise to refuse the action (``Signal.send`` lets exceptions through); that
is how an optional control, such as the payroll budget gate, can block a posting. With no receiver connected (the module
is not installed) nothing happens and the flow is exactly as it was before the module existed.
"""
from django.dispatch import Signal

# Sent just before a payroll run posts to the ledger.
# Provides: payroll_run (the run), total_gross (Decimal).
payroll_pre_post = Signal()
