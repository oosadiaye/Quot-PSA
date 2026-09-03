"""
Payment batching service — every business rule for the bank
payment/confirmation letter lives here, never in the viewset.

Mirrors the structure of ``social_benefit_batch_pay.py``: module-level
helpers plus a service class with classmethods, raising a domain
exception the HTTP layer translates.
"""
from __future__ import annotations

from datetime import date as _date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from core.services.sod_evaluator import enforce_action

BATCH_NUMBER_PREFIX = 'PB'

# Permission codes from the seeded catalogue. Referenced here only so the
# SoD evaluator can look up whichever rules a tenant has configured
# against them — the pairings themselves are database rows, not constants.
PERM_CREATE = 'accounting.payment_batch.create'
PERM_DISPATCH = 'accounting.payment_batch.dispatch'
PERM_CONFIRM = 'accounting.payment_batch.confirm'


def format_batch_number(year: int, sequence: int) -> str:
    """``PB/2026/0001``.

    Nigeria's fiscal year aligns with the calendar year, so the year
    component is simply the calendar year of ``batch_date``.
    """
    if sequence < 1:
        raise ValueError(f'sequence must be >= 1, got {sequence}')
    return f'{BATCH_NUMBER_PREFIX}/{year}/{sequence:04d}'


def resolve_payee_snapshot(payment) -> dict:
    """Freeze the letter row for ``payment``.

    Reads the Payment Voucher first — it is the statutory authority to pay
    and already snapshots payee bank details as at authorisation. Falls
    back per-field to the live Vendor record, because
    ``Payment.payment_voucher`` is nullable (mandatory only when
    ``AccountingSettings.require_pv_before_payment`` is on).

    ``amount`` is ALWAYS ``payment.total_amount`` — the cash actually
    leaving the government account, which is what the bank is being told
    to move and what was posted to the GL.

    It is deliberately NOT ``pv.net_amount``. ``Payment.payment_voucher``
    is a plain FK with no uniqueness, so one PV may be settled by several
    payments; taking the PV net would put the FULL voucher amount on every
    one of those lines and instruct the bank to pay it more than once. A
    single partial settlement over-instructs the same way. The PV remains
    the source for payee *identity* (it snapshots the authorised payee at
    authorisation time) — but never for the sum.
    """
    pv = getattr(payment, 'payment_voucher', None)
    vendor = getattr(payment, 'vendor', None)

    def pick(pv_attr: str, vendor_attr: str) -> str:
        pv_val = (getattr(pv, pv_attr, '') or '') if pv else ''
        if pv_val:
            return pv_val
        return (getattr(vendor, vendor_attr, '') or '') if vendor else ''

    purpose = (getattr(pv, 'narration', '') or '') if pv else ''
    if not purpose:
        purpose = getattr(payment, 'reference_number', '') or ''

    amount = getattr(payment, 'total_amount', None) or Decimal('0')

    return {
        'payee_name': pick('payee_name', 'name'),
        'payee_bank': pick('payee_bank', 'bank_name'),
        'payee_account': pick('payee_account', 'bank_account_number'),
        'purpose': purpose[:255],
        'amount': amount,
    }


class PaymentBatchError(ValidationError):
    """Raised when a batch operation cannot proceed."""


