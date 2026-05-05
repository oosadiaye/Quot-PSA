import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { lazy, Suspense } from 'react';
import { ThemeProvider } from './context/ThemeContext';
import { CurrencyProvider } from './context/CurrencyContext';
import { AuthProvider } from './context/AuthContext';
import { BrandingProvider } from './context/BrandingContext';
import { ToastProvider } from './context/ToastContext';
import ToastContainer from './components/ToastContainer';
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
import GovernmentDashboard from './pages/GovernmentDashboard';
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
const FixedAssetForm = lazy(() => import('./features/accounting/assets/FixedAssetForm'));
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
// Intercompany removed — public sector does not use intercompany accounting

// ── Government IFMIS Pages (Phase 10) ────────────────────
const AppropriationList = lazy(() => import('./pages/gov').then(m => ({ default: m.AppropriationList })));
const AppropriationListByMda = lazy(() => import('./pages/gov').then(m => ({ default: m.AppropriationListByMda })));
const WarrantList = lazy(() => import('./pages/gov').then(m => ({ default: m.WarrantList })));
const RevenueBudgetList = lazy(() => import('./pages/gov').then(m => ({ default: m.RevenueBudgetList })));
const TSAAccountList = lazy(() => import('./pages/gov').then(m => ({ default: m.TSAAccountList })));
const PaymentVoucherList = lazy(() => import('./pages/gov').then(m => ({ default: m.PaymentVoucherList })));
const PaymentInstructionList = lazy(() => import('./pages/gov').then(m => ({ default: m.PaymentInstructionList })));
const RevenueHeadList = lazy(() => import('./pages/gov').then(m => ({ default: m.RevenueHeadList })));
const RevenueCollectionList = lazy(() => import('./pages/gov').then(m => ({ default: m.RevenueCollectionList })));
const NCoAEconomicList = lazy(() => import('./pages/gov').then(m => ({ default: m.NCoAEconomicList })));
const NCoAAdminList = lazy(() => import('./pages/gov').then(m => ({ default: m.NCoAAdminList })));
const NCoAFunctionalList = lazy(() => import('./pages/gov').then(m => ({ default: m.NCoAFunctionalList })));
const NCoAProgrammeList = lazy(() => import('./pages/gov').then(m => ({ default: m.NCoAProgrammeList })));
const NCoAFundList = lazy(() => import('./pages/gov').then(m => ({ default: m.NCoAFundList })));
const NCoAGeoList = lazy(() => import('./pages/gov').then(m => ({ default: m.NCoAGeoList })));
const NCoACodeList = lazy(() => import('./pages/gov').then(m => ({ default: m.NCoACodeList })));
const ProcurementThresholdList = lazy(() => import('./pages/gov').then(m => ({ default: m.ProcurementThresholdList })));
const NoObjectionList = lazy(() => import('./pages/gov').then(m => ({ default: m.NoObjectionList })));

// ── Government Form Pages ────────────────────────────────
const PaymentVoucherForm = lazy(() => import('./pages/gov/PaymentVoucherForm'));
const RevenueCollectionForm = lazy(() => import('./pages/gov/RevenueCollectionForm'));
const AppropriationForm = lazy(() => import('./pages/gov/AppropriationForm'));
const AppropriationDetail = lazy(() => import('./pages/gov/AppropriationDetail'));
const AppropriationTransactions = lazy(() => import('./pages/gov/AppropriationTransactions'));
const VirementForm = lazy(() => import('./pages/gov/VirementForm'));
const WarrantForm = lazy(() => import('./pages/gov/WarrantForm'));
const WarrantDetail = lazy(() => import('./pages/gov/WarrantDetail'));
const RevenueBudgetForm = lazy(() => import('./pages/gov/RevenueBudgetForm'));
const TSAAccountForm = lazy(() => import('./pages/gov/TSAAccountForm'));
const TSALedger = lazy(() => import('./pages/gov/TSALedger'));
const BankReconciliation = lazy(() => import('./pages/gov/BankReconciliation'));
const NCoAAdminForm = lazy(() => import('./pages/gov/NCoAAdminForm'));
const NCoAFunctionalForm = lazy(() => import('./pages/gov/NCoAFunctionalForm'));
const NCoAProgrammeForm = lazy(() => import('./pages/gov/NCoAProgrammeForm'));
const NCoAFundForm = lazy(() => import('./pages/gov/NCoAFundForm'));
const NCoAGeoForm = lazy(() => import('./pages/gov/NCoAGeoForm'));

