import { Layout, Menu, Typography, Button, Space, ConfigProvider, theme, Modal } from 'antd';
import { useNavigate } from 'react-router-dom';
import {
  BarChartOutlined, ShopOutlined, CrownOutlined, DollarOutlined,
  UserOutlined, AppstoreOutlined, AuditOutlined, ClusterOutlined,
  SettingOutlined, ReloadOutlined, LogoutOutlined,
  TeamOutlined, CustomerServiceOutlined, GlobalOutlined,
  FileTextOutlined, NotificationOutlined,
} from '@ant-design/icons';
import { useState, lazy, Suspense } from 'react';
import { useQueryClient } from '@tanstack/react-query';

const { Header, Sider, Content } = Layout;
const { Title } = Typography;

const OverviewTab = lazy(() => import('./tabs/OverviewTab'));
const TenantsTab = lazy(() => import('./tabs/TenantsTab'));
const PlansTab = lazy(() => import('./tabs/PlansTab'));
const PaymentsTab = lazy(() => import('./tabs/PaymentsTab'));
const UsersTab = lazy(() => import('./tabs/UsersTab'));
const ModulesTab = lazy(() => import('./tabs/ModulesTab'));
const AuditLogsTab = lazy(() => import('./tabs/AuditLogsTab'));
const SystemHealthTab = lazy(() => import('./tabs/SystemHealthTab'));
const SettingsTab = lazy(() => import('./tabs/SettingsTab'));
const ReferralsTab = lazy(() => import('./tabs/ReferralsTab'));
const SupportTab = lazy(() => import('./tabs/SupportTab'));
const PlatformConfigTab = lazy(() => import('./tabs/PlatformConfigTab'));
const BillingTab = lazy(() => import('./tabs/BillingTab'));
const AnnouncementsTab = lazy(() => import('./tabs/AnnouncementsTab'));

const TAB_MAP: Record<string, React.LazyExoticComponent<React.ComponentType>> = {
  overview: OverviewTab,
  tenants: TenantsTab,
  plans: PlansTab,
  payments: PaymentsTab,
  users: UsersTab,
  modules: ModulesTab,
  audit: AuditLogsTab,
  health: SystemHealthTab,
  settings: SettingsTab,
  referrals: ReferralsTab,
  support: SupportTab,
  platform: PlatformConfigTab,
  billing: BillingTab,
  announcements: AnnouncementsTab,
};

