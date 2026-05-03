"""
Contracts app — Contract & Milestone Payment Management Module
Delta State Government of Nigeria / Quot PSE IFMIS

Implements structural overpayment prevention across 10 control layers:
  1. Contract ceiling (original sum + approved variations)
  2. Progress-payment coherence (IPC net ≤ certified - already paid)
  3. Cumulative monotonicity (each IPC ≥ previous IPC cumulative)
  4. Mobilization pro-rata recovery
  5. Retention cap enforcement
  6. Variation approval tiers (BPP due-process thresholds)
  7. Duplicate IPC prevention (integrity hash)
  8. Fiscal-year boundary (IPSAS accrual)
  9. Three-way match (IPC ↔ Measurement Book ↔ Payment Voucher)
 10. Segregation of Duties matrix
"""
import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class ContractsConfig(AppConfig):
    name = "contracts"
    verbose_name = "Contract & Milestone Payments"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        # Register signal handlers once the app registry is fully loaded.
        try:
            import contracts.signals  # noqa: F401
        except ImportError:
            pass

        from django.apps import apps

        optional_deps = {
            "accounting": "GL posting, budget commitment JEs",
            "procurement": "Vendor master, PO linkage",
            "budget": "Appropriation / budget validation",
            "workflow": "Multi-level approval routing",
        }
        for mod, features in optional_deps.items():
            if apps.is_installed(mod):
                logger.debug("contracts: optional module '%s' available (%s)", mod, features)
            else:
                logger.info(
                    "contracts: optional module '%s' not installed — %s disabled",
                    mod,
                    features,
                )