// ── Government Detail Pages ──────────────────────────────
const PaymentVoucherDetail = lazy(() => import('./pages/gov/PaymentVoucherDetail'));
const RevenueCollectionDetail = lazy(() => import('./pages/gov/RevenueCollectionDetail'));

// ── IPSAS Report Pages ───────────────────────────────────
const FinancialPositionReport = lazy(() => import('./pages/gov/reports/FinancialPositionReport'));
const FinancialPerformanceReport = lazy(() => import('./pages/gov/reports/FinancialPerformanceReport'));
const BudgetPerformanceReport = lazy(() => import('./pages/gov/reports/BudgetPerformanceReport'));
const WarrantUtilizationReport = lazy(() => import('./pages/gov/reports/WarrantUtilizationReport'));
const CashFlowStatementReport = lazy(() => import('./pages/gov/reports/CashFlowStatementReport'));
const ChangesInNetAssetsReport = lazy(() => import('./pages/gov/reports/ChangesInNetAssetsReport'));
const NotesToFinancialStatementsReport = lazy(() => import('./pages/gov/reports/NotesToFinancialStatementsReport'));
const BudgetVsActualReport = lazy(() => import('./pages/gov/reports/BudgetVsActualReport'));
const RevenuePerformanceReport = lazy(() => import('./pages/gov/reports/RevenuePerformanceReport'));
const TSACashPositionReport = lazy(() => import('./pages/gov/reports/TSACashPositionReport'));
const FunctionalClassificationReport = lazy(() => import('./pages/gov/reports/FunctionalClassificationReport'));
const ProgrammePerformanceReport = lazy(() => import('./pages/gov/reports/ProgrammePerformanceReport'));
const GeographicDistributionReport = lazy(() => import('./pages/gov/reports/GeographicDistributionReport'));
const FundPerformanceReport = lazy(() => import('./pages/gov/reports/FundPerformanceReport'));
const CommitmentReport = lazy(() => import('./pages/gov/reports/CommitmentReport'));
const DataQualityPage = lazy(() => import('./pages/gov/DataQualityPage'));
const RolesAndPermissionsPage = lazy(() => import('./pages/gov/RolesAndPermissionsPage'));
const ApprovalRulesPage = lazy(() => import('./pages/gov/ApprovalRulesPage'));
const OverrideAuditPage = lazy(() => import('./pages/gov/OverrideAuditPage'));
const FiscalYearAdminPage = lazy(() => import('./pages/gov/FiscalYearAdminPage'));
const AppropriationAdminPage = lazy(() => import('./pages/gov/AppropriationAdminPage'));
const ExecutionReport = lazy(() => import('./pages/gov/reports/ExecutionReport'));
const GovernmentSetup = lazy(() => import('./pages/gov/GovernmentSetup'));
const OrganizationManagement = lazy(() => import('./pages/gov/OrganizationManagement'));
const AuditTrailViewer = lazy(() => import('./pages/gov/AuditTrailViewer'));

// ── Financial Reports ────────────────────────────────────
const TrialBalance = lazy(() => import('./features/accounting/reports/TrialBalance'));
const BalanceSheet = lazy(() => import('./features/accounting/reports/BalanceSheet'));
const ProfitLoss = lazy(() => import('./features/accounting/reports/ProfitLoss'));
const CashFlowStatement = lazy(() => import('./features/accounting/reports/CashFlow'));
const PeriodClose = lazy(() => import('./features/accounting/reports/PeriodClose'));

