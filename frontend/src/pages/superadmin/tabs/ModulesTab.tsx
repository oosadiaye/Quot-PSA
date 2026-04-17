import { Card, Table, Tag, Button, Space, Switch, Alert, Progress, Typography, List, Badge, Empty, Drawer, Select, Popconfirm, App } from 'antd';
import {
  AppstoreOutlined, ReloadOutlined, CheckCircleOutlined, CloseCircleOutlined, SettingOutlined,
  AccountBookOutlined, DollarOutlined, ShoppingCartOutlined, DatabaseOutlined,
  TeamOutlined, BranchesOutlined
} from '@ant-design/icons';
import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useGlobalModules, useTenants, useTenantModules, useToggleGlobalModule, useToggleTenantModule } from '../hooks/useSuperAdmin';
import type { GlobalModule, TenantModuleItem } from '../hooks/useSuperAdmin';

const { Text } = Typography;

const cardStyle: React.CSSProperties = {
  borderRadius: 12, border: 'none',
  boxShadow: '0 2px 8px rgba(0, 0, 0, 0.06), 0 1px 2px rgba(0, 0, 0, 0.04)',
};

const MODULE_ICONS: Record<string, React.ReactNode> = {
  dimensions: <DatabaseOutlined style={{ fontSize: 'var(--text-lg)', color: '#fff' }} />,
  accounting: <AccountBookOutlined style={{ fontSize: 'var(--text-lg)', color: '#fff' }} />,
  budget: <DollarOutlined style={{ fontSize: 'var(--text-lg)', color: '#fff' }} />,
  procurement: <ShoppingCartOutlined style={{ fontSize: 'var(--text-lg)', color: '#fff' }} />,
  inventory: <DatabaseOutlined style={{ fontSize: 'var(--text-lg)', color: '#fff' }} />,
  hrm: <TeamOutlined style={{ fontSize: 'var(--text-lg)', color: '#fff' }} />,
  workflow: <BranchesOutlined style={{ fontSize: 'var(--text-lg)', color: '#fff' }} />,
};

const MODULE_DEPENDENCIES: Record<string, string[]> = {
  budget: ['accounting', 'dimensions'],
  procurement: ['accounting', 'inventory'],
};

