import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { lazy, Suspense } from 'react';
import { ThemeProvider } from './context/ThemeContext';
import { CurrencyProvider } from './context/CurrencyContext';
import { AuthProvider } from './context/AuthContext';
import { BrandingProvider } from './context/BrandingContext';
import LoadingScreen from './components/common/LoadingScreen';
import ProtectedRoute from './components/ProtectedRoute';
import ErrorBoundary from './components/ErrorBoundary';
import ModuleGuard from './components/ModuleGuard';
import Login from './pages/Login';
import Register from './pages/Register';
import ForgotPassword from './pages/ForgotPassword';
import ResetPassword from './pages/ResetPassword';
import VerifyEmail from './pages/VerifyEmail';
import AccountProfile from './pages/AccountProfile';
import Dashboard from './pages/Dashboard';
import SuperAdminDashboard from './pages/superadmin/SuperAdminDashboard';
import ImpersonationBanner from './components/ImpersonationBanner';
import ImpersonationHandler from './components/ImpersonationHandler';
import LandingPage from './pages/public/LandingPage';
import PricingPage from './pages/public/PricingPage';
import ModuleDetailPage from './pages/public/ModuleDetailPage';
import SetupWizard from './pages/SetupWizard';

// ── Accounting ────────────────────────────────────────────
const AccountingDashboard = lazy(() => import('./features/accounting/AccountingDashboard'));
const JournalList = lazy(() => import('./features/accounting/JournalList'));
const JournalForm = lazy(() => import('./features/accounting/JournalForm'));
const ChartOfAccounts = lazy(() => import('./features/accounting/coa/ChartOfAccounts'));
const APManagement = lazy(() => import('./features/accounting/ap/APManagement'));
const ARManagement = lazy(() => import('./features/accounting/ar/ARManagement'));
const IncomingPaymentsPage = lazy(() => import('./features/accounting/ar/IncomingPaymentsPage'));
const OutgoingPaymentsPage = lazy(() => import('./features/accounting/ap/OutgoingPaymentsPage'));
const FixedAssets = lazy(() => import('./features/accounting/assets/FixedAssets'));
const AssetCategoriesPage = lazy(() => import('./features/accounting/assets/AssetCategories'));
const GLReports = lazy(() => import('./features/accounting/reports/GLReports'));
const FundManagement = lazy(() => import('./features/accounting/pages/FundManagement'));
const FunctionManagement = lazy(() => import('./features/accounting/pages/FunctionManagement'));
const ProgramManagement = lazy(() => import('./features/accounting/pages/ProgramManagement'));
const GeoManagement = lazy(() => import('./features/accounting/pages/GeoManagement'));
const DimensionsDashboard = lazy(() => import('./features/accounting/pages/DimensionsDashboard'));
const BankCashDashboard = lazy(() => import('./features/accounting/bank-cash/BankCashDashboard'));
const CashAccountsPage = lazy(() => import('./features/accounting/cash/CashAccountsPage'));
const FiscalYearPage = lazy(() => import('./features/accounting/fiscal-year/FiscalYearPage'));
const TaxManagement = lazy(() => import('./features/accounting/tax/TaxManagement'));
const CostCenters = lazy(() => import('./features/accounting/CostCenters'));
const RecurringJournalList = lazy(() => import('./features/accounting/RecurringJournalList'));
const RecurringJournalForm = lazy(() => import('./features/accounting/RecurringJournalForm'));
const AccrualDeferralList = lazy(() => import('./features/accounting/AccrualDeferralList'));
const AccrualDeferralForm = lazy(() => import('./features/accounting/AccrualDeferralForm'));
const MultiCompanyPage = lazy(() => import('./features/accounting/multi-company/MultiCompanyPage'));
const InterCompanyPage = lazy(() => import('./features/accounting/multi-company/InterCompanyPage'));
const ConsolidationPage = lazy(() => import('./features/accounting/multi-company/ConsolidationPage'));

// ── Budget ────────────────────────────────────────────────
import BudgetLayout from './features/accounting/budget/BudgetLayout';
const BudgetDashboard = lazy(() => import('./features/accounting/budget/pages/BudgetDashboard'));
const BudgetEntry = lazy(() => import('./features/accounting/budget/pages/BudgetEntry'));
const VarianceAnalysis = lazy(() => import('./features/accounting/budget/pages/VarianceAnalysis'));
const BudgetCreate = lazy(() => import('./features/accounting/budget/pages/BudgetCreate'));

