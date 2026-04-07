# DTSG ERP - Comprehensive Accounting Implementation Plan

## Executive Summary

This document outlines the comprehensive implementation plan for all missing accounting features in the DTSG ERP system. The plan addresses critical financial controls, tax compliance (FIRS/NDIC), and professional accounting requirements under IFRS/IAS standards.

---

## Critical Distinction: Asset Revaluation vs Currency Revaluation

### Currency Revaluation (ALREADY IMPLEMENTED)
| Aspect | Details |
|--------|---------|
| **Purpose** | Adjust monetary items (cash, AR, AP, loans) denominated in foreign currency |
| **Basis** | Change in EXCHANGE RATES |
| **Accounting** | P&L impact - FX Gain/Loss |
| **Accounts Used** | 7100 Unrealized FX Gain, 8100 Unrealized FX Loss |
| **Standard** | IAS 21 - Effects of Changes in Foreign Exchange Rates |
| **Model** | `CurrencyRevaluationRun`, `CurrencyRevaluationDetail` |
| **Service** | `CurrencyRevaluationService` |

### Asset Revaluation (NEEDS IMPLEMENTATION)
| Aspect | Details |
|--------|---------|
| **Purpose** | Adjust NON-MONETARY assets (PPE, intangibles) to fair value |
| **Basis** | Change in FAIR VALUE of asset |
| **Accounting** | Equity impact - Revaluation Surplus |
| **Accounts Used** | Asset Cost/Accum Depr accounts, 3100 Revaluation Surplus |
| **Standard** | IAS 16 - Property, Plant and Equipment |
| **Model** | `AssetRevaluation`, `AssetRevaluationDetail` (TO BE CREATED) |
| **Service** | `AssetRevaluationService` (TO BE CREATED) |

---

## Implementation Phases

### Phase 1: Tax & Regulatory Foundation (Critical)
**Priority: CRITICAL | Timeline: Week 1-2**

| Feature | Description | Files to Create/Modify |
|---------|-------------|------------------------|
| TaxRate Model | VAT rates configuration | `accounting/models.py` |
| TaxCode Model | Tax codes for transactions | `accounting/models.py` |
| TaxCalculationService Enhancement | VAT/WHT auto-calculation | `accounting/services/tax_calculation.py` |
| VATReturns Model | VAT return submissions | `accounting/models.py` |
| VATReturnService | Generate VAT returns | `accounting/services/vat_returns.py` |
| WHTCertificate Model | WHT certificate records | `accounting/models.py` |
| WHTCertificateService | Generate WHT certificates | `accounting/services/wht_certificates.py` |

### Phase 2: Core Financial Controls (Critical)
**Priority: CRITICAL | Timeline: Week 2-3**

| Feature | Description | Files to Create/Modify |
|---------|-------------|------------------------|
| Trial Balance Service | Generate trial balance | `accounting/services/trial_balance.py` |
| Period Closing Service | Period-end closing workflow | `accounting/services/period_closing.py` |
| Year-End Closing Service | Annual closing entries | `accounting/services/year_end_closing.py` |
| SuspenseAccount Handling | Suspense clearing | `accounting/services/suspense_accounting.py` |
| JournalReversal Model | Reversal tracking | `accounting/models.py` |

### Phase 3: Banking & Cash Management (High)
**Priority: HIGH | Timeline: Week 3-4**

| Feature | Description | Files to Create/Modify |
|---------|-------------|------------------------|
| PettyCashVoucher Model | Petty cash vouchers | `accounting/models.py` |
| PettyCashReplenishment Model | Float replenishment | `accounting/models.py` |
| PettyCashService | Petty cash operations | `accounting/services/petty_cash.py` |
| ChequeRegister Model | Cheque tracking | `accounting/models.py` |
| ChequeService | Cheque management | `accounting/services/cheque_management.py` |
| PaymentVoucher Model | Payment authorization | `accounting/models.py` |
| PaymentVoucherService | Payment workflow | `accounting/services/payment_voucher.py` |
| CashFlowStatementService | Indirect method cash flow | `accounting/services/cashflow_statement.py` |
| CashFlowForecastService | Cash forecasting | `accounting/services/cashflow_forecast.py` |