// ── Budget ────────────────────────────────────────────────
import BudgetLayout from './features/accounting/budget/BudgetLayout';
const BudgetDashboard = lazy(() => import('./features/accounting/budget/pages/BudgetDashboard'));
const BudgetEntry = lazy(() => import('./features/accounting/budget/pages/BudgetEntry'));
const VarianceAnalysis = lazy(() => import('./features/accounting/budget/pages/VarianceAnalysis'));
const BudgetCreate = lazy(() => import('./features/accounting/budget/pages/BudgetCreate'));

// ── Procurement ───────────────────────────────────────────
const ProcurementDashboard = lazy(() => import('./features/procurement/ProcurementDashboard'));
const VendorList = lazy(() => import('./features/procurement/VendorList'));
const ExpiredVendors = lazy(() => import('./pages/gov/ExpiredVendors'));
const PurchaseOrderList = lazy(() => import('./features/procurement/PurchaseOrderList'));
const POForm = lazy(() => import('./features/procurement/POForm'));
const PurchaseRequisitions = lazy(() => import('./features/procurement/PurchaseRequisitions'));
const PurchaseRequisitionForm = lazy(() => import('./features/procurement/PurchaseRequisitionForm'));
const PurchaseRequisitionView = lazy(() => import('./features/procurement/PurchaseRequisitionView'));
const GoodsReceivedNotes = lazy(() => import('./features/procurement/GoodsReceivedNotes'));
const GRNForm = lazy(() => import('./features/procurement/GRNForm'));
const GRNView = lazy(() => import('./features/procurement/GRNView'));
const InvoiceMatchingPage = lazy(() => import('./features/procurement/InvoiceMatching'));
const NewInvoiceMatching = lazy(() => import('./features/procurement/NewInvoiceMatching'));
const InvoiceMatchingView = lazy(() => import('./features/procurement/InvoiceMatchingView'));
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

// ── Workflow & Approvals ──────────────────────────────────
const WorkflowInbox = lazy(() => import('./features/workflow/WorkflowInbox'));
const ApprovalDashboard = lazy(() => import('./features/workflow/ApprovalDashboard'));
const ApprovalGroups = lazy(() => import('./features/workflow/pages/ApprovalGroups'));
const ApprovalTemplates = lazy(() => import('./features/workflow/pages/ApprovalTemplates'));
const ApprovalHistory = lazy(() => import('./features/workflow/pages/ApprovalHistory'));

// ── Settings ─────────────────────────────────────────────
const AccountingSettingsPage  = lazy(() => import('./features/settings/AccountingSettings'));
const BudgetCheckRulesSettings = lazy(() => import('./features/settings/BudgetCheckRulesSettings'));
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

// ── User Management ──────────────────────────────────────────
const UserManagement = lazy(() => import('./pages/UserManagement'));

// ── Employee Self-Service Portal ─────────────────────────────
const MyDashboard = lazy(() => import('./features/portal/pages/MyDashboard'));
const MyPayslips  = lazy(() => import('./features/portal/pages/MyPayslips'));
const MyLeave     = lazy(() => import('./features/portal/pages/MyLeave'));
const MyProfile   = lazy(() => import('./features/portal/pages/MyProfile'));
const MyDocuments = lazy(() => import('./features/portal/pages/MyDocuments'));