// ── Procurement ───────────────────────────────────────────
const ProcurementDashboard = lazy(() => import('./features/procurement/ProcurementDashboard'));
const VendorList = lazy(() => import('./features/procurement/VendorList'));
const PurchaseOrderList = lazy(() => import('./features/procurement/PurchaseOrderList'));
const POForm = lazy(() => import('./features/procurement/POForm'));
const PurchaseRequisitions = lazy(() => import('./features/procurement/PurchaseRequisitions'));
const PurchaseRequisitionForm = lazy(() => import('./features/procurement/PurchaseRequisitionForm'));
const GoodsReceivedNotes = lazy(() => import('./features/procurement/GoodsReceivedNotes'));
const GRNForm = lazy(() => import('./features/procurement/GRNForm'));
const InvoiceMatchingPage = lazy(() => import('./features/procurement/InvoiceMatching'));
const NewInvoiceMatching = lazy(() => import('./features/procurement/NewInvoiceMatching'));
const VendorPerformance = lazy(() => import('./features/procurement/VendorPerformance'));
const PurchaseReturns = lazy(() => import('./features/procurement/PurchaseReturns'));
const PurchaseReturnForm = lazy(() => import('./features/procurement/PurchaseReturnForm'));
const VendorCategoryList = lazy(() => import('./features/procurement/VendorCategoryList'));

// ── Inventory ─────────────────────────────────────────────
const ItemInventory = lazy(() => import('./features/inventory/ItemInventory'));
const InventoryDashboard = lazy(() => import('./features/inventory/pages/InventoryDashboard'));
const StockValuation = lazy(() => import('./features/inventory/pages/StockValuation'));
const ItemForm = lazy(() => import('./features/inventory/pages/ItemForm'));
const WarehouseList = lazy(() => import('./features/inventory/pages/WarehouseList'));
const StockMovementList = lazy(() => import('./features/inventory/pages/StockMovementList'));
const InventoryAdjustment = lazy(() => import('./features/inventory/pages/InventoryAdjustment'));
const BatchList = lazy(() => import('./features/inventory/pages/BatchList'));
const StockLevelList = lazy(() => import('./features/inventory/pages/StockLevelList'));
const ProductCategoryList = lazy(() => import('./features/inventory/pages/ProductCategoryList'));
const SerialNumberList = lazy(() => import('./features/inventory/pages/SerialNumberList'));
const ReorderAlertList = lazy(() => import('./features/inventory/pages/ReorderAlertList'));
const ExpiryAlertList = lazy(() => import('./features/inventory/pages/ExpiryAlertList'));
const ReconciliationList = lazy(() => import('./features/inventory/pages/ReconciliationList'));
const ProductTypes = lazy(() => import('./features/inventory/pages/ProductTypes'));

// ── Service ───────────────────────────────────────────────
const ServiceDashboard = lazy(() => import('./features/service/ServiceDashboard'));
const WorkOrders = lazy(() => import('./features/service/pages/WorkOrders'));
const CitizenRequests = lazy(() => import('./features/service/pages/CitizenRequests'));
const ServiceMetrics = lazy(() => import('./features/service/pages/ServiceMetrics'));
const ServiceAssets = lazy(() => import('./features/service/pages/ServiceAssets'));
const Technicians = lazy(() => import('./features/service/pages/Technicians'));
const MaintenanceSchedules = lazy(() => import('./features/service/pages/MaintenanceSchedules'));
const ServiceTickets = lazy(() => import('./features/service/pages/ServiceTickets'));
const ServiceTicketDetail = lazy(() => import('./features/service/pages/ServiceTicketDetail'));
const WorkOrderDetail = lazy(() => import('./features/service/pages/WorkOrderDetail'));

// ── Sales ─────────────────────────────────────────────────
const SalesDashboard = lazy(() => import('./features/sales/SalesDashboard'));
const CRMLite = lazy(() => import('./features/sales/pages/CRMLite'));
const Quotations = lazy(() => import('./features/sales/pages/Quotations'));
const SalesOrders = lazy(() => import('./features/sales/pages/SalesOrders'));
const AutomatedInvoicing = lazy(() => import('./features/sales/pages/AutomatedInvoicing'));
const CustomerCreditLimits = lazy(() => import('./features/sales/pages/CustomerCreditLimits'));
const DeliveryNotesList = lazy(() => import('./features/sales/pages/DeliveryNotesList'));
const QuotationForm = lazy(() => import('./features/sales/pages/QuotationForm'));
const SalesOrderForm = lazy(() => import('./features/sales/pages/SalesOrderForm'));
const DeliveryNoteForm = lazy(() => import('./features/sales/pages/DeliveryNoteForm'));
const CustomerList = lazy(() => import('./features/sales/pages/CustomerList'));
const CustomerLedger = lazy(() => import('./features/sales/pages/CustomerLedger'));
const CustomerForm = lazy(() => import('./features/sales/pages/CustomerForm'));
const CustomerCategoryList = lazy(() => import('./features/sales/pages/CustomerCategoryList'));

