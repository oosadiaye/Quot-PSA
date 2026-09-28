/**
 * Payment-gateway configuration (superadmin).
 *
 * The disbursement counterpart of AIProvidersTab. Two things it must get
 * right, both one click from a mistake:
 *
 *  - **Secrets are never displayed.** The API returns only masked tails so
 *    an operator can tell which credential is loaded; the fields here are
 *    write-only and left blank means "leave the stored secret alone".
 *  - **A keyless gateway cannot be enabled.** The toggle refuses (the API
 *    enforces it too) — an on-but-uncredentialled gateway reads as live
 *    while every call fails.
 *
 * Providers are created here (Remita / Xpresspay), their platform switch
 * flipped, and the transaction log read. Per-tenant enablement lives on the
 * tenant's own settings page; this is the platform surface.
 */
import { useState } from 'react';
import {
    Card, Table, Tag, Button, Space, Switch, Alert, Typography, Modal, Form,
    Input, App, Empty, Select, InputNumber, Checkbox,
} from 'antd';
import {
    CreditCardOutlined, ReloadOutlined, ApiOutlined, KeyOutlined,
    CheckCircleOutlined, PlusOutlined,
} from '@ant-design/icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import apiClient from '../../../api/client';
import { formatApiError } from '../../../utils/apiError';

const { Text } = Typography;

const cardStyle: React.CSSProperties = {
    borderRadius: 12,
    border: 'none',
    boxShadow: '0 2px 8px rgba(0, 0, 0, 0.06), 0 1px 2px rgba(0, 0, 0, 0.04)',
};

interface GatewayProvider {
    id: number;
    key: string;
    key_display: string;
    display_name: string;
    base_url: string;
    environment: string;
    merchant_id: string;
    supports_disbursement: boolean;
    supports_collection: boolean;
    is_enabled: boolean;
    sort_order: number;
    api_key_masked: string;
    secret_key_masked: string;
    is_configured: boolean;
    is_usable: boolean;
}

interface GatewayTxn {
    id: number;
    tenant_name: string;
    provider_name: string;
    direction: string;
    idempotency_key: string;
    gateway_reference: string;
    amount: string;
    status: string;
    http_status: number | null;
    error_message: string;
    settled_at: string | null;
    created_at: string;
}

/** DRF may paginate or not; tolerate both. */
const listOf = <T,>(data: unknown): T[] =>
    Array.isArray(data) ? (data as T[]) : (((data as { results?: T[] })?.results) ?? []);

/** Nigerian convention: dates render DD/MM/YYYY (en-GB). */
const fmtDate = (iso: string | null): string =>
    iso ? new Date(iso).toLocaleString('en-GB') : '—';

const STATUS_COLOUR: Record<string, string> = {
    success: 'green', reversed: 'orange', failed: 'red',
    sent: 'blue', pending: 'default',
};

