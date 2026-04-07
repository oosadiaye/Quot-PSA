import { Card, Row, Col, Statistic, Progress, Tag, Button, Typography, Empty, Skeleton } from 'antd';
import { DatabaseOutlined, ShopOutlined, CheckCircleOutlined, ClockCircleOutlined, StopOutlined, ReloadOutlined } from '@ant-design/icons';
import { useSystemHealth } from '../hooks/useSuperAdmin';
import { useQueryClient } from '@tanstack/react-query';

const { Text } = Typography;

const cardStyle: React.CSSProperties = {
  borderRadius: 12, border: 'none',
  boxShadow: '0 2px 8px rgba(0, 0, 0, 0.06), 0 1px 2px rgba(0, 0, 0, 0.04)',
};

const SystemHealthTab = () => {
  const { data: health, isLoading } = useSystemHealth();
  const qc = useQueryClient();

  const getHealthStatus = (status: string) => {
    if (status === 'healthy') return { color: '#52c41a', text: 'Healthy' };
    if (status === 'unhealthy') return { color: '#ff4d4f', text: 'Unhealthy' };
    return { color: '#faad14', text: 'Unknown' };
  };

  return (
    <div>
      <Row gutter={[20, 20]}>
        <Col xs={24} lg={12}>
          <Card title={<span style={{ fontWeight: 600, fontSize: 'var(--text-base)' }}>Database Status</span>} style={cardStyle}>
            {isLoading ? <Skeleton active paragraph={{ rows: 2 }} /> : health ? (
              <div>
                <div style={{ display: 'flex', alignItems: 'center', marginBottom: 16 }}>
                  <DatabaseOutlined style={{ fontSize: 'var(--text-xl)', marginRight: 12, color: getHealthStatus(health.database).color }} />
                  <div>
                    <Text strong>PostgreSQL</Text>
                    <br />
                    <Tag color={getHealthStatus(health.database).color}>{getHealthStatus(health.database).text}</Tag>
                  </div>
                </div>
                <Text>Active Connections: {health.active_connections}</Text>
              </div>
            ) : <Empty description="Unable to load system health" />}
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card title={<span style={{ fontWeight: 600, fontSize: 'var(--text-base)' }}>System Resources</span>} style={cardStyle}>
            {isLoading ? <Skeleton active paragraph={{ rows: 4 }} /> : health ? (
              <div>
                <div style={{ marginBottom: 16 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                    <Text>Disk Usage</Text>
                    <Text>{health.disk_usage.toFixed(1)}%</Text>
                  </div>
                  <Progress percent={health.disk_usage} showInfo={false}
                    strokeColor={health.disk_usage > 80 ? '#ff4d4f' : '#52c41a'} />
                </div>
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                    <Text>Memory Usage</Text>
                    <Text>{health.memory_usage.toFixed(1)}%</Text>
                  </div>
                  <Progress percent={health.memory_usage} showInfo={false}
                    strokeColor={health.memory_usage > 80 ? '#ff4d4f' : '#52c41a'} />
                </div>
              </div>
            ) : <Empty description="Unable to load system resources" />}
          </Card>
        </Col>
      </Row>

      <Card title={<span style={{ fontWeight: 600, fontSize: 'var(--text-base)' }}>Tenant Status</span>} style={{ ...cardStyle, marginTop: 20 }}>
        {isLoading ? <Skeleton active paragraph={{ rows: 2 }} /> : health ? (
          <Row gutter={16}>
            <Col span={6}>
              <Statistic title="Total Tenants" value={health.tenants.total} prefix={<ShopOutlined />} />
            </Col>
            <Col span={6}>
              <Statistic title="Active" value={health.tenants.active} prefix={<CheckCircleOutlined />} styles={{ content: { color: '#52c41a' } }} />
            </Col>
            <Col span={6}>
              <Statistic title="Trial" value={health.tenants.trial} prefix={<ClockCircleOutlined />} styles={{ content: { color: '#faad14' } }} />
            </Col>
            <Col span={6}>
              <Statistic title="Suspended" value={health.tenants.suspended} prefix={<StopOutlined />} styles={{ content: { color: '#ff4d4f' } }} />
            </Col>
          </Row>
        ) : <Empty description="Unable to load tenant status" />}
      </Card>

      <Button type="primary" icon={<ReloadOutlined />}
        onClick={() => qc.invalidateQueries({ queryKey: ['superadmin-system-health'] })}
        loading={isLoading} style={{ marginTop: 20 }}>
        Refresh Health Status
      </Button>
    </div>
  );
};

export default SystemHealthTab;
