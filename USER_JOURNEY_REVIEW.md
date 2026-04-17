# QUOT ERP - Complete User Journey & Business Process Review

**Date:** March 26, 2026  
**Version:** 1.0  
**Prepared by:** System Review

---

## Executive Summary

This document maps the complete business processes through the QUOT ERP system from end-to-end, identifying gaps, missing integrations, and recommendations for production readiness.

---

## MODULE 1: PROCUREMENT TO PAYMENT (P2P)

### Complete User Journey

```
[1. USER ACTION]                    [2. SYSTEM RESPONSE]              [3. VALIDATION]
───────────────────────────────────────────────────────────────────────────────────────
PR Creation                         → PR Number Generated               → Budget Check
   ↓                                  (Auto: PR-YYYY-NNNN)                 (Available/Exceeded)
   ↓                                  ↓                                    ↓
Submit PR                       → Approval Request Created           → Workflow Routing
   ↓                                  ↓                                    → Amount-based routing
   ↓                                  ↓                                    → Delegation check
Approve PR                       → Status: Approved                  → Budget Encumbered
   ↓                                  ↓                                    (Not implemented)
   ↓                                  ↓                                    
Create PO                       → PO Number Generated                → PR Linkage
   ↓                                  (Auto: PO-YYYY-NNNN)                 (Optional - no validation)
   ↓                                  ↓                                    ↓
Submit PO                       → Approval Request                   → Vendor Active Check
   ↓                                  ↓                                    
Approve PO                       → Status: Approved                  → Budget Encumbrance Created
   ↓                                  ↓                                    ↓
Post PO                          → GL Journal Created                → Inventory Update
   ↓                                  (Encumbrance entry)                   (Not updated)
   ↓                                  ↓                                    
Create GRN                     → GRN Number Generated              → PO Line Qty Check
   ↓                                  (Auto: GRN-YYYY-NNNN)                 (Partial allowed)
   ↓                                  ↓                                    ↓
Post GRN                          → Stock Updated                     → Quality Trigger
   ↓                                  (Material received)                   (Optional - not enforced)
   ↓                                  ↓                                    
Match Invoice                   → Three-Way Match Calculated        → Variance Check
   ↓                                  (PO vs GRN vs Invoice)                (Threshold: 5%)
   ↓                                  ↓                                    
Post Invoice Matching              → Payment Hold Flag                → Hold if variance > threshold
   ↓                                  ↓                                    
Create Payment                  → Payment Registered                → Matched Status Check
   ↓                                  ↓                                    (NOT IMPLEMENTED)
   ↓                                  ↓                                    
Post Payment                     → GL Journal Created               → Encumbrance Liquidated
   ↓                                  (AP Debit, Bank Credit)               (NOT IMPLEMENTED)
   ↓                                  ↓                                    
Vendor Paid                      → Vendor Balance Updated           → Complete
```

### Critical Issues Found

| # | Stage | Issue | Severity | Fix Required |
|---|-------|-------|----------|--------------|
| 1 | PR Approval | Budget encumbrance NOT created | CRITICAL | Create encumbrance on PR approval |
| 2 | PO Creation | No PR linkage validation | HIGH | Require approved PR for PO |
| 3 | GRN Posting | Quality inspection NOT enforced | HIGH | Block GRN if inspection failed |
| 4 | Invoice Matching | Cannot create VendorInvoice | CRITICAL | Add link to accounting.VendorInvoice |
| 5 | Payment | No payment hold check | CRITICAL | Check InvoiceMatching.payment_hold |
| 6 | Payment | Encumbrance NOT liquidated | CRITICAL | Clear encumbrance on payment |

### API Endpoints for P2P

```python
# Purchase Request
POST   /api/procurement/purchase-requests/           # Create PR
POST   /api/procurement/purchase-requests/{id}/submit/  # Submit for approval
POST   /api/procurement/purchase-requests/{id}/approve/ # Approve
POST   /api/procurement/purchase-requests/{id}/reject/  # Reject

# Purchase Order
POST   /api/procurement/purchase-orders/              # Create PO
POST   /api/procurement/purchase-orders/{id}/post/     # Post to GL

# Goods Received Note
POST   /api/procurement/goods-received-notes/         # Create GRN
POST   /api/procurement/goods-received-notes/{id}/post/

# Invoice Matching
POST   /api/procurement/invoice-matchings/            # Create match
POST   /api/procurement/invoice-matchings/{id}/approve/

# Payment (Accountant module)
POST   /api/accounting/payments/                      # Create payment
POST   /api/accounting/payments/{id}/post/            # Post payment
```