// ── Workflow & Approvals ──────────────────────────────────
const WorkflowInbox = lazy(() => import('./features/workflow/WorkflowInbox'));
const ApprovalDashboard = lazy(() => import('./features/workflow/ApprovalDashboard'));
const ApprovalGroups = lazy(() => import('./features/workflow/pages/ApprovalGroups'));
const ApprovalTemplates = lazy(() => import('./features/workflow/pages/ApprovalTemplates'));
const ApprovalHistory = lazy(() => import('./features/workflow/pages/ApprovalHistory'));

// ── Settings ─────────────────────────────────────────────
const AccountingSettingsPage  = lazy(() => import('./features/settings/AccountingSettings'));
const InventorySettingsPage   = lazy(() => import('./features/settings/InventorySettingsPage'));
const CurrencyManagement = lazy(() => import('./features/settings/CurrencyManagement'));
const BankAccountSettings = lazy(() => import('./features/settings/BankAccountSettings'));
const BrandingSettings = lazy(() => import('./features/settings/BrandingSettings'));

// ── HRM ───────────────────────────────────────────────────
const HRMDashboard = lazy(() => import('./features/hrm/pages/HRMDashboard'));
const EmployeeList = lazy(() => import('./features/hrm/pages/EmployeeList'));
const EmployeeForm = lazy(() => import('./features/hrm/pages/EmployeeForm'));
const DepartmentList = lazy(() => import('./features/hrm/pages/DepartmentList'));
const PositionList = lazy(() => import('./features/hrm/pages/PositionList'));
const LeaveManagement = lazy(() => import('./features/hrm/pages/LeaveManagement'));
const AttendanceList = lazy(() => import('./features/hrm/pages/AttendanceList'));
const HolidayList = lazy(() => import('./features/hrm/pages/HolidayList'));
const JobPostList = lazy(() => import('./features/hrm/pages/JobPostList'));
const CandidateList = lazy(() => import('./features/hrm/pages/CandidateList'));
const PayrollList = lazy(() => import('./features/hrm/pages/PayrollList'));
const PayslipList = lazy(() => import('./features/hrm/pages/PayslipList'));
const PerformanceList = lazy(() => import('./features/hrm/pages/PerformanceList'));
const TrainingList = lazy(() => import('./features/hrm/pages/TrainingList'));
const SkillList = lazy(() => import('./features/hrm/pages/SkillList'));
const PolicyList = lazy(() => import('./features/hrm/pages/PolicyList'));
const ComplianceList = lazy(() => import('./features/hrm/pages/ComplianceList'));
const ExitManagement = lazy(() => import('./features/hrm/pages/ExitManagement'));

// ── Production ─────────────────────────────────────────────
const ProductionDashboard = lazy(() => import('./features/production/pages/ProductionDashboard'));
const WorkCenterList = lazy(() => import('./features/production/pages/WorkCenterList'));
const BillOfMaterialsList = lazy(() => import('./features/production/pages/BillOfMaterialsList'));
const ProductionOrderList = lazy(() => import('./features/production/pages/ProductionOrderList'));
const ProductionOrderDetail = lazy(() => import('./features/production/pages/ProductionOrderDetail'));

// ── Quality ───────────────────────────────────────────────
const QualityDashboard = lazy(() => import('./features/quality/pages/QualityDashboard'));
const Inspections = lazy(() => import('./features/quality/pages/Inspections'));
const NonConformances = lazy(() => import('./features/quality/pages/NonConformances'));
const CustomerComplaints = lazy(() => import('./features/quality/pages/CustomerComplaints'));
const Checklists = lazy(() => import('./features/quality/pages/Checklists'));
const Calibrations = lazy(() => import('./features/quality/pages/Calibrations'));
const SupplierQuality = lazy(() => import('./features/quality/pages/SupplierQuality'));

// ── User Management ──────────────────────────────────────────
const UserManagement = lazy(() => import('./pages/UserManagement'));

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000,
      gcTime: 10 * 60 * 1000,
      refetchOnWindowFocus: false,
      retry: false,
    },
  },
});

import { App as AntApp } from 'antd';

