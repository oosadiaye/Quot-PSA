"""
Procurement Posting Service — accounting domain.

Handles GL posting for all purchase-cycle transactions:
Purchase Orders, Goods Received Notes, Vendor Invoices, Payments,
Purchase Returns, Vendor Credit Notes, and Vendor Debit Notes.
"""

import logging
from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from accounting.models import JournalHeader, JournalLine, Account
from accounting.services.base_posting import BasePostingService, TransactionPostingError, get_gl_account

logger = logging.getLogger(__name__)


def get_vendor_ap_account(vendor):
    """
    Resolve the AP control account for a given vendor.

    Lookup chain (in priority order, first hit wins):
      1. ``vendor.category.reconciliation_account`` — the canonical
         per-category AP recon GL. The ``VendorCategory.reconciliation_account``
         FK is constrained at the model level to accounts with
         ``reconciliation_type='accounts_payable'``, so this guarantees
         a properly-flagged AP account when the vendor is categorised.
      2. Any active ``Account`` flagged ``reconciliation_type='accounts_payable'``
         in the Chart of Accounts. Used as a soft fallback when the
         vendor or its category isn't fully configured — better than
         hard-failing the posting.
      3. Legacy ``DEFAULT_GL_ACCOUNTS['ACCOUNTS_PAYABLE']`` settings code.
         Last resort for tenants that haven't migrated to the
         per-category model yet.

    Returns:
        (Account, source_label) tuple. ``source_label`` is a short
        human description of which step in the chain matched —
        useful for warning logs when fallbacks fire.

    Raises:
        TransactionPostingError with an actionable message naming the
        broken link in the chain when no AP account can be resolved.
    """
    # Primary: vendor → category → recon account
    if vendor is None:
        raise TransactionPostingError(
            "Cannot resolve AP account — invoice/payment has no vendor. "
            "Attach a vendor before posting."
        )
    category = getattr(vendor, 'category', None)
    if category is not None:
        recon = getattr(category, 'reconciliation_account', None)
        if recon is not None:
            return recon, f'vendor category "{category.name}"'

    # Fallback 1: any reconciliation_type='accounts_payable' account
    fallback_recon = Account.objects.filter(
        reconciliation_type='accounts_payable', is_active=True,
    ).first()
    if fallback_recon is not None:
        logger.warning(
            "AP fallback: vendor %s has no category recon account; "
            "using global reconciliation_type='accounts_payable' account %s. "
            "Configure a vendor category to silence this warning.",
            getattr(vendor, 'code', vendor.pk), fallback_recon.code,
        )
        return fallback_recon, 'global reconciliation_type=accounts_payable'

    # Fallback 2: legacy settings code
    legacy = get_gl_account('ACCOUNTS_PAYABLE', 'Liability', 'Payable')
    if legacy is not None:
        logger.warning(
            "AP fallback: vendor %s has no category recon account and no "
            "Liability is flagged reconciliation_type=accounts_payable; "
            "using legacy DEFAULT_GL_ACCOUNTS['ACCOUNTS_PAYABLE'] = %s.",
            getattr(vendor, 'code', vendor.pk), legacy.code,
        )
        return legacy, 'DEFAULT_GL_ACCOUNTS settings code'

    # Nothing matched — name the missing link so the operator knows
    # exactly where to fix it.
    if category is None:
        raise TransactionPostingError(
            f"Vendor '{vendor.name}' has no category assigned. "
            "Open Settings → Vendors, edit this vendor and assign a "
            "vendor category whose reconciliation account is the "
            "right AP control GL for this vendor's class "
            "(e.g. Local Suppliers, Foreign Suppliers, Statutory)."
        )
    raise TransactionPostingError(
        f"Vendor category '{category.name}' has no reconciliation account "
        "configured. Open Settings → Vendor Categories, edit this "
        "category and pick the AP control GL — only accounts flagged "
        "reconciliation_type='accounts_payable' in Chart of Accounts "
        "are selectable."
    )


def get_input_vat_account(tax_code_obj=None):
    """Resolve the Input VAT GL account via a layered ladder.

    Order (first hit wins):
      1. ``tax_code.input_tax_account`` — operator's explicit per-code
         configuration. The most precise signal of intent.
      2. ``tax_code.tax_account`` — legacy single-account TaxCode field.
      3. Any active ``Account`` flagged ``reconciliation_type='input_tax'``
         or ``'vat_recoverable'`` in the Chart of Accounts. Lets a tenant
         designate one VAT-recoverable control account once.
      4. Legacy ``DEFAULT_GL_ACCOUNTS['INPUT_TAX']`` /
         ``DEFAULT_GL_ACCOUNTS['TAX_PAYABLE']`` settings codes.
      5. Heuristic: any active Asset whose name contains
         "Input VAT" or "Input Tax".

    Returns:
        ``Account`` instance or ``None`` if no candidate matches. Callers
        must handle ``None`` gracefully — typically by absorbing the tax
        amount into the GR/IR debit so the journal still balances.
    """
    if tax_code_obj is not None:
        acct = (
            getattr(tax_code_obj, 'input_tax_account', None)
            or getattr(tax_code_obj, 'tax_account', None)
        )
        if acct is not None:
            return acct
    # Reconciliation-type flag (CoA-portable; doesn't depend on numbering)
    acct = Account.objects.filter(
        reconciliation_type__in=['input_tax', 'vat_recoverable'],
        is_active=True,
    ).first()
    if acct is not None:
        return acct
    # Legacy settings codes
    for key in ('INPUT_TAX', 'TAX_PAYABLE'):
        candidate = get_gl_account(key, 'Asset', 'Input Tax')
        if candidate is not None:
            return candidate
    # Last-resort heuristic — Asset named "Input VAT/Tax".
    return Account.objects.filter(
        account_type='Asset', is_active=True, name__iregex=r'input.*(vat|tax)',
    ).first()