// ── Contracts & Milestone Payments ───────────────────────────
const ContractsDashboard  = lazy(() => import('./features/contracts/ContractsDashboard'));
const ContractsList       = lazy(() => import('./features/contracts/ContractsList'));
const ContractDetail      = lazy(() => import('./features/contracts/ContractDetail'));
const ContractForm        = lazy(() => import('./features/contracts/ContractForm'));
const IPCList             = lazy(() => import('./features/contracts/ipcs/IPCList'));
const IPCSubmitForm       = lazy(() => import('./features/contracts/ipcs/IPCSubmitForm'));
const IPCDetail           = lazy(() => import('./features/contracts/ipcs/IPCDetail'));
const VariationList       = lazy(() => import('./features/contracts/variations/VariationList'));
const VariationForm       = lazy(() => import('./features/contracts/variations/VariationForm'));
const VariationDetail     = lazy(() => import('./features/contracts/variations/VariationDetail'));

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
import { useSearchParams } from 'react-router-dom';

/**
 * Wrapper that shows a loading screen when `?impersonation=pending` is in the URL,
 * preventing the LandingPage from flashing before ImpersonationHandler redirects.
 */
function LandingOrImpersonation() {
  const [searchParams] = useSearchParams();
  if (searchParams.get('impersonation') === 'pending') {
    return <LoadingScreen message="Setting up impersonation session..." />;
  }
  return <LandingPage />;
}

