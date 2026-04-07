# DTSG ERP Production Readiness Plan

**Project:** DTSG ERP - Government & Public/Private Sector Financial System  
**Prepared for:** Financial Planning, Product Ownership & Implementation  
**Date:** March 2026

---

## Executive Summary

This comprehensive plan addresses all gaps identified for production deployment of the DTSG ERP system. The plan is organized into **7 major workstreams** with **32 specific deliverables** across testing, reporting, integrations, and operational readiness.

**Total Estimated Timeline:** 16-20 weeks  
**Team Composition Required:** 4-6 developers + 1 product owner + 1 QA engineer

---

## Workstream 1: Test Coverage & Quality Assurance

### Objective
Achieve 70%+ test coverage on core financial logic before production deployment.

### 1.1 Unit Tests for Core Financial Modules

| Test Suite | Models/Logic to Cover | Priority |
|------------|----------------------|----------|
| **Budget Tests** | UnifiedBudget creation, allocation calculations, encumbrance tracking, variance computation, amendment workflows, budget availability checks | P1 |
| **Accounting Tests** | Journal entry validation, GL balance updates, trial balance calculation, account reconciliation | P1 |
| **Procurement Tests** | PO creation, 3-way matching, GRN generation, invoice matching | P1 |
| **Inventory Tests** | Stock movements, valuation (FIFO/WA), reorder alerts, batch tracking | P1 |
| **Sales Tests** | Invoice generation, receipt allocation, credit limit checks | P1 |
| **HRM Tests** | Payroll calculations, compliance task assignments | P2 |

#### Deliverables
- [ ] `budget/tests.py` - 25+ test cases covering budget lifecycle
- [ ] `accounting/tests.py` - 30+ test cases for journal & GL operations
- [ ] `procurement/tests.py` - 15+ test cases for procurement workflow
- [ ] `inventory/tests.py` - 15+ test cases for inventory operations
- [ ] `sales/tests.py` - 15+ test cases for sales/receivables
- [ ] `hrm/tests.py` - 10+ test cases for payroll

#### Implementation Notes
```python
# Example test structure for Budget
class UnifiedBudgetTestCase(TestCase):
    def setUp(self):
        self.fiscal_year = FiscalPeriod.objects.create(year=2026)
        self.mda = MDA.objects.create(code='001', name='Ministry of Finance')
        self.account = Account.objects.create(code='50100000', name='Travel Expense')
        
    def test_budget_creation(self):
        budget = UnifiedBudget.objects.create(
            budget_code='2026-001',
            fiscal_year='2026',
            mda=self.mda,
            account=self.account,
            original_amount=1000000,
            status='APPROVED'
        )
        self.assertEqual(budget.allocated_amount, 1000000)
        
    def test_encumbrance_tracking(self):
        # Test PO commitment reduces available budget
        pass
        
    def test_variance_calculation(self):
        # Test period/YTD variance computation
        pass
```

---

### 1.2 Integration Tests

| Test Scenario | Description | Priority |
|---------------|-------------|----------|
| **Budget-PO Integration** | Creating PO should create encumbrance; receiving should liquidate | P1 |
| **Invoice-Payment Flow** | Invoice → Receipt → Allocation → GL update | P1 |
| **Procurement-GRN Flow** | PR → PO → GRN → Invoice → Payment | P1 |
| **Multi-period Closing** | Test period transitions and balance carry-forward | P1 |
| **Multi-tenant Isolation** | Verify tenant data separation | P1 |

#### Deliverables
- [ ] `tests/integration/test_budget_po_flow.py`
- [ ] `tests/integration/test_invoice_payment_flow.py`
- [ ] `tests/integration/test_procurement_flow.py`
- [ ] `tests/integration/test_period_closing.py`

---

### 1.3 End-to-End User Workflow Tests

| Workflow | Description | Priority |
|----------|-------------|----------|
| **Budget Approval Workflow** | Create budget → Submit → Approve → Close | P1 |
| **Procurement Cycle** | Create PR → Approve → Convert to PO → Receive → Match Invoice → Pay | P1 |
| **Sales Cycle** | Create Quote → Sales Order → Invoice → Receive Payment | P1 |
| **Month-End Close** | Generate reports → Validate → Close period | P1 |

