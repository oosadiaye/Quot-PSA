import { useNavigate, useParams } from 'react-router-dom';
import { Form, InputNumber, Input, Button, Card, Alert, App as AntApp } from 'antd';
import { useState } from 'react';
import PageHeader from '../../../components/PageHeader';
import { useContract, useContractAppropriation } from '../hooks/useContracts';
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
  const { data: appropriation } = useContractAppropriation(Number(contractId));
  const createMut = useCreateVariation();

  const ceiling = Number(contract?.contract_ceiling || 0);
  // ``approved_variations_total`` is what the serializer exposes (the old
  // ``cumulative_variation_amount`` was never served → always 0).
  const existingCumulative = Number(contract?.approved_variations_total || 0);
  const tier = computeProjectedTier(ceiling, existingCumulative, delta);

  // Budget cap — a write-up may not exceed the appropriation's available
  // balance. ``resolved: false`` means no appropriation matched, so the cap is
  // advisory only (the backend also won't block).
  const budgetResolved = appropriation?.resolved === true;
  const available = budgetResolved ? Number(appropriation?.available_balance || 0) : null;
  const overBudget = available != null && delta > available;

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
      message.success('Write-up created');
      navigate(`/contracts/variations/${created.id}`);
    } catch (e) {
      message.error(formatServiceError(e, 'Create failed'));
    }
  };

  return (
    <ListPageShell>
        <PageHeader
          title="New Write-up"
          subtitle={`Contract #${contractId} — upward revaluation of contract amount`}
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
              Current ceiling {formatCurrency(ceiling)} — existing cumulative write-ups{' '}
              {formatCurrency(existingCumulative)}
            </div>
          )}
          {budgetResolved && available != null && (
            <Alert
              type={overBudget ? 'error' : 'info'}
              showIcon
              message={
                overBudget
                  ? `Exceeds budget by ${formatCurrency(delta - available)}`
                  : `Budget available for write-up: ${formatCurrency(available)}`
              }
              description={
                overBudget
                  ? `A write-up may not exceed the appropriation's available balance of ${formatCurrency(available)}. Reduce the amount or raise a supplementary budget first.`
                  : "The write-up cannot exceed the contract appropriation's available balance."
              }
              style={{ marginBottom: '1rem' }}
            />
          )}
          <Form form={form} layout="vertical" onFinish={onFinish}>
            <Form.Item
              label="Write-up Amount"
              name="amount"
              rules={[
                { required: true, message: 'Amount required' },
                {
                  // Write-ups are upward revaluations only, and may not exceed
                  // the appropriation's available balance. The backend enforces
                  // both; these client guards give faster feedback.
                  validator: (_, v) => {
                    if (v == null) return Promise.resolve();
                    if (Number(v) <= 0)
                      return Promise.reject(
                        new Error(
                          'Write-up amount must be greater than zero — downward revaluations are not handled here.',
                        ),
                      );
                    if (available != null && Number(v) > available)
                      return Promise.reject(
                        new Error(
                          `Exceeds the appropriation's available balance of ${formatCurrency(available)}.`,
                        ),
                      );
                    return Promise.resolve();
                  },
                },
              ]}
              extra="Increase to the contract amount. Must be greater than zero — write-ups revalue the contract upward only."
            >
              <InputNumber
                min={0.01}
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
              <Button
                type="primary"
                htmlType="submit"
                loading={createMut.isPending}
                disabled={overBudget}
                title={overBudget ? 'Reduce the amount to within the available budget' : undefined}
              >
                Submit Write-up
              </Button>
            </div>
          </Form>
        </Card>
    </ListPageShell>
  );
};

export default VariationForm;
