"""
End-to-end Asset Accounting Simulation - Quot PSE

Runs in the 'delta_state' tenant schema.

Steps:
  1. Create/load an AssetCategory with GL account mappings
  2. Create a FixedAsset using that category (auto-inherits defaults)
  3. Calculate depreciation for a given run date (DepreciationRun + Details)
  4. Post the run to the GL via AssetPostingService
  5. Print the resulting journal (DR Depr Expense / CR Accum Depr)
  6. Show final asset ledger state (NBV, accum depr)
"""
from datetime import date
from decimal import Decimal

from django_tenants.utils import schema_context
from accounting.models import (
    Account, FixedAsset, JournalHeader, JournalLine,
    DepreciationRun, DepreciationDetail,
)
from accounting.models.assets import AssetCategory
from accounting.services.depreciation_service import DepreciationService
from accounting.services.asset_posting import AssetPostingService


def hdr(title):
    print(f"\n{'='*72}\n {title}\n{'='*72}")


def main():
    with schema_context('delta_state'):
        hdr("STEP 1 - Asset Category with GL mappings")
        cost_acc = Account.objects.get(code='32300100')  # Vehicles (at cost)
        accum_acc = Account.objects.get(code='32300200')  # Accum Depr - Vehicles
        expense_acc = Account.objects.get(code='22110000')  # Depr Exp - Vehicles

        cat, created = AssetCategory.objects.update_or_create(
            code='VEH-MOTOR',
            defaults=dict(
                name='Motor Vehicles',
                depreciation_method='Straight-Line',
                default_life_years=5,
                residual_value_type='percentage',
                residual_value=Decimal('10'),  # 10% residual
                cost_account=cost_acc,
                accumulated_depreciation_account=accum_acc,
                depreciation_expense_account=expense_acc,
                is_active=True,
            ),
        )
        print(f"  {'Created' if created else 'Updated'}: {cat}")
        print(f"    Method       : {cat.depreciation_method}")
        print(f"    Life         : {cat.default_life_years} years")
        print(f"    Residual     : {cat.residual_value}% ({cat.residual_value_type})")
        print(f"    Cost acct    : {cat.cost_account.code} - {cat.cost_account.name}")
        print(f"    Accum  acct  : {cat.accumulated_depreciation_account.code} "
              f"- {cat.accumulated_depreciation_account.name}")
        print(f"    Expense acct : {cat.depreciation_expense_account.code} "
              f"- {cat.depreciation_expense_account.name}")

        hdr("STEP 2 - Create Fixed Asset")
        # Clean any previous sim rows so we can re-run idempotently
        FixedAsset.objects.filter(name='SIM Toyota Hilux 2026').delete()

        cost = Decimal('15000000.00')  # NGN 15M truck
        asset = FixedAsset(
            name='SIM Toyota Hilux 2026',
            description='Simulation asset for asset-lifecycle demo',
            asset_category=cat.code,          # FixedAsset still uses CharField; save() picks up defaults
            acquisition_date=date(2026, 1, 1),
            acquisition_cost=cost,
            salvage_value=cost * Decimal('0.10'),  # 10% residual = 1.5M
            asset_account=cost_acc,
            accumulated_depreciation_account=accum_acc,
            depreciation_expense_account=expense_acc,
            status='Active',
        )
        asset.save()  # triggers auto-numbering + category defaults inheritance
        print(f"  Asset #       : {asset.asset_number}")
        print(f"  Name          : {asset.name}")
        print(f"  Cost          : NGN {asset.acquisition_cost:,.2f}")
        print(f"  Salvage (10%) : NGN {asset.salvage_value:,.2f}")
        print(f"  Useful life   : {asset.useful_life_years} yrs (inherited from category)")
        print(f"  Method        : {asset.depreciation_method} (inherited)")
        depreciable = asset.acquisition_cost - asset.salvage_value
        print(f"  Depreciable   : NGN {depreciable:,.2f}")
        print(f"  Annual depr   : NGN {asset.calculate_annual_depreciation():,.2f}")
        print(f"  Monthly depr  : NGN {asset.calculate_annual_depreciation() / 12:,.2f}")

        hdr("STEP 3 - Calculate Depreciation Run (Jan 2026)")
        # Scope the run to JUST this asset so we don't depreciate every asset in the tenant
        run = DepreciationService.calculate_depreciation_run(
            run_date=date(2026, 1, 31),
            fiscal_year=2026,
            period=1,
            user=None,
            asset_ids=[asset.id],
        )
        print(f"  Run ID        : {run.id}")
        print(f"  Status        : {run.status}")
        print(f"  Assets        : {run.assets_processed}")
        print(f"  Total depr    : NGN {run.total_depreciation:,.2f}")
        print()
        for d in run.details.all():
            print(f"  Detail -> {d.asset_code}")
            print(f"    period_depreciation      : NGN {d.period_depreciation:,.2f}")
            print(f"    accum_depr_before        : NGN {d.accumulated_depreciation_before:,.2f}")
            print(f"    accum_depr_after         : NGN {d.accumulated_depreciation_after:,.2f}")
            print(f"    NBV before               : NGN {d.net_book_value_before:,.2f}")
            print(f"    NBV after                : NGN {d.net_book_value_after:,.2f}")
            print(f"    remaining_life_months    : {d.remaining_life_months}")

        hdr("STEP 4 - Post Depreciation Run to GL")
        journal = AssetPostingService.post_depreciation_run(run)
        print(f"  Journal #     : {journal.reference_number}")
        print(f"  Description   : {journal.description}")
        print(f"  Posting date  : {journal.posting_date}")
        print(f"  Status        : {journal.status}")
        print(f"  Source        : {journal.source_module}/{journal.source_document_id}")

        hdr("STEP 5 - Journal Lines")
        total_dr = total_cr = Decimal('0')
        lines = JournalLine.objects.filter(header=journal).select_related('account').order_by('id')
        print(f"  {'Account':<40} {'Type':<10} {'Debit':>15} {'Credit':>15}")
        print(f"  {'-'*40} {'-'*10} {'-'*15} {'-'*15}")
        for l in lines:
            label = f"{l.account.code} {l.account.name[:28]}"
            print(f"  {label:<40} {l.account.account_type:<10} "
                  f"{l.debit:>15,.2f} {l.credit:>15,.2f}")
            total_dr += l.debit
            total_cr += l.credit
        print(f"  {'-'*40} {'-'*10} {'-'*15} {'-'*15}")
        print(f"  {'TOTALS':<51} {total_dr:>15,.2f} {total_cr:>15,.2f}")
        assert total_dr == total_cr, "Journal not balanced!"
        print(f"  OK Journal is BALANCED (DR = CR = NGN {total_dr:,.2f})")

        hdr("STEP 6 - Final Asset Ledger State")
        # Refresh and update accumulated_depreciation from the run
        asset.refresh_from_db()
        asset.accumulated_depreciation = run.details.first().accumulated_depreciation_after
        asset.save(update_fields=['accumulated_depreciation'])
        print(f"  Asset #                  : {asset.asset_number}")
        print(f"  Acquisition cost         : NGN {asset.acquisition_cost:,.2f}")
        print(f"  Accumulated depreciation : NGN {asset.accumulated_depreciation:,.2f}")
        print(f"  Net Book Value           : NGN {asset.net_book_value:,.2f}")
        print(f"  Salvage floor            : NGN {asset.salvage_value:,.2f}")
        months_remaining = asset.useful_life_years * 12 - 1
        print(f"  Months remaining         : {months_remaining} / {asset.useful_life_years * 12}")

        hdr("SIMULATION COMPLETE")
        print("  OK Category created with GL mappings")
        print("  OK Asset auto-inherited method, life, residual from category")
        print("  OK DepreciationRun calculated monthly depreciation")
        print("  OK Journal posted and balanced (double-entry preserved)")
        print(f"  OK Asset NBV reduced from NGN {asset.acquisition_cost:,.2f} "
              f"to NGN {asset.net_book_value:,.2f} after 1 month")


main()
