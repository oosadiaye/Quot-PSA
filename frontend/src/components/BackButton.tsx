import { ArrowLeft, ChevronRight } from 'lucide-react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useMemo } from 'react';

// ── Route-to-label mapping for breadcrumb display ──────────────────────
const ROUTE_LABELS: Record<string, string> = {
  '/dashboard': 'Dashboard',
  '/accounting/dashboard': 'Accounting',
  '/accounting': 'Journal Entries',
  '/accounting/new': 'New Journal',
  '/accounting/coa': 'Chart of Accounts',
  '/accounting/ap': 'Accounts Payable',
  '/accounting/ar': 'Accounts Receivable',
  '/accounting/fixed-assets': 'Fixed Assets',
  '/accounting/asset-categories': 'Asset Categories',
  '/accounting/reports': 'GL Reports',
  '/accounting/bank-cash': 'Bank & Cash',
  '/accounting/cash-accounts': 'Cash Accounts',
  '/accounting/cost-centers': 'Cost Centers',
  '/accounting/recurring-journals': 'Recurring Journals',
  '/accounting/recurring-journals/new': 'New Recurring Journal',
  '/accounting/accruals-deferrals': 'Accruals & Deferrals',
  '/accounting/intercompany': 'Intercompany',
  '/accounting/multi-company': 'Multi-Company',
  '/accounting/consolidation': 'Consolidation',
  '/accounting/dimensions': 'Dimensions',
  '/accounting/dimensions/funds': 'Funds',
  '/accounting/dimensions/functions': 'Functions',
  '/accounting/dimensions/programs': 'Programs',
  '/accounting/dimensions/geos': 'Geo Locations',
  '/accounting/budget/dashboard': 'Budget Dashboard',
  '/accounting/budget/entry': 'Budget Entry',
  '/accounting/budget/variance': 'Variance Analysis',
  '/accounting/budget/create': 'Create Budget',
  '/procurement/dashboard': 'Procurement',
  '/procurement/vendors': 'Vendors',
  '/procurement/requisitions': 'Requisitions',
  '/procurement/requisitions/new': 'New Requisition',
  '/procurement/orders': 'Purchase Orders',
  '/procurement/orders/new': 'New Purchase Order',
  '/procurement/grn': 'Goods Received',
  '/procurement/grn/new': 'New GRN',
  '/procurement/matching': '3-Way Matching',
  '/procurement/vendor-performance': 'Vendor Performance',
  '/procurement/returns': 'Purchase Returns',
  '/inventory/dashboard': 'Inventory',
  '/inventory': 'Products',
  '/inventory/new': 'New Product',
  '/inventory/valuation': 'Stock Valuation',
  '/inventory/product-types': 'Product Types',
  '/inventory/categories': 'Categories',
  '/inventory/warehouses': 'Warehouses',
  '/inventory/stocks': 'Stock Levels',
  '/inventory/batches': 'Batches',
  '/inventory/serial-numbers': 'Serial Numbers',
  '/inventory/movements': 'Stock Movements',
  '/inventory/reconciliations': 'Reconciliations',
  '/inventory/reorder-alerts': 'Reorder Alerts',
  '/inventory/expiry-alerts': 'Expiry Alerts',
  '/sales/dashboard': 'Sales',
  '/sales': 'Sales Dashboard',
  '/sales/customers': 'Customers',
  '/sales/customer/new': 'New Customer',
  '/sales/crm': 'CRM Lite',
  '/sales/quotations': 'Quotations',
  '/sales/quotations/new': 'New Quotation',
  '/sales/orders': 'Sales Orders',
  '/sales/orders/new': 'New Sales Order',
  '/sales/delivery-notes': 'Delivery Notes',
  '/sales/delivery-notes/new': 'New Delivery Note',
  '/sales/invoicing': 'Automated Invoicing',
  '/sales/credit-limits': 'Credit Limits',
  '/service/dashboard': 'Service',
  '/service': 'Service Dashboard',
  '/service/assets': 'Service Assets',
  '/service/technicians': 'Technicians',
  '/service/tickets': 'Service Tickets',
  '/service/schedules': 'Maintenance Schedules',
  '/service/work-orders': 'Work Orders',
  '/service/citizen-requests': 'Citizen Requests',
  '/service/metrics': 'Service Metrics',
  '/hrm/dashboard': 'Human Resources',
  '/hrm': 'HR Dashboard',
  '/hrm/employees': 'Employees',
  '/hrm/employees/new': 'New Employee',
  '/hrm/departments': 'Departments',
  '/hrm/positions': 'Positions',
  '/hrm/leave': 'Leave Management',
  '/hrm/attendance': 'Attendance',
  '/hrm/holidays': 'Holidays',
  '/hrm/job-posts': 'Job Posts',
  '/hrm/candidates': 'Candidates',
  '/hrm/payroll': 'Payroll',
  '/hrm/payslips': 'Payslips',
  '/hrm/performance': 'Performance',
  '/hrm/training': 'Training',
  '/hrm/skills': 'Skills',
  '/hrm/policies': 'Policies',
  '/hrm/compliance': 'Compliance',
  '/hrm/exit': 'Exit Management',
  '/production/dashboard': 'Production',
  '/production/bom': 'Bill of Materials',
  '/production/work-centers': 'Work Centers',
  '/production/orders': 'Production Orders',
  '/quality/dashboard': 'Quality',
  '/quality/inspections': 'Inspections',
  '/quality/ncr': 'Non-Conformance',
  '/quality/complaints': 'Complaints',
  '/quality/checklists': 'Checklists',
  '/quality/calibrations': 'Calibrations',
  '/quality/supplier-quality': 'Supplier Quality',
  '/approvals/dashboard': 'Approvals',
  '/approvals': 'Approval Inbox',
  '/approvals/groups': 'Approval Groups',
  '/approvals/templates': 'Approval Templates',
  '/approvals/history': 'Approval History',
  '/workflow/dashboard': 'Workflow',
  '/workflow/inbox': 'Workflow Inbox',
  '/workflow/definitions': 'Definitions',
  '/workflow/groups': 'Groups',
  '/workflow/instances': 'Instances',
  '/settings/accounting': 'Accounting Settings',
  '/settings/accounting/currencies': 'Currencies',
  '/settings/fiscal-year': 'Fiscal Year',
  '/settings/tax': 'Tax Management',
  '/settings/bank-accounts': 'Bank Accounts',
  '/user-management': 'User Management',
  '/superadmin': 'System Admin',
};