#### Deliverables
- [ ] `tests/e2e/test_budget_approval_workflow.py`
- [ ] `tests/e2e/test_procurement_complete_flow.py`
- [ ] `tests/e2e/test_sales_complete_flow.py`
- [ ] `tests/e2e/test_month_end_close.py`

---

## Workstream 2: Government & Public Sector Reports

### Objective
Implement IPSAS-compliant and government-specific financial reporting required for public sector deployments.

### 2.1 IPSAS-Compliant Financial Statements

| Report | Description | Deliverable |
|--------|-------------|-------------|
| **IPSAS Balance Sheet** | Statement of Financial Position with public sector assets | `accounting/reports/ipsas_balance_sheet.py` |
| **IPSAS Operating Statement** | Revenue/Expense recognition (IPSAS accrual basis) | `accounting/reports/ipsas_operating_statement.py` |
| **IPSAS Cash Flow** | Cash flow from operating, investing, financing activities | `accounting/reports/ipsas_cash_flow.py` |
| **IPSAS Statement of Changes in Net Assets** | Equity changes, donor contributions | `accounting/reports/ipsas_net_assets.py` |
| **Notes to Financial Statements** | Disclosures and accounting policies | `accounting/reports/ipsas_notes.py` |

#### Deliverables
- [ ] Implement `IPSASReportService` class
- [ ] Add IPSAS report endpoints to API
- [ ] Create report templates for PDF export
- [ ] Add unit tests for IPSAS calculations

#### Implementation Structure
```python
# accounting/reports/ipsas_balance_sheet.py
class IPSASBalanceSheetService:
    """
    Generates IPSAS-compliant Statement of Financial Position
    Includes:
    - Current assets (cash, receivables, inventory)
    - Non-current assets (fixed assets, intangible assets)
    - Current liabilities (payables, provisions)
    - Non-current liabilities (loans, deferred revenue)
    - Net assets/equity
    """
    
    def generate(self, tenant_id, fiscal_year, period_end):
        # Implementation
        pass
```

---

### 2.2 MDA (Ministries/Departments/Agencies) Reports

| Report | Description | Priority |
|--------|-------------|----------|
| **MDA Expenditure Report** | Expenditure by ministry with budget vs actual | P1 |
| **MDA Budget Implementation** | Quarterly budget utilization by MDA | P1 |
| **MDA Payroll Summary** | Personnel costs by ministry | P1 |
| **MDA Asset Register** | Fixed assets owned by each MDA | P2 |
| **Inter-MDA Transfers** | Transfers between MDAs | P2 |

#### Deliverables
- [ ] `accounting/reports/mda_expenditure.py`
- [ ] `accounting/reports/mda_budget_implementation.py`
- [ ] `accounting/reports/mda_payroll_summary.py`
- [ ] Add MDA dimension to all expenditure queries

---

### 2.3 Fund & Treasury Reports

| Report | Description | Priority |
|--------|-------------|----------|
| **Fund Balance Report** | Balances across all funds (recurrent, capital, donor) | P1 |
| **Treasury Single Account (TSA) Report** | Consolidated government cash position | P1 |
| **Donor Fund Tracker** | Tracking donor-funded project expenditures | P1 |
| **Appropriation Account** | Budget vs actual by appropriation line | P1 |

#### Deliverables
- [ ] `accounting/reports/fund_balance.py`
- [ ] `accounting/reports/treasury_report.py`
- [ ] `accounting/reports/donor_fund_tracker.py`
- [ ] `accounting/reports/appropriation_account.py`

---

### 2.4 Budget Implementation Reports

| Report | Description | Priority |
|--------|-------------|----------|
| **Budget Variance Analysis** | Monthly/quarterly variance by MDA/cost center | P1 |
| **Budget Forecast** | Year-end projection based on burn rate | P1 |
| **Encumbrance Summary** | Outstanding commitments | P1 |
| **Supplemental Budget Report** | Additional allocations/virements | P2 |

