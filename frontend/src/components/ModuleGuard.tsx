/**
 * ModuleGuard — React Router v6 layout-route guard for module-level access control.
 *
 * Usage (layout route pattern in App.tsx):
 *   <Route element={<ModuleGuard module="accounting" />}>
 *     <Route path="/accounting/dashboard" element={<ProtectedRoute>...</ProtectedRoute>} />
 *   </Route>
 *
 * When the module is disabled (toggled off by superadmin globally or per-tenant),
 * every child route renders a "Module Disabled" result page instead of the real page.
 * The sidebar already hides the nav item; this guard ensures direct URL navigation
 * is also blocked.
 */
import { Outlet, useNavigate } from 'react-router-dom';
import { Result, Button, Space, Tag } from 'antd';
import { LockOutlined, AppstoreOutlined } from '@ant-design/icons';
import { useTenantModules } from '../hooks/useTenantModules';

const MODULE_META: Record<string, { title: string; icon: string; color: string }> = {
  accounting:  { title: 'Accounting',          icon: '📒', color: '#1677ff' },
  dimensions:  { title: 'Dimensions',           icon: '🗂️', color: '#722ed1' },
  budget:      { title: 'Budget Management',    icon: '💰', color: '#52c41a' },
  procurement: { title: 'Procurement',          icon: '🛒', color: '#fa8c16' },
  contracts:   { title: 'Contracts & Milestones', icon: '🤝', color: '#0ea5e9' },
  inventory:   { title: 'Inventory',            icon: '📦', color: '#13c2c2' },
  hrm:         { title: 'Human Resources',      icon: '👥', color: '#eb2f96' },
  workflow:    { title: 'Workflow & Approvals', icon: '🔀', color: '#722ed1' },
};

interface ModuleGuardProps {
  /** The module key, e.g. "accounting", "hrm", etc. */
  module: string;
}

const ModuleDisabledPage = ({ module }: { module: string }) => {
  const navigate = useNavigate();
  const meta = MODULE_META[module] ?? { title: module, icon: '🔒', color: '#d9d9d9' };

  return (
    <div
      style={{
        minHeight: '70vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '48px 24px',
      }}
    >
      <Result
        icon={
          <div
            style={{
              width: 96,
              height: 96,
              borderRadius: 24,
              background: `linear-gradient(135deg, ${meta.color}22, ${meta.color}44)`,
              border: `2px solid ${meta.color}44`,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: 44,
              margin: '0 auto',
            }}
          >
            <LockOutlined style={{ color: meta.color, fontSize: 40 }} />
          </div>
        }
        title={
          <Space direction="vertical" size={4} align="center">
            <span style={{ fontSize: 20, fontWeight: 700, color: '#262626' }}>
              {meta.icon} {meta.title} — Module Disabled
            </span>
            <Tag
              color="warning"
              style={{ borderRadius: 6, fontSize: 12, fontWeight: 500 }}
            >
              Access Restricted
            </Tag>
          </Space>
        }
        subTitle={
          <span style={{ color: '#8c8c8c', fontSize: 14, lineHeight: 1.7 }}>
            The <strong>{meta.title}</strong> module has been deactivated by your system
            administrator. All features and data within this module are temporarily
            unavailable.
            <br />
            Contact your administrator to re-enable access.
          </span>
        }
        extra={
          <Space>
            <Button
              type="primary"
              icon={<AppstoreOutlined />}
              onClick={() => navigate('/dashboard')}
              style={{ borderRadius: 8 }}
            >
              Go to Dashboard
            </Button>
            <Button
              onClick={() => window.history.back()}
              style={{ borderRadius: 8 }}
            >
              Go Back
            </Button>
          </Space>
        }
        style={{ maxWidth: 520 }}
      />
    </div>
  );
};

/**
 * Layout-route guard — must be used as the `element` of a pathless <Route>.
 * Renders <Outlet /> (the matched child route) when the module is active,
 * or <ModuleDisabledPage /> when deactivated.
 */
const ModuleGuard = ({ module }: ModuleGuardProps) => {
  const { data: tenantModules, isLoading } = useTenantModules();

  // While loading, render the outlet so the page doesn't flash.
  // The sidebar already handles the loading state by showing all items.
  if (isLoading) return <Outlet />;

  const enabledModules = tenantModules?.enabled_modules ?? {};
  const hasConfiguration = Object.keys(enabledModules).length > 0;

  // If the backend returned no module config (fresh tenant or API error),
  // allow access to everything — this matches the sidebar fallback behaviour.
  if (!hasConfiguration) return <Outlet />;

  const isEnabled = enabledModules[module] === true;
  if (!isEnabled) return <ModuleDisabledPage module={module} />;

  return <Outlet />;
};

export default ModuleGuard;
