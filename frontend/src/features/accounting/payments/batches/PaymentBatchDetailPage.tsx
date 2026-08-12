import { App as AntApp, Button, Descriptions, Popconfirm, Space, Table, Tag, Typography } from 'antd';
import { useNavigate, useParams } from 'react-router-dom';
import {
  useCancelBatch, useConfirmBatch, useDispatchBatch, usePaymentBatch,
  useRemoveBatchLine, type PaymentBatchLine,
} from '../../hooks/usePaymentBatches';

function apiError(e: unknown): string {
  const r = (e as { response?: { data?: { error?: string } } }).response;
  return r?.data?.error || 'The operation failed. Please try again.';
}

export default function PaymentBatchDetailPage() {
  const { id } = useParams<{ id: string }>();
  const batchId = Number(id);
  const navigate = useNavigate();
  const { message } = AntApp.useApp();

  const { data: batch, isLoading } = usePaymentBatch(batchId);
  const removeLine = useRemoveBatchLine(batchId);
  const dispatchBatch = useDispatchBatch(batchId);
  const confirmBatch = useConfirmBatch(batchId);
  const cancelBatch = useCancelBatch(batchId);

  if (isLoading || !batch) return <div style={{ padding: 24 }}>Loading…</div>;

  const isDraft = batch.status === 'Draft';

  const run = (p: Promise<unknown>, ok: string) =>
    p.then(() => message.success(ok)).catch((e) => message.error(apiError(e)));

  const columns = [
    { title: 'S/N', dataIndex: 'sequence', key: 'sequence', width: 60 },
    { title: 'Vendor Name', dataIndex: 'payee_name', key: 'payee_name' },
    { title: 'Bank', dataIndex: 'payee_bank', key: 'payee_bank' },
    { title: 'Account', dataIndex: 'payee_account', key: 'payee_account' },
    { title: 'Purpose', dataIndex: 'purpose', key: 'purpose' },
    {
      title: 'Amount', dataIndex: 'amount', key: 'amount', align: 'right' as const,
      render: (v: string) => Number(v).toLocaleString('en-NG', { minimumFractionDigits: 2 }),
    },
    ...(isDraft ? [{
      title: '', key: 'remove',
      render: (_: unknown, row: PaymentBatchLine) => (
        <Button size="small" danger
          onClick={() => run(removeLine.mutateAsync({ line_id: row.id }), 'Line removed')}>
          Remove
        </Button>
      ),
    }] : []),
  ];

  return (
    <div style={{ padding: 24 }}>
      <Space style={{ marginBottom: 12 }}>
        <Typography.Title level={3} style={{ margin: 0 }}>{batch.batch_number}</Typography.Title>
        <Tag>{batch.status}</Tag>
      </Space>

      <Descriptions size="small" bordered column={2} style={{ marginBottom: 16 }}>
        <Descriptions.Item label="Bank">{batch.addressee_bank_name}</Descriptions.Item>
        <Descriptions.Item label="Account No.">{batch.addressee_account_no}</Descriptions.Item>
        <Descriptions.Item label="Lines">{batch.line_count}</Descriptions.Item>
        <Descriptions.Item label="Total">
          {Number(batch.total_amount).toLocaleString('en-NG', { minimumFractionDigits: 2 })}
        </Descriptions.Item>
      </Descriptions>

      <Space style={{ marginBottom: 12 }}>
        <Button onClick={() => navigate(`/accounting/payment-batches/${batchId}/letter`)}>
          View letter
        </Button>
        {isDraft && (
          <Popconfirm
            title="Dispatch this batch?"
            description="This marks the letter as sent to the bank and locks the lines."
            onConfirm={() => run(dispatchBatch.mutateAsync(), 'Batch dispatched')}
          >
            <Button type="primary">Dispatch</Button>
          </Popconfirm>
        )}
        {batch.status === 'Dispatched' && (
          <Button onClick={() => run(confirmBatch.mutateAsync(), 'Batch confirmed')}>
            Mark confirmed by bank
          </Button>
        )}
        {batch.status !== 'Confirmed' && batch.status !== 'Cancelled' && (
          <Popconfirm
            title="Cancel this batch?"
            description="Its payments return to the eligible pool."
            onConfirm={() => run(
              cancelBatch.mutateAsync({ reason: 'Cancelled by operator' }), 'Batch cancelled')}
          >
            <Button danger>Cancel batch</Button>
          </Popconfirm>
        )}
      </Space>

      <Table
        rowKey="id"
        size="small"
        dataSource={batch.lines.filter((l) => l.is_active_membership)}
        columns={columns}
        pagination={false}
      />
    </div>
  );
}
