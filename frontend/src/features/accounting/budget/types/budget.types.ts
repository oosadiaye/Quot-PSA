// Budget Management Type Definitions

export interface BudgetPeriod {
    id: number;
    fiscal_year: number;
    period_type: 'ANNUAL' | 'QUARTERLY' | 'MONTHLY';
    period_number: number;
    start_date: string;
    end_date: string;
    /** OPEN = posted by fiscal year creation; ACTIVE = manually activated; DRAFT/CLOSED/LOCKED = locked states */
    status: 'DRAFT' | 'OPEN' | 'ACTIVE' | 'ADJUSTMENT' | 'CLOSED' | 'LOCKED';
    allow_postings: boolean;
    allow_adjustments: boolean;
    notes?: string;
    created_at?: string;
    updated_at?: string;
}

export interface MDA {
    id: number;
    code: string;
    name: string;
    mda_type: 'MINISTRY' | 'DEPARTMENT' | 'AGENCY';
    parent?: number;
    is_active: boolean;
}

export interface Fund {
    id: number;
    code: string;
    name: string;
    fund_type: string;
    is_active: boolean;
}

export interface Function {
    id: number;
    code: string;
    name: string;
    is_active: boolean;
}

export interface Program {
    id: number;
    code: string;
    name: string;
    is_active: boolean;
}

export interface Geo {
    id: number;
    code: string;
    name: string;
    is_active: boolean;
}

export interface Account {
    id: number;
    code: string;
    name: string;
    account_type: 'Asset' | 'Liability' | 'Equity' | 'Income' | 'Expense';
    parent?: number;
    is_active: boolean;
}

export interface CostCenterRef {
    id: number;
    code: string;
    name: string;
    center_type: string;
    is_active: boolean;
}

export interface Budget {
    id: number;
    budget_code: string;
    period: number | BudgetPeriod;
    mda: number | MDA;
    account: number | Account;
    fund?: number | Fund;
    function?: number | Function;
    program?: number | Program;
    geo?: number | Geo;
    cost_center?: number | CostCenterRef | null;
    allocated_amount: string;
    revised_amount: string;
    encumbered_amount?: string;
    expended_amount?: string;
    available_amount?: string;
    utilization_rate?: number;
    control_level: 'NONE' | 'WARNING' | 'HARD_STOP';
    enable_encumbrance: boolean;
    notes?: string;
    created_by?: number;
    updated_by?: number;
    created_at?: string;
    updated_at?: string;
}

export interface BudgetEncumbrance {
    id: number;
    budget: number | Budget;
    reference_type: 'PO' | 'CONTRACT';
    reference_id: number;
    encumbrance_date: string;
    amount: string;
    liquidated_amount: string;
    remaining_amount?: string;
    status: 'ACTIVE' | 'PARTIALLY_LIQUIDATED' | 'FULLY_LIQUIDATED' | 'CANCELLED';
    description: string;
    created_at: string;
    updated_at: string;
}

export interface BudgetCheckLog {
    id: number;
    budget: number | Budget;
    transaction_type: string;
    transaction_id: number;
    requested_amount: string;
    available_amount: string;
    check_result: 'PASSED' | 'WARNING' | 'BLOCKED';
    override_by?: number;
    check_date: string;
}

export interface BudgetSummary {
    total_allocated: string;
    total_revised: string;
    total_encumbered: string;
    total_expended: string;
    total_available: string;
    overall_utilization: number;
    budget_count: number;
}

export interface BudgetUtilization {
    account_type: string;
    account_type_display: string;
    allocated: string;
    revised: string;
    encumbered: string;
    expended: string;
    available: string;
    utilization_percentage: number;
}

export interface BudgetAlert {
    id: number;
    budget: Budget;
    alert_type: 'WARNING' | 'CRITICAL';
    message: string;
    threshold_percentage: number;
    current_percentage: number;
    created_at: string;
}

export interface VarianceAnalysisResult {
    budget_code: string;
    account_code: string;
    account_name: string;
    allocated: string;
    revised: string;
    encumbered: string;
    expended: string;
    total_used: string;
    available: string;
    variance_amount: string;
    variance_percentage: number;
    status: 'UNDER' | 'ON_TRACK' | 'OVER';
}

export interface BudgetFilters {
    period?: number;
    mda?: number;
    fund?: number;
    function?: number;
    program?: number;
    geo?: number;
    cost_center?: number;
    account?: number;
    control_level?: 'NONE' | 'WARNING' | 'HARD_STOP';
    status?: string;
    search?: string;
}

export interface BudgetFormData {
    period: number;
    mda: number;
    account: number;
    fund?: number;
    function?: number;
    program?: number;
    geo?: number;
    cost_center?: number | null;
    allocated_amount: string;
    revised_amount?: string;
    control_level: 'NONE' | 'WARNING' | 'HARD_STOP';
    enable_encumbrance: boolean;
    notes?: string;
}

export interface BudgetImportRow {
    account_code: string;
    account_name?: string;
    allocated_amount: string;
    revised_amount?: string;
    control_level?: string;
    enable_encumbrance?: boolean;
    notes?: string;
    errors?: string[];
}

export interface BudgetImportResult {
    success_count: number;
    error_count: number;
    errors: Array<{
        row: number;
        account_code: string;
        message: string;
    }>;
    created_budgets: Budget[];
}