const SuperAdminDashboard = () => {
  const [activeTab, setActiveTab] = useState('overview');
  const navigate = useNavigate();
  const qc = useQueryClient();

  const handleLogout = () => {
    Modal.confirm({
      title: 'Sign Out',
      content: 'Are you sure you want to sign out of the SuperAdmin panel?',
      okText: 'Sign Out',
      okType: 'danger',
      cancelText: 'Cancel',
      onOk: () => {
        localStorage.removeItem('authToken');
        localStorage.removeItem('user');
        localStorage.removeItem('tenantDomain');
        localStorage.removeItem('tenantInfo');
        localStorage.removeItem('tenantPermissions');
        localStorage.removeItem('impersonation');
        sessionStorage.removeItem('pending_impersonation');
        sessionStorage.removeItem('impersonation_session');
        navigate('/login');
      },
    });
  };

  const handleRefresh = () => {
    qc.invalidateQueries({ queryKey: ['superadmin-stats'] });
    qc.invalidateQueries({ queryKey: ['superadmin-tenants'] });
    qc.invalidateQueries({ queryKey: ['superadmin-plans'] });
    qc.invalidateQueries({ queryKey: ['superadmin-payments'] });
    qc.invalidateQueries({ queryKey: ['superadmin-users'] });
  };

  const ActiveTab = TAB_MAP[activeTab] || OverviewTab;

  return (
    <ConfigProvider
      theme={{
        token: {
          colorPrimary: '#242a88',
          borderRadius: 10,
          fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
          fontSize: 14,
          fontWeightStrong: 600,
        },
        algorithm: theme.defaultAlgorithm,
      }}
    >
      <style>{`
        .sa-sidebar .ant-menu-item {
          margin: 2px 8px !important;
          border-radius: 8px !important;
          height: 40px !important;
          line-height: 40px !important;
          color: rgba(255,255,255,0.75) !important;
          font-size: 13.5px !important;
          font-weight: 500 !important;
          transition: all 0.15s !important;
        }
        .sa-sidebar .ant-menu-item:hover {
          background: rgba(255,255,255,0.07) !important;
          color: white !important;
        }
        .sa-sidebar .ant-menu-item-selected {
          background: rgba(255,255,255,0.14) !important;
          color: white !important;
          font-weight: 600 !important;
        }
        .sa-sidebar .ant-menu-item-divider {
          background: rgba(255,255,255,0.08) !important;
          margin: 8px 16px !important;
        }
        .sa-sidebar .ant-menu-item .anticon {
          font-size: 16px !important;
        }
        .sa-content .ant-card {
          border-radius: 14px !important;
          border: 1px solid #e2e8f0 !important;
          transition: all 0.2s !important;
        }
        .sa-content .ant-card:hover {
          box-shadow: 0 8px 24px rgba(0, 0, 0, 0.08) !important;
          transform: translateY(-1px);
        }
        .sa-content .ant-statistic-title {
          font-size: 13px !important;
          font-weight: 500 !important;
          color: #64748b !important;
          text-transform: uppercase;
          letter-spacing: 0.3px;
        }
        .sa-content .ant-statistic-content-value {
          font-size: 28px !important;
          font-weight: 700 !important;
          color: #0f172a !important;
        }
        .sa-content .ant-table-thead > tr > th {
          background: #f8fafc !important;
          font-weight: 600 !important;
          font-size: 13px !important;
          text-transform: uppercase;
          letter-spacing: 0.3px;
          color: #475569 !important;
        }
        .sa-content .ant-table-tbody > tr:hover > td {
          background: rgba(36, 42, 136, 0.04) !important;
        }
      `}</style>
      <Layout style={{ minHeight: '100vh', background: '#eef2f7' }}>
        <Sider
          width={260}
          breakpoint="lg"
          collapsedWidth="0"
          style={{
            background: 'linear-gradient(180deg, #1a1f66 0%, #242a88 100%)',
            boxShadow: '4px 0 20px rgba(0,0,0,0.15)',
            zIndex: 10,
            borderRight: '1px solid rgba(255,255,255,0.07)',
          }}
          className="sa-sidebar"
        >
          {/* Sidebar header */}
          <div style={{
            height: 72, display: 'flex', alignItems: 'center',
            padding: '0 20px', borderBottom: '1px solid rgba(255,255,255,0.1)',
          }}>
            <div style={{
              width: 38, height: 38, borderRadius: 10,
              background: 'rgba(255,255,255,0.15)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              marginRight: 12,
              flexShrink: 0
            }}>
              <svg viewBox="0 0 40 40" fill="none" width="20" height="20">
                <rect x="4" y="8" width="14" height="14" rx="3" fill="white"/>
                <rect x="22" y="8" width="14" height="14" rx="3" fill="rgba(255,255,255,0.7)"/>
                <rect x="4" y="26" width="14" height="6" rx="3" fill="rgba(255,255,255,0.5)"/>
                <rect x="22" y="26" width="14" height="6" rx="3" fill="rgba(255,255,255,0.3)"/>
              </svg>
            </div>
            <div>
              <div style={{ fontSize: '16px', fontWeight: 700, color: '#ffffff', letterSpacing: '0.3px' }}>
                DTSG Platform
              </div>
              <div style={{ fontSize: '11px', color: 'rgba(255,255,255,0.45)', fontWeight: 500 }}>
                Super Admin
              </div>
            </div>
          </div>
          <Menu
            mode="inline"
            selectedKeys={[activeTab]}
            onClick={({ key }) => setActiveTab(key)}
            style={{ background: 'transparent', borderRight: 0, marginTop: 8 }}
            theme="dark"
            items={[
              { key: 'overview', label: 'Overview', icon: <BarChartOutlined /> },
              { key: 'tenants', label: 'Tenants', icon: <ShopOutlined /> },
              { key: 'plans', label: 'Plans', icon: <CrownOutlined /> },
              { key: 'payments', label: 'Payments', icon: <DollarOutlined /> },
              { key: 'users', label: 'Users', icon: <UserOutlined /> },
              { key: 'modules', label: 'Modules', icon: <AppstoreOutlined /> },
              { type: 'divider' },
              { key: 'referrals', label: 'Referrals', icon: <TeamOutlined /> },
              { key: 'support', label: 'Support', icon: <CustomerServiceOutlined /> },
              { key: 'billing', label: 'Billing', icon: <FileTextOutlined /> },
              { key: 'announcements', label: 'Announcements', icon: <NotificationOutlined /> },
              { key: 'platform', label: 'Platform', icon: <GlobalOutlined /> },
              { type: 'divider' },
              { key: 'audit', label: 'Audit Logs', icon: <AuditOutlined /> },
              { key: 'health', label: 'System Health', icon: <ClusterOutlined /> },
              { key: 'settings', label: 'Settings', icon: <SettingOutlined /> },
            ]}
          />
        </Sider>
        <Layout>
          <Header
            style={{
              background: '#ffffff',
              padding: '0 28px',
              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              boxShadow: '0 1px 2px rgba(0,0,0,0.04)',
              zIndex: 5, height: 64,
              borderBottom: '1px solid #e2e8f0',
            }}
          >
            <Title level={4} style={{
              margin: 0, color: '#0f172a', fontWeight: 700,
              fontSize: '18px', letterSpacing: '-0.3px'
            }}>
              Command Center
            </Title>
            <Space>
              <Button
                icon={<ReloadOutlined />}
                onClick={handleRefresh}
                style={{
                  borderColor: '#e2e8f0', color: '#475569',
                  borderRadius: '8px', fontWeight: 500
                }}
              >
                Refresh
              </Button>
              <Button
                type="text"
                icon={<LogoutOutlined />}
                onClick={handleLogout}
                style={{
                  color: '#ef4444', fontWeight: 500,
                  border: '1px solid #fecaca', borderRadius: '8px'
                }}
              >
                Sign Out
              </Button>
            </Space>
          </Header>
          <Content
            style={{
              margin: '24px', padding: 24,
              background: 'transparent', borderRadius: 12,
              minHeight: 280, overflow: 'auto'
            }}
            className="sa-content"
          >
            <Suspense fallback={
              <div style={{
                padding: 60, textAlign: 'center', color: '#64748b',
                fontSize: '15px'
              }}>
                Loading...
              </div>
            }>
              <ActiveTab />
            </Suspense>
          </Content>
        </Layout>
      </Layout>
    </ConfigProvider>
  );
};

export default SuperAdminDashboard;
