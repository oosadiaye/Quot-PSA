# Accounting Module Specification

> **Project:** DTSG ERP
> **Module:** Accounting
> **Version:** 1.0.0
> **Last Updated:** 2026-03-01

---

## 1. Module Overview

The Accounting module provides comprehensive financial management including journal entries, chart of accounts, recurring journals, accruals & deferrals, fixed assets, AP/AR management, and financial reporting.

### Key Features
- Journal entry management with approval workflow
- Chart of Accounts (COA)
- Recurring journals with auto-posting
- Accruals & deferrals with auto-reversal
- Fixed assets tracking
- Accounts Payable & Receivable
- Multi-company accounting
- Budget management
- Tax management

---

## 2. File Structure

```
frontend/src/features/accounting/
├── AccountingDashboard.tsx        # Main dashboard
├── AccountingLayout.tsx          # Layout wrapper
├── JournalList.tsx              # Journal entries list
├── JournalForm.tsx               # Journal entry form
├── CostCenters.tsx              # Cost center management
├── RecurringJournalList.tsx     # Recurring journal templates
├── RecurringJournalForm.tsx     # Create/edit recurring journal
├── AccrualDeferralList.tsx      # Accruals & deferrals list
├── AccrualDeferralForm.tsx     # Create/edit accrual/deferral
├── hooks/
│   ├── useJournal.ts           # Journal hooks
│   ├── useRecurringJournal.ts   # Recurring journal hooks
│   └── useAccrualDeferral.ts   # Accrual/deferral hooks
├── pages/
│   ├── FundManagement.tsx
│   ├── FunctionManagement.tsx
│   ├── ProgramManagement.tsx
│   ├── GeoManagement.tsx
│   └── DimensionsDashboard.tsx
├── coa/
│   └── ChartOfAccounts.tsx
├── ap/
│   └── APManagement.tsx
├── ar/
│   └── ARManagement.tsx
├── assets/
│   ├── FixedAssets.tsx
│   └── AssetCategories.tsx
├── reports/
│   └── GLReports.tsx
├── budget/
│   └── pages/
├── tax/
│   └── TaxManagement.tsx
├── fiscal-year/
│   └── FiscalYearPage.tsx
├── cash/
├── bank-cash/
├── multi-company/
└── SPEC.md                      # This file
```

---

## 3. Pages/Components

### 3.1 AccountingDashboard
**Route:** `/accounting/dashboard`

### 3.2 JournalList
**Route:** `/accounting`

### 3.3 JournalForm
**Route:** `/accounting/new` | `/accounting/:id`

### 3.4 CostCenters
**Route:** `/accounting/cost-centers`

### 3.5 RecurringJournalList
**Route:** `/accounting/recurring-journals`

**Features:**
- List recurring journal templates
- Filter: All, Active, Inactive
- Generate Now button
- Delete templates
- Edit templates

**Fields:**
| Field | Type | Description |
|-------|------|-------------|
| name | string | Template name |
| code | string | Auto-generated (PREFIX-YYYYMMDD-XXX) |
| code_prefix | string | Code prefix (default: REC) |
| description | string | Template description |
| frequency | select | daily, weekly, biweekly, monthly, quarterly, annually |
| start_date | date | Start date |
| end_date | date | End date |
| start_type | select | "now" (Start Now) or "scheduled" (Schedule Future) |
| scheduled_posting_date | date | Future posting date |
| is_active | boolean | Active status |
| auto_post | boolean | Auto-post when generated |
| use_month_end_default | boolean | Use last day of month as posting date |
| auto_reverse_on_month_start | boolean | Auto-reverse on 1st of next month |

### 3.6 RecurringJournalForm
**Route:** `/accounting/recurring-journals/new` | `/accounting/recurring-journals/:id`

### 3.7 AccrualDeferralList
**Route:** `/accounting/accruals-deferrals`

**Features:**
- Tabs: Accruals, Deferrals
- Post accrual action
- Reverse accrual action
- Create new accrual/deferral

### 3.8 AccrualDeferralForm
**Route:** `/accounting/accruals-deferrals/new/:type` | `/accounting/accruals-deferrals/:type/:id`

