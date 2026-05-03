import { useNavigate, useParams } from 'react-router-dom';
import { Card, Descriptions, Tag, Button, Space, App as AntApp } from 'antd';
import PageHeader from '../../../components/PageHeader';
import LoadingScreen from '../../../components/common/LoadingScreen';
import {
  useVariation,
  useReviewVariation,
  useApproveVariation,
  useRejectVariation,
} from '../hooks/useVariations';
import { formatServiceError } from '../utils/errors';
import { useCurrency } from '../../../context/CurrencyContext';
import { ListPageShell } from '../../../components/layout';

const TIER_COLOR: Record<string, string> = {
  LOCAL: 'blue',
  BOARD: 'orange',
  BPP_REQUIRED: 'red',
};

const ACTIONS: Record<string, Array<'review' | 'approve'>> = {
  SUBMITTED: ['review'],
  REVIEWED: ['approve'],
};

const VariationDetail = () => {
  const { id } = useParams<{ id: string }>();
  const vid = Number(id);
  const navigate = useNavigate();
  const { message } = AntApp.useApp();
  const { formatCurrency } = useCurrency();

  const { data: v, isLoading } = useVariation(vid);
  const review = useReviewVariation();
  const approve = useApproveVariation();
  const reject = useRejectVariation();

  if (isLoading) return <LoadingScreen />;
  if (!v) return null;

  const run = async (
    label: string,
    hook: { mutateAsync: (p: { id: number }) => Promise<unknown> },
  ) => {
    try {
      await hook.mutateAsync({ id: vid });
      message.success(`${label} successful`);
    } catch (e) {
      message.error(formatServiceError(e, `${label} failed`));
    }
  };

  const allowed = ACTIONS[v.status] ?? [];
  const terminal = ['APPROVED', 'REJECTED'].includes(v.status);

  return (
    <ListPageShell>
        <PageHeader
          title={v.variation_number}
          subtitle={`Variation — ${v.contract_reference ?? `contract #${v.contract}`}`}
          actions={
            <Space>
              {allowed.includes('review') && (
                <Button type="primary" onClick={() => run('Review', review)}>
                  Review
                </Button>
              )}
              {allowed.includes('approve') && (
                <Button type="primary" onClick={() => run('Approve', approve)}>
                  Approve
                </Button>
              )}
              {!terminal && (
                <Button danger onClick={() => run('Reject', reject)}>
                  Reject
                </Button>
              )}
            </Space>
          }
        />
        <Card>
          <Descriptions column={2} bordered size="small">
            <Descriptions.Item label="Status">
              <Tag>{v.status}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="Tier">
              <Tag color={TIER_COLOR[v.approval_tier] || 'default'}>{v.approval_tier}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="Delta">
              {formatCurrency(Number(v.delta_amount || 0))}
            </Descriptions.Item>
            <Descriptions.Item label="Cumulative %">{Number(v.cumulative_pct ?? 0).toFixed(1)}%</Descriptions.Item>
            <Descriptions.Item label="Justification" span={2}>
              {v.justification || '—'}
            </Descriptions.Item>
            <Descriptions.Item label="Supporting Reference" span={2}>
              {v.supporting_reference || '—'}
            </Descriptions.Item>
          </Descriptions>
          <div style={{ marginTop: '1rem' }}>
            <Button onClick={() => navigate(`/contracts/${v.contract}`)}>Back to contract</Button>
          </div>
        </Card>
    </ListPageShell>
  );
};

export default VariationDetail;
