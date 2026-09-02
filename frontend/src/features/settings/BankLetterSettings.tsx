import { App as AntApp, Button, Card, Form, Input, Typography } from 'antd';
import { useEffect } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import apiClient from '../../api/client';
import { useBankLetterSettings } from '../accounting/hooks/usePaymentBatches';

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

  if (isLoading) return <div style={{ padding: 24 }}>Loading…</div>;

  return (
    <div style={{ padding: 24, maxWidth: 760 }}>
      <Typography.Title level={3}>Bank Letter Settings</Typography.Title>
      <Typography.Paragraph type="secondary">
        Letterhead and signatories for the bank payment/confirmation letter.
        These are separate from the warrant printout settings.
      </Typography.Paragraph>

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
    </div>
  );
}
