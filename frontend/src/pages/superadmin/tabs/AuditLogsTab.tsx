import { Card, Table, Tag, Button, Empty, Skeleton } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { useAuditLogs } from '../hooks/useSuperAdmin';
import { useQueryClient } from '@tanstack/react-query';

const cardStyle: React.CSSProperties = {
  borderRadius: 12, border: 'none',
  boxShadow: '0 2px 8px rgba(0, 0, 0, 0.06), 0 1px 2px rgba(0, 0, 0, 0.04)',
};

const AuditLogsTab = () => {
  const { data: logs = [], isLoading } = useAuditLogs({ limit: 100 });
  const qc = useQueryClient();

  const columns = [
    { title: 'Timestamp', dataIndex: 'timestamp', key: 'timestamp', width: 180,
      render: (text: string) => text ? new Date(text).toLocaleString() : '-' },
    { title: 'Tenant', dataIndex: 'tenant_name', key: 'tenant_name', width: 150 },
    { title: 'Action', dataIndex: 'action_type', key: 'action_type', width: 100,
      render: (type: string) => {
        const colors: Record<string, string> = {
          CREATE: 'green', UPDATE: 'blue', DELETE: 'red',
          LOGIN: 'purple', LOGOUT: 'orange', APPROVE: 'green', REJECT: 'red'
        };
        return <Tag color={colors[type] || 'default'}>{type || '-'}</Tag>;
      }
    },
    { title: 'Module', dataIndex: 'module', key: 'module', width: 120 },
    { title: 'Description', dataIndex: 'object_repr', key: 'object_repr', ellipsis: true },
  ];

  return (
    <Card
      title={<span style={{ fontWeight: 600, fontSize: 'var(--text-base)' }}>Audit Logs</span>}
      extra={<Button icon={<ReloadOutlined />} onClick={() => qc.invalidateQueries({ queryKey: ['superadmin-audit-logs'] })} loading={isLoading}>Refresh</Button>}
      style={cardStyle}
    >
      {isLoading ? (
        <Skeleton active paragraph={{ rows: 8 }} />
      ) : logs.length > 0 ? (
        <Table columns={columns} dataSource={logs} rowKey="id" pagination={{ pageSize: 10 }} size="middle" />
      ) : (
        <Empty description="No audit logs available" />
      )}
    </Card>
  );
};

export default AuditLogsTab;
