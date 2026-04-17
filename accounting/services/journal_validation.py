"""Journal Validation Service

Provides comprehensive validation for journal entries including:
- Debit/Credit balance enforcement
- Line item validation
- Business rule validation
"""
from decimal import Decimal
from typing import Optional, Tuple, List, Dict, Any
from rest_framework import serializers


class JournalValidationService:
    """Service for validating journal entries."""

    TOLERANCE = Decimal('0.01')

    @classmethod
    def validate_balance(cls, lines: List[Dict[str, Any]]) -> Tuple[bool, Optional[str]]:
        """
        Validate that total debits equal total credits.

        Args:
            lines: List of journal line dictionaries with 'debit' and 'credit' keys

        Returns:
            Tuple of (is_valid, error_message)
        """
        total_debit = sum(Decimal(str(line.get('debit', 0))) for line in lines)
        total_credit = sum(Decimal(str(line.get('credit', 0))) for line in lines)

        difference = abs(total_debit - total_credit)

        if difference > cls.TOLERANCE:
            return False, (
                f"Journal entry is not balanced. "
                f"Total Debits: {total_debit}, Total Credits: {total_credit}, "
                f"Difference: {difference}"
            )

        return True, None

    @classmethod
    def validate_line(cls, line_data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Validate a single journal line.

        Args:
            line_data: Journal line dictionary

        Returns:
            Tuple of (is_valid, error_message)
        """
        debit = Decimal(str(line_data.get('debit', 0)))
        credit = Decimal(str(line_data.get('credit', 0)))

        if debit > 0 and credit > 0:
            return False, "A journal line cannot have both debit and credit amounts."

        if debit < 0 or credit < 0:
            return False, "Journal amounts cannot be negative."

        if debit == 0 and credit == 0:
            return False, "A journal line must have either a debit or credit amount."

        if not line_data.get('account'):
            return False, "Each journal line must have an account assigned."

        return True, None

    @classmethod
    def validate_lines(cls, lines: List[Dict[str, Any]]) -> Tuple[bool, List[str]]:
        """
        Validate all journal lines.

        Args:
            lines: List of journal line dictionaries

        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []

        if not lines:
            errors.append("Journal entry must have at least one line.")
            return False, errors

        for idx, line in enumerate(lines, 1):
            is_valid, error = cls.validate_line(line)
            if not is_valid:
                errors.append(f"Line {idx}: {error}")

        is_balanced, balance_error = cls.validate_balance(lines)
        if not is_balanced:
            errors.append(balance_error)

        return len(errors) == 0, errors

    @classmethod
    def validate_journal_header(cls, header_data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """
        Validate journal header data.

        Args:
            header_data: Journal header dictionary

        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []

        if not header_data.get('posting_date'):
            errors.append("Posting date is required.")

        if not header_data.get('description'):
            errors.append("Description is required.")

        return len(errors) == 0, errors

    @classmethod
    def validate_complete_journal(
        cls,
        header_data: Dict[str, Any],
        lines_data: List[Dict[str, Any]]
    ) -> Tuple[bool, List[str]]:
        """
        Validate a complete journal entry (header + lines).

        Args:
            header_data: Journal header dictionary
            lines_data: List of journal line dictionaries

        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        all_errors = []

        header_valid, header_errors = cls.validate_journal_header(header_data)
        all_errors.extend(header_errors)

        lines_valid, line_errors = cls.validate_lines(lines_data)
        all_errors.extend(line_errors)

        return len(all_errors) == 0, all_errors

    @classmethod
    def get_balance_summary(cls, lines: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Get a summary of the journal balance.

        Args:
            lines: List of journal line dictionaries

        Returns:
            Dictionary with balance summary
        """
        total_debit = sum(Decimal(str(line.get('debit', 0))) for line in lines)
        total_credit = sum(Decimal(str(line.get('credit', 0))) for line in lines)
        difference = total_debit - total_credit

        return {
            'total_debit': total_debit,
            'total_credit': total_credit,
            'difference': difference,
            'is_balanced': abs(difference) <= cls.TOLERANCE,
            'line_count': len(lines),
        }

    @classmethod
    def suggest_balance_lines(cls, target_amount: Decimal, account_codes: List[str]) -> List[Dict[str, Any]]:
        """
        Suggest balancing lines for a journal entry.

        Args:
            target_amount: The amount that needs to be balanced
            account_codes: List of account codes to use

        Returns:
            List of suggested journal lines
        """
        if not account_codes:
            return []

        lines = []
        remaining = target_amount

        for code in account_codes[:-1]:
            if remaining <= 0:
                break
            lines.append({
                'account_code': code,
                'debit': remaining,
                'credit': Decimal('0'),
            })
            remaining = Decimal('0')

        if remaining > 0 and account_codes:
            lines.append({
                'account_code': account_codes[-1],
                'debit': Decimal('0'),
                'credit': remaining,
            })

        return lines


class JournalBalanceSerializer(serializers.Serializer):
    """Serializer for validating journal balance via API."""

    lines = serializers.ListField(
        child=serializers.DictField(),
        min_length=2,
        help_text="List of journal line dictionaries"
    )

    def validate_lines(self, lines):
        is_valid, errors = JournalValidationService.validate_lines(lines)
        if not is_valid:
            raise serializers.ValidationError(errors)
        return lines
