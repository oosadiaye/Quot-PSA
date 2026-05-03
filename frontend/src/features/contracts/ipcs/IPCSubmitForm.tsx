import { useNavigate, useParams } from 'react-router-dom';
import { Form, InputNumber, DatePicker, Input, Button, Card, App as AntApp } from 'antd';
import PageHeader from '../../../components/PageHeader';
import { useCreateIPC } from '../hooks/useIPCs';
import { formatServiceError } from '../utils/errors';
import { ListPageShell } from '../../../components/layout';

const IPCSubmitForm = () => {
  const { id: contractId } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { message } = AntApp.useApp();
  const [form] = Form.useForm();
  const createMut = useCreateIPC();

  const onFinish = async (values: any) => {
    const payload = {
      ...values,
      contract: Number(contractId),
      posting_date: values.posting_date?.format('YYYY-MM-DD'),
    };
    try {
      const created = await createMut.mutateAsync(payload);
      message.success('IPC submitted — routed to certifier');
      navigate(`/contracts/ipcs/${created.id}`);
    } catch (e) {
      // Backend will reject with CONTRACT_CEILING_BREACH or IPC_DUPLICATE_HASH —
      // formatServiceError surfaces the code-specific hint.
      message.error(formatServiceError(e, 'Could not submit IPC'));
    }
  };

  return (
    <ListPageShell>
        <PageHeader
          title="Submit IPC"
          subtitle={`Contract #${contractId} — new interim payment certificate`}
        />
        <Card>
          <Form form={form} layout="vertical" onFinish={onFinish}>
            <Form.Item
              label="Posting Date"
              name="posting_date"
              rules={[{ required: true, message: 'Posting date is required' }]}
              extra="Effective date for this IPC — must fall inside the contract's fiscal year."
            >
              <DatePicker style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item
              label="Cumulative Work Done to Date"
              name="cumulative_work_done_to_date"
              rules={[{ required: true, message: 'Cumulative amount required' }]}
              extra={
                'Engineer\'s running total of all work completed on this contract to date. ' +
                'The server computes this certificate\'s gross as (cumulative − previously certified), ' +
                'and rejects the submission if it breaches the ceiling or goes backwards from the last IPC.'
              }
            >
              <InputNumber
                min={0}
                step={1000}
                style={{ width: '100%' }}
                formatter={(v) => `${v}`.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}
                parser={(v) => Number((v ?? '').toString().replace(/,/g, ''))}
              />
            </Form.Item>
            <Form.Item label="Measurement Book Ref" name="measurement_book_reference">
              <Input />
            </Form.Item>
            <Form.Item label="Notes" name="notes">
              <Input.TextArea rows={3} />
            </Form.Item>
            <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}>
              <Button onClick={() => navigate(-1)}>Cancel</Button>
              <Button type="primary" htmlType="submit" loading={createMut.isPending}>
                Submit for Certification
              </Button>
            </div>
          </Form>
        </Card>
    </ListPageShell>
  );
};

export default IPCSubmitForm;
