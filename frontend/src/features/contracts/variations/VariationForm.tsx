import { useNavigate, useParams } from 'react-router-dom';
import { Form, InputNumber, Input, Button, Card, Alert, App as AntApp } from 'antd';
import { useState } from 'react';
import PageHeader from '../../../components/PageHeader';
import { useContract } from '../hooks/useContracts';
import { useCreateVariation } from '../hooks/useVariations';
import { formatServiceError } from '../utils/errors';
import { useCurrency } from '../../../context/CurrencyContext';
import { ListPageShell } from '../../../components/layout';

/**
 * Compute the *projected* approval tier client-side as the user types so
 * they see the governance consequence before submitting. The server is
 * the source of truth — this is UX polish, not enforcement.
 */
function computeProjectedTier(
  ceiling: number,
  existingCumulative: number,
  delta: number,
): 'LOCAL' | 'BOARD' | 'BPP_REQUIRED' | null {
  if (!ceiling) return null;
  const pct = ((existingCumulative + delta) / ceiling) * 100;
  if (pct > 25) return 'BPP_REQUIRED';
  if (pct > 15) return 'BOARD';
  return 'LOCAL';
}

const VariationForm = () => {
  const { id: contractId } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { message } = AntApp.useApp();
  const { formatCurrency } = useCurrency();
  const [form] = Form.useForm();
  const [delta, setDelta] = useState<number>(0);

  const { data: contract } = useContract(Number(contractId));
  const createMut = useCreateVariation();

  const ceiling = Number(contract?.contract_ceiling || 0);
  const existingCumulative = Number(contract?.cumulative_variation_amount || 0);
  const tier = computeProjectedTier(ceiling, existingCumulative, delta);

  const tierCopy = {
    LOCAL: 'Local-level sign-off (≤15% cumulative).',
    BOARD: 'Tenders Board approval required (≤25%).',
    BPP_REQUIRED: 'Exceeds 25% — BPP No-Objection required before approval.',
  };

  const onFinish = async (values: any) => {
    try {
      const created = await createMut.mutateAsync({
        ...values,
        contract: Number(contractId),
      });
      message.success('Variation created');
      navigate(`/contracts/variations/${created.id}`);
    } catch (e) {
      message.error(formatServiceError(e, 'Create failed'));
    }
  };

  return (
    <ListPageShell>
        <PageHeader
          title="New Variation"
          subtitle={`Contract #${contractId} — change order`}
        />
        <Card>
          {tier && (
            <Alert
              type={tier === 'BPP_REQUIRED' ? 'error' : tier === 'BOARD' ? 'warning' : 'info'}
              showIcon
              message={`Projected approval tier: ${tier}`}
              description={tierCopy[tier]}
              style={{ marginBottom: '1rem' }}
            />
          )}
          {ceiling > 0 && (
            <div style={{ marginBottom: '1rem', fontSize: '0.9rem', opacity: 0.75 }}>
              Current ceiling {formatCurrency(ceiling)} — existing cumulative variation{' '}
              {formatCurrency(existingCumulative)}
            </div>
          )}
          <Form form={form} layout="vertical" onFinish={onFinish}>
            <Form.Item
              label="Delta Amount"
              name="delta_amount"
              rules={[{ required: true, message: 'Delta required' }]}
              extra="Positive for scope-up; negative for scope-down."
            >
              <InputNumber
                step={1000}
                style={{ width: '100%' }}
                onChange={(v) => setDelta(Number(v || 0))}
              />
            </Form.Item>
            <Form.Item
              label="Justification"
              name="justification"
              rules={[{ required: true, message: 'Justification required for audit' }]}
            >
              <Input.TextArea rows={4} />
            </Form.Item>
            <Form.Item label="Supporting Reference" name="supporting_reference">
              <Input placeholder="e.g. BoQ rev 2, site instruction 0045" />
            </Form.Item>
            <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}>
              <Button onClick={() => navigate(-1)}>Cancel</Button>
              <Button type="primary" htmlType="submit" loading={createMut.isPending}>
                Submit Variation
              </Button>
            </div>
          </Form>
        </Card>
    </ListPageShell>
  );
};

export default VariationForm;
