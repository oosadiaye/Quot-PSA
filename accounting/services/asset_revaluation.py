"""Asset Revaluation Service (IAS 16)

Implements asset revaluation per IAS 16 - Property, Plant and Equipment.

NOTE: This is DIFFERENT from Currency Revaluation!
- Currency Revaluation: Adjusts monetary items (cash, AR, AP) for FX rate changes
- Asset Revaluation: Adjusts non-monetary assets (PPE) to fair market value

Key IAS 16 Requirements:
1. Revaluation must be to fair value (market price or expert valuation)
2. Revaluation surplus goes to equity (not P&L)
3. Revaluation loss goes to P&L (unless there's prior surplus)
4. Regular revaluation required to ensure carrying amount not materially different from fair value
"""
from datetime import date
from decimal import Decimal
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass
from django.db import models, transaction
from django.contrib.auth.models import User
from django.utils import timezone
from accounting.models import (
    AssetRevaluationRun, AssetRevaluationDetail, FixedAsset,
    JournalHeader, JournalLine, FiscalPeriod, Account, TransactionSequence
)


@dataclass
class RevaluationAssetResult:
    """Result of revaluation for a single asset."""
    asset_id: int
    asset_code: str
    asset_name: str
    cost_before: Decimal
    cost_after: Decimal
    cost_adjustment: Decimal
    accum_depr_before: Decimal
    accum_depr_after: Decimal
    accum_depr_adjustment: Decimal
    nbv_before: Decimal
    nbv_after: Decimal
    revaluation_surplus: Decimal
    revaluation_loss: Decimal
    fair_value: Decimal
    valuation_source: str


@dataclass
class RevaluationResult:
    """Result of asset revaluation run."""
    revaluation_id: int
    revaluation_number: str
    assets_processed: int
    total_cost_adjustment: Decimal
    total_accum_depr_adjustment: Decimal
    total_revaluation_surplus: Decimal
    total_revaluation_loss: Decimal
    journal_id: Optional[int]
    status: str
    details: List[Dict[str, Any]]