---

## MODULE 2: PRODUCTION TO FINISH GOOD (P2FG)

### Complete User Journey

```
[1. USER ACTION]                    [2. SYSTEM RESPONSE]              [3. VALIDATION]
───────────────────────────────────────────────────────────────────────────────────────
Create BOM                        → BOM Number Generated              → Component Valid
   ↓                                  (Auto: BOM-YYYY-NNNN)                 (Must be active)
   ↓                                  ↓                                    
Add BOM Lines                   → Component Quantities              → Scrap % Applied
   ↓                                  (Calculated with scrap)               ↓
   ↓                                  ↓                                    
Create Routing                  → Operation Steps                    → Work Center Valid
   ↓                                  (Sequenced operations)                  ↓
   ↓                                  ↓                                    
Create Production Order         → PO Number Generated                → BOM Valid
   ↓                                  (Auto: PRD-YYYY-NNNN)                 ↓
   ↓                                  ↓                                    
Schedule                       → Status: Scheduled                 → Work Center Capacity
   ↓                                  ↓                                    (Check available hours)
   ↓                                  ↓                                    
Issue Materials               → Stock Movements Created           → Stock Available
   ↓                                  (Material Issue)                       ↓
   ↓                                  ↓                                    
Start Job Cards               → Status: In Progress              → Work Center Assigned
   ↓                                  ↓                                    
Complete Operations            → Actual Time Captured             → Labor Cost Calc
   ↓                                  ↓                                    
Post Material Issue            → GL: WIP Dr, RM Cr               → Complete
   ↓                                  ↓                                    
Receive Finish Goods          → FG Inventory Updated              → Batch Created
   ↓                                  ↓                                    
Create Quality Inspection      → Inspection Created                → Link to PO
   ↓                                  ↓                                    
Complete Inspection            → Result: Pass/Fail                → NCR if Fail
   ↓                                  ↓                                    (NOT AUTO-CREATED)
   ↓                                  ↓                                    
Post Material Receipt          → GL: FG Dr, WIP Cr                → Complete
   ↓                                  ↓                                    
Complete Production Order      → Status: Done                     → FG Quantity OK
   ↓                                  ↓                                    
Post to GL                     → Cost Accumulated                 → Complete
```

### Critical Issues Found

| # | Stage | Issue | Severity | Fix Required |
|---|-------|-------|----------|--------------|
| 1 | BOM | No cost rollup calculation | MEDIUM | Calculate total BOM cost from components |
| 2 | Material Issue | No WIP tracking | HIGH | Track WIP inventory separately |
| 3 | Overhead | Overhead rate NOT applied | MEDIUM | Apply WorkCenter.overhead_rate |
| 4 | Quality | Failed inspection doesn't block | HIGH | Hold FG if inspection fails |
| 5 | NCR | Auto-NCR creation NOT implemented | HIGH | Create NCR on inspection failure |
| 6 | BOM↔Inventory | No explicit item linking | HIGH | Link BOM items to inventory.Items |

### API Endpoints for P2FG

```python
# Bill of Materials
POST   /api/production/bill-of-materials/           # Create BOM
POST   /api/production/bill-of-materials/{id}/components/ # Add components

# Work Center
GET    /api/production/work-centers/{id}/capacity/  # Check capacity

# Production Order
POST   /api/production/production-orders/          # Create
POST   /api/production/production-orders/{id}/schedule/
POST   /api/production/production-orders/{id}/start/
POST   /api/production/production-orders/{id}/complete/
POST   /api/production/production-orders/{id}/post_to_gl/

# Material Issue
POST   /api/production/material-issues/            # Create
POST   /api/production/material-issues/{id}/post_to_gl/

# Material Receipt
POST   /api/production/material-receipts/        # Create
POST   /api/production/material-receipts/{id}/post_to_gl/

# Job Cards
POST   /api/production/job-cards/{id}/start_operation/
POST   /api/production/job-cards/{id}/complete_operation/

# Quality
POST   /api/production/production-orders/{id}/create_quality_inspection/
```

---

## MODULE 3: ORDER TO CASH (O2C)

### Complete User Journey