### Phase 4: Fixed Assets (High)
**Priority: HIGH | Timeline: Week 4-5**

| Feature | Description | Files to Create/Modify |
|---------|-------------|------------------------|
| AssetRevaluation Model | Asset revaluation records | `accounting/models.py` |
| AssetRevaluationDetail Model | Per-asset revaluation | `accounting/models.py` |
| AssetRevaluationService | IAS 16 revaluation | `accounting/services/asset_revaluation.py` |
| AssetDisposal Model | Disposal transactions | `accounting/models.py` |
| AssetDisposalService | Gain/loss calculation | `accounting/services/asset_disposal.py` |
| AssetImpairment Model | Impairment records | `accounting/models.py` |
| AssetImpairmentService | IAS 36 impairment | `accounting/services/asset_impairment.py` |
| LeaseAsset Model | IFRS 16 ROU assets | `accounting/models.py` |
| LeaseAssetService | Lease accounting | `accounting/services/lease_accounting.py` |
| CapitalWorkInProgress Model | CWIP tracking | `accounting/models.py` |
| AssetInsurance Model | Insurance tracking | `accounting/models.py` |

### Phase 5: Receivables & Payables (High)
**Priority: HIGH | Timeline: Week 5-6**

| Feature | Description | Files to Create/Modify |
|---------|-------------|------------------------|
| CreditNote Model | AR credit notes | `accounting/models.py` |
| DebitNote Model | AP debit notes | `accounting/models.py` |
| CreditNoteService | Credit note operations | `accounting/services/credit_notes.py` |
| AgingReportService | AR/AP aging | `accounting/services/aging_reports.py` |
| BadDebtProvision Model | Provision records | `accounting/models.py` |
| BadDebtProvisionService | IFRS 9 provisioning | `accounting/services/bad_debt_provision.py` |
| CollectionLetter Model | Collection templates | `accounting/models.py` |
| LatePaymentInterest Service | Interest calculation | `accounting/services/late_payment.py` |

### Phase 6: Budgeting & Cost Management (Medium)
**Priority: MEDIUM | Timeline: Week 6-7**

| Feature | Description | Files to Create/Modify |
|---------|-------------|------------------------|
| BudgetVarianceService | Budget vs Actual | `accounting/services/budget_variance.py` |
| BudgetRevision Model | Budget amendments | `accounting/services/budget_revision.py` |
| ActivityBasedCosting Model | ABC definitions | `accounting/models.py` |
| ActivityBasedCostingService | ABC calculations | `accounting/services/abc.py` |
| CapexTracking Model | Capex vs Opex | `accounting/models.py` |

### Phase 7: Financial Reporting (High)
**Priority: HIGH | Timeline: Week 7-8**

| Feature | Description | Files to Create/Modify |
|---------|-------------|------------------------|
| GeneralLedgerService | GL detail report | `accounting/services/general_ledger.py` |
| SubLedgerService | Sub-ledger reports | `accounting/services/sub_ledger.py` |
| CashBookService | Cash receipts/payments | `accounting/services/cash_book.py` |
| VATAccountReport Service | VAT ledger | `accounting/services/vat_account.py` |
| WHTAccountReport Service | WHT ledger | `accounting/services/wht_account.py` |
| RatioAnalysisService | Financial ratios | `accounting/services/ratio_analysis.py` |
| CommonSizeAnalysis Service | Common size statements | `accounting/services/common_size.py` |
| ManagementAccounts Service | Internal reporting | `accounting/services/management_accounts.py` |
| DashboardKPIService | Executive dashboard | `accounting/services/dashboard_kpi.py` |

### Phase 8: HMO-Specific Features (Medium)
**Priority: MEDIUM | Timeline: Week 8-9**

| Feature | Description | Files to Create/Modify |
|---------|-------------|------------------------|
| PremiumReceipt Model | Premium tracking | `accounting/models.py` |
| CapitationRegister Model | Per-capita records | `accounting/models.py` |
| ClaimsCostAnalysis Service | Claims analysis | `accounting/services/claims_analysis.py` |
| ProviderSettlement Model | Provider payments | `accounting/models.py` |
| IBNRReserve Model | IFRS 17 reserves | `accounting/models.py` |
| ReinsuranceAccounting Model | Reinsurance records | `accounting/models.py` |