// Module root paths for "parent" navigation
const MODULE_ROOTS: Record<string, string> = {
  '/accounting': 'Accounting',
  '/procurement': 'Procurement',
  '/inventory': 'Inventory',
  '/sales': 'Sales',
  '/service': 'Service',
  '/hrm': 'Human Resources',
  '/production': 'Production',
  '/quality': 'Quality',
  '/approvals': 'Approvals',
  '/workflow': 'Workflow',
  '/settings': 'Settings',
};

function getPageLabel(pathname: string): string {
  // Exact match
  if (ROUTE_LABELS[pathname]) return ROUTE_LABELS[pathname];
  // Dynamic routes (e.g., /service/tickets/123)
  const basePath = pathname.replace(/\/\d+$/, '');
  if (ROUTE_LABELS[basePath]) return ROUTE_LABELS[basePath];
  // Convert path segment to readable name
  const segments = pathname.split('/').filter(Boolean);
  const last = segments[segments.length - 1];
  if (last) {
    return last.replace(/[-_]/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
  }
  return 'Page';
}

function getModuleFromPath(pathname: string): { key: string; label: string } | null {
  for (const [prefix, label] of Object.entries(MODULE_ROOTS)) {
    if (pathname.startsWith(prefix)) {
      return { key: prefix, label };
    }
  }
  return null;
}

function getBreadcrumbs(pathname: string): { label: string; path?: string }[] {
  const crumbs: { label: string; path?: string }[] = [];
  const module = getModuleFromPath(pathname);

  if (module) {
    const dashboardPath = `${module.key}/dashboard`;
    if (pathname !== dashboardPath && pathname !== module.key) {
      crumbs.push({ label: module.label, path: ROUTE_LABELS[dashboardPath] ? dashboardPath : module.key });
    }
  }

  crumbs.push({ label: getPageLabel(pathname) });
  return crumbs;
}

interface BackButtonProps {
  /** Compact mode renders inline (for sidebar). Full mode renders with breadcrumbs. */
  variant?: 'compact' | 'full';
  /** Light mode for dark backgrounds (e.g. blue gradient headers). */
  light?: boolean;
}

const BackButton = ({ variant = 'full', light = false }: BackButtonProps) => {
  const navigate = useNavigate();
  const location = useLocation();
  const pathname = location.pathname;

  const isDashboard = pathname === '/dashboard';
  const isSuperAdmin = pathname === '/superadmin';

  const breadcrumbs = useMemo(() => getBreadcrumbs(pathname), [pathname]);

  // Don't show on dashboard or login-type pages
  if (isDashboard || isSuperAdmin) return null;

  if (variant === 'compact') {
    return (
      <button
        onClick={() => navigate(-1)}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '6px',
          padding: '6px 12px',
          fontSize: '12px',
          fontWeight: 500,
          background: 'rgba(36, 42, 136, 0.08)',
          border: '1px solid rgba(36, 42, 136, 0.15)',
          borderRadius: '6px',
          cursor: 'pointer',
          color: 'var(--color-primary, #242a88)',
          transition: 'all 0.15s ease',
          width: '100%',
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.background = 'rgba(36, 42, 136, 0.15)';
          e.currentTarget.style.borderColor = 'rgba(36, 42, 136, 0.3)';
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.background = 'rgba(36, 42, 136, 0.08)';
          e.currentTarget.style.borderColor = 'rgba(36, 42, 136, 0.15)';
        }}
      >
        <ArrowLeft size={14} />
        <span style={{ flex: 1, textAlign: 'left' }}>Back</span>
        {breadcrumbs.length > 0 && (
          <span style={{
            fontSize: '10px',
            color: 'var(--color-text-muted, #6b7280)',
            maxWidth: '120px',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}>
            {breadcrumbs[breadcrumbs.length - 1].label}
          </span>
        )}
      </button>
    );
  }

  // Full variant with breadcrumbs
  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      gap: '12px',
      marginBottom: '4px',
    }}>
      <button
        onClick={() => navigate(-1)}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '6px',
          padding: '6px 14px',
          fontSize: 'var(--text-sm, 13px)',
          fontWeight: 500,
          background: light ? 'rgba(255,255,255,0.15)' : 'var(--color-surface, #fff)',
          border: light ? '1px solid rgba(255,255,255,0.25)' : '1px solid var(--color-border, #e5e7eb)',
          borderRadius: '8px',
          cursor: 'pointer',
          color: light ? 'white' : 'var(--color-text, #111)',
          transition: 'all 0.15s ease',
        }}
        onMouseEnter={(e) => {
          if (light) {
            e.currentTarget.style.background = 'rgba(255,255,255,0.25)';
          } else {
            e.currentTarget.style.background = 'rgba(36, 42, 136, 0.08)';
            e.currentTarget.style.borderColor = 'var(--color-primary, #242a88)';
            e.currentTarget.style.color = 'var(--color-primary, #242a88)';
          }
        }}
        onMouseLeave={(e) => {
          if (light) {
            e.currentTarget.style.background = 'rgba(255,255,255,0.15)';
          } else {
            e.currentTarget.style.background = 'var(--color-surface, #fff)';
            e.currentTarget.style.borderColor = 'var(--color-border, #e5e7eb)';
            e.currentTarget.style.color = 'var(--color-text, #111)';
          }
        }}
      >
        <ArrowLeft size={15} />
        Back
      </button>

      {/* Breadcrumb trail */}
      {breadcrumbs.length > 0 && (
        <nav style={{
          display: 'flex',
          alignItems: 'center',
          gap: '4px',
          fontSize: 'var(--text-xs, 12px)',
          color: light ? 'rgba(255,255,255,0.6)' : 'var(--color-text-muted, #6b7280)',
        }}>
          <span
            onClick={() => navigate('/dashboard')}
            style={{
              cursor: 'pointer',
              color: light ? 'rgba(255,255,255,0.85)' : 'var(--color-primary, #242a88)',
              fontWeight: 500,
            }}
            onMouseEnter={(e) => { e.currentTarget.style.textDecoration = 'underline'; }}
            onMouseLeave={(e) => { e.currentTarget.style.textDecoration = 'none'; }}
          >
            Home
          </span>
          {breadcrumbs.map((crumb, idx) => (
            <span key={idx} style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
              <ChevronRight size={12} style={{ opacity: 0.5 }} />
              {crumb.path && idx < breadcrumbs.length - 1 ? (
                <span
                  onClick={() => navigate(crumb.path!)}
                  style={{
                    cursor: 'pointer',
                    color: light ? 'rgba(255,255,255,0.85)' : 'var(--color-primary, #242a88)',
                    fontWeight: 500,
                  }}
                  onMouseEnter={(e) => { e.currentTarget.style.textDecoration = 'underline'; }}
                  onMouseLeave={(e) => { e.currentTarget.style.textDecoration = 'none'; }}
                >
                  {crumb.label}
                </span>
              ) : (
                <span style={{ fontWeight: 600, color: light ? 'white' : 'var(--color-text, #111)' }}>
                  {crumb.label}
                </span>
              )}
            </span>
          ))}
        </nav>
      )}
    </div>
  );
};

export default BackButton;
