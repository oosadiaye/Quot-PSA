import { Card, Row, Col, Form, Input, InputNumber, Select, Switch, Button, Skeleton, App, Divider, Popconfirm } from 'antd';
import { MailOutlined, SendOutlined, ReloadOutlined } from '@ant-design/icons';
import { useEffect, useState } from 'react';
import { useSuperAdminSettings, useSaveSuperAdminSettings, useTestSmtp } from '../hooks/useSuperAdmin';

const cardStyle: React.CSSProperties = {
  borderRadius: 12, border: 'none',
  boxShadow: '0 2px 8px rgba(0, 0, 0, 0.06), 0 1px 2px rgba(0, 0, 0, 0.04)',
};

const SettingsTab = () => {
  const { message } = App.useApp();
  const { data: settings, isLoading } = useSuperAdminSettings();
  const saveSettings = useSaveSuperAdminSettings();
  const testSmtp = useTestSmtp();
  const [form] = Form.useForm();
  const [testEmail, setTestEmail] = useState('');

  useEffect(() => {
    if (settings) {
      form.setFieldsValue(settings);
    }
  }, [settings, form]);

  const handleSave = async () => {
    try {
      const values = await form.validateFields();
      await saveSettings.mutateAsync(values);
      message.success('Settings saved successfully');
    } catch (err: any) {
      if (err?.errorFields) return;
      message.error('Failed to save settings');
    }
  };

  const handleTestEmail = async () => {
    if (!testEmail) {
      message.warning('Enter a recipient email address');
      return;
    }
    try {
      await testSmtp.mutateAsync(testEmail);
      message.success(`Test email sent to ${testEmail}`);
    } catch (err: any) {
      message.error(err?.response?.data?.error || 'SMTP test failed');
    }
  };

  if (isLoading) return <Skeleton active paragraph={{ rows: 12 }} />;

  return (
    <Form form={form} layout="vertical" initialValues={settings || {}}>
      <Row gutter={20}>
        <Col span={12}>
          <Card title={<span style={{ fontWeight: 600, fontSize: 'var(--text-base)' }}>General Settings</span>} style={cardStyle}>
            <Form.Item label="Organization Name" name="organization_name">
              <Input />
            </Form.Item>
            <Form.Item label="Default Timezone" name="default_timezone">
              <Select>
                <Select.Option value="UTC">UTC</Select.Option>
                <Select.Option value="Africa/Lagos">Africa/Lagos</Select.Option>
                <Select.Option value="America/New_York">America/New York</Select.Option>
                <Select.Option value="Europe/London">Europe/London</Select.Option>
                <Select.Option value="Asia/Dubai">Asia/Dubai</Select.Option>
              </Select>
            </Form.Item>
            <Form.Item label="Default Currency" name="default_currency">
              <Select>
                <Select.Option value="NGN">Nigerian Naira (NGN)</Select.Option>
                <Select.Option value="USD">US Dollar (USD)</Select.Option>
                <Select.Option value="EUR">Euro (EUR)</Select.Option>
                <Select.Option value="GBP">British Pound (GBP)</Select.Option>
              </Select>
            </Form.Item>
            <Form.Item label="Maintenance Mode" name="maintenance_mode" valuePropName="checked">
              <Switch checkedChildren="ON" unCheckedChildren="OFF" />
            </Form.Item>
          </Card>
        </Col>
        <Col span={12}>
          <Card title={<span style={{ fontWeight: 600, fontSize: 'var(--text-base)' }}>Security Settings</span>} style={cardStyle}>
            <Form.Item label="Session Timeout (minutes)" name="session_timeout_minutes">
              <InputNumber min={5} max={1440} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item label="Require Special Characters" name="require_special_chars" valuePropName="checked">
              <Switch />
            </Form.Item>
            <Form.Item label="Require Uppercase Letters" name="require_uppercase" valuePropName="checked">
              <Switch />
            </Form.Item>
            <Form.Item label="Minimum Password Length" name="min_password_length">
              <InputNumber min={6} max={32} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item label="Two-Factor Authentication" name="two_factor_enabled" valuePropName="checked">
              <Switch checkedChildren="ENABLED" unCheckedChildren="DISABLED" />
            </Form.Item>
          </Card>
        </Col>
      </Row>

      <Card title={<span style={{ fontWeight: 600, fontSize: 'var(--text-base)' }}>API Settings</span>} style={{ ...cardStyle, marginTop: 20 }}>
        <Row gutter={16}>
          <Col span={8}>
            <Form.Item label="Rate Limit (requests/hour)" name="rate_limit_per_hour">
              <InputNumber min={100} style={{ width: '100%' }} />
            </Form.Item>
          </Col>
          <Col span={8}>
            <Form.Item label="Token Expiry (days)" name="token_expiry_days">
              <InputNumber min={1} max={365} style={{ width: '100%' }} />
            </Form.Item>
          </Col>
          <Col span={8}>
            <Form.Item label="Max Login Attempts" name="max_login_attempts">
              <InputNumber min={3} max={20} style={{ width: '100%' }} />
            </Form.Item>
          </Col>
        </Row>
      </Card>

      <Card
        title={<span style={{ fontWeight: 600, fontSize: 'var(--text-base)' }}><MailOutlined style={{ marginRight: 8 }} />Email / SMTP Configuration</span>}
        style={{ ...cardStyle, marginTop: 20 }}
      >
        <Form.Item label="Enable SMTP" name="smtp_enabled" valuePropName="checked">
          <Switch checkedChildren="ENABLED" unCheckedChildren="DISABLED" />
        </Form.Item>
        <Row gutter={16}>
          <Col span={12}>
            <Form.Item label="SMTP Host" name="smtp_host">
              <Input placeholder="smtp.gmail.com" />
            </Form.Item>
          </Col>
          <Col span={6}>
            <Form.Item label="SMTP Port" name="smtp_port">
              <InputNumber min={1} max={65535} style={{ width: '100%' }} placeholder="587" />
            </Form.Item>
          </Col>
          <Col span={6}>
            <Row gutter={8}>
              <Col span={12}>
                <Form.Item label="Use TLS" name="smtp_use_tls" valuePropName="checked">
                  <Switch size="small" />
                </Form.Item>
              </Col>
              <Col span={12}>
                <Form.Item label="Use SSL" name="smtp_use_ssl" valuePropName="checked">
                  <Switch size="small" />
                </Form.Item>
              </Col>
            </Row>
          </Col>
        </Row>
        <Row gutter={16}>
          <Col span={12}>
            <Form.Item label="SMTP Username" name="smtp_username">
              <Input placeholder="user@example.com" />
            </Form.Item>
          </Col>
          <Col span={12}>
            <Form.Item label="SMTP Password" name="smtp_password">
              <Input.Password placeholder="App password or SMTP password" />
            </Form.Item>
          </Col>
        </Row>
        <Row gutter={16}>
          <Col span={8}>
            <Form.Item label="From Email" name="smtp_from_email">
              <Input placeholder="noreply@example.com" />
            </Form.Item>
          </Col>
          <Col span={8}>
            <Form.Item label="From Name" name="smtp_from_name">
              <Input placeholder="DTSG ERP" />
            </Form.Item>
          </Col>
          <Col span={8}>
            <Form.Item label="Support Email" name="support_email">
              <Input placeholder="support@example.com" />
            </Form.Item>
          </Col>
        </Row>

        <Divider />
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <Input
            placeholder="recipient@example.com"
            value={testEmail}
            onChange={(e) => setTestEmail(e.target.value)}
            style={{ maxWidth: 300 }}
          />
          <Button
            icon={<SendOutlined />}
            onClick={handleTestEmail}
            loading={testSmtp.isPending}
          >
            Send Test Email
          </Button>
        </div>
      </Card>

      <div style={{ marginTop: 20, display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
        <Popconfirm
          title="Reset all unsaved changes?"
          description="Your form will revert to the last saved values."
          onConfirm={() => {
            if (settings) {
              // Restore saved values; keep smtp_password blank — it is always masked
              form.setFieldsValue({ ...settings, smtp_password: '' });
            } else {
              form.resetFields();
            }
            message.info('Settings reset to last saved values');
          }}
          okText="Reset"
          cancelText="Cancel"
        >
          <Button size="large" icon={<ReloadOutlined />}>
            Reset to Saved
          </Button>
        </Popconfirm>
        <Button type="primary" size="large" onClick={handleSave} loading={saveSettings.isPending}>
          Save All Settings
        </Button>
      </div>
    </Form>
  );
};

export default SettingsTab;
