"""Phase 1 — Vendor Advance Special-GL ledger.

Creates:
  • RECONCILIATION_TYPE_CHOICES gains 'vendor_advance' (no schema-level
    change — choices are validated at form time, the column already
    holds a 30-char free string).
  • Two new tables:
      ``accounting_vendoradvance``           — one row per advance disbursed
      ``accounting_vendoradvanceclearance``  — one row per clearance event
  • Indexes for the hot popup query (vendor + status) and source FK
    deep-linking.
  • Check constraints enforcing the recovered ≤ paid invariant at
    the DB level (defence in depth — the service layer asserts the
    same rule before save).

This migration is shape-only — no backfill yet. Phase 2 will migrate
existing ``MobilizationPayment`` PAID rows into ``VendorAdvance``
records.
"""
from django.conf import settings
from django.db import migrations, models
import django.core.validators
from decimal import Decimal


class Migration(migrations.Migration):

    dependencies = [
        ('accounting', '0096_backfill_grir_clearing_account'),
        ('procurement', '0047_invoicematching_verification_number'),
    ]

    operations = [
        migrations.CreateModel(
            name='VendorAdvance',
            fields=[
                ('id',         models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('source_type', models.CharField(
                    choices=[
                        ('MOBILIZATION',   'Contract Mobilisation'),
                        ('PO_DOWNPAYMENT', 'PO Down Payment'),
                        ('AP_DOWNPAYMENT', 'AP Down Payment'),
                        ('OTHER',          'Other Advance'),
                    ],
                    db_index=True, max_length=20,
                )),
                ('source_id', models.PositiveIntegerField(blank=True, db_index=True, null=True,
                    help_text='FK id of the originating document '
                              '(MobilizationPayment / DownPaymentRequest / etc.).')),
                ('reference', models.CharField(
                    db_index=True, max_length=100,
                    help_text='User-visible reference, e.g. "DSG/WORKS/2026/001-MOB".',
                )),
                ('amount_paid', models.DecimalField(
                    max_digits=20, decimal_places=2,
                    validators=[django.core.validators.MinValueValidator(Decimal('0.00'))],
                    help_text='Gross amount disbursed at the time the advance was paid.',
                )),
                ('amount_recovered', models.DecimalField(
                    max_digits=20, decimal_places=2, default=Decimal('0.00'),
                    validators=[django.core.validators.MinValueValidator(Decimal('0.00'))],
                    help_text='Cumulative amount cleared (recovered) so far.',
                )),
                ('status', models.CharField(
                    choices=[
                        ('OUTSTANDING', 'Outstanding'),
                        ('PARTIAL',     'Partially Recovered'),
                        ('CLEARED',     'Fully Cleared'),
                    ],
                    db_index=True, default='OUTSTANDING', max_length=15,
                )),
                ('posting_date', models.DateField(help_text='Date the disbursement journal posted.')),
                ('notes', models.TextField(blank=True, default='')),

                ('created_by', models.ForeignKey(
                    blank=True, null=True, on_delete=models.deletion.SET_NULL,
                    related_name='+', to=settings.AUTH_USER_MODEL,
                )),
                ('updated_by', models.ForeignKey(
                    blank=True, null=True, on_delete=models.deletion.SET_NULL,
                    related_name='+', to=settings.AUTH_USER_MODEL,
                )),
                ('vendor', models.ForeignKey(
                    on_delete=models.deletion.PROTECT,
                    related_name='advances', to='procurement.vendor',
                )),
                ('recon_account', models.ForeignKey(
                    on_delete=models.deletion.PROTECT,
                    related_name='vendor_advances',
                    limit_choices_to={'reconciliation_type': 'vendor_advance'},
                    to='accounting.account',
                    help_text='Special-GL account that holds the advance '
                              '(behaves like AP recon but for advances).',
                )),
                ('disbursement_journal', models.ForeignKey(
                    blank=True, null=True, on_delete=models.deletion.PROTECT,
                    related_name='vendor_advances_disbursed',
                    to='accounting.journalheader',
                    help_text='The DR Vendor-Advance / CR Cash journal that '
                              'recognised this advance.',
                )),
            ],
            options={
                'ordering': ['-posting_date', '-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='vendoradvance',
            index=models.Index(
                fields=['vendor', 'status'],
                name='acct_vendor_advance_open_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='vendoradvance',
            index=models.Index(
                fields=['source_type', 'source_id'],
                name='acct_vendor_advance_src_idx',
            ),
        ),
        migrations.AddConstraint(
            model_name='vendoradvance',
            constraint=models.CheckConstraint(
                check=models.Q(amount_paid__gte=0),
                name='acct_vendor_advance_paid_non_negative',
            ),
        ),
        migrations.AddConstraint(
            model_name='vendoradvance',
            constraint=models.CheckConstraint(
                check=models.Q(amount_recovered__gte=0),
                name='acct_vendor_advance_recovered_non_negative',
            ),
        ),
        migrations.AddConstraint(
            model_name='vendoradvance',
            constraint=models.CheckConstraint(
                check=models.Q(amount_recovered__lte=models.F('amount_paid')),
                name='acct_vendor_advance_recovered_lte_paid',
            ),
        ),

        migrations.CreateModel(
            name='VendorAdvanceClearance',
            fields=[
                ('id',         models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('amount', models.DecimalField(
                    max_digits=20, decimal_places=2,
                    validators=[django.core.validators.MinValueValidator(Decimal('0.01'))],
                    help_text='Amount cleared in this event.',
                )),
                ('posting_date', models.DateField()),
                ('cleared_against_type', models.CharField(
                    blank=True, default='', max_length=30,
                    help_text='e.g. "VendorInvoice", "IPC", "PaymentVoucher".',
                )),
                ('cleared_against_id', models.PositiveIntegerField(blank=True, null=True)),
                ('cleared_against_reference', models.CharField(blank=True, default='', max_length=100)),
                ('notes', models.TextField(blank=True, default='')),

                ('created_by', models.ForeignKey(
                    blank=True, null=True, on_delete=models.deletion.SET_NULL,
                    related_name='+', to=settings.AUTH_USER_MODEL,
                )),
                ('updated_by', models.ForeignKey(
                    blank=True, null=True, on_delete=models.deletion.SET_NULL,
                    related_name='+', to=settings.AUTH_USER_MODEL,
                )),
                ('advance', models.ForeignKey(
                    on_delete=models.deletion.CASCADE,
                    related_name='clearances', to='accounting.vendoradvance',
                )),
                ('clearing_journal', models.ForeignKey(
                    blank=True, null=True, on_delete=models.deletion.PROTECT,
                    related_name='vendor_advance_clearances',
                    to='accounting.journalheader',
                )),
            ],
            options={
                'ordering': ['-posting_date', '-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='vendoradvanceclearance',
            index=models.Index(
                fields=['advance', 'posting_date'],
                name='acct_vadv_clearance_idx',
            ),
        ),
        migrations.AddConstraint(
            model_name='vendoradvanceclearance',
            constraint=models.CheckConstraint(
                check=models.Q(amount__gt=0),
                name='acct_vadv_clearance_amount_positive',
            ),
        ),
    ]
