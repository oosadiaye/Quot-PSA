import {
  Card, Row, Col, Statistic, Table, Tag, Typography, Progress, Divider, Flex,
  Empty, Skeleton, Space, Button,
} from 'antd';
import {
  ShopOutlined, CheckCircleOutlined, CrownOutlined, DollarOutlined,
  StopOutlined, TeamOutlined, CustomerServiceOutlined, NotificationOutlined,
  WarningOutlined, ClockCircleOutlined,
} from '@ant-design/icons';
import { useDashboardStats, useAuditLogs, useExpiringTrials } from '../hooks/useSuperAdmin';
import { useCurrency } from '../../../context/CurrencyContext';
import { useQuery } from '@tanstack/react-query';
import { superadminApi } from '../../../api/superadmin';

const { Text, Title } = Typography;

const cardStyle: React.CSSProperties = {
  borderRadius: 12,
  border: 'none',
  boxShadow: '0 2px 8px rgba(0, 0, 0, 0.06), 0 1px 2px rgba(0, 0, 0, 0.04)',
};

const statCardStyle = (color: string): React.CSSProperties => ({
  ...cardStyle,
  background: `linear-gradient(135deg, ${color}08 0%, ${color}03 100%)`,
  borderLeft: `4px solid ${color}`,
});

const OverviewTab = () => {
  const { data: stats, isLoading } = useDashboardStats();
  const { data: recentLogs, isLoading: logsLoading } = useAuditLogs({ limit: 5 });
  const { data: expiringTrials = [] } = useExpiringTrials(7);
  const { formatCurrency } = useCurrency();
  const { data: saasStats } = useQuery({
    queryKey: ['saas-stats'],
    queryFn: () => superadminApi.getSaaSStats().then(r => r.data),
  });

  const auditColumns = [
    {
      title: 'Timestamp', dataIndex: 'timestamp', key: 'timestamp',
      render: (ts: string) => ts ? <Text type="secondary" style={{ fontSize: 12 }}>{new Date(ts).toLocaleString()}</Text> : '-',
    },
    { title: 'Tenant', dataIndex: 'tenant_name', key: 'tenant_name', render: (v: string) => v ? <Tag color="blue">{v}</Tag> : '-' },
    {
      title: 'Action', dataIndex: 'action_type', key: 'action_type',
      render: (action: string) => {
        const colors: Record<string, string> = { CREATE: 'green', UPDATE: 'blue', DELETE: 'red', LOGIN: 'purple', LOGOUT: 'default' };
        return <Tag color={colors[action] || 'default'}>{action}</Tag>;
      },
    },
    { title: 'Module', dataIndex: 'module', key: 'module' },
    { title: 'Details', dataIndex: 'object_repr', key: 'object_repr', ellipsis: true },
  ];

  if (isLoading) return <Skeleton active paragraph={{ rows: 12 }} />;

  const s = stats || {
    total_tenants: 0, active_subscriptions: 0, trial_subscriptions: 0,
    suspended: 0, expired_subscriptions: 0, cancelled_subscriptions: 0,
    total_revenue: '0', recent_signups: [],
  };

  // Use the direct API value — derived arithmetic (total − active − trial − suspended)
  // is inaccurate because it doesn't account for cancelled subscriptions.
  const expiredCount = s.expired_subscriptions || 0;
  const trialsList = Array.isArray(expiringTrials) ? expiringTrials : [];

  return (
    <div>
      {/* ── Primary Stats ────────────────────────────────────── */}
      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} lg={6}>
          <Card hoverable style={statCardStyle('#1890ff')}>
            <Statistic
              className="superadmin-statistic"
              title="Total Tenants"
              value={s.total_tenants}
              prefix={<ShopOutlined style={{ fontSize: 20, color: '#1890ff' }} />}
              styles={{ content: { color: '#1890ff', fontWeight: 700, fontSize: 28 } }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card hoverable style={statCardStyle('#52c41a')}>
            <Statistic
              className="superadmin-statistic"
              title="Active Subscriptions"
              value={s.active_subscriptions}
              prefix={<CheckCircleOutlined style={{ fontSize: 20, color: '#52c41a' }} />}
              styles={{ content: { color: '#52c41a', fontWeight: 700, fontSize: 28 } }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card hoverable style={statCardStyle('#faad14')}>
            <Statistic
              className="superadmin-statistic"
              title="Trial Subscriptions"
              value={s.trial_subscriptions}
              prefix={<CrownOutlined style={{ fontSize: 20, color: '#faad14' }} />}
              styles={{ content: { color: '#faad14', fontWeight: 700, fontSize: 28 } }}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} lg={6}>
          <Card hoverable style={statCardStyle('#722ed1')}>
            <Statistic
              className="superadmin-statistic"
              title="Total Revenue"
              value={parseInt(s.total_revenue || '0')}
              prefix={<DollarOutlined style={{ fontSize: 20, color: '#722ed1' }} />}
              styles={{ content: { color: '#722ed1', fontWeight: 700, fontSize: 28 } }}
              formatter={(value) => formatCurrency(Number(value))}
            />
          </Card>
        </Col>
      </Row>

      {/* ── Secondary Stats ──────────────────────────────────── */}
      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        <Col xs={12} sm={6}>
          <Card size="small" hoverable style={statCardStyle('#ff4d4f')}>
            <Statistic
              title="Suspended"
              value={s.suspended}
              prefix={<StopOutlined style={{ color: '#ff4d4f' }} />}
              styles={{ content: { color: '#ff4d4f' } }}
            />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card size="small" hoverable style={statCardStyle('#8c8c8c')}>
            <Statistic
              title="Expired"
              value={expiredCount > 0 ? expiredCount : 0}
              prefix={<ClockCircleOutlined style={{ color: '#8c8c8c' }} />}
              styles={{ content: { color: '#8c8c8c' } }}
            />
          </Card>
        </Col>
        {saasStats && (
          <>
            <Col xs={12} sm={6}>
              <Card size="small" hoverable style={statCardStyle('#13c2c2')}>
                <Statistic
                  title="Referrers"
                  value={saasStats.referrers?.total || 0}
                  suffix={<Text type="secondary" style={{ fontSize: 12 }}>({saasStats.referrers?.active || 0} active)</Text>}
                  prefix={<TeamOutlined style={{ color: '#13c2c2' }} />}
                  styles={{ content: { color: '#13c2c2' } }}
                />
              </Card>
            </Col>
            <Col xs={12} sm={6}>
              <Card size="small" hoverable style={statCardStyle('#eb2f96')}>
                <Statistic
                  title="Open Tickets"
                  value={saasStats.support?.open || 0}
                  prefix={<CustomerServiceOutlined style={{ color: '#eb2f96' }} />}
                  styles={{ content: { color: '#eb2f96' } }}
                />
              </Card>
            </Col>
          </>
        )}
      </Row>

      {/* ── Expiring Trials Alert ────────────────────────────── */}
      {trialsList.length > 0 && (
        <Card
          size="small"
          style={{ ...cardStyle, marginTop: 16, borderLeft: '4px solid #faad14', background: '#fffbe6' }}
        >
          <Space>
            <WarningOutlined style={{ color: '#faad14', fontSize: 18 }} />
            <Text strong>{trialsList.length} trial{trialsList.length > 1 ? 's' : ''} expiring within 7 days:</Text>
          </Space>
          <div style={{ marginTop: 8 }}>
            {trialsList.map((t: any) => (
              <Tag key={t.tenant_id} color="orange" style={{ marginBottom: 4 }}>
                {t.tenant_name} — {t.days_remaining} day{t.days_remaining !== 1 ? 's' : ''} left
              </Tag>
            ))}
          </div>
        </Card>
      )}

      {/* ── Main Content ─────────────────────────────────────── */}
      <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
        {/* Recent Signups */}
        <Col xs={24} lg={14}>
          <Card
            title={<Text strong style={{ fontSize: 15 }}>Recent Signups</Text>}
            variant="borderless"
            style={cardStyle}
          >
            {(s.recent_signups || []).length > 0 ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                {s.recent_signups.map((item: any, idx: number) => (
                  <div key={idx} style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                    <div
                      style={{
                        width: 42, height: 42, borderRadius: 10,
                        background: 'linear-gradient(135deg, #1890ff 0%, #096dd9 100%)',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        flexShrink: 0,
                      }}
                    >
                      <ShopOutlined style={{ fontSize: 18, color: '#fff' }} />
                    </div>
                    <div style={{ flex: 1 }}>
                      <Text strong>{item.name}</Text>
                      <div><Text type="secondary" style={{ fontSize: 12 }}>Joined {new Date(item.created_on).toLocaleDateString()}</Text></div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <Empty description="No recent signups" />
            )}
          </Card>
        </Col>

        {/* Subscription Breakdown */}
        <Col xs={24} lg={10}>
          <Card
            title={<Text strong style={{ fontSize: 15 }}>Subscription Breakdown</Text>}
            variant="borderless"
            style={cardStyle}
          >
            <Progress
              percent={Math.round((s.active_subscriptions / (s.total_tenants || 1)) * 100)}
              status="active"
              strokeColor={{ '0%': '#1890ff', '100%': '#52c41a' }}
              style={{ marginBottom: 16 }}
            />
            <Flex vertical gap={8}>
              {[
                { label: 'Active', count: s.active_subscriptions, color: '#52c41a', bg: 'rgba(82, 196, 26, 0.08)' },
                { label: 'Trial', count: s.trial_subscriptions, color: '#faad14', bg: 'rgba(250, 173, 20, 0.08)' },
                { label: 'Suspended', count: s.suspended, color: '#ff4d4f', bg: 'rgba(255, 77, 79, 0.08)' },
                { label: 'Expired', count: expiredCount > 0 ? expiredCount : 0, color: '#8c8c8c', bg: 'rgba(140, 140, 140, 0.08)' },
              ].map((item) => (
                <div
                  key={item.label}
                  style={{
                    display: 'flex', justifyContent: 'space-between',
                    padding: '8px 12px', background: item.bg, borderRadius: 8,
                  }}
                >
                  <Text strong>{item.label}</Text>
                  <Tag color={item.color} style={{ borderRadius: 6 }}>{item.count}</Tag>
                </div>
              ))}
            </Flex>
          </Card>
        </Col>
      </Row>

      {/* ── Recent Activity ──────────────────────────────────── */}
      <Card
        title={<Text strong style={{ fontSize: 15 }}>Recent Activity</Text>}
        variant="borderless"
        style={{ ...cardStyle, marginTop: 16 }}
      >
        {logsLoading ? (
          <Skeleton active paragraph={{ rows: 4 }} />
        ) : (
          (() => {
            const logsList = Array.isArray(recentLogs) ? recentLogs : (recentLogs as any)?.results || [];
            return logsList.length > 0 ? (
              <Table
                columns={auditColumns}
                dataSource={logsList}
                rowKey="id"
                pagination={{ pageSize: 5 }}
                size="middle"
              />
            ) : (
              <Empty description="No recent activity" />
            );
          })()
        )}
      </Card>
    </div>
  );
};

export default OverviewTab;