```
[1. USER ACTION]                    [2. SYSTEM RESPONSE]              [3. VALIDATION]
───────────────────────────────────────────────────────────────────────────────────────
Create Lead                       → Lead Created                     → Duplicate Check
   ↓                                                                 (NOT IMPLEMENTED)
   ↓                                                                 
Qualify Lead                     → Status: Qualified                → Sales Rep Assigned
   ↓                                                                 
Create Opportunity              → Opportunity Tracked               → Stage Defined
   ↓                                                                 
Create Quotation                → Quote Number Generated            → Price List Applied
   ↓                                  (Auto: QT-YYYY-NNNN)                 (If linked)
   ↓                                  ↓                                    
Send Quotation                  → Customer Notified                → Email sent
   ↓                                  ↓                                    
Customer Accepts               → Status: Accepted                 → Convert to SO
   ↓                                  ↓                                    
Create Sales Order             → SO Number Generated               → Credit Check
   ↓                                  (Auto: SO-YYYY-NNNN)                 (At approval, NOT creation)
   ↓                                  ↓                                    
Approve SO                      → Status: Approved                → Credit Available?
   ↓                                  ↓                                    (Blocks if exceeded)
   ↓                                  ↓                                    
Post SO                         → GL: AR Dr, Revenue Cr          → Revenue Recognized
   ↓                                  ↓                                    (At posting, NOT delivery)
   ↓                                  ↓                                    
Create Delivery Note           → DN Number Generated               → Stock Available
   ↓                                  (Auto: DN-YYYY-NNNN)                 (Stock check NOT enforced)
   ↓                                  ↓                                    
Post Delivery                  → Stock Deducted                   → Duplicate Check?
   ↓                                  (Stock Movement OUT)                   (Risk of double COGS)
   ↓                                  ↓                                    
Create Invoice                 → Invoice Number Generated          → Based on DN
   ↓                                  (Auto: INV-YYYY-NNNN)                 ↓
   ↓                                  ↓                                    
Post Invoice                   → AR Updated                      → Match DN
   ↓                                  ↓                                    
Record Payment                → Receipt Created                  → Amount OK?
   ↓                                  ↓                                    
Post Receipt                   → GL: Bank Dr, AR Cr               → Complete
   ↓                                  ↓                                    
AR Cleared                     → Invoice Status: Paid             → Complete
```

### Critical Issues Found

| # | Stage | Issue | Severity | Fix Required |
|---|-------|-------|----------|--------------|
| 1 | Lead | No duplicate check | MEDIUM | Check existing by email/phone |
| 2 | SO Creation | Credit check NOT at creation | MEDIUM | Check at creation, warn if exceeded |
| 3 | Delivery | Stock validation NOT enforced | HIGH | Validate stock before delivery |
| 4 | Revenue | Posted at SO, not delivery | HIGH | Consider accrual accounting |
| 5 | COGS | Double posting risk | CRITICAL | Prevent if already posted via SO |
| 6 | Invoice | Auto-created but editable | MEDIUM | Lock once created from DN |

### API Endpoints for O2C

```python
# Lead
POST   /api/sales/leads/                       # Create
POST   /api/sales/leads/{id}/qualify/          # Qualify

# Quotation
POST   /api/sales/quotations/                 # Create
POST   /api/sales/quotations/{id}/send/        # Send to customer
POST   /api/sales/quotations/{id}/accept/      # Accept -> Convert to SO

# Sales Order
POST   /api/sales/sales-orders/                # Create
POST   /api/sales/sales-orders/{id}/approve/   # Approve (credit check)
POST   /api/sales/sales-orders/{id}/post/     # Post to GL

# Delivery Note
POST   /api/sales/delivery-notes/              # Create
POST   /api/sales/delivery-notes/{id}/post/   # Post (deduct stock)

# Customer Invoice
POST   /api/accounting/customer-invoices/     # Create
POST   /api/accounting/customer-invoices/{id}/post/

# Receipt
POST   /api/accounting/receipts/              # Create
POST   /api/accounting/receipts/{id}/allocate/ # Allocate to invoices
POST   /api/accounting/receipts/{id}/post/
```

---

## MODULE 4: HR HIRE TO PAY (H2P)

### Complete User Journey