class PaymentBatchService:
    """All payment-batch business rules.

    Every rule raises, naming the offending payment. Nothing is silently
    skipped — a silently-dropped row means the bank is under-instructed
    and a vendor goes unpaid without anyone noticing.
    """

    @classmethod
    def eligible_payments(cls, bank_account):
        """Posted payments on ``bank_account`` not already actively batched."""
        from accounting.models import Payment
        return (
            Payment.objects
            .filter(status='Posted', bank_account=bank_account)
            .exclude(batch_lines__is_active_membership=True)
            .select_related('vendor', 'payment_voucher', 'currency')
            .distinct()
        )

    @classmethod
    def _validate_and_snapshot(cls, payment, bank_account) -> dict:
        label = payment.payment_number or f'payment #{payment.pk}'

        if payment.status != 'Posted':
            raise PaymentBatchError(
                f'{label}: only Posted payments can be batched '
                f'(status is {payment.status}).')

        if payment.bank_account_id != bank_account.pk:
            raise PaymentBatchError(
                f'{label}: drawn on a different bank account. A letter '
                f'instructs one bank about one account.')

        if payment.batch_lines.filter(is_active_membership=True).exists():
            raise PaymentBatchError(
                f'{label}: already belongs to an active batch.')

        snap = resolve_payee_snapshot(payment)
        who = snap['payee_name'] or label
        if not snap['payee_bank'] or not snap['payee_account']:
            raise PaymentBatchError(
                f'{who}: missing bank name or account number. The bank '
                f'cannot execute a line with blank details — add them on '
                f'the vendor record first.')
        return snap

    @staticmethod
    def _next_sequence(year: int) -> int:
        """Allocate the next per-year batch sequence under a row lock.

        Uses the codebase's own ``TransactionSequence`` counter rather than
        ``MAX(batch_number)``. Two reasons the old approach was unsafe:

        * ``select_for_update()`` over a filter matching ZERO rows locks
          nothing, so the first batch of each new year raced — two
          creators both computed 1 and the loser died on the unique
          constraint with an unhandled IntegrityError (a 500, not a
          clean 400).
        * String ordering on a 4-digit pad breaks at 10 000: the text
          ``'PB/2026/10000'`` sorts BELOW ``'PB/2026/9999'``, so the max
          would stop advancing and start colliding.

        A counter row always exists to lock, and the value is an integer.
        """
        from accounting.models import TransactionSequence

        seq, _ = TransactionSequence.objects.select_for_update().get_or_create(
            name=f'payment_batch_{year}',
            defaults={'prefix': f'{BATCH_NUMBER_PREFIX}/{year}/'},
        )
        value = seq.next_value
        seq.next_value += 1
        seq.save(update_fields=['next_value'])
        return value

    @classmethod
    @transaction.atomic
    def create_batch(cls, *, bank_account, batch_date, payment_ids, user):
        from accounting.models import PaymentBatch
        batch_date = batch_date or _date.today()

        year = batch_date.year
        next_seq = cls._next_sequence(year)

        batch = PaymentBatch.objects.create(
            batch_number=format_batch_number(year, next_seq),
            batch_date=batch_date,
            source_bank_account=bank_account,
            addressee_bank_name=bank_account.bank_name or bank_account.name,
            addressee_account_no=bank_account.account_number,
            created_by=user,
        )
        cls.add_payments(batch, payment_ids, user)
        return batch

    @classmethod
    @transaction.atomic
    def add_payments(cls, batch, payment_ids, user):
        from accounting.models import Payment, PaymentBatchLine

        if batch.status != batch.STATUS_DRAFT:
            raise PaymentBatchError(
                f'{batch.batch_number} is {batch.status}; only Draft '
                f'batches can be modified.')

        payment_ids = list(payment_ids)
        # Lock the candidate rows so two operators cannot both claim the
        # same payment and instruct the bank to pay a vendor twice.
        #
        # ``of=('self',)`` is required, not cosmetic. ``vendor`` and
        # ``payment_voucher`` are both nullable FKs, so ``select_related``
        # emits LEFT OUTER JOINs, and Postgres rejects a bare
        # ``SELECT ... FOR UPDATE`` across the nullable side of an outer
        # join ("FOR UPDATE cannot be applied to the nullable side of an
        # outer join"). Restricting the lock to the Payment table itself
        # keeps the join for free and locks exactly what we mean to lock.
        payments = list(
            Payment.objects.select_for_update(of=('self',))
            .filter(pk__in=payment_ids)
            .select_related('vendor', 'payment_voucher')
        )
        found = {p.pk for p in payments}
        missing = set(payment_ids) - found
        if missing:
            raise PaymentBatchError(f'Unknown payment ids: {sorted(missing)}')

        # Assign S/N in the order the caller supplied, not the arbitrary
        # order Postgres returns rows for a pk__in filter. The letter is a
        # signed document: an operator who picks payments in a deliberate
        # order must get that order, and two prints of one batch must be
        # diffable line by line.
        caller_order = {pk: index for index, pk in enumerate(payment_ids)}
        payments.sort(key=lambda p: caller_order[p.pk])

        next_seq = (batch.lines.aggregate(m=Max('sequence'))['m'] or 0) + 1
        for payment in payments:
            snap = cls._validate_and_snapshot(payment, batch.source_bank_account)
            PaymentBatchLine.objects.create(
                batch=batch, payment=payment, sequence=next_seq,
                created_by=user, **snap)
            next_seq += 1
        return batch

    @classmethod
    @transaction.atomic
    def remove_line(cls, batch, line_id, user):
        if batch.status != batch.STATUS_DRAFT:
            raise PaymentBatchError(
                f'{batch.batch_number} is {batch.status}; lines are locked.')
        line = batch.lines.filter(pk=line_id).first()
        if line is None:
            raise PaymentBatchError(f'Line {line_id} is not in this batch.')
        line.delete()
        # Renumber so the printed S/N column stays 1..N with no gaps.
        for index, remaining in enumerate(batch.lines.order_by('sequence'), start=1):
            if remaining.sequence != index:
                remaining.sequence = index
                remaining.save(update_fields=['sequence'])
        return batch

    @classmethod
    @transaction.atomic
    def dispatch(cls, batch, user):
        """Mark the letter as printed and sent to the bank."""
        if batch.status != batch.STATUS_DRAFT:
            raise PaymentBatchError(
                f'Only Draft batches can be dispatched; '
                f'{batch.batch_number} is {batch.status}.')
        if not batch.lines.filter(is_active_membership=True).exists():
            raise PaymentBatchError(
                f'{batch.batch_number} has no lines — nothing to instruct.')

        # Segregation of duties. NOTHING is hardcoded here: the evaluator
        # reads core.SoDRule rows, which a tenant admin edits, deactivates
        # or re-scopes from the SoD-rules page. Ship a system rule pairing
        # create × dispatch (see seed_permission_catalog) and the default
        # is four-eyes; deactivate that row and this call becomes a no-op.
        enforce_action(user, PERM_DISPATCH, batch)

        batch.status = batch.STATUS_DISPATCHED
        batch.dispatched_at = timezone.now()
        batch.dispatched_by = user
        batch.save(update_fields=['status', 'dispatched_at', 'dispatched_by',
                                  'updated_at'])
        return batch

    @classmethod
    @transaction.atomic
    def confirm(cls, batch, user):
        """Record the bank's confirmation that the payments were made."""
        if batch.status != batch.STATUS_DISPATCHED:
            raise PaymentBatchError(
                f'Only Dispatched batches can be confirmed; '
                f'{batch.batch_number} is {batch.status}.')

        # Same rule-driven SoD gate. ``dispatched_by`` is not one of the
        # evaluator's conventional actor attributes, so the mapping is
        # passed explicitly — the RULE itself still lives in the database.
        enforce_action(
            user, PERM_CONFIRM, batch,
            document_actor_attr_map={PERM_DISPATCH: 'dispatched_by_id'},
        )

        batch.status = batch.STATUS_CONFIRMED
        batch.confirmed_at = timezone.now()
        batch.confirmed_by = user
        batch.save(update_fields=['status', 'confirmed_at', 'confirmed_by',
                                  'updated_at'])
        return batch

    @classmethod
    @transaction.atomic
    def cancel(cls, batch, user, reason: str = ''):
        """Cancel and release every payment back to the eligible pool."""
        if batch.status == batch.STATUS_CONFIRMED:
            raise PaymentBatchError(
                f'{batch.batch_number} is Confirmed — the bank has already '
                f'acted on it. Cancellation is not possible.')
        if batch.status == batch.STATUS_CANCELLED:
            raise PaymentBatchError(f'{batch.batch_number} is already cancelled.')

        # Cancelling a DISPATCHED batch is materially different from
        # cancelling a Draft: the letter is physically with the bank. If
        # the bank acted on it and the confirmation was never recorded,
        # releasing these payments lets them be re-batched and re-sent.
        # Draft cancellation stays frictionless; this one must be justified
        # in writing, because that text is the audit trail for a decision
        # that can end in a double payment.
        if batch.status == batch.STATUS_DISPATCHED and not (reason or '').strip():
            raise PaymentBatchError(
                f'{batch.batch_number} has already been dispatched to '
                f'{batch.addressee_bank_name}. Recalling it requires a written '
                f'reason — confirm with the bank that the instruction was not '
                f'acted on before releasing these payments.')

        batch.status = batch.STATUS_CANCELLED
        batch.cancelled_reason = reason
        batch.save(update_fields=['status', 'cancelled_reason', 'updated_at'])
        # Flip membership so the partial unique index frees these payments.
        batch.lines.update(is_active_membership=False)
        return batch