#### Deliverables
- [ ] `budget/reports/variance_analysis.py`
- [ ] `budget/reports/budget_forecast.py`
- [ ] `budget/reports/encumbrance_summary.py`

---

## Workstream 3: Statutory & Compliance Reports

### Objective
Implement statutory reporting required for government and private sector compliance.

### 3.1 Tax Reports

| Report | Description | Deliverable |
|--------|-------------|-------------|
| **VAT Returns** | Output/input tax with net payable | `accounting/reports/vat_return.py` |
| **Withholding Tax Report** | Tax deducted at source | `accounting/reports/withholding_tax.py` |
| **PAYE Summary** | Pay-as-you-earn deductions | `hrm/reports/paye_report.py` |
| **Tax Certificate** | Annual tax certificates for vendors/employees | `accounting/reports/tax_certificate.py` |

#### Deliverables
- [ ] `accounting/reports/vat_return.py`
- [ ] `accounting/reports/withholding_tax.py`
- [ ] `hrm/reports/paye_report.py`
- [ ] Add tax configuration to settings (tax rates per jurisdiction)

---

### 3.2 Payroll & HR Reports

| Report | Description | Priority |
|--------|-------------|----------|
| **Payroll Register** | All employees with earnings/deductions | P1 |
| **Payslips** | Individual employee payslips | P1 |
| **P9 Form Equivalent** | Annual tax deduction summary | P1 |
| **Leave Report** | Employee leave balances and usage | P2 |
| **Staff Count Report** | Headcount by department/MDA | P2 |

#### Deliverables
- [ ] `hrm/reports/payroll_register.py`
- [ ] `hrm/reports/payslip_generator.py`
- [ ] `hrm/reports/annual_tax_summary.py`
- [ ] `hrm/reports/leave_report.py`

---

### 3.3 Audit & Compliance Reports

| Report | Description | Priority |
|--------|-------------|----------|
| **Audit Trail Report** | All transactions with user/timestamp | P1 |
| **Compliance Status Report** | Outstanding compliance tasks | P1 |
| **Period Closing Checklist** | Pre-closing validation checks | P1 |
| **User Activity Report** | Login history, actions by user | P2 |

#### Deliverables
- [ ] `core/reports/audit_trail_report.py`
- [ ] `hrm/reports/compliance_status.py`
- [ ] `accounting/reports/period_closing_checklist.py`
- [ ] `core/reports/user_activity.py`

---

### 3.4 Regulatory Reports

| Report | Description | Priority |
|--------|-------------|----------|
| **Annual Financial Statements** | Full annual report for auditors | P1 |
| **Management Accounts** | Monthly management information pack | P1 |
| **Bank Reconciliation Statement** | Bank-to-book reconciliation | P1 |

#### Deliverables
- [ ] `accounting/reports/annual_statements.py`
- [ ] `accounting/reports/management_accounts.py`
- [ ] `accounting/reports/bank_reconciliation_statement.py`

---

## Workstream 4: Integration Points

### Objective
Enable connectivity with external systems required for end-to-end financial operations.

### 4.1 Banking Integration

| Feature | Description | Priority |
|---------|-------------|----------|
| **Bank Statement Import** | Import OFX/CAMT/CSV statements | P1 |
| **Auto-Reconciliation** | Match bank transactions to GL | P1 |
| **Payment File Export** | Generate payment files for batch payments | P2 |
| **Bank API Integration** | Real-time balance fetch (optional) | P3 |

#### Deliverables
- [ ] `accounting/integrations/bank_statement_parser.py`
- [ ] `accounting/integrations/auto_reconciliation.py`
- [ ] `accounting/integrations/payment_file_generator.py`

#### Implementation Notes
```python
# accounting/integrations/bank_statement_parser.py
class BankStatementParser:
    """Parse bank statements from various formats"""
    
    SUPPORTED_FORMATS = ['OFX', 'CAMT.053', 'CSV', 'MT940']
    
    def parse(self, file_content, format_type):
        if format_type == 'CAMT.053':
            return self.parse_camt(file_content)
        elif format_type == 'CSV':
            return self.parse_csv(file_content)
        # etc.
```