**Accrual Fields:**
| Field | Type | Description |
|-------|------|-------------|
| name | string | Entry name |
| code | string | Entry code |
| description | string | Description |
| posting_date | date | Journal posting date |
| reversal_date | date | Reversal date |
| use_default_dates | boolean | Use month-end defaults |
| auto_reverse_on_month_start | boolean | Auto-reverse on 1st of next month |
| recurring_journal | FK | Link to recurring journal template |

**Deferral Fields:**
| Field | Type | Description |
|-------|------|-------------|
| name | string | Entry name |
| code | string | Entry code |
| description | string | Description |
| posting_date | date | Journal posting date |
| auto_recognize | boolean | Auto-recognize revenue/expense |
| auto_recognize_on_month_start | boolean | Auto-recognize on 1st of next month |
| recurring_journal | FK | Link to recurring journal template |

---

## 4. API Endpoints

### Recurring Journals
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/accounting/recurring-journals/` | GET, POST | List/Create |
| `/api/accounting/recurring-journals/:id/` | GET, PATCH, DELETE | Retrieve/Update/Delete |
| `/api/accounting/recurring-journals/:id/generate_now/` | POST | Generate journal now |
| `/api/accounting/recurring-journals/default_dates/` | GET | Get default posting/reversal dates |

### Accruals
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/accounting/accruals/` | GET, POST | List/Create |
| `/api/accounting/accruals/:id/` | GET, PATCH, DELETE | Retrieve/Update/Delete |
| `/api/accounting/accruals/:id/post/` | POST | Post accrual |
| `/api/accounting/accruals/:id/reverse/` | POST | Reverse accrual |
| `/api/accounting/accruals/default_dates/` | GET | Get default dates |

### Deferrals
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/accounting/deferrals/` | GET, POST | List/Create |
| `/api/accounting/deferrals/:id/` | GET, PATCH, DELETE | Retrieve/Update/Delete |

---

## 5. Frontend Routes

| Route | Component | Description |
|-------|-----------|-------------|
| `/accounting/dashboard` | AccountingDashboard | Main dashboard |
| `/accounting` | JournalList | Journal entries |
| `/accounting/new` | JournalForm | Create journal |
| `/accounting/:id` | JournalForm | Edit journal |
| `/accounting/coa` | ChartOfAccounts | Chart of accounts |
| `/accounting/ap` | APManagement | Accounts payable |
| `/accounting/ar` | ARManagement | Accounts receivable |
| `/accounting/fixed-assets` | FixedAssets | Fixed assets |
| `/accounting/reports` | GLReports | GL Reports |
| `/accounting/cost-centers` | CostCenters | Cost centers |
| `/accounting/recurring-journals` | RecurringJournalList | Recurring templates |
| `/accounting/recurring-journals/new` | RecurringJournalForm | Create template |
| `/accounting/recurring-journals/:id` | RecurringJournalForm | Edit template |
| `/accounting/accruals-deferrals` | AccrualDeferralList | List |
| `/accounting/accruals-deferrals/new/:type` | AccrualDeferralForm | Create |
| `/accounting/accruals-deferrals/:type/:id` | AccrualDeferralForm | Edit |
| `/accounting/tax` | TaxManagement | Tax management |
| `/accounting/dimensions` | DimensionsDashboard | Dimensions |
| `/accounting/dimensions/funds` | FundManagement | Funds |
| `/accounting/dimensions/functions` | FunctionManagement | Functions |
| `/accounting/dimensions/programs` | ProgramManagement | Programs |
| `/accounting/dimensions/geos` | GeoManagement | Geo locations |
| `/accounting/budget/dashboard` | BudgetDashboard | Budget dashboard |
| `/accounting/budget/entry` | BudgetEntry | Budget entry |
| `/accounting/budget/variance` | VarianceAnalysis | Variance analysis |

---

## 6. Custom Hooks

### Journal Hooks (`useJournal.ts`)
- `useJournals(filters)` - List journals
- `useCreateJournal()` - Create journal
- `usePostJournal()` - Post journal
- `useDimensions()` - Get funds, functions, programs, geos, accounts

### Recurring Journal Hooks (`useRecurringJournal.ts`)
- `useRecurringJournals(filters)` - List templates
- `useRecurringJournal(id)` - Single template
- `useCreateRecurringJournal()` - Create
- `useUpdateRecurringJournal()` - Update
- `useDeleteRecurringJournal()` - Delete
- `useGenerateRecurringJournalNow(id)` - Generate now
- `useGenerateRecurringJournals()` - Generate all
- `useDefaultDates()` - Get default dates
- `useRecurringJournalRuns(id)` - Get run history

### Accrual/Deferral Hooks (`useAccrualDeferral.ts`)
- `useAccruals(filters)` - List accruals
- `useAccrual(id)` - Single accrual
- `useCreateAccrual()` - Create accrual
- `useUpdateAccrual()` - Update accrual
- `useDeleteAccrual()` - Delete accrual
- `usePostAccrual(id)` - Post accrual
- `useReverseAccrual(id)` - Reverse accrual
- `useDeferrals(filters)` - List deferrals
- `useDeferral(id)` - Single deferral
- `useCreateDeferral()` - Create deferral
- `useUpdateDeferral()` - Update deferral
- `useDeleteDeferral()` - Delete deferral

---

## 7. Backend Models

### RecurringJournal
```python
class RecurringJournal(models.Model):
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=50, unique=True)
    code_prefix = models.CharField(max_length=10, default='REC')
    description = models.TextField(blank=True)
    frequency = models.CharField(max_length=20)  # daily, weekly, monthly, etc.
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    start_type = models.CharField(max_length=10)  # now, scheduled
    scheduled_posting_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    auto_post = models.BooleanField(default=False)
    use_month_end_default = models.BooleanField(default=False)
    auto_reverse_on_month_start = models.BooleanField(default=False)
    next_run_date = models.DateField(null=True, blank=True)
    # dimensions (fund, function, program, geo)
    # lines (journal lines)
