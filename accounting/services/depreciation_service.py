"""Depreciation Service

Provides depreciation calculation and consolidation:
- Multiple depreciation methods
- Depreciation scheduling
- Consolidation of duplicate models
"""
from datetime import date
from decimal import Decimal
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass
from django.db import transaction
from django.contrib.auth.models import User
from accounting.models import DepreciationRun, DepreciationDetail


@dataclass
class DepreciationCalculation:
    """Result of depreciation calculation for an asset."""
    asset_id: int
    asset_code: str
    period_depreciation: Decimal
    accumulated_depreciation: Decimal
    net_book_value: Decimal
    is_fully_depreciated: bool
    remaining_life_months: int


class DepreciationService:
    """Service for depreciation calculations and operations."""

    METHODS = {
        'Straight-Line': 'straight_line',
        'Declining Balance': 'declining_balance',
        'Double Declining Balance': 'double_declining_balance',
        'Sum of Years Digits': 'sum_of_years',
        'Units of Production': 'units_of_production',
    }

    @classmethod
    def straight_line(
        cls,
        acquisition_cost: Decimal,
        salvage_value: Decimal,
        useful_life_years: int,
        period_months: int = 1
    ) -> Decimal:
        """Calculate straight-line depreciation."""
        if useful_life_years <= 0:
            return Decimal('0')
        
        depreciable = acquisition_cost - salvage_value
        annual = depreciable / Decimal(str(useful_life_years))
        monthly = annual / Decimal('12')
        
        return (monthly * Decimal(str(period_months))).quantize(Decimal('0.01'))

    @classmethod
    def declining_balance(
        cls,
        current_value: Decimal,
        salvage_value: Decimal,
        useful_life_years: int,
        period_months: int = 1
    ) -> Decimal:
        """Calculate declining balance depreciation."""
        if useful_life_years <= 0:
            return Decimal('0')
        
        rate = Decimal('1') / Decimal(str(useful_life_years))
        annual = current_value * rate
        monthly = annual / Decimal('12')
        
        depreciation = monthly * Decimal(str(period_months))
        
        max_depreciation = current_value - salvage_value
        if depreciation > max_depreciation:
            depreciation = max_depreciation
        
        return depreciation.quantize(Decimal('0.01'))

    @classmethod
    def double_declining_balance(
        cls,
        current_value: Decimal,
        salvage_value: Decimal,
        useful_life_years: int,
        period_months: int = 1
    ) -> Decimal:
        """Calculate double declining balance depreciation."""
        if useful_life_years <= 0:
            return Decimal('0')
        
        rate = (Decimal('2') / Decimal(str(useful_life_years)))
        annual = current_value * rate
        monthly = annual / Decimal('12')
        
        depreciation = monthly * Decimal(str(period_months))
        
        max_depreciation = current_value - salvage_value
        if depreciation > max_depreciation:
            depreciation = max_depreciation
        
        return depreciation.quantize(Decimal('0.01'))

    @classmethod
    def sum_of_years(
        cls,
        acquisition_cost: Decimal,
        salvage_value: Decimal,
        useful_life_years: int,
        current_year: int,
        period_months: int = 1
    ) -> Decimal:
        """Calculate sum of years digits depreciation."""
        if useful_life_years <= 0:
            return Decimal('0')
        
        n = useful_life_years
        sum_of_years = (n * (n + 1)) / 2
        
        remaining_life = n - current_year + 1
        
        depreciable = acquisition_cost - salvage_value
        annual = depreciable * (Decimal(str(remaining_life)) / Decimal(str(sum_of_years)))
        monthly = annual / Decimal('12')
        
        return (monthly * Decimal(str(period_months))).quantize(Decimal('0.01'))

    @classmethod
    def calculate_asset_depreciation(
        cls,
        asset: 'FixedAsset',
        as_of_date: date = None,
        period_months: int = 1
    ) -> DepreciationCalculation:
        """
        Calculate depreciation for a single asset.
        
        Args:
            asset: FixedAsset instance
            as_of_date: Date to calculate depreciation as of
            period_months: Number of months to calculate
            
        Returns:
            DepreciationCalculation with results
        """
        if as_of_date is None:
            as_of_date = date.today()
        
        acquisition_cost = Decimal(str(asset.acquisition_cost))
        salvage_value = Decimal(str(asset.salvage_value))
        useful_life_years = asset.useful_life_years
        useful_life_months = useful_life_years * 12
        
        accumulated = Decimal(str(asset.accumulated_depreciation))
        current_value = acquisition_cost - accumulated
        
        if useful_life_months <= 0:
            return DepreciationCalculation(
                asset_id=asset.id,
                asset_code=asset.asset_number,
                period_depreciation=Decimal('0'),
                accumulated_depreciation=accumulated,
                net_book_value=current_value,
                is_fully_depreciated=True,
                remaining_life_months=0,
            )
        
        age_months = (as_of_date.year - asset.acquisition_date.year) * 12 + (as_of_date.month - asset.acquisition_date.month)
        remaining_months = max(0, useful_life_months - age_months)
        
        method = asset.depreciation_method or 'Straight-Line'
        
        if method == 'Straight-Line':
            period_depreciation = cls.straight_line(
                acquisition_cost, salvage_value, useful_life_years, period_months
            )
        elif method == 'Declining Balance':
            period_depreciation = cls.declining_balance(
                current_value, salvage_value, useful_life_years, period_months
            )
        elif method == 'Double Declining Balance':
            period_depreciation = cls.double_declining_balance(
                current_value, salvage_value, useful_life_years, period_months
            )
        else:
            period_depreciation = cls.straight_line(
                acquisition_cost, salvage_value, useful_life_years, period_months
            )
        
        is_fully_depreciated = remaining_months <= 0 or current_value <= salvage_value
        
        new_accumulated = accumulated + period_depreciation
        new_net_book_value = acquisition_cost - new_accumulated
        
        if new_net_book_value < salvage_value:
            period_depreciation = current_value - salvage_value
            new_accumulated = accumulated + period_depreciation
            new_net_book_value = salvage_value
            is_fully_depreciated = True
        
        return DepreciationCalculation(
            asset_id=asset.id,
            asset_code=asset.asset_number,
            period_depreciation=period_depreciation,
            accumulated_depreciation=new_accumulated,
            net_book_value=new_net_book_value,
            is_fully_depreciated=is_fully_depreciated,
            remaining_life_months=remaining_months,
        )

    @classmethod
    def calculate_depreciation_run(
        cls,
        run_date: date,
        fiscal_year: int = None,
        period: int = None,
        user: User = None,
        asset_ids: List[int] = None
    ) -> DepreciationRun:
        """
        Calculate depreciation for all eligible assets.
        
        Args:
            run_date: Date of depreciation run
            fiscal_year: Fiscal year
            period: Period number
            user: User performing run
            asset_ids: Optional specific asset IDs
            
        Returns:
            DepreciationRun with all calculations
        """
        from accounting.models import FixedAsset
        
        if fiscal_year is None:
            fiscal_year = run_date.year
        if period is None:
            period = run_date.month
        
        run = DepreciationRun.objects.create(
            run_date=run_date,
            fiscal_year=fiscal_year,
            period=period,
            created_by=user,
            status='DRAFT',
        )
        
        assets = FixedAsset.objects.filter(status='Active')
        if asset_ids:
            assets = assets.filter(id__in=asset_ids)
        
        assets_processed = 0
        total_depreciation = Decimal('0')
        total_accumulated = Decimal('0')
        
        for asset in assets:
            calc = cls.calculate_asset_depreciation(asset, run_date)
            
            DepreciationDetail.objects.create(
                run=run,
                asset=asset,
                asset_code=asset.asset_number,
                asset_name=asset.name,
                acquisition_cost=asset.acquisition_cost,
                salvage_value=asset.salvage_value,
                depreciable_amount=asset.acquisition_cost - asset.salvage_value,
                useful_life_years=asset.useful_life_years,
                useful_life_months=asset.useful_life_years * 12,
                depreciation_method=asset.depreciation_method,
                period_depreciation=calc.period_depreciation,
                accumulated_depreciation_before=asset.accumulated_depreciation,
                accumulated_depreciation_after=calc.accumulated_depreciation,
                net_book_value_before=asset.net_book_value,
                net_book_value_after=calc.net_book_value,
                is_in_use=not calc.is_fully_depreciated,
                remaining_life_months=calc.remaining_life_months,
            )
            
            assets_processed += 1
            total_depreciation += calc.period_depreciation
            total_accumulated = calc.accumulated_depreciation
        
        run.assets_processed = assets_processed
        run.total_depreciation = total_depreciation
        run.total_accumulated = total_accumulated
        run.status = 'CALCULATED'
        run.save()
        
        return run

    @classmethod
    def post_depreciation(
        cls,
        run_id: int,
        user: User
    ) -> Tuple[bool, str, int]:
        """
        Post depreciation to the general ledger.
        
        Args:
            run_id: DepreciationRun ID
            user: User posting
            
        Returns:
            Tuple of (success, message, journal_id)
        """
        from accounting.models import JournalHeader, JournalLine, FixedAsset
        
        try:
            run = DepreciationRun.objects.get(id=run_id)
        except DepreciationRun.DoesNotExist:
            return False, "Depreciation run not found", 0
        
        if run.status != 'CALCULATED':
            return False, f"Cannot post: status is {run.status}", 0
        
        if run.total_depreciation <= 0:
            return False, "No depreciation to post", 0
        
        journal = None
        
        with transaction.atomic():
            journal = JournalHeader.objects.create(
                posting_date=run.run_date,
                description=f"Depreciation Run FY{run.fiscal_year} P{run.period}",
                reference_number=f"DEP-{run.fiscal_year}{run.period:02d}-{run.id}",
                status='Draft',
                source_module='assets',
                source_document_id=run.pk,
            )
            
            depreciation_account = None
            accumulated_account = None
            
            for detail in run.details.all():
                if detail.period_depreciation <= 0:
                    continue
                
                asset = detail.asset
                
                if asset.depreciation_expense_account:
                    JournalLine.objects.create(
                        header=journal,
                        account=asset.depreciation_expense_account,
                        debit=detail.period_depreciation,
                        memo=f"Depreciation: {detail.asset_code}"
                    )
                
                if asset.accumulated_depreciation_account:
                    JournalLine.objects.create(
                        header=journal,
                        account=asset.accumulated_depreciation_account,
                        credit=detail.period_depreciation,
                        memo=f"Accumulated Depreciation: {detail.asset_code}"
                    )
                
                asset.accumulated_depreciation = detail.accumulated_depreciation_after
                asset.save()
                
                from accounting.models import DepreciationSchedule
                schedule, created = DepreciationSchedule.objects.get_or_create(
                    asset=asset,
                    period_date=run.run_date,
                    defaults={
                        'depreciation_amount': detail.period_depreciation,
                        'is_posted': True,
                    }
                )
                if not created:
                    schedule.depreciation_amount = detail.period_depreciation
                    schedule.is_posted = True
                    schedule.save()
                
                detail.schedule_line_id = schedule.id
                detail.save()
            
            journal.status = 'Posted'
            journal.save()
            
            run.status = 'POSTED'
            run.posted_at = timezone.now()
            run.posted_by = user
            run.journal_id = journal.id
            run.save()
        
        return True, f"Posted depreciation journal {journal.id}", journal.id

    @classmethod
    def consolidate_depreciation_schedules(cls) -> Dict[str, Any]:
        """
        Consolidate duplicate depreciation schedule models.
        
        Migrates all AssetDepreciationSchedule records to DepreciationSchedule
        and removes the duplicate model.
        
        Returns:
            Dictionary with consolidation results
        """
        from accounting.models import AssetDepreciationSchedule, DepreciationSchedule, FixedAsset
        
        results = {
            'migrated': 0,
            'skipped': 0,
            'errors': [],
        }
        
        asset_schedules = AssetDepreciationSchedule.objects.all()
        
        for asset_schedule in asset_schedules:
            try:
                existing = DepreciationSchedule.objects.filter(
                    asset=asset_schedule.asset,
                    period_date=asset_schedule.period_date
                ).first()
                
                if existing:
                    results['skipped'] += 1
                    continue
                
                DepreciationSchedule.objects.create(
                    asset=asset_schedule.asset,
                    period_date=asset_schedule.period_date,
                    depreciation_amount=asset_schedule.depreciation_amount,
                    is_posted=asset_schedule.is_posted,
                )
                
                results['migrated'] += 1
                
            except Exception as e:
                results['errors'].append(str(e))
        
        return results

    @classmethod
    def generate_depreciation_report(
        cls,
        run_id: int
    ) -> Dict[str, Any]:
        """Generate a detailed depreciation report."""
        try:
            run = DepreciationRun.objects.get(id=run_id)
        except DepreciationRun.DoesNotExist:
            return {'error': 'Run not found'}
        
        details = []
        for detail in run.details.all():
            details.append({
                'asset_code': detail.asset_code,
                'asset_name': detail.asset_name,
                'acquisition_cost': float(detail.acquisition_cost),
                'depreciable_amount': float(detail.depreciable_amount),
                'useful_life_years': detail.useful_life_years,
                'method': detail.depreciation_method,
                'period_depreciation': float(detail.period_depreciation),
                'accumulated_before': float(detail.accumulated_depreciation_before),
                'accumulated_after': float(detail.accumulated_depreciation_after),
                'net_book_value_before': float(detail.net_book_value_before),
                'net_book_value_after': float(detail.net_book_value_after),
                'is_in_use': detail.is_in_use,
                'remaining_life_months': detail.remaining_life_months,
            })
        
        return {
            'run_id': run.id,
            'run_date': str(run.run_date),
            'fiscal_year': run.fiscal_year,
            'period': run.period,
            'status': run.status,
            'assets_processed': run.assets_processed,
            'total_depreciation': float(run.total_depreciation),
            'journal_id': run.journal_id,
            'details': details,
            'created_by': run.created_by.username if run.created_by else 'Unknown',
            'created_at': run.created_at.isoformat() if run.created_at else None,
            'posted_at': run.posted_at.isoformat() if run.posted_at else None,
            'posted_by': run.posted_by.username if run.posted_by else None,
        }


try:
    from django.utils import timezone
except ImportError:
    timezone = None