---

### 4.2 Payment Gateway Integration

| Feature | Description | Priority |
|---------|-------------|----------|
| **Payment Link Generation** | Create payment links for invoices | P2 |
| **Webhook Handler** | Receive payment notifications | P2 |
| **Receipt Generation** | Auto-generate receipt on payment | P2 |

#### Deliverables
- [ ] `accounting/integrations/payment_gateway.py`
- [ ] `accounting/integrations/webhook_handler.py`
- [ ] API endpoints for payment link creation

---

### 4.3 Notification System

| Feature | Description | Priority |
|---------|-------------|----------|
| **Email Notifications** | Transaction alerts, approval requests | P1 |
| **In-App Notifications** | Dashboard notifications | P1 |
| **SMS Notifications** (optional) | Critical alerts via SMS | P3 |

#### Deliverables
- [ ] `core/notifications/email_service.py`
- [ ] `core/notifications/in_app_notifications.py`
- [ ] Notification templates for key events

---

### 4.4 Webhook & API Framework

| Feature | Description | Priority |
|---------|-------------|----------|
| **Webhook Configuration** | Define outbound webhooks | P2 |
| **Event Triggers** | Fire webhooks on key events | P2 |
| **REST API Documentation** | OpenAPI/Swagger docs | P2 |

#### Deliverables
- [ ] `core/integrations/webhook_service.py`
- [ ] `core/integrations/event_registry.py`
- [ ] OpenAPI schema generation

---

### 4.5 Data Export

| Feature | Description | Priority |
|---------|-------------|----------|
| **Excel Export** | Export reports to Excel with formatting | P1 |
| **CSV Export** | Raw data export | P1 |
| **PDF Generation** | Branded PDF reports | P2 |

#### Deliverables
- [ ] `core/utils/excel_export.py`
- [ ] `core/utils/csv_export.py`
- [ ] `core/utils/pdf_generator.py`

---

## Workstream 5: Dashboard & Analytics

### Objective
Provide real-time visibility into organizational financial health.

### 5.1 Executive Dashboard

| KPI | Description | Data Source |
|-----|-------------|-------------|
| **Total Revenue** | YTD revenue vs budget | GL + Budget |
| **Total Expenditure** | YTD spending vs budget | GL + Budget |
| **Cash Position** | Current bank balances | Bank Accounts |
| **Budget Utilization** | % of budget consumed | Budget |
| **Outstanding Payables** | AP aging | Vendor Invoices |
| **Outstanding Receivables** | AR aging | Customer Invoices |

#### Deliverables
- [ ] `core/dashboard/executive_dashboard.py`
- [ ] Dashboard API endpoint
- [ ] Frontend dashboard component

---

### 5.2 Budget Dashboard

| View | Description |
|------|-------------|
| **Budget Overview** | All budgets with status, allocated, spent |
| **Budget Heat Map** | Visual by MDA/department |
| **Variance Alerts** | Budgets exceeding thresholds |
| **Forecast View** | Projected year-end position |

#### Deliverables
- [ ] `budget/dashboard/budget_overview.py`
- [ ] `budget/dashboard/variance_alerts.py`

---

### 5.3 Operational Dashboards

| Dashboard | Description |
|-----------|-------------|
| **Procurement Dashboard** | PO status, pending approvals, vendor performance |
| **Inventory Dashboard** | Stock levels, slow-moving items, reorder alerts |
| **Sales Dashboard** | Pipeline, conversions, revenue by product/customer |

#### Deliverables
- [ ] `procurement/dashboard/procurement_dashboard.py`
- [ ] `inventory/dashboard/inventory_dashboard.py`
- [ ] `sales/dashboard/sales_dashboard.py`

---

## Workstream 6: Operational Workflows

### Objective
Automate period-end closing and approval processes.

### 6.1 Period-End Closing Workflow