function App() {
  return (
    <AntApp>
      <ThemeProvider>
        <QueryClientProvider client={queryClient}>
          <BrandingProvider>
          <AuthProvider>
            <CurrencyProvider>
              <ErrorBoundary>
                <Router>
                  {/* Skip navigation link for keyboard / screen-reader users */}
                  <a
                    href="#main-content"
                    className="skip-link"
                    onClick={(e) => {
                      e.preventDefault();
                      const main = document.getElementById('main-content') || document.querySelector('main');
                      if (main) {
                        main.setAttribute('tabindex', '-1');
                        main.focus();
                        main.scrollIntoView();
                      }
                    }}
                  >
                    Skip to main content
                  </a>
                  <ImpersonationBanner />
                  <ImpersonationHandler />
                  <Suspense fallback={<LoadingScreen message="Starting application..." />}>
                    <Routes>
                      {/* ── Public / Auth ────────────────────────────── */}
                      <Route path="/" element={<LandingPage />} />
                      <Route path="/pricing" element={<PricingPage />} />
                      <Route path="/pricing/:moduleName" element={<ModuleDetailPage />} />
                      <Route path="/login" element={<Login />} />
                      <Route path="/register" element={<Register />} />
                      <Route path="/forgot-password" element={<ForgotPassword />} />
                      <Route path="/reset-password" element={<ResetPassword />} />
                      <Route path="/verify-email" element={<VerifyEmail />} />

                      {/* ── Setup Wizard (first login) ──────────────── */}
                      <Route path="/setup" element={
                        <ProtectedRoute><SetupWizard /></ProtectedRoute>
                      } />

                      {/* ── Account / Profile ─────────────────────────── */}
                      <Route path="/account" element={
                        <ProtectedRoute><AccountProfile /></ProtectedRoute>
                      } />

                      {/* ── Main Dashboard (no module guard) ─────────── */}
                      <Route path="/dashboard" element={
                        <ProtectedRoute><Dashboard /></ProtectedRoute>
                      } />

                      {/* ── SuperAdmin (no module guard) ──────────────── */}
                      <Route path="/superadmin" element={
                        <ProtectedRoute requiredPerm="is_superuser"><SuperAdminDashboard /></ProtectedRoute>
                      } />

                      {/* ── User Management (no module guard) ────────── */}
                      <Route path="/user-management" element={
                        <ProtectedRoute requiredRole="senior_manager"><UserManagement /></ProtectedRoute>
                      } />

                      {/* ── Settings (no module guard) ───────────────── */}
                      <Route path="/settings/accounting" element={
                        <ProtectedRoute><AccountingSettingsPage /></ProtectedRoute>
                      } />
                      <Route path="/settings/inventory" element={
                        <ProtectedRoute><InventorySettingsPage /></ProtectedRoute>
                      } />
                      <Route path="/settings/accounting/currencies" element={
                        <ProtectedRoute><CurrencyManagement /></ProtectedRoute>
                      } />
                      <Route path="/settings/fiscal-year" element={
                        <ProtectedRoute><FiscalYearPage /></ProtectedRoute>
                      } />
                      <Route path="/settings/tax" element={
                        <ProtectedRoute><TaxManagement /></ProtectedRoute>
                      } />
                      <Route path="/settings/bank-accounts" element={
                        <ProtectedRoute><BankAccountSettings /></ProtectedRoute>
                      } />
                      <Route path="/settings/branding" element={
                        <ProtectedRoute><BrandingSettings /></ProtectedRoute>
                      } />

                      {/* ══ MODULE-GUARDED ROUTES ════════════════════════
                          Each group is wrapped in a pathless layout route.
                          <ModuleGuard> renders <Outlet/> when active, or a
                          "Module Disabled" page when deactivated by admin.
                      ════════════════════════════════════════════════════ */}

                      {/* ── Accounting module ────────────────────────── */}
                      <Route element={<ModuleGuard module="accounting" />}>
                        <Route path="/accounting/dashboard" element={
                          <ProtectedRoute><AccountingDashboard /></ProtectedRoute>
                        } />
                        <Route path="/accounting" element={
                          <ProtectedRoute><JournalList /></ProtectedRoute>
                        } />
                        <Route path="/accounting/new" element={
                          <ProtectedRoute><JournalForm /></ProtectedRoute>
                        } />
                        <Route path="/accounting/coa" element={
                          <ProtectedRoute><ChartOfAccounts /></ProtectedRoute>
                        } />
                        <Route path="/accounting/currencies" element={
                          <Navigate to="/settings/accounting/currencies" replace />
                        } />
                        <Route path="/accounting/ap" element={
                          <ProtectedRoute><APManagement /></ProtectedRoute>
                        } />
                        <Route path="/accounting/ar" element={
                          <ProtectedRoute><ARManagement /></ProtectedRoute>
                        } />
                        <Route path="/accounting/incoming-payments" element={
                          <ProtectedRoute><IncomingPaymentsPage /></ProtectedRoute>
                        } />
                        <Route path="/accounting/outgoing-payments" element={
                          <ProtectedRoute><OutgoingPaymentsPage /></ProtectedRoute>
                        } />
                        <Route path="/accounting/fixed-assets" element={
                          <ProtectedRoute><FixedAssets /></ProtectedRoute>
                        } />
                        <Route path="/accounting/asset-categories" element={
                          <ProtectedRoute><AssetCategoriesPage /></ProtectedRoute>
                        } />
                        <Route path="/accounting/reports" element={
                          <ProtectedRoute><GLReports /></ProtectedRoute>
                        } />
                        <Route path="/accounting/bank-cash" element={
                          <ProtectedRoute><BankCashDashboard /></ProtectedRoute>
                        } />
                        <Route path="/accounting/bank-cash/:id" element={
                          <ProtectedRoute><BankCashDashboard /></ProtectedRoute>
                        } />
                        <Route path="/accounting/cash-accounts" element={
                          <ProtectedRoute><CashAccountsPage /></ProtectedRoute>
                        } />
                        <Route path="/accounting/tax" element={
                          <Navigate to="/settings/tax" replace />
                        } />
                        <Route path="/accounting/cost-centers" element={
                          <ProtectedRoute><CostCenters /></ProtectedRoute>
                        } />
                        <Route path="/accounting/fiscal-year" element={
                          <Navigate to="/settings/fiscal-year" replace />
                        } />
                        <Route path="/accounting/recurring-journals" element={
                          <ProtectedRoute><RecurringJournalList /></ProtectedRoute>
                        } />
                        <Route path="/accounting/recurring-journals/new" element={
                          <ProtectedRoute><RecurringJournalForm /></ProtectedRoute>
                        } />
                        <Route path="/accounting/recurring-journals/:id" element={
                          <ProtectedRoute><RecurringJournalForm /></ProtectedRoute>
                        } />
                        <Route path="/accounting/accruals-deferrals" element={
                          <ProtectedRoute><AccrualDeferralList /></ProtectedRoute>
                        } />
                        <Route path="/accounting/accruals-deferrals/new/:type" element={
                          <ProtectedRoute><AccrualDeferralForm /></ProtectedRoute>
                        } />
                        <Route path="/accounting/accruals-deferrals/:type/:id" element={
                          <ProtectedRoute><AccrualDeferralForm /></ProtectedRoute>
                        } />
                        <Route path="/accounting/intercompany" element={
                          <ProtectedRoute><InterCompanyPage /></ProtectedRoute>
                        } />
                        <Route path="/accounting/multi-company" element={
                          <ProtectedRoute><MultiCompanyPage /></ProtectedRoute>
                        } />
                        <Route path="/accounting/consolidation" element={
                          <ProtectedRoute><ConsolidationPage /></ProtectedRoute>
                        } />
                      </Route>

                      {/* ── Dimensions module ────────────────────────── */}
                      <Route element={<ModuleGuard module="dimensions" />}>
                        <Route path="/accounting/dimensions" element={
                          <ProtectedRoute><DimensionsDashboard /></ProtectedRoute>
                        } />
                        <Route path="/accounting/dimensions/funds" element={
                          <ProtectedRoute><FundManagement /></ProtectedRoute>
                        } />
                        <Route path="/accounting/dimensions/functions" element={
                          <ProtectedRoute><FunctionManagement /></ProtectedRoute>
                        } />
                        <Route path="/accounting/dimensions/programs" element={
                          <ProtectedRoute><ProgramManagement /></ProtectedRoute>
                        } />
                        <Route path="/accounting/dimensions/geos" element={
                          <ProtectedRoute><GeoManagement /></ProtectedRoute>
                        } />
                      </Route>

                      {/* ── Budget module ─────────────────────────────── */}
                      <Route element={<ModuleGuard module="budget" />}>
                        <Route path="/accounting/budget/dashboard" element={
                          <ProtectedRoute><BudgetLayout><BudgetDashboard /></BudgetLayout></ProtectedRoute>
                        } />
                        <Route path="/accounting/budget/entry" element={
                          <ProtectedRoute><BudgetLayout><BudgetEntry /></BudgetLayout></ProtectedRoute>
                        } />
                        <Route path="/accounting/budget/variance" element={
                          <ProtectedRoute><BudgetLayout><VarianceAnalysis /></BudgetLayout></ProtectedRoute>
                        } />
                        <Route path="/accounting/budget/create" element={
                          <ProtectedRoute><BudgetLayout><BudgetCreate /></BudgetLayout></ProtectedRoute>
                        } />
                      </Route>

                      {/* ── Procurement module ───────────────────────── */}
                      <Route element={<ModuleGuard module="procurement" />}>
                        <Route path="/procurement/dashboard" element={
                          <ProtectedRoute><ProcurementDashboard /></ProtectedRoute>
                        } />
                        <Route path="/procurement/vendors" element={
                          <ProtectedRoute><VendorList /></ProtectedRoute>
                        } />
                        <Route path="/procurement/requisitions" element={
                          <ProtectedRoute><PurchaseRequisitions /></ProtectedRoute>
                        } />
                        <Route path="/procurement/requisitions/new" element={
                          <ProtectedRoute><PurchaseRequisitionForm /></ProtectedRoute>
                        } />
                        <Route path="/procurement/orders/new" element={
                          <ProtectedRoute><POForm /></ProtectedRoute>
                        } />
                        <Route path="/procurement/orders/:id" element={
                          <ProtectedRoute><POForm /></ProtectedRoute>
                        } />
                        <Route path="/procurement/orders" element={
                          <ProtectedRoute><PurchaseOrderList /></ProtectedRoute>
                        } />
                        <Route path="/procurement/requisitions/:prId/convert" element={
                          <ProtectedRoute><POForm /></ProtectedRoute>
                        } />
                        <Route path="/procurement/grn/new" element={
                          <ProtectedRoute><GRNForm /></ProtectedRoute>
                        } />
                        <Route path="/procurement/grn" element={
                          <ProtectedRoute><GoodsReceivedNotes /></ProtectedRoute>
                        } />
                        <Route path="/procurement/matching" element={
                          <ProtectedRoute><InvoiceMatchingPage /></ProtectedRoute>
                        } />
                        <Route path="/procurement/matching/new" element={
                          <ProtectedRoute><NewInvoiceMatching /></ProtectedRoute>
                        } />
                        <Route path="/procurement/vendor-performance" element={
                          <ProtectedRoute><VendorPerformance /></ProtectedRoute>
                        } />
                        <Route path="/procurement/returns" element={
                          <ProtectedRoute><PurchaseReturns /></ProtectedRoute>
                        } />
                        <Route path="/procurement/returns/new" element={
                          <ProtectedRoute><PurchaseReturnForm /></ProtectedRoute>
                        } />
                        <Route path="/procurement/vendor-categories" element={
                          <ProtectedRoute><VendorCategoryList /></ProtectedRoute>
                        } />
                      </Route>

                      {/* ── Inventory module ─────────────────────────── */}
                      <Route element={<ModuleGuard module="inventory" />}>
                        <Route path="/inventory/dashboard" element={
                          <ProtectedRoute><InventoryDashboard /></ProtectedRoute>
                        } />
                        <Route path="/inventory" element={
                          <ProtectedRoute><ItemInventory /></ProtectedRoute>
                        } />
                        <Route path="/inventory/new" element={
                          <ProtectedRoute><ItemForm /></ProtectedRoute>
                        } />
                        <Route path="/inventory/:id" element={
                          <ProtectedRoute><ItemForm /></ProtectedRoute>
                        } />
                        <Route path="/inventory/valuation" element={
                          <ProtectedRoute><StockValuation /></ProtectedRoute>
                        } />
                        <Route path="/inventory/product-types" element={
                          <ProtectedRoute><ProductTypes /></ProtectedRoute>
                        } />
                        <Route path="/inventory/categories" element={
                          <ProtectedRoute><ProductCategoryList /></ProtectedRoute>
                        } />
                        <Route path="/inventory/warehouses" element={
                          <ProtectedRoute><WarehouseList /></ProtectedRoute>
                        } />
                        <Route path="/inventory/stocks" element={
                          <ProtectedRoute><StockLevelList /></ProtectedRoute>
                        } />
                        <Route path="/inventory/batches" element={
                          <ProtectedRoute><BatchList /></ProtectedRoute>
                        } />
                        <Route path="/inventory/adjustments" element={
                          <ProtectedRoute><InventoryAdjustment /></ProtectedRoute>
                        } />
                        <Route path="/inventory/movements" element={
                          <ProtectedRoute><StockMovementList /></ProtectedRoute>
                        } />
                        <Route path="/inventory/reconciliations" element={
                          <ProtectedRoute><ReconciliationList /></ProtectedRoute>
                        } />
                        <Route path="/inventory/reorder-alerts" element={
                          <ProtectedRoute><ReorderAlertList /></ProtectedRoute>
                        } />
                        <Route path="/inventory/serial-numbers" element={
                          <ProtectedRoute><SerialNumberList /></ProtectedRoute>
                        } />
                        <Route path="/inventory/expiry-alerts" element={
                          <ProtectedRoute><ExpiryAlertList /></ProtectedRoute>
                        } />
                      </Route>

                      {/* ── Sales module ─────────────────────────────── */}
                      <Route element={<ModuleGuard module="sales" />}>
                        <Route path="/sales/dashboard" element={
                          <ProtectedRoute><SalesDashboard /></ProtectedRoute>
                        } />
                        <Route path="/sales" element={
                          <ProtectedRoute><SalesDashboard /></ProtectedRoute>
                        } />
                        <Route path="/sales/crm" element={
                          <ProtectedRoute><CRMLite /></ProtectedRoute>
                        } />
                        <Route path="/sales/quotations" element={
                          <ProtectedRoute><Quotations /></ProtectedRoute>
                        } />
                        <Route path="/sales/quotations/new" element={
                          <ProtectedRoute><QuotationForm /></ProtectedRoute>
                        } />
                        <Route path="/sales/quotations/:id" element={
                          <ProtectedRoute><QuotationForm /></ProtectedRoute>
                        } />
                        <Route path="/sales/orders" element={
                          <ProtectedRoute><SalesOrders /></ProtectedRoute>
                        } />
                        <Route path="/sales/orders/new" element={
                          <ProtectedRoute><SalesOrderForm /></ProtectedRoute>
                        } />
                        <Route path="/sales/delivery-notes" element={
                          <ProtectedRoute><DeliveryNotesList /></ProtectedRoute>
                        } />
                        <Route path="/sales/delivery-notes/new" element={
                          <ProtectedRoute><DeliveryNoteForm /></ProtectedRoute>
                        } />
                        <Route path="/sales/customers" element={
                          <ProtectedRoute><CustomerList /></ProtectedRoute>
                        } />
                        <Route path="/sales/customer-categories" element={
                          <ProtectedRoute><CustomerCategoryList /></ProtectedRoute>
                        } />
                        <Route path="/sales/customer/new" element={
                          <ProtectedRoute><CustomerForm /></ProtectedRoute>
                        } />
                        <Route path="/sales/customer/:id/ledger" element={
                          <ProtectedRoute><CustomerLedger /></ProtectedRoute>
                        } />
                        <Route path="/sales/customer/:id" element={
                          <ProtectedRoute><CustomerForm /></ProtectedRoute>
                        } />
                        <Route path="/sales/invoicing" element={
                          <ProtectedRoute><AutomatedInvoicing /></ProtectedRoute>
                        } />
                        <Route path="/sales/credit-limits" element={
                          <ProtectedRoute><CustomerCreditLimits /></ProtectedRoute>
                        } />
                      </Route>

                      {/* ── Service module ───────────────────────────── */}
                      <Route element={<ModuleGuard module="service" />}>
                        <Route path="/service/dashboard" element={
                          <ProtectedRoute><ServiceDashboard /></ProtectedRoute>
                        } />
                        <Route path="/service" element={
                          <ProtectedRoute><ServiceDashboard /></ProtectedRoute>
                        } />
                        <Route path="/service/work-orders" element={
                          <ProtectedRoute><WorkOrders /></ProtectedRoute>
                        } />
                        <Route path="/service/citizen-requests" element={
                          <ProtectedRoute><CitizenRequests /></ProtectedRoute>
                        } />
                        <Route path="/service/metrics" element={
                          <ProtectedRoute><ServiceMetrics /></ProtectedRoute>
                        } />
                        <Route path="/service/assets" element={
                          <ProtectedRoute><ServiceAssets /></ProtectedRoute>
                        } />
                        <Route path="/service/technicians" element={
                          <ProtectedRoute><Technicians /></ProtectedRoute>
                        } />
                        <Route path="/service/tickets" element={
                          <ProtectedRoute><ServiceTickets /></ProtectedRoute>
                        } />
                        <Route path="/service/tickets/:id" element={
                          <ProtectedRoute><ServiceTicketDetail /></ProtectedRoute>
                        } />
                        <Route path="/service/work-orders/:id" element={
                          <ProtectedRoute><WorkOrderDetail /></ProtectedRoute>
                        } />
                        <Route path="/service/schedules" element={
                          <ProtectedRoute><MaintenanceSchedules /></ProtectedRoute>
                        } />
                      </Route>

                      {/* ── HRM module ───────────────────────────────── */}
                      <Route element={<ModuleGuard module="hrm" />}>
                        <Route path="/hrm/dashboard" element={
                          <ProtectedRoute><HRMDashboard /></ProtectedRoute>
                        } />
                        <Route path="/hrm" element={
                          <ProtectedRoute><HRMDashboard /></ProtectedRoute>
                        } />
                        <Route path="/hrm/employees" element={
                          <ProtectedRoute><EmployeeList /></ProtectedRoute>
                        } />
                        <Route path="/hrm/employees/new" element={
                          <ProtectedRoute><EmployeeForm /></ProtectedRoute>
                        } />
                        <Route path="/hrm/employees/:id" element={
                          <ProtectedRoute><EmployeeForm /></ProtectedRoute>
                        } />
                        <Route path="/hrm/departments" element={
                          <ProtectedRoute><DepartmentList /></ProtectedRoute>
                        } />
                        <Route path="/hrm/positions" element={
                          <ProtectedRoute><PositionList /></ProtectedRoute>
                        } />
                        <Route path="/hrm/leave" element={
                          <ProtectedRoute><LeaveManagement /></ProtectedRoute>
                        } />
                        <Route path="/hrm/attendance" element={
                          <ProtectedRoute><AttendanceList /></ProtectedRoute>
                        } />
                        <Route path="/hrm/holidays" element={
                          <ProtectedRoute><HolidayList /></ProtectedRoute>
                        } />
                        <Route path="/hrm/job-posts" element={
                          <ProtectedRoute><JobPostList /></ProtectedRoute>
                        } />
                        <Route path="/hrm/candidates" element={
                          <ProtectedRoute><CandidateList /></ProtectedRoute>
                        } />
                        <Route path="/hrm/payroll" element={
                          <ProtectedRoute><PayrollList /></ProtectedRoute>
                        } />
                        <Route path="/hrm/payslips" element={
                          <ProtectedRoute><PayslipList /></ProtectedRoute>
                        } />
                        <Route path="/hrm/performance" element={
                          <ProtectedRoute><PerformanceList /></ProtectedRoute>
                        } />
                        <Route path="/hrm/training" element={
                          <ProtectedRoute><TrainingList /></ProtectedRoute>
                        } />
                        <Route path="/hrm/skills" element={
                          <ProtectedRoute><SkillList /></ProtectedRoute>
                        } />
                        <Route path="/hrm/policies" element={
                          <ProtectedRoute><PolicyList /></ProtectedRoute>
                        } />
                        <Route path="/hrm/compliance" element={
                          <ProtectedRoute><ComplianceList /></ProtectedRoute>
                        } />
                        <Route path="/hrm/exit" element={
                          <ProtectedRoute><ExitManagement /></ProtectedRoute>
                        } />
                      </Route>

                      {/* ── Production module ────────────────────────── */}
                      <Route element={<ModuleGuard module="production" />}>
                        <Route path="/production/dashboard" element={
                          <ProtectedRoute><ProductionDashboard /></ProtectedRoute>
                        } />
                        <Route path="/production/bom" element={
                          <ProtectedRoute><BillOfMaterialsList /></ProtectedRoute>
                        } />
                        <Route path="/production/work-centers" element={
                          <ProtectedRoute><WorkCenterList /></ProtectedRoute>
                        } />
                        <Route path="/production/orders" element={
                          <ProtectedRoute><ProductionOrderList /></ProtectedRoute>
                        } />
                        <Route path="/production/orders/:id" element={
                          <ProtectedRoute><ProductionOrderDetail /></ProtectedRoute>
                        } />
                      </Route>

                      {/* ── Quality module ───────────────────────────── */}
                      <Route element={<ModuleGuard module="quality" />}>
                        <Route path="/quality/dashboard" element={
                          <ProtectedRoute><QualityDashboard /></ProtectedRoute>
                        } />
                        <Route path="/quality/inspections" element={
                          <ProtectedRoute><Inspections /></ProtectedRoute>
                        } />
                        <Route path="/quality/ncr" element={
                          <ProtectedRoute><NonConformances /></ProtectedRoute>
                        } />
                        <Route path="/quality/complaints" element={
                          <ProtectedRoute><CustomerComplaints /></ProtectedRoute>
                        } />
                        <Route path="/quality/checklists" element={
                          <ProtectedRoute><Checklists /></ProtectedRoute>
                        } />
                        <Route path="/quality/calibrations" element={
                          <ProtectedRoute><Calibrations /></ProtectedRoute>
                        } />
                        <Route path="/quality/supplier-quality" element={
                          <ProtectedRoute><SupplierQuality /></ProtectedRoute>
                        } />
                      </Route>

                      {/* ── Workflow module ──────────────────────────── */}
                      <Route element={<ModuleGuard module="workflow" />}>
                        <Route path="/approvals/dashboard" element={
                          <ProtectedRoute><ApprovalDashboard /></ProtectedRoute>
                        } />
                        <Route path="/approvals" element={
                          <ProtectedRoute><WorkflowInbox /></ProtectedRoute>
                        } />
                        <Route path="/approvals/groups" element={
                          <ProtectedRoute><ApprovalGroups /></ProtectedRoute>
                        } />
                        <Route path="/approvals/templates" element={
                          <ProtectedRoute><ApprovalTemplates /></ProtectedRoute>
                        } />
                        <Route path="/approvals/history" element={
                          <ProtectedRoute><ApprovalHistory /></ProtectedRoute>
                        } />
                        <Route path="/workflow/dashboard" element={
                          <ProtectedRoute><ApprovalDashboard /></ProtectedRoute>
                        } />
                        <Route path="/workflow/inbox" element={
                          <ProtectedRoute><WorkflowInbox /></ProtectedRoute>
                        } />
                        <Route path="/workflow/definitions" element={
                          <ProtectedRoute><ApprovalTemplates /></ProtectedRoute>
                        } />
                        <Route path="/workflow/groups" element={
                          <ProtectedRoute><ApprovalGroups /></ProtectedRoute>
                        } />
                        <Route path="/workflow/instances" element={
                          <ProtectedRoute><ApprovalHistory /></ProtectedRoute>
                        } />
                      </Route>
                    </Routes>
                  </Suspense>
                </Router>
              </ErrorBoundary>
            </CurrencyProvider>
          </AuthProvider>
          </BrandingProvider>
        </QueryClientProvider>
      </ThemeProvider>
    </AntApp>
  );
}

export default App;