```
[1. USER ACTION]                    [2. SYSTEM RESPONSE]              [3. VALIDATION]
───────────────────────────────────────────────────────────────────────────────────────
Create Job Post                   → Position Created                 → Department Valid
   ↓                                                                 
Publish Position                 → Status: Open                     → Approval Required?
   ↓                                                                 (Based on settings)
   ↓                                                                 
Receive Applications             → Candidates Created               → Resume Stored
   ↓                                                                 
Schedule Interview              → Interview Set                    → Interviewer Notified
   ↓                                                                 (Email NOT implemented)
   ↓                                                                 
Conduct Interview               → Rating Recorded                 → Score Calculated
   ↓                                                                 
Select Candidate                → Status: Selected                → Offer Letter
   ↓                                                                 
Start Onboarding               → Tasks Assigned                  → HR/IT/Finance Notified
   ↓                                                                 (Manual process)
   ↓                                                                 
Create Employee                → Employee Number                  → Department/Position
   ↓                                  (Auto: EMP-YYYY-NNNN)                 ↓
   ↓                                  ↓                                    
Setup Salary                  → Salary Structure Applied         → Component Valid
   ↓                                  ↓                                    
Record Attendance              → Check In/Out Captured           → Work Hours Calc
   ↓                                  ↓                                    
Apply Leave                    → Leave Request Created            → Balance Check
   ↓                                  ↓                                    
Approve Leave                 → Balance Deducted                → Leave Type Valid
   ↓                                  ↓                                    
Run Payroll                   → Payroll Period Created           → Working Days Calc
   ↓                                  ↓                                    
Calculate Deductions           → Tax/Pension Calculated          → Manual entry
   ↓                                  ↓                                    
Approve Payroll               → Status: Approved                → Manager approval
   ↓                                  ↓                                    
Post Payroll                   → GL Entries Created              → Complete
   ↓                                  (Salary Exp Dr, Liab Cr)            
   ↓                                                                 
Pay Salaries                  → Payment Records                  → Bank Transfer
   ↓                                                                 
Settlement on Exit             → Final Settlement Calc            → Leave Encashment
   ↓                                  ↓                                    
   → P45/Experience Cert        → Generated                       → Complete
```

### Critical Issues Found

| # | Stage | Issue | Severity | Fix Required |
|---|-------|-------|----------|--------------|
| 1 | Interview | No automated notifications | MEDIUM | Email integration |
| 2 | Onboarding | Manual task assignment | MEDIUM | Auto-create tasks |
| 3 | Leave | No auto-deduction in payroll | MEDIUM | Link leave to payroll |
| 4 | Tax | No automatic tax calculation | HIGH | Implement tax brackets |
| 5 | Employer | Pension contribution missing | HIGH | Add employer side |
| 6 | Cost Center | No department breakdown in GL | MEDIUM | Add dimension posting |

### API Endpoints for H2P

```python
# Recruitment
POST   /api/hrm/job-posts/                    # Create position
POST   /api/hrm/candidates/                  # Add candidate
POST   /api/hrm/interviews/                   # Schedule

# Employee
POST   /api/hrm/employees/                    # Create
POST   /api/hrm/employees/{id}/onboard/       # Start onboarding

# Attendance
POST   /api/hrm/attendances/bulk_mark/        # Bulk attendance
GET    /api/hrm/attendances/today_summary/   # Today's status

# Leave
POST   /api/hrm/leave-requests/               # Create
POST   /api/hrm/leave-requests/{id}/approve/  # Approve

# Payroll
POST   /api/hrm/payroll-runs/                 # Create
POST   /api/hrm/payroll-runs/{id}/process/   # Calculate
POST   /api/hrm/payroll-runs/{id}/approve/
POST   /api/hrm/payroll-runs/{id}/post/      # Post to GL
```

---

## MODULE 5: QUALITY ASSURANCE

### Complete User Journey

```
[1. USER ACTION]                    [2. SYSTEM RESPONSE]              [3. VALIDATION]
───────────────────────────────────────────────────────────────────────────────────────
Configure QA                       → Standards Defined                → Checklist Created
   ↓                                                                 
GRN Received                     → Create Inspection                → Auto-trigger
   ↓                                  ↓                                    
Perform Inspection                → Results Recorded                 → Against spec
   ↓                                  ↓                                    
   → PASS                          → Status: Passed                  → GRN Released
   ↓                                  ↓                                    
   → FAIL                          → Status: Failed                  → Approval Required
                                       ↓                                    
                                       → NonConformance Created       → (NOT AUTO)
                                       ↓                                    
                                       → NCR Number Generated         → Root Cause?
                                       ↓                                    
                                       → CAPA Created                 → (Manual)
                                       ↓                                    
                                       → GRN On Hold                  → (NOT IMPLEMENTED)
```

### Critical Issues Found

| # | Stage | Issue | Severity | Fix Required |
|---|-------|-------|----------|--------------|
| 1 | GRN→Inspection | Auto-trigger NOT implemented | HIGH | Create inspection on GRN |
| 2 | Inspection Fail | NCR NOT auto-created | HIGH | Auto-create NCR |
| 3 | NCR | GRN NOT put on hold | HIGH | Block further processing |
| 4 | Production | No hold when inspection fails | HIGH | Block FG if QI fails |
| 5 | Calibration | Not integrated with inspection | MEDIUM | Track calibration status |

