/**
 * Curated "how do I..." answers. Every button name below is the label on the real screen;
 * a guide never mentions a figure and never claims a button that does not exist.
 *
 * `asks` are phrases a person might type. A guide matches when every word of one phrase is in the
 * question (after verb and noun synonyms), so "how do I post a budget" and "enter budget" both hit.
 * `screen` is the menu path the guide lives on; the guide is hidden from users who cannot open it.
 */
export interface Guide {
    id: string;
    title: string;
    /** Menu path the guide starts on, or null for a screen that is not in the sidebar. */
    screen: string | null;
    asks: string[];
    steps: string[];
}

export const GUIDES: readonly Guide[] = [
    {
        id: 'post-budget',
        title: 'Post a budget (appropriation)',
        screen: '/budget/appropriations',
        asks: ['create budget', 'create appropriation', 'upload budget', 'load budget'],
        steps: [
            'Open Budget & Appropriation > Appropriations.',
            'Click New Appropriation and complete the form.',
            'Save. It is kept as a Draft until you submit it.',
            'It then moves through Submitted, Approved and Enacted to Active. Only an Active appropriation can be spent against.',
        ],
    },
    {
        id: 'check-budget',
        title: 'Check a budget',
        screen: '/budget/check',
        asks: ['review budget', 'budget balance', 'budget available', 'available budget', 'budget left', 'budget remaining', 'budget status'],
        steps: [
            'Open Budget & Appropriation > Budget Check.',
            'Search by code, MDA, GL, fund or status.',
            'Open a line to see its Approved, Warrants, Committed, Expended and Available amounts.',
        ],
    },
    {
        id: 'budget-execution',
        title: 'See how a budget is being spent',
        screen: '/budget/execution-report',
        asks: ['budget execution', 'execution report', 'budget performance', 'budget utilization'],
        steps: ['Open Budget & Appropriation > Execution Report.'],
    },
    {
        id: 'supplementary-budget',
        title: 'Add a supplementary budget',
        screen: '/budget/supplementary',
        asks: ['create supplementary', 'supplementary budget', 'additional budget'],
        steps: ['Open Budget & Appropriation > Supplementary Budget.', 'Click New Supplementary and complete the form.'],
    },
    {
        id: 'virement',
        title: 'Move budget between lines (virement)',
        screen: '/budget/virements',
        asks: ['create virement', 'virement', 'move budget', 'transfer budget', 'reallocate budget'],
        steps: [
            'Open Budget & Appropriation > Virement (Transfer).',
            'Click New Virement. The amount taken from one line must equal the amount added to the other.',
        ],
    },
    {
        id: 'warrant',
        title: 'Release a warrant (AIE)',
        screen: '/budget/warrants',
        asks: ['create warrant', 'release warrant', 'warrant', 'aie', 'cash release'],
        steps: ['Open Budget & Appropriation > Warrants / AIE.', 'Click New Warrant and complete the form.'],
    },
    {
        id: 'journal',
        title: 'Raise a journal entry',
        screen: '/accounting',
        asks: ['create journal', 'journal entry', 'journal voucher'],
        steps: ['Open Accounting > Journal Entries.', 'Click New Journal, fill in the lines so debits equal credits, and save.'],
    },
    {
        id: 'supplier-invoice',
        title: 'Record a supplier invoice',
        screen: '/accounting/ap',
        asks: ['create invoice', 'supplier invoice', 'vendor invoice', 'payable invoice', 'enter bill'],
        steps: ['Open Accounting > AP Invoice.', 'Complete the invoice form and save it.', 'Find it later under Accounting > AP Invoices Register.'],
    },
    {
        id: 'pay-supplier',
        title: 'Pay a supplier',
        screen: '/accounting/ap-invoices',
        asks: ['pay supplier', 'pay vendor', 'pay invoice', 'make payment', 'create payment', 'supplier payment', 'disburse payment'],
        steps: [
            'Open Accounting > AP Invoices Register and choose the approved invoice.',
            'Click Create Payment Proposal.',
            'Once the proposal is approved it appears under Treasury & Banking > Outgoing Payments as a draft.',
            'Pick the bank account and click Post Payment. This is the only step that moves cash.',
        ],
    },
    {
        id: 'add-supplier',
        title: 'Add a supplier',
        screen: '/procurement/vendors',
        asks: ['create supplier', 'create vendor', 'register supplier'],
        steps: ['Open Accounting > Suppliers.', 'Click Add New Vendor and fill in the details. A supplier name that already exists is flagged as you type.'],
    },
    {
        id: 'add-user',
        title: 'Add a user and assign MDAs',
        screen: '/user-management',
        asks: ['create user', 'assign mda', 'user mda', 'give access'],
        steps: ['Open Administration > User Management.', 'Click Add User, fill in the details and choose the MDAs the user belongs to.'],
    },
    {
        id: 'requisition',
        title: 'Raise a purchase requisition',
        screen: '/procurement/requisitions',
        asks: ['create requisition', 'create purchase requisition', 'request purchase'],
        steps: ['Open Procurement > Purchase Requisitions.', 'Click New Requisition and complete the form.'],
    },
    {
        id: 'purchase-order',
        title: 'Create a purchase order',
        screen: '/procurement/orders',
        asks: ['create purchase order', 'create po'],
        steps: ['Open Procurement > Purchase Orders.', 'Click New Purchase Order, or use Create PO from an approved requisition.'],
    },
    {
        id: 'trial-balance',
        title: 'Run the trial balance',
        screen: '/accounting/reports/trial-balance',
        asks: ['trial balance', 'view trial balance'],
        steps: ['Open Accounting > Trial Balance.'],
    },
    {
        id: 'financial-statements',
        title: 'Open the IPSAS financial statements',
        screen: '/accounting/ipsas/financial-position',
        asks: ['financial statement', 'ipsas statement', 'financial position', 'financial performance', 'cash flow statement'],
        steps: ['Open IPSAS Reporting.', 'Pick the statement you need, such as Financial Position or Financial Performance.'],
    },
    {
        id: 'approvals',
        title: 'Approve a document',
        screen: '/approvals',
        asks: ['approve document', 'approval inbox', 'pending approval', 'approve'],
        steps: ['Open Approvals > Approval Inbox.', 'Open an item from the inbox to review it.'],
    },
    {
        id: 'change-password',
        title: 'Change your password',
        screen: null,
        asks: ['change password', 'update password', 'reset password'],
        steps: ['Open My Account from your profile.', 'Go to the Security tab, enter your current and new password under Change Password, and click Update Password.'],
    },
];
