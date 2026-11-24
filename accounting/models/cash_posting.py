"""Cash Posting: a cash journal (cash book) in the style of SAP's FBCJ.

A **cash journal** is one cash desk: a Cash, Petty Cash or Imprest account kept by a cashier. Everything that moves cash in
or out is a **cash document** posted in it, with a transaction type that says what it is:

    Cash payment - expense        Dr  GL account            Cr  cash
    Cash receipt - revenue        Dr  cash                  Cr  GL account
    Cash withdrawal from bank     Dr  cash                  Cr  bank        (this is how an imprest fund is REPLENISHED)
    Cash deposit to bank          Dr  bank                  Cr  cash

A document is saved as a Draft, then Posted (one balanced journal; every cash line is tagged with the cash account so the
cash book sees exactly this desk's money), and a posted one is Reversed, never edited. At the end of the day the cashier
**closes** the journal: counts the notes and coins, the count is compared with the book balance, any difference is posted to
the cash-difference account, and nothing dated on or before the closing date can be posted or reversed again.

Public sector: every document carries the NCoA coding block (MDA, fund, function, programme, geo) that flows onto its journal,
and a cash payment to an expense account passes the same appropriation and warrant gates as any other expenditure.
"""
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models

from core.models import AuditBaseModel

#: Bank-account types that can be kept as a cash journal.
CASH_ACCOUNT_TYPES = ('Cash', 'Petty Cash', 'Imprest')


class CashJournal(AuditBaseModel):
    """One cash desk."""
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=100)
    # The MDA that owns the desk; its documents default to this coding.
    mda = models.ForeignKey('accounting.MDA', on_delete=models.PROTECT, null=True, blank=True, related_name='+')
    # The Cash / Petty Cash / Imprest account whose GL account is the cash book. One journal per account.
    cash_account = models.OneToOneField('accounting.BankAccount', on_delete=models.PROTECT, related_name='cash_journal')
    # An imprest float: the amount the fund is topped back up to. 0 = an ordinary cash desk with no fixed float.
    float_amount = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'),
                                       validators=[MinValueValidator(Decimal('0'))])
    # Where a counting difference (cash short / over) is posted when the day is closed.
    difference_account = models.ForeignKey('accounting.Account', on_delete=models.PROTECT, null=True, blank=True,
                                           related_name='+')
    # A cash book cannot go below zero (you cannot pay out cash you do not hold) unless this is ticked.
    allow_negative_balance = models.BooleanField(default=False)
    # How far below zero a journal that allows a negative balance may go. 0 = no limit.
    overdraft_limit = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'),
                                          validators=[MinValueValidator(Decimal('0'))])
    is_active = models.BooleanField(default=True)
    last_closed_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ['code']

    number_prefix = 'CJ-'

    def lowest_balance(self):
        """The lowest the book may go: 0 normally, minus the overdraft limit when overdrawing is allowed, ``None`` for no floor."""
        if not self.allow_negative_balance:
            return Decimal('0')
        return -self.overdraft_limit if self.overdraft_limit and self.overdraft_limit > 0 else None

    def __str__(self):
        return f'{self.code} {self.name}'