| Step | Description | Automated |
|------|-------------|-----------|
| 1 | Lock period for transactions | Yes |
| 2 | Run preliminary validation checks | Yes |
| 3 | Generate preliminary reports | Yes |
| 4 | Review and approve | Manual |
| 5 | Run accruals/reversals | Yes |
| 6 | Generate final reports | Yes |
| 7 | Archive period | Yes |

#### Deliverables
- [ ] `accounting/workflows/period_close_service.py`
- [ ] API endpoint to initiate period close
- [ ] Validation check framework
- [ ] Period close audit trail

---

### 6.2 Budget Amendment Workflow

| Step | Description |
|------|-------------|
| 1 | Create amendment request |
| 2 | Submit for approval (multi-level) |
| 3 | Approve/reject with comments |
| 4 | On approval, update budget amounts |
| 5 | Log amendment for audit |

#### Deliverables
- [ ] Integrate with existing `workflow` module
- [ ] Amendment approval endpoints
- [ ] Amendment audit trail

---

### 6.3 Document Management

| Feature | Description | Priority |
|---------|-------------|----------|
| **Invoice Attachments** | Attach supporting docs to invoices | P1 |
| **Contract Management** | Link contracts to vendors/POs | P2 |
| **Document Search** | Find documents by type/date/vendor | P2 |

#### Deliverables
- [ ] `core/models/document.py`
- [ ] File upload/download endpoints
- [ ] Document linking to transactions

---

## Workstream 7: Technical Production Readiness

### Objective
Ensure the system is production-hardened for secure, reliable operation.

### 7.1 Production Configuration

| Item | Current State | Required |
|------|---------------|----------|
| **DEBUG** | Environment-based | Must be False in production |
| **ALLOWED_HOSTS** | localhost only | Configure domain names |
| **SECURE_SSL_REDIRECT** | Conditional | Always True in production |
| **Database** | PostgreSQL | Add connection pooling |
| **Static Files** | Local | Configure CDN or S3 |

#### Deliverables
- [ ] Production `settings_production.py` file
- [ ] Environment configuration documentation
- [ ] Deployment checklist

---

### 7.2 Caching & Performance

| Item | Current | Required |
|------|---------|----------|
| **Cache** | LocMem | Redis |
| **Session** | Database | Redis |
| **Celery** | Not configured | Add for async tasks |

#### Deliverables
- [ ] `settings_production.py` with Redis config
- [ ] Celery configuration
- [ ] Async task definitions (report generation, notifications)

---

### 7.3 Logging & Monitoring

| Item | Description | Deliverable |
|------|-------------|-------------|
| **Log Rotation** | Daily rotating logs | `settings_production.py` |
| **Error Tracking** | Sentry or similar | Integration |
| **Health Checks** | /health endpoint | `core/views/health.py` |
| **Metrics** | Prometheus metrics | Integration |

#### Deliverables
- [ ] Configure `logging` for production (file + syslog)
- [ ] `/api/health/` endpoint
- [ ] Error tracking setup

---

### 7.4 Backup & Disaster Recovery

| Item | Description |
|------|-------------|
| **Database Backup** | Daily automated backups |
| **Backup Restoration** | Tested restoration procedure |
| **Failover** | High availability setup |

#### Deliverables
- [ ] Backup script documentation
- [ ] Disaster recovery runbook
- [ ] RTO/RPO targets defined

---

### 7.5 Security Hardening

| Item | Description |
|------|-------------|
| **Password Policy** | Enforce strong passwords |
| **Session Management** | Configurable session timeout |
| **API Rate Limiting** | Per-endpoint rate limits |
| **Audit Logging** | Enhanced audit for sensitive operations |

#### Deliverables
- [ ] Update password validators in settings
- [ ] Session configuration
- [ ] Enhanced rate limiting rules

---

## Implementation Timeline

### Phase 1: Foundation (Weeks 1-4)
- [ ] Unit tests for budget and accounting (P1)
- [ ] Integration tests for key flows (P1)
- [ ] Production settings configuration
- [ ] Health check endpoints