export default function GatewayProvidersTab() {
    const { message } = App.useApp();
    const qc = useQueryClient();
    const [credModal, setCredModal] = useState<GatewayProvider | null>(null);
    const [creating, setCreating] = useState(false);
    const [credForm] = Form.useForm();
    const [createForm] = Form.useForm();

    const providers = useQuery({
        queryKey: ['gateway-providers'],
        queryFn: async () => {
            const { data } = await apiClient.get('/superadmin/gateways/providers/');
            return listOf<GatewayProvider>(data);
        },
    });

    const txns = useQuery({
        queryKey: ['gateway-transactions'],
        queryFn: async () => {
            const { data } = await apiClient.get('/superadmin/gateways/transactions/');
            return listOf<GatewayTxn>(data);
        },
    });

    const invalidate = () => {
        qc.invalidateQueries({ queryKey: ['gateway-providers'] });
        qc.invalidateQueries({ queryKey: ['gateway-transactions'] });
    };

    const toggleProvider = useMutation({
        mutationFn: async (p: GatewayProvider) =>
            (await apiClient.post(`/superadmin/gateways/providers/${p.id}/toggle/`)).data,
        onSuccess: (_d, p) => {
            message.success(`${p.display_name} ${p.is_enabled ? 'disabled' : 'enabled'}`);
            invalidate();
        },
        // The API refuses to enable a keyless gateway — surface its reason.
        onError: (err) => message.error(formatApiError(err, 'Could not change the gateway.')),
    });

    const saveCreds = useMutation({
        mutationFn: async ({ id, body }: { id: number; body: Record<string, string> }) =>
            (await apiClient.patch(`/superadmin/gateways/providers/${id}/`, body)).data,
        onSuccess: () => {
            message.success('Credentials saved.');
            setCredModal(null);
            credForm.resetFields();
            invalidate();
        },
        onError: (err) => message.error(formatApiError(err, 'Could not save the credentials.')),
    });

    const createProvider = useMutation({
        mutationFn: async (body: Record<string, unknown>) =>
            (await apiClient.post('/superadmin/gateways/providers/', body)).data,
        onSuccess: () => {
            message.success('Gateway added.');
            setCreating(false);
            createForm.resetFields();
            invalidate();
        },
        onError: (err) => message.error(formatApiError(err, 'Could not add the gateway.')),
    });

    const testConnection = useMutation({
        mutationFn: async (id: number) =>
            (await apiClient.post(`/superadmin/gateways/providers/${id}/test/`)).data,
        onSuccess: (d: { ok: boolean; detail: string }) =>
            d.ok ? message.success(d.detail || 'Reachable.') : message.error(d.detail),
        onError: (err) => message.error(formatApiError(err, 'Connection test failed.')),
    });

    const providerColumns = [
        {
            title: 'Gateway',
            dataIndex: 'display_name',
            render: (name: string, p: GatewayProvider) => (
                <Space orientation="vertical" size={0}>
                    <Space size={6}>
                        <Text strong>{name}</Text>
                        <Tag color={p.environment === 'production' ? 'red' : 'default'}>
                            {p.environment}
                        </Tag>
                    </Space>
                    <Text type="secondary" style={{ fontSize: 12 }}>{p.base_url}</Text>
                </Space>
            ),
        },
        {
            title: 'Credentials',
            render: (_: unknown, p: GatewayProvider) => (
                <Space wrap={false}>
                    {p.is_configured
                        ? <Text code style={{ whiteSpace: 'nowrap' }}>{p.api_key_masked || 'set'}</Text>
                        : <Tag color="default">not set</Tag>}
                    <Button size="small" icon={<KeyOutlined />}
                        onClick={() => { setCredModal(p); credForm.resetFields(); }}>
                        {p.is_configured ? 'Rotate' : 'Add'}
                    </Button>
                </Space>
            ),
        },
        {
            title: 'Rails',
            render: (_: unknown, p: GatewayProvider) => (
                <Space size={4} wrap>
                    {p.supports_disbursement && <Tag color="geekblue">Disbursement</Tag>}
                    {p.supports_collection && <Tag color="green">Collection</Tag>}
                    {!p.supports_disbursement && !p.supports_collection && <Tag>none</Tag>}
                </Space>
            ),
        },
        {
            title: 'Enabled',
            dataIndex: 'is_enabled',
            render: (enabled: boolean, p: GatewayProvider) => (
                <Space>
                    <Switch checked={enabled} loading={toggleProvider.isPending}
                        onChange={() => toggleProvider.mutate(p)} />
                    {p.is_usable
                        ? <Tag color="green" icon={<CheckCircleOutlined />}>Usable</Tag>
                        : <Tag color="default">Not usable</Tag>}
                </Space>
            ),
        },
        {
            title: '',
            render: (_: unknown, p: GatewayProvider) => (
                <Button size="small" icon={<ApiOutlined />}
                    loading={testConnection.isPending}
                    disabled={!p.is_configured}
                    onClick={() => testConnection.mutate(p.id)}>Test</Button>
            ),
        },
    ];

    const txnColumns = [
        { title: 'When', dataIndex: 'created_at', render: (v: string) => <Text style={{ fontSize: 12 }}>{fmtDate(v)}</Text> },
        { title: 'Tenant', dataIndex: 'tenant_name' },
        { title: 'Gateway', dataIndex: 'provider_name' },
        { title: 'Direction', dataIndex: 'direction', render: (d: string) => <Tag>{d}</Tag> },
        { title: 'Reference', dataIndex: 'idempotency_key', render: (v: string) => <Text code style={{ fontSize: 11 }}>{v}</Text> },
        { title: 'Amount', dataIndex: 'amount', render: (v: string) => `₦${Number(v).toLocaleString()}` },
        {
            title: 'Status',
            dataIndex: 'status',
            render: (s: string) => <Tag color={STATUS_COLOUR[s] ?? 'default'}>{s}</Tag>,
        },
    ];

    return (
        <Space orientation="vertical" size={16} style={{ width: '100%' }}>
            <Alert
                type="info"
                showIcon
                icon={<CreditCardOutlined />}
                title="The platform holds the keys; the tenant flips the switch"
                description={
                    'Credentials set here are stored encrypted and never shown again — only a '
                    + 'masked tail reads back. A gateway must be credentialled before it can be '
                    + 'enabled, and enabling it platform-wide only makes it available; each tenant '
                    + 'still turns it on for itself. Real payouts flow the moment both are on.'
                }
            />

            <Card
                style={cardStyle}
                title={<Space><CreditCardOutlined />Gateways</Space>}
                extra={
                    <Space>
                        <Button type="primary" icon={<PlusOutlined />}
                            onClick={() => { setCreating(true); createForm.resetFields(); }}>
                            Add gateway
                        </Button>
                        <Button icon={<ReloadOutlined />} onClick={() => providers.refetch()}>
                            Refresh
                        </Button>
                    </Space>
                }
            >
                <Table
                    rowKey="id"
                    size="small"
                    loading={providers.isLoading}
                    dataSource={providers.data ?? []}
                    columns={providerColumns as never}
                    pagination={false}
                    locale={{ emptyText: <Empty description="No gateways configured yet." /> }}
                />
            </Card>

            <Card style={cardStyle} title={<Space><ApiOutlined />Transaction log</Space>}
                extra={<Button icon={<ReloadOutlined />} onClick={() => txns.refetch()}>Refresh</Button>}>
                <Table
                    rowKey="id"
                    size="small"
                    loading={txns.isLoading}
                    dataSource={txns.data ?? []}
                    columns={txnColumns as never}
                    pagination={{ pageSize: 10, hideOnSinglePage: true }}
                    locale={{ emptyText: <Empty description="No gateway transactions yet." /> }}
                />
            </Card>

            {/* Credentials — write-only. Blank fields leave the stored secret alone. */}
            <Modal
                open={!!credModal}
                title={`Credentials — ${credModal?.display_name ?? ''}`}
                onCancel={() => { setCredModal(null); credForm.resetFields(); }}
                onOk={() => credForm.submit()}
                confirmLoading={saveCreds.isPending}
                okText="Save"
            >
                <Alert
                    type="warning"
                    showIcon
                    style={{ marginBottom: 16 }}
                    title="Secrets are stored encrypted and never shown again."
                    description="Leave a field blank to keep the stored value. Only a masked tail is displayed afterwards."
                />
                <Form form={credForm} layout="vertical"
                    onFinish={(v) => {
                        if (!credModal) return;
                        // Only send the fields the operator actually filled — an
                        // empty string CLEARS a stored secret on the API, so an
                        // untouched field must be omitted, not sent blank.
                        const body: Record<string, string> = {};
                        for (const f of ['api_key', 'secret_key', 'webhook_secret'] as const) {
                            if (v[f]) body[f] = v[f];
                        }
                        saveCreds.mutate({ id: credModal.id, body });
                    }}>
                    <Form.Item name="api_key" label="API / public key"
                        extra="Sent to identify the merchant.">
                        <Input.Password placeholder="leave blank to keep" autoComplete="off" />
                    </Form.Item>
                    <Form.Item name="secret_key" label="Signing secret"
                        extra="Used to sign outbound requests.">
                        <Input.Password placeholder="leave blank to keep" autoComplete="off" />
                    </Form.Item>
                    <Form.Item name="webhook_secret" label="Webhook secret"
                        extra="Verifies inbound settlement callbacks. Rotatable on its own.">
                        <Input.Password placeholder="leave blank to keep" autoComplete="off" />
                    </Form.Item>
                </Form>
            </Modal>

            {/* Create a new gateway. */}
            <Modal
                open={creating}
                title="Add gateway"
                onCancel={() => { setCreating(false); createForm.resetFields(); }}
                onOk={() => createForm.submit()}
                confirmLoading={createProvider.isPending}
                okText="Add"
                width={560}
                destroyOnHidden
            >
                <Form form={createForm} layout="vertical"
                    initialValues={{ environment: 'sandbox', supports_disbursement: true, supports_collection: false, sort_order: 0 }}
                    onFinish={(v) => createProvider.mutate(v)}>
                    <Form.Item name="key" label="Gateway"
                        rules={[{ required: true, message: 'Choose a gateway.' }]}>
                        <Select
                            placeholder="Which PSP"
                            options={[
                                { value: 'remita', label: 'Remita' },
                                { value: 'xpresspay', label: 'Xpresspay' },
                            ]}
                        />
                    </Form.Item>
                    <Form.Item name="display_name" label="Display name"
                        rules={[{ required: true, message: 'Name it.' }]}>
                        <Input placeholder="e.g. Remita" />
                    </Form.Item>
                    <Form.Item name="base_url" label="API base URL"
                        rules={[{ required: true, message: 'The PSP API base.' }, { type: 'url', message: 'A valid URL.' }]}>
                        <Input placeholder="https://sandbox.remita.net" />
                    </Form.Item>
                    <Form.Item name="environment" label="Environment">
                        <Select options={[
                            { value: 'sandbox', label: 'Sandbox' },
                            { value: 'production', label: 'Production' },
                        ]} />
                    </Form.Item>
                    <Form.Item name="merchant_id" label="Merchant / biller ID"
                        extra="Not a secret — shown and filterable.">
                        <Input placeholder="optional" />
                    </Form.Item>
                    <Space size={24}>
                        <Form.Item name="supports_disbursement" valuePropName="checked" noStyle>
                            <Checkbox>Disbursement (money out)</Checkbox>
                        </Form.Item>
                        <Form.Item name="supports_collection" valuePropName="checked" noStyle>
                            <Checkbox>Collection (money in)</Checkbox>
                        </Form.Item>
                    </Space>
                    <Form.Item name="sort_order" label="Sort order" style={{ marginTop: 16 }}>
                        <InputNumber min={0} step={1} style={{ width: '100%' }} />
                    </Form.Item>
                    <Alert type="info" showIcon
                        title="Add credentials after creating"
                        description="The gateway is created switched off and uncredentialled. Add its keys with Rotate, then enable it." />
                </Form>
            </Modal>
        </Space>
    );
}