class CashDocument(AuditBaseModel):
    EXPENSE = 'EXPENSE'
    REVENUE = 'REVENUE'
    BANK_WITHDRAWAL = 'BANK_WITHDRAWAL'
    BANK_DEPOSIT = 'BANK_DEPOSIT'
    TRANSACTION_TYPES = [
        (EXPENSE, 'Cash payment - expense'),
        (REVENUE, 'Cash receipt - revenue'),
        (BANK_WITHDRAWAL, 'Cash withdrawal from bank'),
        (BANK_DEPOSIT, 'Cash deposit to bank'),
    ]
    #: Which of them bring cash IN; the rest take cash out.
    RECEIPT_TYPES = (REVENUE, BANK_WITHDRAWAL)

    DRAFT = 'Draft'
    POSTED = 'Posted'
    REVERSED = 'Reversed'
    STATUS_CHOICES = [(DRAFT, 'Draft'), (POSTED, 'Posted'), (REVERSED, 'Reversed')]

    cash_journal = models.ForeignKey(CashJournal, on_delete=models.PROTECT, related_name='documents')
    document_number = models.CharField(max_length=50, unique=True, blank=True, default='')
    posting_date = models.DateField()
    transaction_type = models.CharField(max_length=30, choices=TRANSACTION_TYPES)
    amount = models.DecimalField(max_digits=15, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    description = models.CharField(max_length=255, blank=True, default='')
    # Payee / payer, or the receipt or voucher number: what the cashier writes on the document.
    reference = models.CharField(max_length=100, blank=True, default='')
    # The person who received the cash from the cashier. Printed in the memo of the posted journal, so the GL ledger shows it.
    recipient = models.CharField(max_length=150, blank=True, default='')

    # The other side, by transaction type.
    offset_account = models.ForeignKey('accounting.Account', on_delete=models.PROTECT, null=True, blank=True, related_name='+')
    bank_account = models.ForeignKey('accounting.BankAccount', on_delete=models.PROTECT, null=True, blank=True, related_name='+')

    # NCoA coding block: flows onto the posted journal header (and gates a payment against its appropriation).
    mda = models.ForeignKey('accounting.MDA', on_delete=models.PROTECT, null=True, blank=True, related_name='+')
    fund = models.ForeignKey('accounting.Fund', on_delete=models.PROTECT, null=True, blank=True, related_name='+')
    function = models.ForeignKey('accounting.Function', on_delete=models.PROTECT, null=True, blank=True, related_name='+')
    program = models.ForeignKey('accounting.Program', on_delete=models.PROTECT, null=True, blank=True, related_name='+')
    geo = models.ForeignKey('accounting.Geo', on_delete=models.PROTECT, null=True, blank=True, related_name='+')

    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=DRAFT, db_index=True)
    journal_entry = models.ForeignKey('accounting.JournalHeader', on_delete=models.PROTECT, null=True, blank=True,
                                      related_name='cash_documents')
    reversal_journal = models.ForeignKey('accounting.JournalHeader', on_delete=models.PROTECT, null=True, blank=True,
                                         related_name='reversed_cash_documents')
    posted_at = models.DateTimeField(null=True, blank=True)
    # Who did what and when, for the View screen. ``posted_by`` is also the person who approved it: posting needs the post permission.
    posted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    reversed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    reversed_at = models.DateTimeField(null=True, blank=True)
    edited_at = models.DateTimeField(null=True, blank=True, help_text='When a Draft was last changed by someone (updated_by).')

    class Meta:
        ordering = ['-posting_date', '-id']
        constraints = [
            models.CheckConstraint(condition=models.Q(amount__gt=0), name='cash_document_positive_amount'),
        ]

    @property
    def is_receipt(self) -> bool:
        return self.transaction_type in self.RECEIPT_TYPES

    @property
    def signed_amount(self) -> Decimal:
        """+ for cash in, - for cash out."""
        return self.amount if self.is_receipt else -self.amount

    def __str__(self):
        return f'{self.document_number} {self.get_transaction_type_display()} {self.amount}'


class CashDocumentLine(models.Model):
    """One line item of a cash payment (EXPENSE): a GL account and an amount.

    A document with lines debits each line's account and credits the cash once for the total, which is the document's amount.
    A document with none keeps the single ``offset_account`` it always had.
    """
    document = models.ForeignKey(CashDocument, on_delete=models.CASCADE, related_name='lines')
    account = models.ForeignKey('accounting.Account', on_delete=models.PROTECT, related_name='+')
    description = models.CharField(max_length=255, blank=True, default='')
    amount = models.DecimalField(max_digits=15, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])

    class Meta:
        ordering = ['id']
        constraints = [
            models.CheckConstraint(condition=models.Q(amount__gt=0), name='cash_document_line_positive_amount'),
        ]

    def __str__(self):
        return f'{self.document_id} {self.account_id} {self.amount}'


class CashClosing(AuditBaseModel):
    """The day-end count of a cash journal."""
    cash_journal = models.ForeignKey(CashJournal, on_delete=models.PROTECT, related_name='closings')
    closing_date = models.DateField()
    book_balance = models.DecimalField(max_digits=15, decimal_places=2)
    counted_amount = models.DecimalField(max_digits=15, decimal_places=2, validators=[MinValueValidator(Decimal('0'))])
    # counted - book: negative = cash short, positive = cash over.
    difference = models.DecimalField(max_digits=15, decimal_places=2, default=Decimal('0.00'))
    difference_journal = models.ForeignKey('accounting.JournalHeader', on_delete=models.PROTECT, null=True, blank=True,
                                           related_name='+')
    note = models.CharField(max_length=255, blank=True, default='')

    class Meta:
        ordering = ['-closing_date', '-id']
        constraints = [
            models.UniqueConstraint(fields=['cash_journal', 'closing_date'], name='one_closing_per_cash_journal_day'),
        ]

    def __str__(self):
        return f'{self.cash_journal_id} closed {self.closing_date}'