### Phase 2: Reports (Weeks 5-10)
- [ ] IPSAS financial statements
- [ ] MDA expenditure reports
- [ ] Tax reports (VAT, PAYE)
- [ ] Audit trail reports

### Phase 3: Integrations (Weeks 11-14)
- [ ] Bank statement import & reconciliation
- [ ] Email notification system
- [ ] Data export utilities

### Phase 4: Dashboard & Automation (Weeks 15-18)
- [ ] Executive dashboard
- [ ] Period-end closing workflow
- [ ] Budget amendment workflow

### Phase 5: Production Prep (Weeks 19-20)
- [ ] Performance testing
- [ ] Security audit
- [ ] Documentation
- [ ] Go-live checklist

---

## Resource Requirements

| Role | Quantity | Duration |
|------|----------|----------|
| Senior Django Developer | 2 | Full timeline |
| Python Developer | 2 | Full timeline |
| QA Engineer | 1 | Phase 1-4 |
| Product Owner | 1 | Throughout |
| DevOps/Technical Lead | 0.5 | Phase 1, 5 |

---

## Success Criteria

1. **Test Coverage**: 70%+ on core financial modules
2. **Reports**: All statutory and management reports implemented
3. **Integrations**: Bank reconciliation and notifications functional
4. **Dashboard**: Executive and operational dashboards live
5. **Production Ready**: All security and deployment configurations complete
6. **Documentation**: User guides and technical documentation delivered

---

## Risk Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| Scope creep | High | Strict prioritization, phase gates |
| Test complexity | Medium | Start with critical paths first |
| Integration challenges | Medium | Build adapters with clear interfaces |
| Timeline delays | Medium | Buffer in each phase, parallel workstreams |

---

## Appendix: File Structure After Implementation

```
dtsg_erp/
├── accounting/
│   ├── reports/
│   │   ├── __init__.py
│   │   ├── ipsas_balance_sheet.py
│   │   ├── ipsas_operating_statement.py
│   │   ├── ipsas_cash_flow.py
│   │   ├── mda_expenditure.py
│   │   ├── fund_balance.py
│   │   ├── treasury_report.py
│   │   ├── vat_return.py
│   │   ├── withholding_tax.py
│   │   ├── bank_reconciliation.py
│   │   └── period_closing.py
│   ├── integrations/
│   │   ├── bank_statement_parser.py
│   │   ├── auto_reconciliation.py
│   │   ├── payment_gateway.py
│   │   └── webhook_handler.py
│   └── workflows/
│       └── period_close_service.py
├── budget/
│   ├── reports/
│   │   ├── variance_analysis.py
│   │   ├── budget_forecast.py
│   │   └── encumbrance_summary.py
│   └── dashboard/
│       ├── budget_overview.py
│       └── variance_alerts.py
├── hrm/
│   ├── reports/
│   │   ├── payroll_register.py
│   │   ├── payslip_generator.py
│   │   ├── annual_tax_summary.py
│   │   └── leave_report.py
├── core/
│   ├── reports/
│   │   ├── audit_trail.py
│   │   └── user_activity.py
│   ├── dashboard/
│   │   └── executive_dashboard.py
│   ├── notifications/
│   │   ├── email_service.py
│   │   └── in_app_notifications.py
│   ├── integrations/
│   │   └── webhook_service.py
│   └── utils/
│       ├── excel_export.py
│       ├── csv_export.py
│       └── pdf_generator.py
├── tests/
│   ├── __init__.py
│   ├── integration/
│   │   ├── __init__.py
│   │   ├── test_budget_po_flow.py
│   │   ├── test_invoice_payment_flow.py
│   │   ├── test_procurement_flow.py
│   │   └── test_period_closing.py
│   └── e2e/
│       ├── __init__.py
│       ├── test_budget_approval_workflow.py
│       ├── test_procurement_complete_flow.py
│       ├── test_sales_complete_flow.py
│       └── test_month_end_close.py
└── dtsg_erp/
    └── settings_production.py
```

---

*Document Version: 1.0*  
*Next Review: After Phase 1 completion*
