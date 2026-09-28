import { App as AntApp, Button, Card, Form, Input } from 'antd';
import { useEffect } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { FileText } from 'lucide-react';
import apiClient from '../../api/client';
import { useBankLetterSettings } from '../accounting/hooks/usePaymentBatches';
import SettingsLayout from './SettingsLayout';

const SUBTITLE =
  'Letterhead and signatories for the bank payment/confirmation letter. These are separate from the warrant printout settings.';

export default function BankLetterSettingsPage() {
  const [form] = Form.useForm();
  const { message } = AntApp.useApp();
  const qc = useQueryClient();
  const { data, isLoading } = useBankLetterSettings();

  useEffect(() => { if (data) form.setFieldsValue(data); }, [data, form]);

  const save = useMutation({
    mutationFn: async (values: Record<string, unknown>) =>
      (await apiClient.patch('/accounting/bank-letter-settings/current/', values)).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['bank-letter-settings'] });
      message.success('Bank letter settings saved');
    },
    onError: () => message.error('Could not save settings'),
  });

  const layoutProps = {
    title: 'Bank Letter Settings',
    breadcrumb: 'Bank Letter',
    subtitle: SUBTITLE,
    icon: <FileText size={22} color="white" />,
    maxWidth: '760px',
  } as const;

  if (isLoading) {
    return (
      <SettingsLayout {...layoutProps}>
        <div style={{ padding: 24, color: 'var(--color-text-muted)' }}>Loading…</div>
      </SettingsLayout>
    );
  }

  return (
    <SettingsLayout {...layoutProps}>
      <Form form={form} layout="vertical" onFinish={(v) => save.mutate(v)}>
        <Card size="small" title="Letterhead" style={{ marginBottom: 16 }}>
          <Form.Item name="ministry_name" label="Ministry"><Input /></Form.Item>
          <Form.Item name="office_name" label="Office"><Input /></Form.Item>
          <Form.Item name="office_address" label="Address (e.g. Asaba)"><Input /></Form.Item>
        </Card>

        <Card size="small" title="Signatory 1 — Accountant General" style={{ marginBottom: 16 }}>
          <Form.Item name="accountant_general_name" label="Name"><Input /></Form.Item>
          <Form.Item name="accountant_general_title" label="Title"><Input /></Form.Item>
        </Card>

        <Card size="small" title="Signatory 2 — Director Treasury" style={{ marginBottom: 16 }}>
          <Form.Item name="director_treasury_name" label="Name"><Input /></Form.Item>
          <Form.Item name="director_treasury_title" label="Title"><Input /></Form.Item>
        </Card>

        <Card size="small" title="Signatory 3 — Director Management Accounts" style={{ marginBottom: 16 }}>
          <Form.Item name="director_mgmt_acct_name" label="Name"><Input /></Form.Item>
          <Form.Item name="director_mgmt_acct_title" label="Title"><Input /></Form.Item>
        </Card>

        <Button type="primary" htmlType="submit" loading={save.isPending}>Save settings</Button>
      </Form>
    </SettingsLayout>
  );
}
