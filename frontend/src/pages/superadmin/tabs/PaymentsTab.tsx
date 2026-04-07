import { useState, useMemo } from 'react';
import {
  Card, Table, Tag, Button, Space, Typography, App, Row, Col, Statistic,
  Drawer, Descriptions, Timeline, Input, Select, DatePicker, Modal, Divider,
  Badge, Empty,
} from 'antd';
import {
  DollarOutlined, CheckCircleOutlined, CloseCircleOutlined,
  ClockCircleOutlined, ReloadOutlined, EyeOutlined, FilterOutlined,
  FileTextOutlined, SearchOutlined,
} from '@ant-design/icons';
import { usePayments, useApprovePayment } from '../hooks/useSuperAdmin';
import { useQueryClient } from '@tanstack/react-query';
import { useCurrency } from '../../../context/CurrencyContext';
import dayjs from 'dayjs';

const { Text, Title, Paragraph } = Typography;
const { TextArea } = Input;
const { RangePicker } = DatePicker;

const cardStyle: React.CSSProperties = {
  borderRadius: 12, border: 'none',
  boxShadow: '0 2px 8px rgba(0, 0, 0, 0.06), 0 1px 2px rgba(0, 0, 0, 0.04)',
};

const STATUS_COLORS: Record<string, string> = {
  pending: 'orange',
  approved: 'green',
  rejected: 'red',
  refunded: 'blue',
  processed: 'cyan',
};

const STATUS_ICONS: Record<string, React.ReactNode> = {
  pending: <ClockCircleOutlined />,
  approved: <CheckCircleOutlined />,
  rejected: <CloseCircleOutlined />,
  refunded: <DollarOutlined />,
  processed: <CheckCircleOutlined />,
};