---

## MODULE 6: WORKFLOW APPROVALS

### Current Implementation Status

| Module | Approval Required | Actual Routing | Delegation |
|--------|------------------|---------------|------------|
| PR | Settings-based | Manual | Not enforced |
| PO | Settings-based | Manual | Not enforced |
| Sales SO | Settings-based | Manual | Not enforced |
| Payroll | Settings-based | Manual | Implemented |
| Budget | Settings-based | Manual | Implemented |
| QC Fail | Always | Auto | Not implemented |

### Missing: Automatic Routing

```python
# CURRENT (Manual)
POST /api/procurement/purchase-requests/{id}/approve/  # Sets status directly

# SHOULD BE
1. User submits PR
2. System checks amount → finds threshold
3. Routes to appropriate ApprovalGroup
4. Each approver notified (email)
5. Approval recorded in workflow tables
6. Status updated only after full approval
```

---

## MODULE 7: BUDGET TO REPORTS

### Budget Integration Map

| Module | Budget Check | Encumbrance | Actual |
|--------|--------------|-------------|--------|
| Procurement PR | ✓ | ✗ | ✗ |
| Procurement PO | ✓ | ✓ | ✗ |
| Journal Entry | ✓ | ✗ | ✓ |
| Production | ✗ | ✗ | ✗ |
| Sales | ✗ | ✗ | ✗ |
| Payroll | ✗ | ✗ | ✓ |

### Report Availability

| Report | Status | Notes |
|--------|--------|-------|
| Trial Balance | ✓ | Working |
| Balance Sheet | ✓ | Working |
| Income Statement | ✓ | Working |
| Cash Flow | ✓ | Working |
| General Ledger | ✓ | Working |
| Budget vs Actual | ✓ | Working |
| Stock Valuation | ✓ | Working |
| Age Analysis (AR/AP) | ✓ | Working |
| Payroll Summary | ✓ | Working |
| Attendance Report | ✓ | Working |
| Quality Metrics | ✗ | NOT IMPLEMENTED |
| Production Cost Report | ✗ | NOT IMPLEMENTED |
| Procurement Analytics | ✗ | NOT IMPLEMENTED |

---

## CROSS-MODULE INTEGRATION GAPS

### Integration Matrix

```
FROM/TO        PROCUREMENT    PRODUCTION    SALES        HR          QUALITY
PROCUREMENT    -              ✗            ✗            ✗           ✓
PRODUCTION     ✗              -            ✗            ✗           ✓
SALES          ✗              ✗            -            ✗           ✗
HR             ✗              ✗            ✗            -           ✗
QUALITY        ✗              ✗            ✗            ✗           -
BUDGET         ✓              ✗            ✗            ✓           ✗
```

---

## CRITICAL FIXES PRIORITY LIST

### CRITICAL (Must Fix Before Production)

1. **P2P Payment Hold Check**
   - File: `accounting/views/payables.py`
   - Add: Check `InvoiceMatching.payment_hold` before payment

2. **P2P Encumbrance Liquidation**
   - File: `accounting/views/payables.py`
   - Add: Reduce encumbrance on payment post

3. **O2C COGS Double Posting Prevention**
   - File: `sales/views.py`
   - Add: Check if SO already posted before DN

4. **Invoice Matching → Vendor Invoice Link**
   - File: `procurement/models.py`
   - Add: Create accounting.VendorInvoice from matching

### HIGH (Should Fix Soon)

5. **GRN Quality Enforcement**
   - File: `procurement/views.py`
   - Add: Block GRN use if inspection failed

6. **Production Quality Gate**
   - File: `production/views.py`
   - Add: Hold FG if quality inspection failed

7. **Auto NCR Creation**
   - File: `quality/signals.py` (new)
   - Add: Signal on inspection failure

8. **O2C Credit Check at Creation**
   - File: `sales/views.py`
   - Add: Warning at creation, block at approval

### MEDIUM (Nice to Have)

9. BOM Cost Rollup
10. Overhead Application
11. Tax Bracket Calculation
12. Department Cost Center Posting

---

## RECOMMENDED ACTIONS

1. **Immediate**: Fix CRITICAL items before go-live
2. **Week 1**: Complete HIGH priority items
3. **Week 2**: Complete MEDIUM priority items
4. **Ongoing**: Add missing reports

---

*Document End*