---

## Implementation Summary

### Models to Create (Total: 35+)

```
accounting/models.py additions:
├── TaxRate
├── TaxCode
├── VATReturn
├── VATReturnDetail
├── WHTCertificate
├── WHTCertificateDetail
├── PettyCashVoucher
├── PettyCashReplenishment
├── ChequeRegister
├── PaymentVoucher
├── JournalReversal
├── AssetRevaluation
├── AssetRevaluationDetail
├── AssetDisposal
├── AssetImpairment
├── LeaseAsset
├── LeasePayment
├── CapitalWorkInProgress
├── AssetInsurance
├── CreditNote
├── DebitNote
├── BadDebtProvision
├── CollectionLetter
├── PremiumReceipt
├── CapitationRegister
├── ClaimsReserve (IBNR)
├── ReinsuranceEntry
└── SuspenseClearing
```

### Services to Create (Total: 25+)

```
accounting/services/
├── tax_calculation.py (ENHANCE)
├── vat_returns.py (NEW)
├── wht_certificates.py (NEW)
├── trial_balance.py (NEW)
├── period_closing.py (NEW)
├── year_end_closing.py (NEW)
├── suspense_accounting.py (NEW)
├── petty_cash.py (NEW)
├── cheque_management.py (NEW)
├── payment_voucher.py (NEW)
├── cashflow_statement.py (NEW)
├── cashflow_forecast.py (NEW)
├── asset_revaluation.py (NEW) <-- DIFFERENT from currency_revaluation
├── asset_disposal.py (NEW)
├── asset_impairment.py (NEW)
├── lease_accounting.py (NEW)
├── aging_reports.py (NEW)
├── credit_notes.py (NEW)
├── bad_debt_provision.py (NEW)
├── budget_variance.py (NEW)
├── general_ledger.py (NEW)
├── sub_ledger.py (NEW)
├── cash_book.py (NEW)
├── vat_account.py (NEW)
├── wht_account.py (NEW)
├── ratio_analysis.py (NEW)
└── dashboard_kpi.py (NEW)
```

---

## Nigerian Regulatory Compliance

### FIRS Requirements
- VAT Returns (Form VAT 1/2/3)
- Withholding Tax Certificates (Form WHT 1A)
- Tax Clearance Certificate applications
- e-Tax filing preparation

### CBN Requirements
- Bank Reconciliation
- Cash Flow Statement
- Exchange gain/loss handling

### NDPR Compliance
- Data audit trails
- Consent logging
- Data retention policies

---

## IFRS Standards Covered

| Standard | Feature |
|----------|---------|
| IAS 1 | Presentation of Financial Statements |
| IAS 2 | Inventories |
| IAS 7 | Statement of Cash Flows |
| IAS 8 | Accounting Policies, Changes |
| IAS 12 | Income Taxes |
| IAS 16 | Property, Plant and Equipment |
| IAS 17 | Leases (superseded by IFRS 16) |
| IAS 21 | Foreign Currency |
| IAS 23 | Borrowing Costs |
| IAS 36 | Impairment of Assets |
| IFRS 9 | Financial Instruments |
| IFRS 15 | Revenue |
| IFRS 16 | Leases |
| IFRS 17 | Insurance Contracts |

---

## Risk Assessment

| Risk | Mitigation |
|------|------------|
| Data Integrity | All changes logged via AuditTrailService |
| Regulatory Non-compliance | FIRS-aligned tax calculations |
| Financial Errors | Journal validation before posting |
| Audit Failures | Comprehensive audit trail |
| Fraud | Dual control and approval workflows |

---

## Next Steps

1. Implement Phase 1 (Tax Foundation) immediately
2. Implement Phase 2 (Core Controls) in parallel
3. Continue through remaining phases
4. Test each module thoroughly
5. Create API endpoints for all services
6. Build frontend components

---

*Document Version: 1.0*
*Last Updated: March 2026*
*Prepared by: DTSG ERP Implementation Team*