const PaymentsTab = () => {
  const { message } = App.useApp();
  const { data: payments = [], isLoading } = usePayments();
  const approvePayment = useApprovePayment();
  const qc = useQueryClient();
  const { formatCurrency, currencySymbol } = useCurrency();

  // Drawer state
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [selectedPayment, setSelectedPayment] = useState<any>(null);
  const [actionNotes, setActionNotes] = useState('');

  // Filters
  const [statusFilter, setStatusFilter] = useState<string | undefined>();
  const [tenantFilter, setTenantFilter] = useState<string | undefined>();
  const [searchText, setSearchText] = useState('');
  const [dateRange, setDateRange] = useState<[dayjs.Dayjs | null, dayjs.Dayjs | null] | null>(null);

  // Compute filtered data
  const filteredPayments = useMemo(() => {
    let data = [...payments];
    if (statusFilter) data = data.filter((p: any) => p.status === statusFilter);
    if (tenantFilter) data = data.filter((p: any) => p.tenant === tenantFilter);
    if (searchText) {
      const lower = searchText.toLowerCase();
      data = data.filter((p: any) =>
        (p.transaction_reference || '').toLowerCase().includes(lower) ||
        (p.tenant || '').toLowerCase().includes(lower)
      );
    }
    if (dateRange && dateRange[0] && dateRange[1]) {
      data = data.filter((p: any) => {
        const d = dayjs(p.payment_date);
        return d.isAfter(dateRange[0]!.startOf('day')) && d.isBefore(dateRange[1]!.endOf('day'));
      });
    }
    return data;
  }, [payments, statusFilter, tenantFilter, searchText, dateRange]);

  // Compute stats
  const stats = useMemo(() => {
    const total = payments.length;
    const pending = payments.filter((p: any) => p.status === 'pending').length;
    const approved = payments.filter((p: any) => p.status === 'approved').length;
    const totalRevenue = payments
      .filter((p: any) => p.status === 'approved' || p.status === 'processed')
      .reduce((sum: number, p: any) => sum + Number(p.amount || 0), 0);
    return { total, pending, approved, totalRevenue };
  }, [payments]);

  // Unique tenants for filter
  const tenantOptions = useMemo(() => {
    const set = new Set(payments.map((p: any) => p.tenant).filter(Boolean));
    return Array.from(set).sort().map((t) => ({ label: t as string, value: t as string }));
  }, [payments]);

  const handleAction = async (id: number, action: 'approve' | 'reject', notes?: string) => {
    try {
      await approvePayment.mutateAsync({ id, action, notes });
      message.success(`Payment ${action === 'approve' ? 'approved' : 'rejected'} successfully`);
      setDrawerOpen(false);
      setSelectedPayment(null);
      setActionNotes('');
    } catch {
      message.error('Payment action failed');
    }
  };

  const confirmAction = (id: number, action: 'approve' | 'reject') => {
    Modal.confirm({
      title: `${action === 'approve' ? 'Approve' : 'Reject'} Payment`,
      content: (
        <div>
          <Paragraph>Are you sure you want to {action} this payment?</Paragraph>
          <TextArea
            placeholder="Add notes (optional)"
            rows={3}
            value={actionNotes}
            onChange={(e) => setActionNotes(e.target.value)}
          />
        </div>
      ),
      okText: action === 'approve' ? 'Approve' : 'Reject',
      okType: action === 'approve' ? 'primary' : 'danger',
      onOk: () => handleAction(id, action, actionNotes),
      onCancel: () => setActionNotes(''),
    });
  };

  const openDrawer = (record: any) => {
    setSelectedPayment(record);
    setDrawerOpen(true);
    setActionNotes('');
  };

  const columns = [
    {
      title: 'Reference', dataIndex: 'transaction_reference', key: 'ref',
      width: 160,
      render: (ref: string) => (
        <Text style={{ fontFamily: 'monospace', fontSize: 12 }}>{ref || '-'}</Text>
      ),
    },
    {
      title: 'Tenant', dataIndex: 'tenant', key: 'tenant',
      render: (t: string) => <Text strong>{t}</Text>,
    },
    {
      title: 'Amount', dataIndex: 'amount', key: 'amount',
      sorter: (a: any, b: any) => Number(a.amount) - Number(b.amount),
      render: (amount: string) => (
        <Text strong style={{ color: '#0f172a' }}>{formatCurrency(Number(amount))}</Text>
      ),
    },
    {
      title: 'Method', dataIndex: 'payment_method', key: 'method',
      render: (method: string) => (
        <Tag style={{ borderRadius: 6 }}>{(method || '').replace(/_/g, ' ').toUpperCase()}</Tag>
      ),
    },
    {
      title: 'Status', dataIndex: 'status', key: 'status',
      filters: [
        { text: 'Pending', value: 'pending' },
        { text: 'Approved', value: 'approved' },
        { text: 'Rejected', value: 'rejected' },
        { text: 'Processed', value: 'processed' },
      ],
      onFilter: (value: any, record: any) => record.status === value,
      render: (status: string) => (
        <Tag
          icon={STATUS_ICONS[status]}
          color={STATUS_COLORS[status] || 'default'}
          style={{ borderRadius: 6, fontWeight: 500 }}
        >
          {(status || '').toUpperCase()}
        </Tag>
      ),
    },
    {
      title: 'Date', dataIndex: 'payment_date', key: 'date',
      sorter: (a: any, b: any) => dayjs(a.payment_date).unix() - dayjs(b.payment_date).unix(),
      render: (date: string) => date ? dayjs(date).format('MMM DD, YYYY') : '-',
    },
    {
      title: 'Actions', key: 'actions', width: 180,
      render: (_: any, record: any) => (
        <Space size="small">
          <Button
            size="small"
            type="text"
            icon={<EyeOutlined />}
            onClick={() => openDrawer(record)}
            style={{ color: '#2471a3' }}
          >
            View
          </Button>
          {record.status === 'pending' && (
            <>
              <Button
                size="small"
                type="primary"
                icon={<CheckCircleOutlined />}
                loading={approvePayment.isPending}
                onClick={() => confirmAction(record.id, 'approve')}
                style={{ borderRadius: 6 }}
              >
                Approve
              </Button>
              <Button
                size="small"
                danger
                icon={<CloseCircleOutlined />}
                loading={approvePayment.isPending}
                onClick={() => confirmAction(record.id, 'reject')}
                style={{ borderRadius: 6 }}
              >
                Reject
              </Button>
            </>
          )}
        </Space>
      ),
    },
  ];

  return (
    <div>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
        <Title level={4} style={{ margin: 0, color: '#0f172a', fontWeight: 700 }}>
          Payment Management
        </Title>
        <Button
          icon={<ReloadOutlined />}
          onClick={() => qc.invalidateQueries({ queryKey: ['superadmin-payments'] })}
          style={{ borderRadius: 8 }}
        >
          Refresh
        </Button>
      </div>

      {/* Summary Stats */}
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col xs={12} sm={6}>
          <Card size="small" style={cardStyle}>
            <Statistic
              title="Total Payments"
              value={stats.total}
              prefix={<FileTextOutlined style={{ color: '#2471a3' }} />}
            />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card size="small" style={cardStyle}>
            <Statistic
              title="Pending Approval"
              value={stats.pending}
              prefix={<ClockCircleOutlined style={{ color: '#fa8c16' }} />}
              styles={{ content: { color: '#fa8c16' } }}
            />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card size="small" style={cardStyle}>
            <Statistic
              title="Approved"
              value={stats.approved}
              prefix={<CheckCircleOutlined style={{ color: '#52c41a' }} />}
              styles={{ content: { color: '#52c41a' } }}
            />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card size="small" style={cardStyle}>
            <Statistic
              title="Total Revenue"
              value={stats.totalRevenue}
              prefix={currencySymbol}
              precision={2}
              styles={{ content: { color: '#2471a3' } }}
            />
          </Card>
        </Col>
      </Row>

      {/* Filters */}
      <Card size="small" style={{ ...cardStyle, marginBottom: 16 }}>
        <Row gutter={[12, 12]} align="middle">
          <Col xs={24} sm={6}>
            <Input
              placeholder="Search reference or tenant..."
              prefix={<SearchOutlined />}
              allowClear
              value={searchText}
              onChange={(e) => setSearchText(e.target.value)}
              style={{ borderRadius: 8 }}
            />
          </Col>
          <Col xs={12} sm={5}>
            <Select
              placeholder="Status"
              allowClear
              value={statusFilter}
              onChange={setStatusFilter}
              style={{ width: '100%', borderRadius: 8 }}
              options={[
                { label: 'Pending', value: 'pending' },
                { label: 'Approved', value: 'approved' },
                { label: 'Rejected', value: 'rejected' },
                { label: 'Processed', value: 'processed' },
              ]}
            />
          </Col>
          <Col xs={12} sm={5}>
            <Select
              placeholder="Tenant"
              allowClear
              showSearch
              value={tenantFilter}
              onChange={setTenantFilter}
              style={{ width: '100%' }}
              options={tenantOptions}
              filterOption={(input, opt) => (opt?.label || '').toLowerCase().includes(input.toLowerCase())}
            />
          </Col>
          <Col xs={24} sm={8}>
            <RangePicker
              style={{ width: '100%', borderRadius: 8 }}
              value={dateRange as any}
              onChange={(val) => setDateRange(val as any)}
            />
          </Col>
        </Row>
      </Card>

      {/* Table */}
      <Card style={cardStyle}>
        <Table
          columns={columns}
          dataSource={filteredPayments}
          rowKey="id"
          loading={isLoading}
          size="middle"
          pagination={{ pageSize: 15, showSizeChanger: true, showTotal: (t) => `${t} payments` }}
          onRow={(record) => ({
            onClick: () => openDrawer(record),
            style: { cursor: 'pointer' },
          })}
        />
      </Card>

      {/* Payment Detail Drawer */}
      <Drawer
        title={
          <Space>
            <DollarOutlined style={{ color: '#2471a3' }} />
            <span>Payment Details</span>
            {selectedPayment && (
              <Tag
                icon={STATUS_ICONS[selectedPayment.status]}
                color={STATUS_COLORS[selectedPayment.status] || 'default'}
                style={{ marginLeft: 8, borderRadius: 6 }}
              >
                {(selectedPayment.status || '').toUpperCase()}
              </Tag>
            )}
          </Space>
        }
        open={drawerOpen}
        onClose={() => { setDrawerOpen(false); setSelectedPayment(null); setActionNotes(''); }}
        styles={{ wrapper: { width: '540px' } }}
        footer={
          selectedPayment?.status === 'pending' ? (
            <div style={{ display: 'flex', gap: 12 }}>
              <Button
                type="primary"
                icon={<CheckCircleOutlined />}
                block
                loading={approvePayment.isPending}
                onClick={() => handleAction(selectedPayment.id, 'approve', actionNotes)}
                style={{ borderRadius: 8 }}
              >
                Approve Payment
              </Button>
              <Button
                danger
                icon={<CloseCircleOutlined />}
                block
                loading={approvePayment.isPending}
                onClick={() => handleAction(selectedPayment.id, 'reject', actionNotes)}
                style={{ borderRadius: 8 }}
              >
                Reject Payment
              </Button>
            </div>
          ) : null
        }
      >
        {selectedPayment && (
          <div>
            {/* Tenant & Amount Header */}
            <div style={{
              background: 'linear-gradient(135deg, #f0f7ff 0%, #e6f0fa 100%)',
              borderRadius: 12, padding: 20, marginBottom: 24,
              border: '1px solid #d1e3f6',
            }}>
              <Text type="secondary" style={{ fontSize: 12, textTransform: 'uppercase', letterSpacing: 0.5 }}>
                Payment Amount
              </Text>
              <div style={{ fontSize: 32, fontWeight: 700, color: '#0f172a', marginTop: 4 }}>
                {formatCurrency(Number(selectedPayment.amount))}
              </div>
              <Text style={{ color: '#475569' }}>
                from <Text strong>{selectedPayment.tenant}</Text>
              </Text>
            </div>

            {/* Payment Info */}
            <Descriptions
              column={1}
              size="small"
              labelStyle={{ fontWeight: 500, color: '#64748b', width: 160 }}
              contentStyle={{ color: '#0f172a' }}
            >
              <Descriptions.Item label="Tenant">{selectedPayment.tenant}</Descriptions.Item>
              <Descriptions.Item label="Transaction Ref">
                <Text copyable style={{ fontFamily: 'monospace' }}>
                  {selectedPayment.transaction_reference || '-'}
                </Text>
              </Descriptions.Item>
              <Descriptions.Item label="Amount">{formatCurrency(Number(selectedPayment.amount))}</Descriptions.Item>
              <Descriptions.Item label="Currency">{selectedPayment.currency || 'NGN'}</Descriptions.Item>
              <Descriptions.Item label="Payment Method">
                <Tag style={{ borderRadius: 6 }}>
                  {(selectedPayment.payment_method || '').replace(/_/g, ' ').toUpperCase()}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="Payment Date">
                {selectedPayment.payment_date ? dayjs(selectedPayment.payment_date).format('MMMM DD, YYYY') : '-'}
              </Descriptions.Item>
              <Descriptions.Item label="Status">
                <Tag
                  icon={STATUS_ICONS[selectedPayment.status]}
                  color={STATUS_COLORS[selectedPayment.status] || 'default'}
                  style={{ borderRadius: 6 }}
                >
                  {(selectedPayment.status || '').toUpperCase()}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="Created">
                {selectedPayment.created_at ? dayjs(selectedPayment.created_at).format('MMM DD, YYYY HH:mm') : '-'}
              </Descriptions.Item>
            </Descriptions>

            {/* Approval notes area for pending */}
            {selectedPayment.status === 'pending' && (
              <>
                <Divider />
                <Title level={5} style={{ marginBottom: 12 }}>Approval / Rejection Notes</Title>
                <TextArea
                  placeholder="Enter reason for approval or rejection..."
                  rows={3}
                  value={actionNotes}
                  onChange={(e) => setActionNotes(e.target.value)}
                  style={{ borderRadius: 8 }}
                />
              </>
            )}

            {/* Payment History Timeline */}
            <Divider />
            <Title level={5} style={{ marginBottom: 16 }}>Payment Timeline</Title>
            <Timeline
              items={[
                {
                  color: 'blue',
                  children: (
                    <div>
                      <Text strong>Payment Submitted</Text>
                      <br />
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        {selectedPayment.created_at
                          ? dayjs(selectedPayment.created_at).format('MMM DD, YYYY HH:mm')
                          : 'Date unknown'}
                      </Text>
                    </div>
                  ),
                },
                ...(selectedPayment.payment_date ? [{
                  color: 'blue',
                  children: (
                    <div>
                      <Text strong>Payment Date Recorded</Text>
                      <br />
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        {dayjs(selectedPayment.payment_date).format('MMM DD, YYYY')}
                      </Text>
                    </div>
                  ),
                }] : []),
                ...(selectedPayment.status === 'approved' ? [{
                  color: 'green',
                  children: (
                    <div>
                      <Text strong style={{ color: '#52c41a' }}>Payment Approved</Text>
                      {selectedPayment.approval_notes && (
                        <>
                          <br />
                          <Text type="secondary" style={{ fontSize: 12 }}>
                            Notes: {selectedPayment.approval_notes}
                          </Text>
                        </>
                      )}
                    </div>
                  ),
                }] : []),
                ...(selectedPayment.status === 'rejected' ? [{
                  color: 'red',
                  children: (
                    <div>
                      <Text strong style={{ color: '#f5222d' }}>Payment Rejected</Text>
                      {selectedPayment.approval_notes && (
                        <>
                          <br />
                          <Text type="secondary" style={{ fontSize: 12 }}>
                            Reason: {selectedPayment.approval_notes}
                          </Text>
                        </>
                      )}
                    </div>
                  ),
                }] : []),
                ...(selectedPayment.status === 'pending' ? [{
                  color: 'orange',
                  children: (
                    <div>
                      <Badge status="processing" />
                      <Text strong style={{ color: '#fa8c16', marginLeft: 4 }}>Awaiting Review</Text>
                    </div>
                  ),
                }] : []),
              ]}
            />
          </div>
        )}
      </Drawer>
    </div>
  );
};

export default PaymentsTab;