```

### Accrual
```python
class Accrual(models.Model):
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=50)
    description = models.TextField(blank=True)
    posting_date = models.DateField()
    reversal_date = models.DateField(null=True, blank=True)
    use_default_dates = models.BooleanField(default=False)
    auto_reverse_on_month_start = models.BooleanField(default=False)
    is_posted = models.BooleanField(default=False)
    is_reversed = models.BooleanField(default=False)
    recurring_journal = models.ForeignKey(RecurringJournal, null=True)
    # dimensions, lines
```

### Deferral
```python
class Deferral(models.Model):
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=50)
    description = models.TextField(blank=True)
    posting_date = models.DateField()
    auto_recognize = models.BooleanField(default=False)
    auto_recognize_on_month_start = models.BooleanField(default=False)
    is_recognized = models.BooleanField(default=False)
    recurring_journal = models.ForeignKey(RecurringJournal, null=True)
    # dimensions, lines
```

### JournalReversal
```python
class JournalReversal(models.Model):
    original_journal = models.ForeignKey(JournalHeader)
    reversal_journal = models.ForeignKey(JournalHeader)
    reversal_date = models.DateField()
    is_auto_created = models.BooleanField(default=False)
```

---

## 8. Sidebar Menu Structure

```
Accounting
├── Chart of Accounts (/accounting/coa)
├── Journal Entries (/accounting)
├── GL Reports (/accounting/reports)
├── Accounts Payable (/accounting/ap)
├── Accounts Receivable (/accounting/ar)
├── Fixed Assets (/accounting/fixed-assets)
├── Tax Management (/accounting/tax)
├── Cost Centers (/accounting/cost-centers)
├── Recurring Journals (/accounting/recurring-journals)
├── Accruals & Deferrals (/accounting/accruals-deferrals)
└── Intercompany (/accounting/intercompany)
```

---

## 9. Utility Functions

### `accounting/utils.py`

| Function | Description |
|----------|-------------|
| `get_month_end_date(date)` | Get last day of month |
| `get_next_month_first_day(date)` | Get 1st day of next month |
| `get_default_posting_and_reversal_dates()` | Get default dates for accruals |
| `calculate_next_run_date(frequency, start_date)` | Calculate next run date |

---

## 10. Design System Compliance

All components follow the MASTER.md design system:
- Colors: CSS variables (--color-primary, etc.)
- Typography: IBM Plex Sans
- Icons: Lucide React
- Spacing: Token system
- Dark mode: Supported

---

*End of Specification*
