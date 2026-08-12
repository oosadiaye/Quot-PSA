import { Button, Space, Table, Tag, Typography } from 'antd';
import { useNavigate } from 'react-router-dom';
import { usePaymentBatches, type PaymentBatch, type PaymentBatchStatus }
  from '../../hooks/usePaymentBatches';

const STATUS_COLOUR: Record<PaymentBatchStatus, string> = {
  Draft: 'default',
  Dispatched: 'processing',
  Confirmed: 'success',
  Cancelled: 'error',
};

function formatDate(iso: string): string {
  const [y, m, d] = iso.split('-').map(Number);
  return new Date(y, m - 1, d).toLocaleDateString('en-GB');
}

export default function PaymentBatchListPage() {
  const navigate = useNavigate();
  const { data: batches = [], isLoading } = usePaymentBatches();

  const columns = [
    { title: 'Batch No.', dataIndex: 'batch_number', key: 'batch_number' },
    {
      title: 'Date', dataIndex: 'batch_date', key: 'batch_date',
      render: (v: string) => formatDate(v),
    },
    { title: 'Bank', dataIndex: 'addressee_bank_name', key: 'addressee_bank_name' },
    { title: 'Account', dataIndex: 'addressee_account_no', key: 'addressee_account_no' },
    { title: 'Lines', dataIndex: 'line_count', key: 'line_count', align: 'right' as const },
    {
      title: 'Total', dataIndex: 'total_amount', key: 'total_amount',
      align: 'right' as const,
      render: (v: string) => Number(v).toLocaleString('en-NG', { minimumFractionDigits: 2 }),
    },
    {
      title: 'Status', dataIndex: 'status', key: 'status',
      render: (s: PaymentBatchStatus) => <Tag color={STATUS_COLOUR[s]}>{s}</Tag>,
    },
    {
      title: '', key: 'actions',
      render: (_: unknown, row: PaymentBatch) => (
        <Space>
          <Button size="small" onClick={() => navigate(`/accounting/payment-batches/${row.id}`)}>
            Open
          </Button>
          <Button size="small" onClick={() => navigate(`/accounting/payment-batches/${row.id}/letter`)}>
            Letter
          </Button>
        </Space>
      ),
    },
  ];

  return (
    <div style={{ padding: 24 }}>
      <Typography.Title level={3} style={{ marginBottom: 4 }}>Payment Batches</Typography.Title>
      <Typography.Paragraph type="secondary">
        Group posted payments drawn on one government account into a signed
        bank payment/confirmation letter.
      </Typography.Paragraph>
      <Table
        rowKey="id"
        loading={isLoading}
        dataSource={batches}
        columns={columns}
        size="small"
      />
    </div>
  );
}
