from rest_framework.decorators import api_view, permission_classes as perm_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from ..models import AccountingSettings, Account
from ..serializers import AccountingSettingsSerializer


# ===================== Accounting Settings =====================

@api_view(['GET', 'PUT'])
@perm_classes([IsAuthenticated])
def accounting_settings_api(request):
    """GET/PUT the per-tenant accounting settings (singleton)."""
    settings_obj, _ = AccountingSettings.objects.get_or_create(pk=1)

    if request.method == 'GET':
        serializer = AccountingSettingsSerializer(settings_obj)
        return Response(serializer.data)

    serializer = AccountingSettingsSerializer(settings_obj, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data)


@api_view(['POST'])
@perm_classes([IsAuthenticated])
def seed_default_coa(request):
    """Auto-seed a default Chart of Accounts based on the configured digit count and number series."""
    settings_obj, _ = AccountingSettings.objects.get_or_create(pk=1)
    digits = settings_obj.account_code_digits

    # Ensure number series is populated with defaults
    if not settings_obj.account_number_series:
        settings_obj.account_number_series = dict(AccountingSettings.DEFAULT_NUMBER_SERIES)
        settings_obj.save(update_fields=['account_number_series'])

    def pad(prefix, sub):
        """Build a zero-padded account code.
        e.g. digits=8, prefix='1', sub='001' → '10010000'
        """
        raw = prefix + sub
        return raw.ljust(digits, '0')[:digits]

    seed_accounts = [
        # 1-series: Assets
        (pad('1', '001'), 'Cash and Cash Equivalents', 'Asset'),
        (pad('1', '002'), 'Bank Accounts', 'Asset'),
        (pad('1', '003'), 'Accounts Receivable', 'Asset'),
        (pad('1', '004'), 'Prepaid Expenses', 'Asset'),
        (pad('1', '005'), 'Inventory', 'Asset'),
        (pad('1', '006'), 'Fixed Assets', 'Asset'),
        (pad('1', '007'), 'Accumulated Depreciation', 'Asset'),
        # 2-series: Liabilities
        (pad('2', '001'), 'Accounts Payable', 'Liability'),
        (pad('2', '002'), 'Accrued Liabilities', 'Liability'),
        (pad('2', '003'), 'Short-term Loans', 'Liability'),
        (pad('2', '004'), 'Long-term Debt', 'Liability'),
        # 3-series: Equity
        (pad('3', '001'), "Owner's Equity", 'Equity'),
        (pad('3', '002'), 'Retained Earnings', 'Equity'),
        (pad('3', '003'), 'Capital Reserves', 'Equity'),
        # 4-series: Income
        (pad('4', '001'), 'Service Revenue', 'Income'),
        (pad('4', '002'), 'Sales Revenue', 'Income'),
        (pad('4', '003'), 'Interest Income', 'Income'),
        (pad('4', '004'), 'Other Income', 'Income'),
        # 5-series: COGS / Production Expenses
        (pad('5', '001'), 'Cost of Goods Sold', 'Expense'),
        (pad('5', '002'), 'Materials', 'Expense'),
        (pad('5', '003'), 'Direct Labor', 'Expense'),
        # 6-series: General / Admin Expenses
        (pad('6', '001'), 'Salaries and Wages', 'Expense'),
        (pad('6', '002'), 'Rent Expense', 'Expense'),
        (pad('6', '003'), 'Utilities', 'Expense'),
        (pad('6', '004'), 'Office Supplies', 'Expense'),
        (pad('6', '005'), 'Depreciation Expense', 'Expense'),
        (pad('6', '006'), 'Travel Expense', 'Expense'),
        (pad('6', '007'), 'Insurance Expense', 'Expense'),
    ]

    existing_codes = set(Account.objects.values_list('code', flat=True))
    created = 0
    skipped = 0
    to_create = []

    for code, name, account_type in seed_accounts:
        if code in existing_codes:
            skipped += 1
        else:
            to_create.append(Account(code=code, name=name, account_type=account_type, is_active=True))
            created += 1

    if to_create:
        Account.objects.bulk_create(to_create)

    return Response({
        'success': True,
        'created': created,
        'skipped': skipped,
        'total_seed': len(seed_accounts),
        'account_code_digits': digits,
        'account_number_series': settings_obj.get_number_series(),
    })