class ProcurementPostingService(BasePostingService):
    """
    GL posting service for the Procurement domain.
    """

    @staticmethod
    @transaction.atomic
    def post_purchase_order(po):
        """
        IPSAS 3-way match — a Purchase Order creates NO GL journal.

        In public-sector accounting a PO is only a *commitment* (the
        legal promise to spend), not expenditure recognition. The GL
        stays untouched until physical receipt (GRN) or invoice
        verification. This function therefore returns ``None`` — we
        keep it for call-site compatibility (``post_order`` expects
        ``journal`` back) but no rows are ever written.

        The commitment itself is booked via
        ``accounting.services.procurement_commitments.create_commitment_for_po``
        at the Approve step — that's what rolls the appropriation's
        ``total_committed`` up and also enforces warrant ceilings.

        Returns:
            None — no journal is created at PO post.
        """
        if po.status != 'Posted':
            raise TransactionPostingError(f"PO must be Posted status, got {po.status}")
        # Commitment, warrant, and appropriation gates run during the
        # Approve step; post_order is a UX nicety that flips the status
        # for visibility. No ledger posting happens here.
        return None

    # The legacy implementation below (DR Inventory / CR AP at PO post)
    # is retained for reference / reversible migration if a tenant ever
    # opts back into private-sector semantics. It is no longer reachable
    # from ``post_purchase_order`` above.
    @staticmethod
    def _legacy_post_purchase_order(po):  # pragma: no cover - kept for history
        """Deprecated private-sector path — DR Inventory / CR AP at PO post.

        No longer called. Reinstating requires restoring the original
        ``post_purchase_order`` body and removing the early-return in
        ``post_goods_received_note`` so the two don't double-post.
        """
        if po.status != 'Posted':
            raise TransactionPostingError(f"PO must be Posted status, got {po.status}")

        ProcurementPostingService._check_duplicate_posting(po.po_number)
        ProcurementPostingService._validate_fiscal_period(po.order_date)

        if po.lines.count() == 0:
            raise TransactionPostingError("PO has no lines")

        total_amount = po.subtotal
        tax_amount = po.tax_amount
        grand_total = total_amount + tax_amount

        # AP discovery — driven by the vendor's category recon account,
        # not a global default. See ``get_vendor_ap_account`` for the
        # full lookup chain and operator-actionable error messages.
        ap_account, ap_source = get_vendor_ap_account(po.vendor)

        # Create journal header
        journal = JournalHeader.objects.create(
            posting_date=po.order_date,
            description=f"Purchase Order {po.po_number} - Vendor: {po.vendor.name}",
            reference_number=po.po_number,
            mda=po.mda,
            fund=po.fund,
            function=po.function,
            program=po.program,
            geo=po.geo,
            status='Posted',
            source_module='procurement',
            source_document_id=po.pk,
        )

        # Inventory/Asset Debit
        if total_amount > 0:
            # Group by account
            account_totals = {}
            for line in po.lines.all():
                inventory_account = line.item.inventory_account if line.item else None
                if not inventory_account and line.product_type:
                    inventory_account = line.product_type.inventory_account

                if not inventory_account:
                    # Use configured default inventory account
                    inventory_account = get_gl_account('INVENTORY', 'Asset', 'Inventory')

                if inventory_account.id not in account_totals:
                    account_totals[inventory_account.id] = {
                        'account': inventory_account,
                        'amount': Decimal('0.00')
                    }

                line_total = line.quantity * line.unit_price
                account_totals[inventory_account.id]['amount'] += line_total

            for acc_data in account_totals.values():
                JournalLine.objects.create(
                    header=journal,
                    account=acc_data['account'],
                    debit=acc_data['amount'],
                    credit=Decimal('0.00'),
                    memo=f"PO {po.po_number}"
                )

        # AP Credit (full amount including tax)
        if grand_total > 0:
            JournalLine.objects.create(
                header=journal,
                account=ap_account,
                debit=Decimal('0.00'),
                credit=grand_total,
                memo=f"AP from PO {po.po_number}"
            )

        # Tax Liability Debit (if tax amount)
        if tax_amount > 0:
            tax_account = get_gl_account('TAX_PAYABLE', 'Liability', 'Tax')
            if tax_account:
                JournalLine.objects.create(
                    header=journal,
                    account=tax_account,
                    debit=tax_amount,
                    credit=Decimal('0.00'),
                    memo=f"Input Tax from PO {po.po_number}"
                )

        # Update vendor balance (atomic F()-based)
        if hasattr(po, 'vendor') and po.vendor:
            from django.db.models import F
            type(po.vendor).objects.filter(pk=po.vendor.pk).update(
                balance=F('balance') + grand_total
            )

        # Validate journal is balanced before GL update
        ProcurementPostingService._validate_journal_balanced(journal)

        # Update GL balances
        ProcurementPostingService._update_gl_balances(journal)

        # ── Commitment link: safety net in case the Approved-status hook
        # was bypassed (e.g. legacy data migrated into 'Posted' directly).
        # ``create_commitment_for_po`` is idempotent — if a link already
        # exists it just refreshes the committed amount.
        #
        # S1-10 — ``BudgetExceededError`` MUST propagate so the PO post
        # fails when the appropriation ceiling would be breached. The old
        # blanket ``except Exception: log.warning`` swallowed this error
        # and silently allowed over-commitment. We now let the ceiling
        # error bubble up while still tolerating non-critical failures
        # (missing NCoA bridges, etc.) so the GL post isn't aborted by
        # a configuration issue.
        try:
            create_commitment_for_po(po, grand_total)
        except Exception as exc:
            # Ceiling breaches MUST abort posting.
            from budget.services import BudgetExceededError
            if isinstance(exc, BudgetExceededError):
                raise
            import logging
            logging.getLogger(__name__).warning(
                "Failed to create ProcurementBudgetLink for PO %s: %s",
                po.po_number, exc,
            )

        return journal

    @staticmethod
    def _create_budget_commitment(po, committed_amount):
        """Deprecated alias — delegates to ``procurement_commitments.create_commitment_for_po``.

        Kept for backward compatibility with the GL-posting call site.
        New callers (e.g. the PO model's status-transition hook) should
        use ``create_commitment_for_po`` from the commitments module
        directly so the same logic runs for any "Approved" → commitment
        trigger, not only "Posted" → GL entry.
        """
        from accounting.services.procurement_commitments import create_commitment_for_po
        return create_commitment_for_po(po, committed_amount)

    # NOTE: Commitment helpers (create_commitment_for_po,
    # cancel_commitment_for_po, mark_commitment_invoiced_for_po) live in
    # ``accounting/services/procurement_commitments.py`` so model save()
    # hooks can import them without pulling in the whole service class.

    @staticmethod
    @transaction.atomic
    def post_goods_received_note(grn):
        """
        Post a Goods Received Note to the GL — IPSAS three-way match.

        P2P accounting logic:

        - **PO Posted first** (legacy/inventoried path): DR Inventory / CR AP
          was already recorded at PO posting. GRN here only confirms physical
          receipt — no additional GL entry. Returns ``None``.

        - **PO not yet Posted** (canonical 3-way match):
            * DR Expense / Asset / Inventory  (per po_line — see priority below)
            * CR GR/IR Clearing                                  (liability)

          Debit-account priority per line:
            1. Inventoriable item  → ``item.inventory_account``
                                     → ``product_type.inventory_account``
                                     → ``DEFAULT_GL_ACCOUNTS['INVENTORY']``
            2. Fixed asset PO line → ``po_line.asset.gl_account``
            3. Service / direct expense → ``po_line.account`` (always set)

        The credit (GR/IR Clearing) is parked until the vendor invoice clears
        it via ``post_vendor_invoice`` — at which point AP is recognised and
        the budget commitment moves INVOICED → CLOSED.

        Args:
            grn: GoodsReceivedNote instance (must be in 'Posted' status)

        Returns:
            JournalHeader or None
        """
        if grn.status != 'Posted':
            raise TransactionPostingError(f"GRN must be Posted status, got {grn.status}")

        ProcurementPostingService._check_duplicate_posting(grn.grn_number)
        ProcurementPostingService._validate_fiscal_period(grn.received_date)

        po = grn.purchase_order

        # IPSAS 3-way match — the GRN is ALWAYS the first GL event for a
        # purchase, regardless of whether ``post_order`` was run on the
        # PO earlier. Previously this block returned ``None`` when the
        # PO was already Posted, relying on a legacy "PO-post creates
        # DR Inventory / CR AP" path that conflates the commitment,
        # receipt and obligation stages into one entry. That conflicts
        # with the public-sector doctrine we enforce elsewhere:
        #   - PO approve  → commitment (create_commitment_for_po)
        #   - GRN post    → DR Inventory / CR GR/IR Clearing   ← here
        #   - Invoice     → DR GR/IR / CR AP
        #   - Payment     → DR AP / CR Bank
        # So we drop the early-return — every GRN now creates its own
        # journal so the trial balance, Budget Performance, Variance
        # Analysis, and Warrant Utilization reports reflect receipts
        # in real time.
        #
        # 3-way match: DR Inventory / CR GR/IR Clearing (NOT AP directly).
        # AP is recognised only when the vendor invoice is matched and posted.
        grn_ir_account = get_gl_account('GOODS_RECEIPT_CLEARING', 'Liability', 'GR/IR')
        if not grn_ir_account:
            raise TransactionPostingError(
                "GR/IR Clearing account not found. "
                "Configure DEFAULT_GL_ACCOUNTS['GOODS_RECEIPT_CLEARING'] in settings "
                "and ensure a Liability account in the 41xxxxxx series "
                "(default code: 41090000 — GR/IR Clearing Account) exists in the Chart of Accounts."
            )

        journal = JournalHeader.objects.create(
            posting_date=grn.received_date,
            description=f"GRN {grn.grn_number} - PO: {po.po_number}",
            reference_number=grn.grn_number,
            mda=po.mda,
            fund=po.fund,
            function=po.function,
            program=po.program,
            geo=po.geo,
            status='Posted',
            # Distinct source_module so GRN, PO and Invoice pks can't
            # collide on the unique (source_module, source_document_id)
            # constraint. Previously all three used 'procurement' which
            # meant PO #1 and GRN #1 fought over the same slot.
            source_module='grn',
            source_document_id=grn.pk,
        )

        # IPSAS three-way match — debit side selection priority:
        #   1. Inventoriable items: DR Inventory account (item.inventory_account
        #      → product_type.inventory_account → DEFAULT_GL_ACCOUNTS['INVENTORY'])
        #   2. Fixed-asset POs: DR the asset's GL account (capitalised on receipt)
        #   3. Service / direct-expense lines: DR po_line.account (the expense
        #      account chosen when the PO line was raised)
        # In all three cases we credit GR/IR Clearing — the liability that
        # parks the value until the vendor invoice clears it.
        total_received = Decimal('0.00')
        skipped_lines = []
        for grn_line in grn.lines.all():
            po_line = grn_line.po_line
            if not po_line:
                skipped_lines.append(grn_line.pk)
                continue

            quantity = grn_line.quantity_received
            unit_cost = po_line.unit_price
            line_total = quantity * unit_cost
            if line_total <= 0:
                continue

            # Resolve debit account — see priority order above.
            debit_account = None
            memo_label = po_line.item_description or 'Goods/Services'

            if po_line.item:
                item = po_line.item
                debit_account = item.inventory_account
                if not debit_account and item.product_type:
                    debit_account = item.product_type.inventory_account
                if not debit_account:
                    debit_account = get_gl_account('INVENTORY', 'Asset', 'Inventory')
                memo_label = f"{item.sku} x {quantity}"
            elif po_line.asset and getattr(po_line.asset, 'gl_account', None):
                debit_account = po_line.asset.gl_account
                memo_label = f"FA {po_line.asset} x {quantity}"

            # Fall back to the PO line's chosen GL account (always set — see
            # PurchaseOrderLine.account = ForeignKey(Account, on_delete=PROTECT)).
            if not debit_account:
                debit_account = po_line.account

            if not debit_account:
                # Should be unreachable, but keep the journal balanced rather
                # than silently posting an asymmetric entry.
                skipped_lines.append(grn_line.pk)
                continue

            total_received += line_total
            JournalLine.objects.create(
                header=journal,
                account=debit_account,
                debit=line_total,
                credit=Decimal('0.00'),
                memo=f"GRN {grn.grn_number}: {memo_label}",
            )

        # Credit GR/IR Clearing (3-way match — AP recognised at invoice matching).
        # The credit total equals the sum of debits to keep the journal balanced.
        if total_received > 0:
            JournalLine.objects.create(
                header=journal,
                account=grn_ir_account,
                debit=Decimal('0.00'),
                credit=total_received,
                memo=f"GR/IR Clearing from GRN {grn.grn_number}",
            )

        if skipped_lines:
            import logging
            logging.getLogger(__name__).warning(
                "GRN %s posted but %d line(s) had no resolvable debit account "
                "and were skipped: %s",
                grn.grn_number, len(skipped_lines), skipped_lines,
            )

        ProcurementPostingService._validate_journal_balanced(journal)
        ProcurementPostingService._update_gl_balances(journal)

        return journal

    @staticmethod
    @transaction.atomic
    def post_vendor_invoice(invoice):
        """
        Post a Vendor Invoice to the GL.

        Args:
            invoice: VendorInvoice instance

        Returns:
            JournalHeader: The created journal entry
        """
        if invoice.status not in ['Approved', 'Paid']:
            raise TransactionPostingError(f"Invoice must be Approved or Paid, got {invoice.status}")

        ProcurementPostingService._check_duplicate_posting(invoice.invoice_number)
        ProcurementPostingService._validate_fiscal_period(invoice.invoice_date)

        journal = JournalHeader.objects.create(
            posting_date=invoice.invoice_date,
            description=f"Vendor Invoice {invoice.invoice_number}",
            reference_number=invoice.invoice_number,
            mda=invoice.mda,
            fund=invoice.fund,
            function=invoice.function,
            program=invoice.program,
            geo=invoice.geo,
            status='Draft',
            source_module='procurement',
            source_document_id=invoice.pk,
        )

        # Pre-fetch all invoice lines once with related objects to avoid N+1 queries.
        invoice_lines = list(
            invoice.lines.all().select_related(
                'account',
                'tax_code', 'tax_code__input_tax_account', 'tax_code__tax_account',
                'withholding_tax', 'withholding_tax__withholding_account',
            )
        )

        # 3-way match: if this invoice is linked to a GRN (via a PO that was NOT pre-posted),
        # debit GR/IR Clearing to clear it and credit AP. If there's no GRN link (direct
        # invoice) debit the expense/inventory account directly and credit AP.
        grn_ir_account = get_gl_account('GOODS_RECEIPT_CLEARING', 'Liability', 'GR/IR')
        has_grn_match = (
            grn_ir_account is not None
            and invoice.purchase_order is not None
            and invoice.purchase_order.status != 'Posted'  # PO was not pre-posted → GRN created GR/IR
        )

        if has_grn_match:
            # DR GR/IR Clearing — RESIDUAL APPROACH for always-balanced
            # journals. We compute the GR/IR debit as
            # ``invoice.total_amount - input_tax_dr_total`` (deferred
            # below). When an Input VAT account resolves, GR/IR =
            # subtotal (textbook SAP MIRO split). When no Input VAT GL is
            # configured, GR/IR absorbs the tax — the journal still
            # balances. The actual line is written AFTER VAT computation
            # below; here we just remember that we owe a GR/IR debit.
            grn_ir_pending = True
        else:
            grn_ir_pending = False
            # Direct invoice (no prior GRN) — debit per invoice line so that
            # per-line GL accounts (e.g. capex GLs with auto_create_asset=True)
            # land in the journal and trigger asset auto-capitalisation correctly.
            if invoice_lines:
                for inv_line in invoice_lines:
                    if inv_line.amount and inv_line.amount > 0 and inv_line.account:
                        JournalLine.objects.create(
                            header=journal,
                            account=inv_line.account,
                            debit=inv_line.amount,
                            credit=Decimal('0.00'),
                            memo=(inv_line.description or inv_line.account.name or f"Invoice {invoice.invoice_number}")[:255],
                        )
            elif invoice.subtotal > 0 and invoice.account:
                # Fallback for header-only invoices (no line items)
                JournalLine.objects.create(
                    header=journal,
                    account=invoice.account,
                    debit=invoice.subtotal,
                    credit=Decimal('0.00'),
                    memo=f"Invoice {invoice.invoice_number}",
                )

        # ── VAT computation from per-line tax_code ────────────────────────
        #
        # Nigerian IFMIS / FIRS practice is CASH-BASIS WHT recognition: the
        # taxing event is the payment itself, not the invoice accrual.
        # Accordingly, AP posting books the FULL gross (including VAT) to
        # Accounts Payable — NO WHT is booked here. WHT, stamp duty and any
        # other statutory deductions are recognised at payment time via the
        # PaymentVoucher deduction lines (see accounting.views.treasury_revenue
        # ._post_payment_journal).
        #
        # Public-sector AP posting model (accrual of expense + VAT only):
        #   DR  Expense (or GR/IR)        = subtotal  (net of VAT)
        #   DR  Input VAT Receivable      = Σ line.amount × line.tax_code.rate
        #   CR  Accounts Payable          = subtotal + input_vat  (= total_amount)
        #
        # At payment time the PV posts:
        #   DR  Accounts Payable          = total_amount
        #   CR  TSA Cash                  = net payable to vendor
        #   CR  WHT Payable               = WHT deduction
        #   CR  Stamp Duty Payable        = statutory deduction
        #   ... additional deduction lines as needed
        #
        # VAT preference order:
        #   1. Per-line tax_code (preferred — drives compliant tax reporting)
        #   2. Header-level invoice.tax_amount (legacy fallback when no line data)
        input_vat_by_account: dict[int, tuple] = {}
        line_computed_vat = Decimal('0.00')
        has_line_tax_code = False

        for line in invoice_lines:
            if line.tax_code and line.tax_code.rate and line.tax_code.rate > 0:
                has_line_tax_code = True
                # TaxCode.rate is stored as a percentage (e.g. 7.5 for 7.5% VAT)
                rate = Decimal(str(line.tax_code.rate))
                vat_amount = (line.amount * rate / Decimal('100')).quantize(Decimal('0.01'))
                acct = (
                    line.tax_code.input_tax_account
                    or line.tax_code.tax_account
                )
                if acct:
                    prev = input_vat_by_account.get(acct.id, (acct, Decimal('0.00')))
                    input_vat_by_account[acct.id] = (acct, prev[1] + vat_amount)
                    line_computed_vat += vat_amount

        # ── Withholding Tax determination (NOT booked at invoice) ─────
        # Nigerian public-sector practice: WHT is DETERMINED at invoice
        # verification (rate + exempt flag stored on the line / matching)
        # but RECOGNISED at payment time on the PaymentVoucher's deduction
        # rows — the taxing event is the cash outflow, not the accrual.
        # See `accounting.views.treasury_revenue._post_payment_journal`.
        #
        # Therefore this method records NO WHT debit/credit on the invoice
        # journal. AP is credited at the full gross (subtotal + VAT). The
        # WHT FK on the line is left intact so PV creation can read it
        # and auto-build the deduction row at payment time. If the line
        # carries ``wht_exempt=True`` the PV builder will honour the
        # exemption end-to-end.
        line_computed_wht = Decimal('0.00')

        # DR: Input VAT lines (one row per input_tax_account)
        for _, (acct, amount) in input_vat_by_account.items():
            if amount > 0:
                JournalLine.objects.create(
                    header=journal,
                    account=acct,
                    debit=amount,
                    credit=Decimal('0.00'),
                    memo=f"Input VAT — {invoice.invoice_number}",
                )

        # Legacy header-level tax fallback — only when no per-line tax_code was used.
        # Uses the layered ``get_input_vat_account`` ladder so the GL is
        # found via reconciliation_type / settings / heuristic, not just
        # the legacy 'TAX_PAYABLE' code mapping. When NO Input VAT GL is
        # resolvable we deliberately skip the tax line — the GR/IR
        # residual write below absorbs the tax amount so DR = CR.
        if not has_line_tax_code and invoice.tax_amount and invoice.tax_amount > 0:
            tax_account = get_input_vat_account(getattr(invoice, 'tax_code', None))
            if tax_account is not None:
                JournalLine.objects.create(
                    header=journal,
                    account=tax_account,
                    debit=invoice.tax_amount,
                    credit=Decimal('0.00'),
                    memo=f"Input Tax (header) — {invoice.invoice_number}",
                )
                line_computed_vat = invoice.tax_amount  # contributes to AP below

        # CR: Accounts Payable — booked at FULL GROSS (subtotal + VAT).
        # WHT is intentionally NOT deducted here — Nigerian PFM is
        # cash-basis (recognised at payment voucher time). AP via vendor
        # → category → recon_account chain.
        ap_account, ap_source = get_vendor_ap_account(invoice.vendor)

        ap_credit = invoice.total_amount or Decimal('0.00')
        if ap_credit > 0:
            JournalLine.objects.create(
                header=journal,
                account=ap_account,
                debit=Decimal('0.00'),
                credit=ap_credit,
                memo=f"AP {invoice.invoice_number}",
            )

        # ── GR/IR residual write (deferred from above) ────────────────
        # The GR/IR debit is computed AS the residual that balances the
        # journal so DR = CR by construction. Algebra:
        #   CR side = AP + Σ WHT = (total − WHT_total) + WHT_total = total_amount
        #   DR side must also = total_amount = GR/IR + Σ Input VAT
        #     ⇒ GR/IR = total_amount − Σ Input VAT
        # When per-line or header Input VAT GLs resolved, GR/IR =
        # subtotal (textbook SAP MIRO split). When no Input VAT GL was
        # found, Σ Input VAT = 0 and GR/IR absorbs the tax so the
        # journal still balances. Either way, no operator config gap
        # produces an out-of-balance entry.
        if grn_ir_pending and grn_ir_account is not None:
            input_vat_total_dr = sum(
                (amt for _, (_a, amt) in input_vat_by_account.items()),
                Decimal('0.00'),
            )
            # Add the header-fallback tax if it was actually written
            # (line_computed_vat is non-zero only after a successful write).
            if not has_line_tax_code:
                input_vat_total_dr += line_computed_vat
            grn_ir_debit = (
                (invoice.total_amount or Decimal('0.00')) - input_vat_total_dr
            ).quantize(Decimal('0.01'))
            if grn_ir_debit > 0:
                JournalLine.objects.create(
                    header=journal,
                    account=grn_ir_account,
                    debit=grn_ir_debit,
                    credit=Decimal('0.00'),
                    memo=f"GR/IR Clearing — Invoice {invoice.invoice_number}",
                )

        ProcurementPostingService._validate_journal_balanced(journal)
        ProcurementPostingService._update_gl_balances(journal)

        journal.status = 'Posted'
        journal.save(update_fields=['status'], _allow_status_change=True)

        invoice.journal_entry = journal
        invoice.save(_allow_status_change=True)
        return journal

    @staticmethod
    @transaction.atomic
    def post_payment(payment):
        """
        Post a Payment to the GL.

        Args:
            payment: Payment instance

        Returns:
            JournalHeader: The created journal entry
        """
        if payment.status != 'Posted':
            raise TransactionPostingError(f"Payment must be Posted status, got {payment.status}")

        if hasattr(payment, 'journal_entry') and payment.journal_entry:
            raise TransactionPostingError("Payment already posted to GL")

        ProcurementPostingService._validate_fiscal_period(payment.payment_date)

        amount = payment.total_amount

        # AP via vendor → category → recon_account chain.
        ap_account, ap_source = get_vendor_ap_account(payment.vendor)

        bank_gl_account = None
        if payment.bank_account and payment.bank_account.gl_account:
            bank_gl_account = payment.bank_account.gl_account
        if not bank_gl_account:
            bank_gl_account = get_gl_account('CASH_ACCOUNT', 'Asset', 'Bank')
        if not bank_gl_account:
            raise TransactionPostingError("No Bank/Cash GL account found")

        journal = JournalHeader.objects.create(
            posting_date=payment.payment_date,
            description=f"Payment {payment.payment_number}",
            reference_number=payment.payment_number,
            status='Posted',
            source_module='procurement',
            source_document_id=payment.pk,
        )

        # Debit: Accounts Payable (reduces liability)
        JournalLine.objects.create(
            header=journal,
            account=ap_account,
            debit=amount,
            credit=Decimal('0.00'),
            memo=f"Payment {payment.payment_number}"
        )

        # Credit: Bank/Cash (reduces asset)
        JournalLine.objects.create(
            header=journal,
            account=bank_gl_account,
            debit=Decimal('0.00'),
            credit=amount,
            memo=f"Payment {payment.payment_number}"
        )

        payment.journal_entry = journal
        payment.save()

        # Update vendor balance (atomic F()-based)
        if hasattr(payment, 'vendor') and payment.vendor:
            from django.db.models import F
            type(payment.vendor).objects.filter(pk=payment.vendor.pk).update(
                balance=F('balance') - amount
            )

        ProcurementPostingService._validate_journal_balanced(journal)
        ProcurementPostingService._update_gl_balances(journal)
        return journal

    @staticmethod
    @transaction.atomic
    def post_purchase_return(purchase_return):
        """
        Post a Purchase Return to the GL.

        Creates journal entry for:
        - Accounts Payable (debit) — reduces what we owe vendor
        - Inventory (credit) — reduces inventory value

        Args:
            purchase_return: PurchaseReturn instance

        Returns:
            JournalHeader: The created journal entry
        """
        ap_account = Account.objects.filter(
            account_type='Liability',
            name__icontains='Payable'
        ).first()

        if not ap_account:
            raise TransactionPostingError("No Accounts Payable account found")

        journal = JournalHeader.objects.create(
            posting_date=purchase_return.return_date,
            description=f"Purchase Return {purchase_return.return_number} - {purchase_return.vendor.name}",
            reference_number=purchase_return.return_number,
            status='Posted',
            source_module='procurement',
            source_document_id=purchase_return.pk,
            posted_at=timezone.now(),
        )

        # Process each return line
        account_totals = {}
        for line in purchase_return.lines.all():
            line_total = line.quantity * line.unit_price

            inventory_account = None
            if line.item:
                inventory_account = line.item.inventory_account
                if not inventory_account and line.item.product_type:
                    inventory_account = line.item.product_type.inventory_account

            if not inventory_account:
                inventory_account = Account.objects.filter(
                    account_type='Asset',
                    name__icontains='Inventory'
                ).first()

            if inventory_account:
                acc_id = inventory_account.id
                if acc_id not in account_totals:
                    account_totals[acc_id] = {'account': inventory_account, 'amount': Decimal('0.00')}
                account_totals[acc_id]['amount'] += line_total

        total_return_amount = sum(d['amount'] for d in account_totals.values())

        # Debit AP (reduce payable)
        if total_return_amount > 0:
            JournalLine.objects.create(
                header=journal,
                account=ap_account,
                debit=total_return_amount,
                credit=Decimal('0.00'),
                memo=f"AP reversal: Return {purchase_return.return_number}"
            )

        # Credit Inventory accounts
        for acc_data in account_totals.values():
            JournalLine.objects.create(
                header=journal,
                account=acc_data['account'],
                debit=Decimal('0.00'),
                credit=acc_data['amount'],
                memo=f"Inventory return: {purchase_return.return_number}"
            )

        # Update vendor balance (atomic F()-based — reduce what we owe)
        if hasattr(purchase_return, 'vendor') and purchase_return.vendor and total_return_amount > 0:
            from django.db.models import F
            type(purchase_return.vendor).objects.filter(pk=purchase_return.vendor.pk).update(
                balance=F('balance') - total_return_amount
            )

        ProcurementPostingService._validate_journal_balanced(journal)
        ProcurementPostingService._update_gl_balances(journal)
        return journal

    @staticmethod
    @transaction.atomic
    def post_vendor_credit_note(credit_note):
        """
        Post a Vendor Credit Note to the GL.

        Creates journal entry for:
        - Accounts Payable (debit) — reduces what we owe vendor
        - Inventory/Expense (credit) — reduces inventory value or records cost reduction

        Args:
            credit_note: VendorCreditNote instance

        Returns:
            JournalHeader: The created journal entry
        """
        if credit_note.status not in ['Approved', 'Posted']:
            raise TransactionPostingError(f"Credit note must be Approved, got {credit_note.status}")

        ap_account = Account.objects.filter(
            account_type='Liability',
            name__icontains='Payable'
        ).first()

        if not ap_account:
            raise TransactionPostingError("No Accounts Payable account found")

        journal = JournalHeader.objects.create(
            posting_date=credit_note.credit_note_date,
            description=f"Vendor Credit Note {credit_note.credit_note_number} - {credit_note.vendor.name}",
            reference_number=credit_note.credit_note_number,
            status='Posted',
            source_module='procurement',
            source_document_id=credit_note.pk,
            posted_at=timezone.now(),
        )

        total_amount = credit_note.total_amount

        # Debit AP (reduce payable)
        JournalLine.objects.create(
            header=journal,
            account=ap_account,
            debit=total_amount,
            credit=Decimal('0.00'),
            memo=f"AP reduction: Credit Note {credit_note.credit_note_number}"
        )

        # Credit Inventory/Expense account
        inventory_account = None
        if credit_note.purchase_order:
            # Try to get inventory account from PO lines
            for line in credit_note.purchase_order.lines.all():
                if line.item and line.item.inventory_account:
                    inventory_account = line.item.inventory_account
                    break
                if line.product_type and line.product_type.inventory_account:
                    inventory_account = line.product_type.inventory_account
                    break

        if not inventory_account:
            inventory_account = Account.objects.filter(
                account_type='Asset',
                name__icontains='Inventory'
            ).first()

        if inventory_account:
            JournalLine.objects.create(
                header=journal,
                account=inventory_account,
                debit=Decimal('0.00'),
                credit=total_amount,
                memo=f"Credit Note {credit_note.credit_note_number}"
            )

        # Update vendor balance (atomic F()-based — reduce what we owe)
        if hasattr(credit_note, 'vendor') and credit_note.vendor:
            from django.db.models import F
            type(credit_note.vendor).objects.filter(pk=credit_note.vendor.pk).update(
                balance=F('balance') - total_amount
            )

        ProcurementPostingService._validate_journal_balanced(journal)
        ProcurementPostingService._update_gl_balances(journal)
        return journal

    @staticmethod
    @transaction.atomic
    def post_vendor_debit_note(debit_note):
        """
        Post a Vendor Debit Note to the GL.

        Creates journal entry for:
        - Expense/Inventory (debit) — additional charge
        - Accounts Payable (credit) — increases what we owe vendor

        Args:
            debit_note: VendorDebitNote instance

        Returns:
            JournalHeader: The created journal entry
        """
        if debit_note.status not in ['Approved', 'Posted']:
            raise TransactionPostingError(f"Debit note must be Approved, got {debit_note.status}")

        ap_account = Account.objects.filter(
            account_type='Liability',
            name__icontains='Payable'
        ).first()

        if not ap_account:
            raise TransactionPostingError("No Accounts Payable account found")

        journal = JournalHeader.objects.create(
            posting_date=debit_note.debit_note_date,
            description=f"Vendor Debit Note {debit_note.debit_note_number} - {debit_note.vendor.name}",
            reference_number=debit_note.debit_note_number,
            status='Posted',
            source_module='procurement',
            source_document_id=debit_note.pk,
            posted_at=timezone.now(),
        )

        total_amount = debit_note.total_amount

        # Debit Expense/Inventory account
        expense_account = None
        if debit_note.purchase_order:
            for line in debit_note.purchase_order.lines.all():
                if line.item and line.item.expense_account:
                    expense_account = line.item.expense_account
                    break
                if line.product_type and line.product_type.expense_account:
                    expense_account = line.product_type.expense_account
                    break

        if not expense_account:
            expense_account = Account.objects.filter(
                account_type='Expense',
                name__icontains='Purchase'
            ).first() or Account.objects.filter(
                account_type='Asset',
                name__icontains='Inventory'
            ).first()

        if expense_account:
            JournalLine.objects.create(
                header=journal,
                account=expense_account,
                debit=total_amount,
                credit=Decimal('0.00'),
                memo=f"Debit Note {debit_note.debit_note_number}"
            )

        # Credit AP (increase payable)
        JournalLine.objects.create(
            header=journal,
            account=ap_account,
            debit=Decimal('0.00'),
            credit=total_amount,
            memo=f"AP from Debit Note {debit_note.debit_note_number}"
        )

        # Update vendor balance (atomic F()-based — increase what we owe)
        if hasattr(debit_note, 'vendor') and debit_note.vendor:
            from django.db.models import F
            type(debit_note.vendor).objects.filter(pk=debit_note.vendor.pk).update(
                balance=F('balance') + total_amount
            )

        ProcurementPostingService._validate_journal_balanced(journal)
        ProcurementPostingService._update_gl_balances(journal)
        return journal