class AssetRevaluationRunService:
    """Service for asset revaluation per IAS 16."""
    
    REVALUATION_METHODS = [
        'Fair Value',
        'Indexed Cost',
        'External Valuation',
    ]
    
    VALUATION_SOURCES = [
        ('INTERNAL', 'Internal Valuation'),
        ('EXTERNAL', 'External Valuer'),
        ('MARKET', 'Market Comparison'),
        ('INDEX', 'Cost Index'),
    ]
    
    @classmethod
    def calculate_revaluation(
        cls,
        asset_id: int,
        fair_value: Decimal,
        valuation_source: str = 'EXTERNAL',
        revaluation_date: date = None
    ) -> RevaluationAssetResult:
        """
        Calculate revaluation for a single asset.
        
        IAS 16 Treatment:
        - If fair value > NBV: Revaluation surplus (equity)
        - If fair value < NBV: Revaluation loss (P&L)
        - Cost and accumulated depreciation both adjusted proportionally
        """
        asset = FixedAsset.objects.get(id=asset_id)
        revaluation_date = revaluation_date or date.today()
        
        nbv_before = asset.current_value or Decimal('0')
        cost_before = asset.acquisition_cost or Decimal('0')
        accum_depr_before = asset.depreciation_to_date or Decimal('0')
        
        if asset.useful_life_months and asset.useful_life_months > 0:
            remaining_months = max(0, asset.useful_life_months - asset.months_depreciated)
            remaining_life = remaining_months / Decimal('12')
        else:
            remaining_life = Decimal('1')
        
        if remaining_life > 0 and cost_before > Decimal('0'):
            depr_rate = accum_depr_before / cost_before
        else:
            depr_rate = Decimal('1')
        
        nbv_ratio = nbv_before / cost_before if cost_before > 0 else Decimal('1')
        
        cost_after = fair_value * (cost_before / nbv_before) if nbv_before > 0 else fair_value
        accum_depr_after = cost_after * depr_rate if depr_rate < Decimal('1') else cost_after - fair_value
        
        accum_depr_after = min(accum_depr_after, cost_after)
        nbv_after = cost_after - accum_depr_after
        
        cost_adjustment = cost_after - cost_before
        accum_depr_adjustment = accum_depr_after - accum_depr_before
        
        if nbv_after > nbv_before:
            revaluation_surplus = nbv_after - nbv_before
            revaluation_loss = Decimal('0')
        else:
            revaluation_surplus = Decimal('0')
            revaluation_loss = nbv_before - nbv_after
        
        return RevaluationAssetResult(
            asset_id=asset_id,
            asset_code=asset.asset_code,
            asset_name=asset.asset_name,
            cost_before=cost_before,
            cost_after=cost_after,
            cost_adjustment=cost_adjustment,
            accum_depr_before=accum_depr_before,
            accum_depr_after=accum_depr_after,
            accum_depr_adjustment=accum_depr_adjustment,
            nbv_before=nbv_before,
            nbv_after=nbv_after,
            revaluation_surplus=revaluation_surplus,
            revaluation_loss=revaluation_loss,
            fair_value=fair_value,
            valuation_source=valuation_source,
        )
    
    @classmethod
    @transaction.atomic
    def create_revaluation(
        cls,
        revaluation_date: date,
        revaluation_method: str,
        asset_valuations: List[Dict[str, Any]],
        valuator_name: str = '',
        valuator_qualification: str = '',
        valuation_report_reference: str = '',
        revaluation_gain_account: str = '3101',
        revaluation_loss_account: str = '8101',
        revaluation_surplus_account: str = '3100',
        fiscal_period_id: int = None,
        user: User = None
    ) -> RevaluationResult:
        """
        Create a complete asset revaluation with journal entries.
        
        Journal Entry Format (IAS 16):
        Dr  Asset Cost Account         XXX
            Cr  Accumulated Depreciation XXX  (if adjusting accumulated depreciation)
        
        For Surplus:
        Dr  Asset Cost Account         XXX
            Cr  Revaluation Surplus (Equity) XXX
        
        For Loss:
        Dr  Revaluation Loss (P&L)    XXX
            Cr  Asset Cost Account         XXX
        """
        from accounting.models import Account
        
        revaluation_number = cls._generate_revaluation_number()
        
        if fiscal_period_id:
            fiscal_period = FiscalPeriod.objects.get(id=fiscal_period_id)
        else:
            fiscal_period = None
        
        total_cost_adjustment = Decimal('0')
        total_accum_depr_adjustment = Decimal('0')
        total_surplus = Decimal('0')
        total_loss = Decimal('0')
        
        details_data = []
        
        for av in asset_valuations:
            result = cls.calculate_revaluation(
                asset_id=av['asset_id'],
                fair_value=Decimal(str(av['fair_value'])),
                valuation_source=av.get('valuation_source', 'EXTERNAL'),
                revaluation_date=revaluation_date
            )
            
            details_data.append({
                'asset_id': result.asset_id,
                'asset_code': result.asset_code,
                'asset_name': result.asset_name,
                'cost_before': result.cost_before,
                'cost_after': result.cost_after,
                'cost_adjustment': result.cost_adjustment,
                'accum_depr_before': result.accum_depr_before,
                'accum_depr_after': result.accum_depr_after,
                'accum_depr_adjustment': result.accum_depr_adjustment,
                'nbv_before': result.nbv_before,
                'nbv_after': result.nbv_after,
                'revaluation_surplus': result.revaluation_surplus,
                'revaluation_loss': result.revaluation_loss,
                'fair_value': result.fair_value,
                'valuation_source': result.valuation_source,
            })
            
            total_cost_adjustment += result.cost_adjustment
            total_accum_depr_adjustment += result.accum_depr_adjustment
            total_surplus += result.revaluation_surplus
            total_loss += result.revaluation_loss
        
        revaluation = AssetRevaluationRun.objects.create(
            revaluation_date=revaluation_date,
            revaluation_number=revaluation_number,
            revaluation_method=revaluation_method,
            valuator_name=valuator_name,
            valuator_qualification=valuator_qualification,
            valuation_report_reference=valuation_report_reference,
            fiscal_period=fiscal_period,
            total_cost_adjustment=total_cost_adjustment,
            total_accum_depr_adjustment=total_accum_depr_adjustment,
            total_revaluation_surplus=total_surplus,
            total_revaluation_loss=total_loss,
            status='DRAFT',
            revaluation_gain_account=revaluation_gain_account,
            revaluation_loss_account=revaluation_loss_account,
            revaluation_surplus_account=revaluation_surplus_account,
            created_by=user,
        )
        
        for detail_data in details_data:
            AssetRevaluationDetail.objects.create(
                revaluation=revaluation,
                asset_id=detail_data['asset_id'],
                asset_code=detail_data['asset_code'],
                asset_name=detail_data['asset_name'],
                cost_before=detail_data['cost_before'],
                cost_after=detail_data['cost_after'],
                cost_adjustment=detail_data['cost_adjustment'],
                accum_depr_before=detail_data['accum_depr_before'],
                accum_depr_after=detail_data['accum_depr_after'],
                accum_depr_adjustment=detail_data['accum_depr_adjustment'],
                nbv_before=detail_data['nbv_before'],
                nbv_after=detail_data['nbv_after'],
                revaluation_surplus=detail_data['revaluation_surplus'],
                revaluation_loss=detail_data['revaluation_loss'],
                valuation_source=detail_data['valuation_source'],
            )
        
        return RevaluationResult(
            revaluation_id=revaluation.id,
            revaluation_number=revaluation_number,
            assets_processed=len(asset_valuations),
            total_cost_adjustment=total_cost_adjustment,
            total_accum_depr_adjustment=total_accum_depr_adjustment,
            total_revaluation_surplus=total_surplus,
            total_revaluation_loss=total_loss,
            journal_id=None,
            status='DRAFT',
            details=details_data,
        )
    
    @classmethod
    @transaction.atomic
    def post_revaluation(cls, revaluation_id: int, user: User = None) -> RevaluationResult:
        """
        Post the revaluation and create journal entries.
        
        Creates journal entry with:
        - Asset cost adjustments
        - Accumulated depreciation adjustments
        - Revaluation surplus (equity)
        - Revaluation loss (P&L)
        """
        revaluation = AssetRevaluationRun.objects.get(id=revaluation_id)
        
        if revaluation.status != 'DRAFT':
            raise ValueError(f"Cannot post revaluation in status: {revaluation.status}")
        
        gain_account = Account.objects.filter(code=revaluation.revaluation_gain_account).first()
        loss_account = Account.objects.filter(code=revaluation.revaluation_loss_account).first()
        surplus_account = Account.objects.filter(code=revaluation.revaluation_surplus_account).first()
        
        if not all([gain_account, loss_account, surplus_account]):
            raise ValueError("Required revaluation accounts not found")
        
        journal_lines = []
        
        details = revaluation.details.all()
        
        total_surplus_journal = Decimal('0')
        total_loss_journal = Decimal('0')
        
        for detail in details:
            asset = FixedAsset.objects.get(id=detail.asset_id)
            
            if detail.cost_adjustment != 0:
                journal_lines.append({
                    'account_id': asset.asset_account.id if asset.asset_account else None,
                    'description': f"Asset revaluation: {detail.asset_code}",
                    'debit_amount': detail.cost_adjustment if detail.cost_adjustment > 0 else Decimal('0'),
                    'credit_amount': abs(detail.cost_adjustment) if detail.cost_adjustment < 0 else Decimal('0'),
                    'cost_center_id': asset.cost_center_id,
                })
            
            if detail.accum_depr_adjustment != 0:
                accum_depr_account = Account.objects.filter(
                    code=f"{asset.asset_code}-AD"
                ).first() or asset.asset_account
                
                journal_lines.append({
                    'account_id': accum_depr_account.id if accum_depr_account else None,
                    'description': f"Accumulated depreciation adjustment: {detail.asset_code}",
                    'debit_amount': abs(detail.accum_depr_adjustment) if detail.accum_depr_adjustment < 0 else Decimal('0'),
                    'credit_amount': detail.accum_depr_adjustment if detail.accum_depr_adjustment > 0 else Decimal('0'),
                    'cost_center_id': asset.cost_center_id,
                })
            
            if detail.revaluation_surplus > 0:
                total_surplus_journal += detail.revaluation_surplus
            elif detail.revaluation_loss > 0:
                total_loss_journal += detail.revaluation_loss
        
        if total_surplus_journal > 0:
            journal_lines.append({
                'account_id': surplus_account.id,
                'description': 'Total revaluation surplus',
                'debit_amount': Decimal('0'),
                'credit_amount': total_surplus_journal,
                'cost_center_id': None,
            })
            journal_lines.append({
                'account_id': gain_account.id,
                'description': 'Revaluation gain on asset disposal',
                'debit_amount': Decimal('0'),
                'credit_amount': total_surplus_journal,
                'cost_center_id': None,
            })
        
        if total_loss_journal > 0:
            journal_lines.append({
                'account_id': loss_account.id,
                'description': 'Total revaluation loss',
                'debit_amount': total_loss_journal,
                'credit_amount': Decimal('0'),
                'cost_center_id': None,
            })
        
        if journal_lines:
            journal = JournalHeader.objects.create(
                journal_date=revaluation.revaluation_date,
                journal_type='REV',
                reference=f"REV-{revaluation.revaluation_number}",
                description=f"Asset Revaluation: {revaluation.revaluation_number}",
                status='POSTED',
                created_by=user,
                fiscal_period=revaluation.fiscal_period,
                source_module='assets',
                source_document_id=revaluation.pk,
                posted_by=user,
                posted_at=timezone.now(),
            )
            
            for line_data in journal_lines:
                if line_data['account_id']:
                    JournalLine.objects.create(
                        journal_header=journal,
                        account_id=line_data['account_id'],
                        description=line_data['description'],
                        debit_amount=line_data['debit_amount'],
                        credit_amount=line_data['credit_amount'],
                        cost_center_id=line_data['cost_center_id'],
                    )
            
            revaluation.journal_id = journal.id
        
        for detail in details:
            asset = FixedAsset.objects.get(id=detail.asset_id)
            asset.acquisition_cost = detail.cost_after
            asset.depreciation_to_date = detail.accum_depr_after
            asset.current_value = detail.nbv_after
            asset.save()
            
            detail.nbv_after = detail.nbv_after
            detail.journal_line_id = None
            detail.save()
        
        revaluation.status = 'POSTED'
        revaluation.approved_by = user
        revaluation.approved_at = date.today()
        revaluation.save()
        
        return RevaluationResult(
            revaluation_id=revaluation.id,
            revaluation_number=revaluation.revaluation_number,
            assets_processed=details.count(),
            total_cost_adjustment=revaluation.total_cost_adjustment,
            total_accum_depr_adjustment=revaluation.total_accum_depr_adjustment,
            total_revaluation_surplus=revaluation.total_revaluation_surplus,
            total_revaluation_loss=revaluation.total_revaluation_loss,
            journal_id=revaluation.journal_id,
            status='POSTED',
            details=[],
        )
    
    @classmethod
    def _generate_revaluation_number(cls) -> str:
        """Generate unique revaluation number."""
        from accounting.models import TransactionSequence
        today = date.today()
        prefix = f"AR{today.strftime('%Y%m')}"
        
        sequence, created = TransactionSequence.objects.get_or_create(
            document_type='AR',
            fiscal_year=today.year,
            defaults={'last_number': 0}
        )
        
        sequence.last_number += 1
        sequence.save()
        
        return f"{prefix}{sequence.last_number:05d}"
    
    @classmethod
    def get_revaluation_history(cls, asset_id: int) -> List[Dict[str, Any]]:
        """Get revaluation history for an asset."""
        details = AssetRevaluationDetail.objects.filter(
            asset_id=asset_id
        ).select_related('revaluation').order_by('-revaluation__revaluation_date')
        
        history = []
        for detail in details:
            history.append({
                'date': detail.revaluation.revaluation_date,
                'revaluation_number': detail.revaluation.revaluation_number,
                'cost_before': detail.cost_before,
                'cost_after': detail.cost_after,
                'cost_adjustment': detail.cost_adjustment,
                'accum_depr_before': detail.accum_depr_before,
                'accum_depr_after': detail.accum_depr_after,
                'accum_depr_adjustment': detail.accum_depr_adjustment,
                'nbv_before': detail.nbv_before,
                'nbv_after': detail.nbv_after,
                'revaluation_surplus': detail.revaluation_surplus,
                'revaluation_loss': detail.revaluation_loss,
                'status': detail.revaluation.status,
            })
        
        return history
    
    @classmethod
    def validate_revaluation_eligibility(cls, asset_id: int) -> Dict[str, Any]:
        """Check if asset is eligible for revaluation."""
        asset = FixedAsset.objects.get(id=asset_id)
        
        issues = []
        
        if asset.status == 'DISPOSED':
            issues.append('Asset has been disposed')
        
        if asset.status == 'FULLY_DEPRECIATED':
            issues.append('Asset is fully depreciated')
        
        if asset.depreciation_method == 'None':
            issues.append('Asset has no depreciation method')
        
        return {
            'eligible': len(issues) == 0,
            'issues': issues,
            'asset_id': asset_id,
            'asset_code': asset.asset_code,
            'asset_name': asset.asset_name,
            'current_value': asset.current_value,
            'status': asset.status,
        }