function App() {
  return (
    <AntApp>
      <ThemeProvider>
        <QueryClientProvider client={queryClient}>
          <BrandingProvider>
          <AuthProvider>
            <CurrencyProvider>
              <ToastProvider>
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
                  {/* Inner ErrorBoundary scopes route crashes to the
                      content area — the outer ErrorBoundary at the
                      top-level catches anything that escapes; this
                      one absorbs lazy-route render errors so the
                      sidebar + nav stay mounted and the user can
                      navigate to a different page without reloading. */}
                  <Suspense fallback={<LoadingScreen message="Starting application..." />}>
                    <ErrorBoundary>
                    <Routes>
                      {/* ── Public / Auth ────────────────────────────── */}
                      <Route path="/" element={<LandingOrImpersonation />} />
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

                      {/* ── Government IFMIS Dashboard ────────────────── */}
                      <Route path="/dashboard" element={
                        <ProtectedRoute><GovernmentDashboard /></ProtectedRoute>
                      } />
                      <Route path="/dashboard/legacy" element={
                        <ProtectedRoute><Dashboard /></ProtectedRoute>
                      } />

                      {/* ── Employee Self-Service Portal ───────────────── */}
                      <Route path="/portal" element={
                        <ProtectedRoute><MyDashboard /></ProtectedRoute>
                      } />
                      <Route path="/portal/payslips" element={
                        <ProtectedRoute><MyPayslips /></ProtectedRoute>
                      } />
                      <Route path="/portal/leave" element={
                        <ProtectedRoute><MyLeave /></ProtectedRoute>
                      } />
                      <Route path="/portal/profile" element={
                        <ProtectedRoute><MyProfile /></ProtectedRoute>
                      } />
                      <Route path="/portal/documents" element={
                        <ProtectedRoute><MyDocuments /></ProtectedRoute>
                      } />

                      {/* ── SuperAdmin (no module guard) ──────────────── */}
                      <Route path="/superadmin" element={
                        <ProtectedRoute requiredPerm="is_superuser"><SuperAdminDashboard /></ProtectedRoute>
                      } />

                      {/* ── User Management (no module guard) ────────── */}
                      <Route path="/user-management" element={
                        <ProtectedRoute requiredRole="senior_manager"><UserManagement /></ProtectedRoute>
                      } />

                      {/* ── Settings (no module guard) ─────────────────
                          All settings routes mutate tenant-wide
                          configuration; gated to ``admin`` role so a
                          ``viewer`` or ``user`` can't reach them. */}
                      <Route path="/settings/accounting" element={
                        <ProtectedRoute requiredRole="admin"><AccountingSettingsPage /></ProtectedRoute>
                      } />
                      <Route path="/settings/accounting/budget-check-rules" element={
                        <ProtectedRoute requiredRole="admin"><BudgetCheckRulesSettings /></ProtectedRoute>
                      } />
                      <Route path="/settings/inventory" element={
                        <ProtectedRoute requiredRole="admin"><InventorySettingsPage /></ProtectedRoute>
                      } />
                      <Route path="/settings/accounting/currencies" element={
                        <ProtectedRoute requiredRole="admin"><CurrencyManagement /></ProtectedRoute>
                      } />
                      <Route path="/settings/fiscal-year" element={
                        <ProtectedRoute requiredRole="admin"><FiscalYearPage /></ProtectedRoute>
                      } />
                      <Route path="/settings/tax" element={
                        <ProtectedRoute requiredRole="admin"><TaxManagement /></ProtectedRoute>
                      } />
                      <Route path="/settings/bank-accounts" element={
                        <ProtectedRoute requiredRole="admin"><BankAccountSettings /></ProtectedRoute>
                      } />
                      <Route path="/settings/branding" element={
                        <ProtectedRoute requiredRole="admin"><BrandingSettings /></ProtectedRoute>
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
                        <Route path="/accounting/journals/:id/edit" element={
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
                        <Route path="/accounting/fixed-assets/new" element={
                          <ProtectedRoute><FixedAssetForm /></ProtectedRoute>
                        } />
                        <Route path="/accounting/asset-categories" element={
                          <ProtectedRoute><AssetCategoriesPage /></ProtectedRoute>
                        } />
                        <Route path="/accounting/reports" element={
                          <ProtectedRoute><GLReports /></ProtectedRoute>
                        } />
                        <Route path="/accounting/reports/trial-balance" element={
                          <ProtectedRoute><TrialBalance /></ProtectedRoute>
                        } />
                        <Route path="/accounting/reports/balance-sheet" element={
                          <ProtectedRoute><BalanceSheet /></ProtectedRoute>
                        } />
                        <Route path="/accounting/reports/income-statement" element={
                          <ProtectedRoute><ProfitLoss /></ProtectedRoute>
                        } />
                        <Route path="/accounting/reports/cash-flow" element={
                          <ProtectedRoute><CashFlowStatement /></ProtectedRoute>
                        } />
                        <Route path="/accounting/reports/period-close" element={
                          <ProtectedRoute><PeriodClose /></ProtectedRoute>
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
                        {/* Intercompany/consolidation removed — public sector */}
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
                        <Route path="/procurement/vendors-expired" element={
                          <ProtectedRoute><ExpiredVendors /></ProtectedRoute>
                        } />
                        <Route path="/procurement/requisitions" element={
                          <ProtectedRoute><PurchaseRequisitions /></ProtectedRoute>
                        } />
                        <Route path="/procurement/requisitions/new" element={
                          <ProtectedRoute><PurchaseRequisitionForm /></ProtectedRoute>
                        } />
                        <Route path="/procurement/requisitions/:id/edit" element={
                          <ProtectedRoute><PurchaseRequisitionForm /></ProtectedRoute>
                        } />
                        <Route path="/procurement/requisitions/:id" element={
                          <ProtectedRoute><PurchaseRequisitionView /></ProtectedRoute>
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
                        <Route path="/procurement/grn/:id" element={
                          <ProtectedRoute><GRNView /></ProtectedRoute>
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
                        <Route path="/procurement/matching/:id" element={
                          <ProtectedRoute><InvoiceMatchingView /></ProtectedRoute>
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

                      {/* ── Government IFMIS Routes (Phase 10) ────── */}
                      <Route path="/budget/appropriations" element={<ProtectedRoute><AppropriationList /></ProtectedRoute>} />
                      <Route path="/budget/appropriations/by-mda/:mda_id" element={<ProtectedRoute><AppropriationListByMda /></ProtectedRoute>} />
                      <Route path="/budget/warrants" element={<ProtectedRoute><WarrantList /></ProtectedRoute>} />
                      <Route path="/budget/revenue-budget" element={<ProtectedRoute><RevenueBudgetList /></ProtectedRoute>} />
                      <Route path="/budget/revenue-budget/new" element={<ProtectedRoute><RevenueBudgetForm /></ProtectedRoute>} />
                      <Route path="/budget/execution-report" element={<ProtectedRoute><ExecutionReport /></ProtectedRoute>} />
                      <Route path="/accounting/tsa-accounts" element={<ProtectedRoute><TSAAccountList /></ProtectedRoute>} />
                      <Route path="/accounting/payment-vouchers" element={<ProtectedRoute><PaymentVoucherList /></ProtectedRoute>} />
                      <Route path="/accounting/payment-instructions" element={<ProtectedRoute><PaymentInstructionList /></ProtectedRoute>} />
                      <Route path="/accounting/revenue-heads" element={<ProtectedRoute><RevenueHeadList /></ProtectedRoute>} />
                      <Route path="/accounting/revenue-collections" element={<ProtectedRoute><RevenueCollectionList /></ProtectedRoute>} />
                      <Route path="/accounting/ncoa/economic" element={<ProtectedRoute><NCoAEconomicList /></ProtectedRoute>} />
                      <Route path="/accounting/ncoa/administrative" element={<ProtectedRoute><NCoAAdminList /></ProtectedRoute>} />
                      <Route path="/accounting/ncoa/administrative/new" element={<ProtectedRoute><NCoAAdminForm /></ProtectedRoute>} />
                      <Route path="/accounting/ncoa/administrative/:id/edit" element={<ProtectedRoute><NCoAAdminForm /></ProtectedRoute>} />
                      <Route path="/accounting/ncoa/functional" element={<ProtectedRoute><NCoAFunctionalList /></ProtectedRoute>} />
                      <Route path="/accounting/ncoa/functional/new" element={<ProtectedRoute><NCoAFunctionalForm /></ProtectedRoute>} />
                      <Route path="/accounting/ncoa/functional/:id/edit" element={<ProtectedRoute><NCoAFunctionalForm /></ProtectedRoute>} />
                      <Route path="/accounting/ncoa/programme" element={<ProtectedRoute><NCoAProgrammeList /></ProtectedRoute>} />
                      <Route path="/accounting/ncoa/programme/new" element={<ProtectedRoute><NCoAProgrammeForm /></ProtectedRoute>} />
                      <Route path="/accounting/ncoa/programme/:id/edit" element={<ProtectedRoute><NCoAProgrammeForm /></ProtectedRoute>} />
                      <Route path="/accounting/ncoa/fund" element={<ProtectedRoute><NCoAFundList /></ProtectedRoute>} />
                      <Route path="/accounting/ncoa/fund/new" element={<ProtectedRoute><NCoAFundForm /></ProtectedRoute>} />
                      <Route path="/accounting/ncoa/fund/:id/edit" element={<ProtectedRoute><NCoAFundForm /></ProtectedRoute>} />
                      <Route path="/accounting/ncoa/geographic" element={<ProtectedRoute><NCoAGeoList /></ProtectedRoute>} />
                      <Route path="/accounting/ncoa/geographic/new" element={<ProtectedRoute><NCoAGeoForm /></ProtectedRoute>} />
                      <Route path="/accounting/ncoa/geographic/:id/edit" element={<ProtectedRoute><NCoAGeoForm /></ProtectedRoute>} />
                      <Route path="/accounting/ncoa/codes" element={<ProtectedRoute><NCoACodeList /></ProtectedRoute>} />
                      <Route path="/procurement/thresholds" element={<ProtectedRoute><ProcurementThresholdList /></ProtectedRoute>} />
                      <Route path="/procurement/no-objection" element={<ProtectedRoute><NoObjectionList /></ProtectedRoute>} />

                      {/* ── Government Form Pages ────────────────── */}
                      <Route path="/accounting/payment-vouchers/new" element={<ProtectedRoute><PaymentVoucherForm /></ProtectedRoute>} />
                      <Route path="/accounting/payment-vouchers/:id" element={<ProtectedRoute><PaymentVoucherDetail /></ProtectedRoute>} />
                      <Route path="/accounting/revenue-collections/new" element={<ProtectedRoute><RevenueCollectionForm /></ProtectedRoute>} />
                      <Route path="/accounting/revenue-collections/:id" element={<ProtectedRoute><RevenueCollectionDetail /></ProtectedRoute>} />
                      <Route path="/budget/appropriations/new" element={<ProtectedRoute><AppropriationForm /></ProtectedRoute>} />
                      <Route path="/budget/virements/new" element={<ProtectedRoute><VirementForm /></ProtectedRoute>} />
                      <Route path="/budget/appropriations/:id" element={<ProtectedRoute><AppropriationDetail /></ProtectedRoute>} />
                      <Route path="/budget/appropriations/:id/transactions" element={<ProtectedRoute><AppropriationTransactions /></ProtectedRoute>} />
                      <Route path="/budget/warrants/new" element={<ProtectedRoute><WarrantForm /></ProtectedRoute>} />
                      <Route path="/budget/warrants/:id" element={<ProtectedRoute><WarrantDetail /></ProtectedRoute>} />
                      <Route path="/accounting/tsa-accounts/new" element={<ProtectedRoute><TSAAccountForm /></ProtectedRoute>} />
                      <Route path="/accounting/tsa-accounts/:id/edit" element={<ProtectedRoute><TSAAccountForm /></ProtectedRoute>} />
                      <Route path="/accounting/tsa-accounts/:id/ledger" element={<ProtectedRoute><TSALedger /></ProtectedRoute>} />
                      <Route path="/accounting/bank-reconciliation" element={<ProtectedRoute><BankReconciliation /></ProtectedRoute>} />

                      {/* ── IPSAS Report Pages ───────────────────── */}
                      <Route path="/accounting/ipsas/financial-position" element={<ProtectedRoute><FinancialPositionReport /></ProtectedRoute>} />
                      <Route path="/accounting/ipsas/financial-performance" element={<ProtectedRoute><FinancialPerformanceReport /></ProtectedRoute>} />
                      <Route path="/accounting/ipsas/budget-performance" element={<ProtectedRoute><BudgetPerformanceReport /></ProtectedRoute>} />
                      <Route path="/budget/warrant-utilization" element={<ProtectedRoute><WarrantUtilizationReport /></ProtectedRoute>} />
                      <Route path="/accounting/ipsas/cash-flow" element={<ProtectedRoute><CashFlowStatementReport /></ProtectedRoute>} />
                      <Route path="/accounting/ipsas/changes-in-net-assets" element={<ProtectedRoute><ChangesInNetAssetsReport /></ProtectedRoute>} />
                      <Route path="/accounting/ipsas/notes" element={<ProtectedRoute><NotesToFinancialStatementsReport /></ProtectedRoute>} />
                      <Route path="/accounting/ipsas/budget-vs-actual" element={<ProtectedRoute><BudgetVsActualReport /></ProtectedRoute>} />
                      <Route path="/accounting/ipsas/revenue-performance" element={<ProtectedRoute><RevenuePerformanceReport /></ProtectedRoute>} />
                      <Route path="/accounting/ipsas/tsa-cash-position" element={<ProtectedRoute><TSACashPositionReport /></ProtectedRoute>} />
                      <Route path="/accounting/ipsas/functional-classification" element={<ProtectedRoute><FunctionalClassificationReport /></ProtectedRoute>} />
                      <Route path="/accounting/ipsas/programme-performance" element={<ProtectedRoute><ProgrammePerformanceReport /></ProtectedRoute>} />
                      <Route path="/accounting/ipsas/geographic-distribution" element={<ProtectedRoute><GeographicDistributionReport /></ProtectedRoute>} />
                      <Route path="/accounting/ipsas/fund-performance" element={<ProtectedRoute><FundPerformanceReport /></ProtectedRoute>} />
                      <Route path="/accounting/data-quality" element={<ProtectedRoute><DataQualityPage /></ProtectedRoute>} />
                      {/* Admin-only routes — gated by ``requiredRole='admin'``.
                          Previously these were bare ``ProtectedRoute`` so any
                          authenticated user (including ``viewer``) could reach
                          mutating role/approval/audit/fiscal-year config
                          screens. */}
                      <Route path="/admin/roles" element={<ProtectedRoute requiredRole="admin"><RolesAndPermissionsPage /></ProtectedRoute>} />
                      <Route path="/admin/approval-rules" element={<ProtectedRoute requiredRole="admin"><ApprovalRulesPage /></ProtectedRoute>} />
                      <Route path="/admin/audit/overrides" element={<ProtectedRoute requiredRole="admin"><OverrideAuditPage /></ProtectedRoute>} />
                      <Route path="/admin/fiscal-years" element={<ProtectedRoute requiredRole="admin"><FiscalYearAdminPage /></ProtectedRoute>} />
                      <Route path="/budget/appropriations" element={<ProtectedRoute><AppropriationAdminPage /></ProtectedRoute>} />
                      <Route path="/budget/commitment-report" element={<ProtectedRoute><CommitmentReport /></ProtectedRoute>} />
                      <Route path="/settings/government" element={<ProtectedRoute requiredRole="admin"><GovernmentSetup /></ProtectedRoute>} />
                      <Route path="/settings/organizations" element={<ProtectedRoute requiredRole="admin"><OrganizationManagement /></ProtectedRoute>} />
                      <Route path="/audit/trail" element={<ProtectedRoute><AuditTrailViewer /></ProtectedRoute>} />

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

                      {/* Production, Quality removed — Quot PSE is public sector only */}

                      {/* ── Contracts module ─────────────────────────── */}
                      <Route element={<ModuleGuard module="contracts" />}>
                        <Route path="/contracts/dashboard" element={
                          <ProtectedRoute><ContractsDashboard /></ProtectedRoute>
                        } />
                        <Route path="/contracts" element={
                          <ProtectedRoute><ContractsList /></ProtectedRoute>
                        } />
                        <Route path="/contracts/new" element={
                          <ProtectedRoute><ContractForm /></ProtectedRoute>
                        } />
                        <Route path="/contracts/:id/edit" element={
                          <ProtectedRoute><ContractForm /></ProtectedRoute>
                        } />
                        <Route path="/contracts/:id" element={
                          <ProtectedRoute><ContractDetail /></ProtectedRoute>
                        } />
                        <Route path="/contracts/:id/ipcs/new" element={
                          <ProtectedRoute><IPCSubmitForm /></ProtectedRoute>
                        } />
                        <Route path="/contracts/:id/variations/new" element={
                          <ProtectedRoute><VariationForm /></ProtectedRoute>
                        } />
                        <Route path="/contracts/ipcs" element={
                          <ProtectedRoute><IPCList /></ProtectedRoute>
                        } />
                        <Route path="/contracts/ipcs/:id" element={
                          <ProtectedRoute><IPCDetail /></ProtectedRoute>
                        } />
                        <Route path="/contracts/variations" element={
                          <ProtectedRoute><VariationList /></ProtectedRoute>
                        } />
                        <Route path="/contracts/variations/:id" element={
                          <ProtectedRoute><VariationDetail /></ProtectedRoute>
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
                    </ErrorBoundary>
                  </Suspense>
                </Router>
                {/* ToastContainer is rendered OUTSIDE Router so it
                    survives route transitions; it's still inside
                    ToastProvider so it has access to the toasts list.
                    Renders nothing when there are no active toasts. */}
                <ToastContainer />
              </ErrorBoundary>
              </ToastProvider>
            </CurrencyProvider>
          </AuthProvider>
          </BrandingProvider>
        </QueryClientProvider>
      </ThemeProvider>
    </AntApp>
  );
}

export default App;
