import { useState } from 'react';
import {
  Card, Table, Tabs, Button, Tag, Space, Statistic, Row, Col,
  Modal, Form, Input, InputNumber, DatePicker, Select, message, Typography,
} from 'antd';
import {
  DollarOutlined, FileTextOutlined, PlusOutlined, BarChartOutlined,
} from '@ant-design/icons';
import type { Invoice, TenantUsage } from '../../../api/superadmin';
import {
  useInvoices, useCreateInvoice, useUpdateInvoice,
  useTenantUsageRecords, useBillingAnalytics, useTenants,
} from '../hooks/useSuperAdmin';
import { useCurrency } from '../../../context/CurrencyContext';

const { TabPane } = Tabs;
const { Text } = Typography;

const statusColor: Record<string, string> = {
  Draft: 'default',
  Pending: 'processing',
  Paid: 'success',
  Overdue: 'error',
  Cancelled: 'warning',
};

const BillingTab = () => {
  const [activeTab, setActiveTab] = useState('invoices');
  const [invoiceModal, setInvoiceModal] = useState(false);
  const [form] = Form.useForm();
  const { formatCurrency, currencySymbol } = useCurrency();

  // Dedicated hooks — no raw useQuery, no double .data access
  const { data: invoicesPage, isLoading: loadingInvoices } = useInvoices();
  const { data: usagePage, isLoading: loadingUsage } = useTenantUsageRecords();
  const { data: analytics } = useBillingAnalytics();
  const { data: tenants = [] } = useTenants();

  const createInvoiceMut = useCreateInvoice();
  const updateInvoiceMut = useUpdateInvoice();

  const invoices: Invoice[] = invoicesPage?.results || [];
  const usage: TenantUsage[] = usagePage?.results || [];

  const invoiceColumns = [
    { title: 'Invoice #', dataIndex: 'invoice_number', key: 'invoice_number', width: 160 },
    { title: 'Tenant', dataIndex: 'tenant_name', key: 'tenant_name' },
    {
      title: 'Period', key: 'period',
      render: (_: any, r: Invoice) => `${r.period_start} - ${r.period_end}`,
    },
    {
      title: 'Amount', dataIndex: 'total_amount', key: 'total_amount',
      render: (v: string) => formatCurrency(parseFloat(v)),
    },
    {
      title: 'Status', dataIndex: 'status', key: 'status',
      render: (s: string) => <Tag color={statusColor[s] || 'default'}>{s}</Tag>,
    },
    { title: 'Due Date', dataIndex: 'due_date', key: 'due_date' },
    {
      title: 'Actions', key: 'actions',
      render: (_: any, r: Invoice) => (
        <Space size="small">
          {r.status === 'Draft' && (
            <Button size="small" type="link"
              onClick={() => updateInvoiceMut.mutate(
                { id: r.id, data: { status: 'Pending' } },
                { onSuccess: () => message.success('Invoice sent'), onError: (e: any) => message.error(e?.response?.data?.error || 'Failed') },
              )}>
              Send
            </Button>
          )}
          {r.status === 'Pending' && (
            <Button size="small" type="link" style={{ color: '#52c41a' }}
              onClick={() => updateInvoiceMut.mutate(
                { id: r.id, data: { status: 'Paid' } },
                { onSuccess: () => message.success('Marked as paid'), onError: (e: any) => message.error(e?.response?.data?.error || 'Failed') },
              )}>
              Mark Paid
            </Button>
          )}
          {r.status === 'Pending' && (
            <Button size="small" type="link" danger
              onClick={() => updateInvoiceMut.mutate(
                { id: r.id, data: { status: 'Overdue' } },
                { onSuccess: () => message.success('Marked as overdue'), onError: (e: any) => message.error(e?.response?.data?.error || 'Failed') },
              )}>
              Mark Overdue
            </Button>
          )}
        </Space>
      ),
    },
  ];

  const usageColumns = [
    { title: 'Tenant', dataIndex: 'tenant_name', key: 'tenant_name' },
    {
      title: 'Period', key: 'period',
      render: (_: any, r: TenantUsage) => `${r.billing_period_start} - ${r.billing_period_end}`,
    },
    { title: 'Users', dataIndex: 'users_count', key: 'users_count' },
    {
      title: 'Storage', dataIndex: 'storage_mb', key: 'storage_mb',
      render: (v: number) => `${(v / 1024).toFixed(1)} GB`,
    },
    { title: 'API Calls', dataIndex: 'api_calls', key: 'api_calls', render: (v: number) => v.toLocaleString() },
    {
      title: 'Total Cost', dataIndex: 'total_cost', key: 'total_cost',
      render: (v: string) => formatCurrency(parseFloat(v)),
    },
    {
      title: 'Billed', dataIndex: 'is_billed', key: 'is_billed',
      render: (v: boolean) => <Tag color={v ? 'success' : 'warning'}>{v ? 'Yes' : 'No'}</Tag>,
    },
  ];

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
        <h2 style={{ margin: 0 }}>Billing & Invoicing</h2>
      </div>

      {analytics && (
        <Row gutter={16} style={{ marginBottom: 24 }}>
          <Col span={4}>
            <Card size="small">
              <Statistic title="Total Invoiced" value={parseFloat(analytics.summary.total_invoiced)}
                prefix={currencySymbol} precision={2} />
            </Card>
          </Col>
          <Col span={4}>
            <Card size="small">
              <Statistic title="Total Paid" value={parseFloat(analytics.summary.total_paid)}
                prefix={currencySymbol} precision={2} styles={{ content: { color: '#3f8600' } }} />
            </Card>
          </Col>
          <Col span={4}>
            <Card size="small">
              <Statistic title="Pending" value={parseFloat(analytics.summary.total_pending)}
                prefix={currencySymbol} precision={2} styles={{ content: { color: '#1890ff' } }} />
            </Card>
          </Col>
          <Col span={4}>
            <Card size="small">
              <Statistic title="Overdue" value={parseFloat(analytics.summary.total_overdue)}
                prefix={currencySymbol} precision={2} styles={{ content: { color: '#cf1322' } }} />
            </Card>
          </Col>
          <Col span={4}>
            <Card size="small">
              <Statistic title="Commissions Paid" value={parseFloat(analytics.summary.total_commissions_paid)}
                prefix={currencySymbol} precision={2} />
            </Card>
          </Col>
          <Col span={4}>
            <Card size="small">
              <Statistic title="Pending Commissions" value={parseFloat(analytics.summary.pending_commissions)}
                prefix={currencySymbol} precision={2} styles={{ content: { color: '#faad14' } }} />
            </Card>
          </Col>
        </Row>
      )}

      <Tabs activeKey={activeTab} onChange={setActiveTab}>
        <TabPane tab={<span><FileTextOutlined /> Invoices</span>} key="invoices">
          <div style={{ marginBottom: 16 }}>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setInvoiceModal(true)}>
              Create Invoice
            </Button>
          </div>
          <Table
            dataSource={invoices}
            columns={invoiceColumns}
            rowKey="id"
            loading={loadingInvoices}
            size="middle"
            pagination={{ pageSize: 15 }}
          />
        </TabPane>

        <TabPane tab={<span><BarChartOutlined /> Usage</span>} key="usage">
          <Table
            dataSource={usage}
            columns={usageColumns}
            rowKey="id"
            loading={loadingUsage}
            size="middle"
            pagination={{ pageSize: 15 }}
          />
        </TabPane>

        <TabPane tab={<span><DollarOutlined /> Revenue</span>} key="revenue">
          <Card title="Monthly Revenue">
            {analytics?.monthly_revenue?.length ? (
              <Table
                dataSource={analytics.monthly_revenue}
                columns={[
                  {
                    title: 'Month', dataIndex: 'month', key: 'month',
                    render: (v: string) => new Date(v).toLocaleDateString('en-US', { year: 'numeric', month: 'long' }),
                  },
                  {
                    title: 'Revenue', dataIndex: 'total', key: 'total',
                    render: (v: string) => formatCurrency(parseFloat(v)),
                  },
                  { title: 'Invoices', dataIndex: 'count', key: 'count' },
                ]}
                rowKey="month"
                size="middle"
                pagination={false}
              />
            ) : (
              <Text type="secondary">No revenue data yet.</Text>
            )}
          </Card>
        </TabPane>
      </Tabs>

      <Modal
        title="Create Invoice"
        open={invoiceModal}
        onCancel={() => setInvoiceModal(false)}
        onOk={() => form.submit()}
        confirmLoading={createInvoiceMut.isPending}
        width={600}
      >
        <Form form={form} layout="vertical"
          onFinish={(values) => {
            const fmt = (d: any) => {
              if (!d) return '';
              if (typeof d === 'string') return d;
              if (d.$d) return d.$d.toISOString().split('T')[0];
              return d.toISOString().split('T')[0];
            };
            createInvoiceMut.mutate(
              {
                ...values,
                period_start: fmt(values.period_start),
                period_end: fmt(values.period_end),
                due_date: fmt(values.due_date),
              },
              {
                onSuccess: () => { message.success('Invoice created'); setInvoiceModal(false); form.resetFields(); },
                onError: (err: any) => message.error(err?.response?.data?.error || 'Failed'),
              },
            );
          }}>
          <Form.Item name="tenant_id" label="Tenant" rules={[{ required: true }]}>
            <Select placeholder="Select tenant" showSearch
              filterOption={(input, opt) => (opt?.label as string || '').toLowerCase().includes(input.toLowerCase())}
              options={tenants.map((t: any) => ({ value: t.id, label: t.name }))} />
          </Form.Item>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="period_start" label="Period Start" rules={[{ required: true }]}>
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="period_end" label="Period End" rules={[{ required: true }]}>
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="due_date" label="Due Date" rules={[{ required: true }]}>
            <DatePicker style={{ width: '100%' }} />
          </Form.Item>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="subscription_amount" label="Subscription Amount" initialValue={0}>
                <InputNumber style={{ width: '100%' }} min={0} precision={2} prefix={currencySymbol} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="usage_amount" label="Usage Amount" initialValue={0}>
                <InputNumber style={{ width: '100%' }} min={0} precision={2} prefix={currencySymbol} />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item name="tax_amount" label="Tax" initialValue={0}>
                <InputNumber style={{ width: '100%' }} min={0} precision={2} prefix={currencySymbol} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="discount_amount" label="Discount" initialValue={0}>
                <InputNumber style={{ width: '100%' }} min={0} precision={2} prefix={currencySymbol} />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="notes" label="Notes">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default BillingTab;
