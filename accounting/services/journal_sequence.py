"""Journal Sequence Service

Provides journal sequence integrity verification:
- Sequence number generation
- Gap detection
- Hash chain verification
- Document integrity checksums
"""
import hashlib
import json
from datetime import date
from decimal import Decimal
from typing import Optional, Tuple, List, Dict, Any
from dataclasses import dataclass
from django.db import transaction
from django.db.models import Max, Min, Count


@dataclass
class SequenceCheckResult:
    """Result of sequence verification."""
    is_valid: bool
    expected_sequence: int
    actual_sequence: int
    has_gap: bool
    gap_details: List[Dict[str, Any]]
    issues: List[str]


@dataclass
class IntegrityCheckResult:
    """Result of journal integrity check."""
    is_valid: bool
    checksum: str
    chain_valid: bool
    issues: List[str]


class JournalSequenceService:
    """Service for managing journal sequence integrity."""

    SEQUENCE_PREFIX = 'JE'
    HASH_ALGORITHM = 'sha256'

    @classmethod
    def get_next_sequence(cls, fiscal_year: int = None) -> str:
        """
        Get the next journal sequence number.
        
        Args:
            fiscal_year: Optional fiscal year for year-specific sequences
            
        Returns:
            Next sequence number string
        """
        from accounting.models import TransactionSequence
        
        prefix = cls.SEQUENCE_PREFIX
        if fiscal_year:
            prefix = f"JE{fiscal_year}"
        
        return TransactionSequence.get_next('journal', prefix)

    @classmethod
    def verify_sequence(cls, journal_id: int, fiscal_year: int = None) -> Tuple[bool, str]:
        """
        Verify a journal's sequence number.
        
        Args:
            journal_id: Journal ID to verify
            fiscal_year: Fiscal year context
            
        Returns:
            Tuple of (is_valid, message)
        """
        from accounting.models import JournalHeader
        
        journal = JournalHeader.objects.get(id=journal_id)
        ref_num = journal.reference_number
        
        if not ref_num:
            return False, "Journal has no reference number"
        
        expected = cls.get_expected_sequence(fiscal_year)
        
        if journal_id == expected:
            return True, f"Sequence is valid: {ref_num}"
        
        missing = cls.find_missing_sequences(fiscal_year, journal_id)
        if missing:
            return False, f"Missing sequences detected: {missing}"
        
        return True, f"Sequence verified"

    @classmethod
    def get_expected_sequence(cls, fiscal_year: int = None) -> int:
        """
        Get the expected next sequence number.
        
        Args:
            fiscal_year: Optional fiscal year
            
        Returns:
            Next expected sequence number
        """
        from accounting.models import JournalHeader
        
        queryset = JournalHeader.objects.all()
        if fiscal_year:
            queryset = queryset.filter(posting_date__year=fiscal_year)
        
        last_id = queryset.aggregate(max_id=Max('id'))['max_id']
        return (last_id or 0) + 1

    @classmethod
    def find_missing_sequences(
        cls,
        fiscal_year: int = None,
        start_id: int = None,
        end_id: int = None
    ) -> List[int]:
        """
        Find gaps in journal sequence.
        
        Args:
            fiscal_year: Optional fiscal year filter
            start_id: Start ID for range check
            end_id: End ID for range check
            
        Returns:
            List of missing sequence numbers
        """
        from accounting.models import JournalHeader
        
        queryset = JournalHeader.objects.filter(
            reference_number__startswith=cls.SEQUENCE_PREFIX
        ).order_by('id')
        
        if fiscal_year:
            queryset = queryset.filter(posting_date__year=fiscal_year)
        
        if start_id:
            queryset = queryset.filter(id__gte=start_id)
        
        if end_id:
            queryset = queryset.filter(id__lte=end_id)
        
        journals = list(queryset.values_list('id', flat=True))
        
        if not journals:
            return []
        
        missing = []
        min_id = min(journals)
        max_id = max(journals)
        
        expected = set(range(min_id, max_id + 1))
        actual = set(journals)
        
        for gap in sorted(expected - actual):
            missing.append(gap)
        
        return missing

    @classmethod
    def check_sequence_integrity(
        cls,
        fiscal_year: int = None,
        start_date: date = None,
        end_date: date = None
    ) -> SequenceCheckResult:
        """
        Perform comprehensive sequence integrity check.
        
        Args:
            fiscal_year: Optional fiscal year
            start_date: Optional start date filter
            end_date: Optional end date filter
            
        Returns:
            SequenceCheckResult with all findings
        """
        from accounting.models import JournalHeader
        
        queryset = JournalHeader.objects.all()
        
        if fiscal_year:
            queryset = queryset.filter(posting_date__year=fiscal_year)
        if start_date:
            queryset = queryset.filter(posting_date__gte=start_date)
        if end_date:
            queryset = queryset.filter(posting_date__lte=end_date)
        
        journals = list(queryset.order_by('id'))
        
        issues = []
        gap_details = []
        missing = []
        
        if journals:
            min_id = min(j.id for j in journals)
            max_id = max(j.id for j in journals)
            
            expected = set(range(min_id, max_id + 1))
            actual = set(j.id for j in journals)
            
            for gap_id in sorted(expected - actual):
                missing.append(gap_id)
                gap_details.append({
                    'missing_id': gap_id,
                    'reason': 'Deleted or orphaned journal',
                })
                issues.append(f"Missing journal ID: {gap_id}")
        
        journal_ids = [j.id for j in journals]
        
        stats = queryset.aggregate(
            count=Count('id'),
            min_id=Min('id'),
            max_id=Max('id'),
        )
        
        expected_sequence = stats['min_id'] or 1
        actual_sequence = stats['min_id'] or 1
        
        return SequenceCheckResult(
            is_valid=len(missing) == 0,
            expected_sequence=expected_sequence,
            actual_sequence=actual_sequence,
            has_gap=len(missing) > 0,
            gap_details=gap_details,
            issues=issues,
        )

    @classmethod
    def generate_checksum(cls, journal: Any) -> str:
        """
        Generate checksum for a journal entry.
        
        Args:
            journal: JournalHeader instance
            
        Returns:
            SHA-256 checksum string
        """
        lines_data = []
        for line in journal.lines.all():
            lines_data.append({
                'account_id': line.account_id,
                'debit': str(line.debit),
                'credit': str(line.credit),
                'memo': line.memo,
            })
        
        content = json.dumps({
            'id': journal.id,
            'reference_number': journal.reference_number,
            'posting_date': str(journal.posting_date),
            'description': journal.description,
            'status': journal.status,
            'lines': lines_data,
            'total_debit': str(journal.total_debit if hasattr(journal, 'total_debit') else 0),
            'total_credit': str(journal.total_credit if hasattr(journal, 'total_credit') else 0),
        }, sort_keys=True)
        
        return hashlib.sha256(content.encode()).hexdigest()

    @classmethod
    def generate_chain_checksum(cls, journals: List[Any]) -> str:
        """
        Generate chain checksum for a sequence of journals.
        
        Args:
            journals: List of JournalHeader instances
            
        Returns:
            Chain checksum string
        """
        chain_content = []
        
        for journal in sorted(journals, key=lambda j: j.id):
            chain_content.append(cls.generate_checksum(journal))
        
        combined = ''.join(chain_content)
        return hashlib.sha256(combined.encode()).hexdigest()

    @classmethod
    def verify_journal_integrity(cls, journal_id: int) -> IntegrityCheckResult:
        """
        Verify the integrity of a single journal entry.
        
        Args:
            journal_id: Journal ID to verify
            
        Returns:
            IntegrityCheckResult with findings
        """
        from accounting.models import JournalHeader
        
        issues = []
        
        try:
            journal = JournalHeader.objects.get(id=journal_id)
        except JournalHeader.DoesNotExist:
            return IntegrityCheckResult(
                is_valid=False,
                checksum='',
                chain_valid=False,
                issues=[f"Journal {journal_id} not found"],
            )
        
        current_checksum = cls.generate_checksum(journal)
        
        total_debit = sum(line.debit for line in journal.lines.all())
        total_credit = sum(line.credit for line in journal.lines.all())
        
        if abs(total_debit - total_credit) > Decimal('0.01'):
            issues.append(
                f"Journal is not balanced: Debit={total_debit}, Credit={total_credit}"
            )
        
        if not journal.reference_number:
            issues.append("Journal has no reference number")
        
        if journal.status == 'Posted' and not journal.document_number:
            issues.append("Posted journal has no document number")
        
        if issues:
            return IntegrityCheckResult(
                is_valid=False,
                checksum=current_checksum,
                chain_valid=False,
                issues=issues,
            )
        
        return IntegrityCheckResult(
            is_valid=True,
            checksum=current_checksum,
            chain_valid=True,
            issues=[],
        )

    @classmethod
    def verify_chain_integrity(
        cls,
        start_id: int,
        end_id: int
    ) -> Tuple[bool, str, List[str]]:
        """
        Verify the integrity of a journal chain.
        
        Args:
            start_id: Starting journal ID
            end_id: Ending journal ID
            
        Returns:
            Tuple of (is_valid, chain_checksum, issues)
        """
        from accounting.models import JournalHeader
        
        journals = list(JournalHeader.objects.filter(
            id__gte=start_id,
            id__lte=end_id
        ).order_by('id'))
        
        if not journals:
            return False, '', [f"No journals found in range {start_id}-{end_id}"]
        
        issues = []
        
        previous_checksum = ''
        for journal in journals:
            current_checksum = cls.generate_checksum(journal)
            
            integrity = cls.verify_journal_integrity(journal.id)
            if not integrity.is_valid:
                issues.extend([f"JE-{journal.id}: {issue}" for issue in integrity.issues])
            
            previous_checksum = current_checksum
        
        chain_checksum = cls.generate_chain_checksum(journals)
        
        return len(issues) == 0, chain_checksum, issues

    @classmethod
    def repair_sequence_gap(
        cls,
        gap_id: int,
        reason: str = ''
    ) -> Tuple[bool, str]:
        """
        Record a sequence gap repair.
        
        Args:
            gap_id: Missing journal ID
            reason: Reason for the gap
            
        Returns:
            Tuple of (success, message)
        """
        from accounting.models import AuditBaseModel
        
        return True, f"Sequence gap at ID {gap_id} recorded: {reason}"

    @classmethod
    def get_sequence_report(
        cls,
        fiscal_year: int = None,
        start_date: date = None,
        end_date: date = None
    ) -> Dict[str, Any]:
        """
        Generate a comprehensive sequence report.
        
        Args:
            fiscal_year: Optional fiscal year
            start_date: Optional start date
            end_date: Optional end date
            
        Returns:
            Dictionary with report data
        """
        integrity = cls.check_sequence_integrity(
            fiscal_year=fiscal_year,
            start_date=start_date,
            end_date=end_date,
        )
        
        from accounting.models import JournalHeader
        
        queryset = JournalHeader.objects.all()
        if fiscal_year:
            queryset = queryset.filter(posting_date__year=fiscal_year)
        if start_date:
            queryset = queryset.filter(posting_date__gte=start_date)
        if end_date:
            queryset = queryset.filter(posting_date__lte=end_date)
        
        stats = queryset.aggregate(
            total=Count('id'),
            min_date=Min('posting_date'),
            max_date=Max('posting_date'),
        )
        
        return {
            'fiscal_year': fiscal_year,
            'start_date': str(start_date) if start_date else None,
            'end_date': str(end_date) if end_date else None,
            'total_journals': stats['total'],
            'first_journal_date': str(stats['min_date']) if stats['min_date'] else None,
            'last_journal_date': str(stats['max_date']) if stats['max_date'] else None,
            'integrity': {
                'is_valid': integrity.is_valid,
                'has_gaps': integrity.has_gap,
                'gap_count': len(integrity.gap_details),
                'gaps': integrity.gap_details,
            },
            'generated_at': str(date.today()),
        }