const ModulesTab = () => {
  const { message } = App.useApp();
  const { data: globalModules = [], isLoading: globalLoading } = useGlobalModules();
  const { data: tenants = [] } = useTenants();
  const toggleGlobal = useToggleGlobalModule();
  const toggleTenant = useToggleTenantModule();
  const qc = useQueryClient();

  const [selectedTenant, setSelectedTenant] = useState<number | null>(null);
  const [drawerVisible, setDrawerVisible] = useState(false);

  const { data: tenantModules = [] } = useTenantModules(selectedTenant);

  const handleGlobalToggle = async (moduleName: string, isEnabled: boolean) => {
    // Check dependencies when disabling
    if (!isEnabled) {
      const dependents = Object.entries(MODULE_DEPENDENCIES)
        .filter(([, deps]) => deps.includes(moduleName))
        .map(([mod]) => mod);
      if (dependents.length > 0) {
        const activeDependent = globalModules.find(m => dependents.includes(m.module_name) && m.is_globally_enabled);
        if (activeDependent) {
          message.warning(`Warning: "${activeDependent.module_title}" depends on this module. Consider disabling it first.`);
        }
      }
    }

    try {
      await toggleGlobal.mutateAsync({ moduleName, isEnabled });
      message.success(`Module ${isEnabled ? 'enabled' : 'disabled'} globally for all tenants`);
    } catch {
      message.error('Failed to update module');
    }
  };

  const handleTenantModuleToggle = async (moduleName: string, isActive: boolean) => {
    if (!selectedTenant) return;
    try {
      await toggleTenant.mutateAsync({ tenantId: selectedTenant, modules: { [moduleName]: isActive } });
      message.success(`Module ${isActive ? 'activated' : 'deactivated'} successfully`);
    } catch {
      message.error('Failed to update module');
    }
  };

  const handleActivateAll = async () => {
    if (!selectedTenant) return;
    const all: Record<string, boolean> = {};
    tenantModules.forEach(m => { all[m.module_name] = true; });
    try {
      await toggleTenant.mutateAsync({ tenantId: selectedTenant, modules: all });
      message.success('All modules activated');
    } catch {
      message.error('Failed to activate modules');
    }
  };

  const handleDeactivateAll = async () => {
    if (!selectedTenant) return;
    const all: Record<string, boolean> = {};
    tenantModules.forEach(m => { all[m.module_name] = false; });
    try {
      await toggleTenant.mutateAsync({ tenantId: selectedTenant, modules: all });
      message.success('All modules deactivated');
    } catch {
      message.error('Failed to deactivate modules');
    }
  };

  const globalColumns = [
    {
      title: 'Module', dataIndex: 'module_title', key: 'module_title',
      render: (title: string, record: GlobalModule) => (
        <Space>
          <div style={{
            width: 40, height: 40, borderRadius: 10,
            background: record.is_globally_enabled
              ? 'linear-gradient(135deg, #52c41a 0%, #389e0d 100%)'
              : 'linear-gradient(135deg, #d9d9d9 0%, #bfbfbf 100%)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            boxShadow: record.is_globally_enabled ? '0 4px 12px rgba(82, 196, 26, 0.4)' : 'none'
          }}>
            {MODULE_ICONS[record.module_name] || <AppstoreOutlined style={{ fontSize: 'var(--text-lg)', color: '#fff' }} />}
          </div>
          <div>
            <Text strong style={{ fontSize: 'var(--text-sm)' }}>{title}</Text>
            <br />
            <Text type="secondary" style={{ fontSize: 'var(--text-xs)' }}>{record.description}</Text>
            {MODULE_DEPENDENCIES[record.module_name] && (
              <div style={{ marginTop: 2 }}>
                <Text type="secondary" style={{ fontSize: 'var(--text-xs)' }}>
                  Depends on: {MODULE_DEPENDENCIES[record.module_name].join(', ')}
                </Text>
              </div>
            )}
          </div>
        </Space>
      )
    },
    {
      title: 'Status', key: 'status',
      render: (_: any, record: GlobalModule) => (
        <Tag color={record.is_globally_enabled ? 'success' : 'default'} style={{ borderRadius: 6, fontWeight: 500 }}>
          {record.is_globally_enabled ? 'GLOBAL ENABLED' : 'GLOBAL DISABLED'}
        </Tag>
      )
    },
    {
      title: 'Tenant Coverage', key: 'coverage',
      render: (_: any, record: GlobalModule) => (
        <div>
          <Progress percent={Math.round((record.active_tenants / (record.total_tenants || 1)) * 100)} size="small"
            strokeColor={record.is_globally_enabled ? '#52c41a' : '#d9d9d9'} style={{ width: 100 }} />
          <Text type="secondary" style={{ fontSize: 'var(--text-xs)' }}>{record.active_tenants}/{record.total_tenants} tenants</Text>
        </div>
      )
    },
    {
      title: 'Global Toggle', key: 'toggle',
      render: (_: any, record: GlobalModule) => (
        <Popconfirm
          title={`${record.is_globally_enabled ? 'Disable' : 'Enable'} this module globally?`}
          description={`This will ${record.is_globally_enabled ? 'disable' : 'enable'} "${record.module_title}" for ALL tenants.`}
          onConfirm={() => handleGlobalToggle(record.module_name, !record.is_globally_enabled)}
          okText="Yes, proceed" cancelText="Cancel"
          okButtonProps={{ danger: record.is_globally_enabled }}
        >
          <Switch checked={record.is_globally_enabled}
            checkedChildren={<CheckCircleOutlined />} unCheckedChildren={<CloseCircleOutlined />}
            loading={toggleGlobal.isPending}
            style={{ background: record.is_globally_enabled ? 'linear-gradient(90deg, #52c41a, #389e0d)' : '#d9d9d9' }}
          />
        </Popconfirm>
      )
    }
  ];

  return (
    <div>
      <Card
        title={
          <Space>
            <span style={{ fontWeight: 600, fontSize: 'var(--text-base)' }}>Global Module Control</span>
            <Tag color="blue" style={{ borderRadius: 6 }}>Real-time</Tag>
          </Space>
        }
        extra={<Button icon={<ReloadOutlined />} onClick={() => qc.invalidateQueries({ queryKey: ['global-modules'] })} loading={globalLoading} style={{ borderRadius: 8 }}>Refresh</Button>}
        style={{ ...cardStyle, marginBottom: 24 }}
      >
        <Alert title="Global Module Toggle" type="warning" showIcon style={{ marginBottom: 16 }}
          description="Enable or disable modules for ALL tenants at once. Changes take effect in real-time." />
        <Table columns={globalColumns} dataSource={globalModules} rowKey="module_name" loading={globalLoading} pagination={false} />
      </Card>

      <Card
        title={<span style={{ fontWeight: 600, fontSize: 'var(--text-base)' }}>Per-Tenant Module Management</span>}
        extra={
          <Space>
            <Select placeholder="Select Tenant" style={{ width: 200 }} value={selectedTenant} allowClear
              onChange={(id) => { setSelectedTenant(id); if (id) setDrawerVisible(true); }}
              options={tenants.map((t: any) => ({ value: t.id, label: t.name }))} />
            <Button type="primary" icon={<SettingOutlined />}
              onClick={() => { if (selectedTenant) setDrawerVisible(true); else message.warning('Please select a tenant first'); }}
              style={{ borderRadius: 8 }}>Manage Modules</Button>
          </Space>
        }
        style={cardStyle}
      >
        <Alert title="Tenant-Specific Configuration" type="info" showIcon style={{ marginBottom: 16 }}
          description="Select a tenant above to activate or deactivate specific modules for that organization." />
      </Card>

      <Drawer
        title={`Module Configuration - ${tenants.find((t: any) => t.id === selectedTenant)?.name || ''}`}
        placement="right" size="large" open={drawerVisible}
        onClose={() => setDrawerVisible(false)}
        extra={
          <Space>
            <Button onClick={handleActivateAll} size="small">Activate All</Button>
            <Button onClick={handleDeactivateAll} size="small" danger>Deactivate All</Button>
          </Space>
        }
      >
        {tenantModules.length > 0 ? (
          <List
            dataSource={tenantModules}
            renderItem={(item: TenantModuleItem) => (
              <List.Item key={item.module_name} actions={[
                <Switch key="switch" checked={item.is_active}
                  onChange={(checked) => handleTenantModuleToggle(item.module_name, checked)}
                  checkedChildren="ON" unCheckedChildren="OFF" />
              ]}>
                <List.Item.Meta
                  avatar={
                    <div style={{
                      width: 36, height: 36, borderRadius: 8,
                      background: item.is_active
                        ? 'linear-gradient(135deg, #52c41a 0%, #389e0d 100%)'
                        : 'linear-gradient(135deg, #d9d9d9 0%, #bfbfbf 100%)',
                      display: 'flex', alignItems: 'center', justifyContent: 'center'
                    }}>
                      {MODULE_ICONS[item.module_name] || <AppstoreOutlined style={{ fontSize: 'var(--text-base)', color: '#fff' }} />}
                    </div>
                  }
                  title={item.module_title}
                  description={
                    <div>
                      <Text type="secondary" style={{ fontSize: 'var(--text-xs)' }}>{item.description}</Text>
                      <div style={{ marginTop: 4 }}>
                        <Tag color={item.is_active ? 'green' : 'default'}>{item.is_active ? 'Active' : 'Inactive'}</Tag>
                      </div>
                    </div>
                  }
                />
              </List.Item>
            )}
          />
        ) : (
          <Empty description="Select a tenant to manage modules" />
        )}
      </Drawer>
    </div>
  );
};

export default ModulesTab;
