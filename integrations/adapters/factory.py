"""
Adapter Factory
===============
Maps SystemType to the correct adapter class.
Usage:
    adapter = get_adapter(integration_config)
    adapter.test_connection()
"""
from integrations.models import SystemType
from .sap import SAPAdapter
from .dynamics import Dynamics365BCAdapter
from .sage import SageIntacctAdapter, Sage200Adapter
from .generic import (
    QuickBooksAdapter, XeroAdapter, ShopifyAdapter,
    StripeAdapter, PaystackAdapter, FlutterwaveAdapter,
    GenericRESTAdapter,
)


ADAPTER_MAP = {
    SystemType.SAP_ECC: SAPAdapter,
    SystemType.SAP_S4HANA: SAPAdapter,
    SystemType.SAP_BC: SAPAdapter,
    SystemType.DYNAMICS_365_BC: Dynamics365BCAdapter,
    SystemType.DYNAMICS_365_FO: Dynamics365BCAdapter,
    SystemType.DYNAMICS_AX: Dynamics365BCAdapter,
    SystemType.SAGE_INTACCT: SageIntacctAdapter,
    SystemType.SAGE_200: Sage200Adapter,
    SystemType.SAGE_50: Sage200Adapter,
    SystemType.SAGE_X3: Sage200Adapter,
    SystemType.QUICKBOOKS: QuickBooksAdapter,
    SystemType.XERO: XeroAdapter,
    SystemType.SHOPIFY: ShopifyAdapter,
    SystemType.STRIPE: StripeAdapter,
    SystemType.PAYSTACK: PaystackAdapter,
    SystemType.FLUTTERWAVE: FlutterwaveAdapter,
    SystemType.CUSTOM: GenericRESTAdapter,
    SystemType.CUSTOM_SOAP: GenericRESTAdapter,
    SystemType.WEBHOOK_ONLY: GenericRESTAdapter,
}


def get_adapter(config):
    """Return the appropriate adapter instance for an IntegrationConfig."""
    cls = ADAPTER_MAP.get(config.system_type, GenericRESTAdapter)
    return cls(config)
