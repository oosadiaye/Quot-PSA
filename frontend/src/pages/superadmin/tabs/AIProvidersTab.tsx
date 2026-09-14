/**
 * AI provider configuration.
 *
 * Two things this screen has to get right, because both are one click
 * away from a mistake nobody notices:
 *
 *  - **The data policy is shown beside the toggle**, not buried in a
 *    document. Whoever enables a provider for a government tenant should
 *    see what leaves the tenant at the moment they decide, and OpenRouter
 *    is flagged as a broker because its policy is the union of whatever
 *    it routes to.
 *  - **A key is never displayed.** The API returns a masked tail so an
 *    operator can tell which key is loaded; the field here is write-only
 *    and left blank means "leave the stored key alone".
 */
import { useState } from 'react';
import {
    Card, Table, Tag, Button, Space, Switch, Alert, Typography, Modal, Form,
    Input, Tooltip, App, Empty, Statistic, Row, Col, Dropdown,
} from 'antd';
import {
    RobotOutlined, ReloadOutlined, ApiOutlined, KeyOutlined, WarningOutlined,
    CheckCircleOutlined, StopOutlined, CloudServerOutlined,
} from '@ant-design/icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import apiClient from '../../../api/client';
import { formatApiError } from '../../../utils/apiError';

const { Text, Paragraph } = Typography;

const cardStyle: React.CSSProperties = {
    borderRadius: 12,
    border: 'none',
    boxShadow: '0 2px 8px rgba(0, 0, 0, 0.06), 0 1px 2px rgba(0, 0, 0, 0.04)',
};

interface AIProvider {
    id: number;
    key: string;
    key_display: string;
    display_name: string;
    base_url: string;
    available_models: { id: string; label?: string; pricing?: Record<string, string> }[];
    is_enabled: boolean;
    api_key_masked: string;
    is_configured: boolean;
    is_usable: boolean;
    sends_document_images: boolean;
    sends_ledger_amounts: boolean;
    retains_data: boolean;
    is_broker: boolean;
    data_policy_url: string;
}

interface Capability {
    value: string;
    label: string;
}

interface TenantAISetting {
    id: number;
    tenant: number;
    tenant_name: string;
    capability: string;
    capability_display: string;
    provider: number;
    provider_name: string;
    model_id: string;
    is_active: boolean;
    monthly_cost_cap: string;
    require_redaction: boolean;
    is_usable: boolean;
}

/** DRF may paginate or not depending on the viewset; tolerate both. */
const listOf = <T,>(data: unknown): T[] =>
    Array.isArray(data) ? (data as T[]) : (((data as { results?: T[] })?.results) ?? []);

export default function AIProvidersTab() {
    const { message, modal } = App.useApp();
    const qc = useQueryClient();
    const [keyModal, setKeyModal] = useState<AIProvider | null>(null);
    const [form] = Form.useForm();

    const providers = useQuery({
        queryKey: ['ai-providers'],
        queryFn: async () => {
            const { data } = await apiClient.get('/superadmin/ai/providers/');
            return listOf<AIProvider>(data);
        },
    });

    const capabilities = useQuery({
        queryKey: ['ai-capabilities'],
        queryFn: async () => {
            const { data } = await apiClient.get('/superadmin/ai/settings/capabilities/');
            return listOf<Capability>(data);
        },
    });

    const settings = useQuery({
        queryKey: ['ai-settings'],
        queryFn: async () => {
            const { data } = await apiClient.get('/superadmin/ai/settings/');
            return listOf<TenantAISetting>(data);
        },
    });

    const usage = useQuery({
        queryKey: ['ai-usage'],
        queryFn: async () => {
            const { data } = await apiClient.get('/superadmin/ai/calls/usage/');
            return data as { rows: { tenant__name: string; calls: number; cost: string }[] };
        },
    });

    const invalidate = () => {
        qc.invalidateQueries({ queryKey: ['ai-providers'] });
        qc.invalidateQueries({ queryKey: ['ai-settings'] });
    };

    const toggleProvider = useMutation({
        mutationFn: async (p: AIProvider) =>
            (await apiClient.post(`/superadmin/ai/providers/${p.id}/toggle/`)).data,
        onSuccess: (_d, p) => {
            message.success(`${p.display_name} ${p.is_enabled ? 'disabled' : 'enabled'}`);
            invalidate();
        },
        onError: (err) => {
            // The API refuses to enable a provider with no key. Surface
            // its reason rather than a generic failure — the operator can
            // act on "add a key", not on "request failed".
            message.error(formatApiError(err, 'Could not change the provider.'));
        },
    });

    const saveKey = useMutation({
        mutationFn: async ({ id, api_key }: { id: number; api_key: string }) =>
            (await apiClient.patch(`/superadmin/ai/providers/${id}/`, { api_key })).data,
        onSuccess: () => {
            message.success('API key saved.');
            setKeyModal(null);
            form.resetFields();
            invalidate();
        },
        onError: (err) => message.error(formatApiError(err, 'Could not save the key.')),
    });

    const testConnection = useMutation({
        mutationFn: async (id: number) =>
            (await apiClient.post(`/superadmin/ai/providers/${id}/test/`)).data,
        onSuccess: (d: { ok: boolean; model_count: number; detail: string }) =>
            d.ok
                ? message.success(`${d.detail} ${d.model_count} models available.`)
                : message.error(d.detail),
        onError: (err) => message.error(formatApiError(err, 'Connection test failed.')),
    });

    const syncModels = useMutation({
        mutationFn: async (id: number) =>
            (await apiClient.post(`/superadmin/ai/providers/${id}/sync-models/`)).data,
        onSuccess: (d: { model_count: number }) => {
            message.success(`Synced ${d.model_count} models with pricing.`);
            invalidate();
        },
        onError: (err) => message.error(formatApiError(err, 'Could not sync models.')),
    });

    const toggleSetting = useMutation({
        mutationFn: async (s: TenantAISetting) =>
            (await apiClient.post(`/superadmin/ai/settings/${s.id}/toggle/`)).data,
        onSuccess: () => invalidate(),
    });

    const killSwitch = useMutation({
        mutationFn: async (tenant: number) =>
            (await apiClient.post('/superadmin/ai/settings/disable-all/', { tenant })).data,
        onSuccess: (d: { disabled: number }) => {
            message.success(`Disabled ${d.disabled} capabilities.`);
            invalidate();
        },
    });

    const providerColumns = [
        {
            title: 'Provider',
            dataIndex: 'display_name',
            render: (name: string, p: AIProvider) => (
                <Space orientation="vertical" size={0}>
                    <Space size={6}>
                        <Text strong>{name}</Text>
                        {p.is_broker && (
                            <Tooltip title="Routes to upstream providers, so its data policy is the union of theirs.">
                                <Tag color="orange">Broker</Tag>
                            </Tooltip>
                        )}
                    </Space>
                    <Text type="secondary" style={{ fontSize: 12 }}>{p.base_url}</Text>
                </Space>
            ),
        },
        {
            title: 'API key',
            dataIndex: 'api_key_masked',
            render: (masked: string, p: AIProvider) => (
                <Space>
                    {p.is_configured
                        ? <Text code>{masked}</Text>
                        : <Tag color="default">not set</Tag>}
                    <Button size="small" icon={<KeyOutlined />}
                        onClick={() => { setKeyModal(p); form.resetFields(); }}>
                        {p.is_configured ? 'Replace' : 'Add'}
                    </Button>
                </Space>
            ),
        },
        {
            title: 'What leaves the tenant',
            render: (_: unknown, p: AIProvider) => (
                <Space size={4} wrap>
                    {p.sends_document_images && <Tag>Documents</Tag>}
                    {p.sends_ledger_amounts && <Tag>Amounts</Tag>}
                    {p.retains_data
                        ? <Tag color="red" icon={<WarningOutlined />}>Retains data</Tag>
                        : <Tag color="green">No retention</Tag>}
                </Space>
            ),
        },
        {
            title: 'Models',
            dataIndex: 'available_models',
            render: (models: AIProvider['available_models'], p: AIProvider) => (
                <Space>
                    <Text>{models?.length ?? 0}</Text>
                    <Button size="small" icon={<ReloadOutlined />}
                        loading={syncModels.isPending}
                        onClick={() => syncModels.mutate(p.id)}>Sync</Button>
                </Space>
            ),
        },
        {
            title: 'Enabled',
            dataIndex: 'is_enabled',
            render: (enabled: boolean, p: AIProvider) => (
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
            render: (_: unknown, p: AIProvider) => (
                <Button size="small" icon={<ApiOutlined />}
                    loading={testConnection.isPending}
                    disabled={!p.is_configured}
                    onClick={() => testConnection.mutate(p.id)}>Test</Button>
            ),
        },
    ];

    const settingColumns = [
        { title: 'Tenant', dataIndex: 'tenant_name' },
        { title: 'Capability', dataIndex: 'capability_display' },
        { title: 'Provider', dataIndex: 'provider_name' },
        {
            title: 'Model',
            dataIndex: 'model_id',
            render: (m: string) => <Text code style={{ fontSize: 12 }}>{m}</Text>,
        },
        {
            title: 'Redaction',
            dataIndex: 'require_redaction',
            render: (on: boolean) => on
                ? <Tag color="green">On</Tag>
                : <Tag color="red" icon={<WarningOutlined />}>Off</Tag>,
        },
        {
            title: 'Monthly cap',
            dataIndex: 'monthly_cost_cap',
            render: (cap: string) => Number(cap) > 0
                ? <Text>${Number(cap).toFixed(2)}</Text>
                : <Text type="secondary">none</Text>,
        },
        {
            title: 'Active',
            dataIndex: 'is_active',
            render: (active: boolean, s: TenantAISetting) => (
                <Space>
                    <Switch checked={active} onChange={() => toggleSetting.mutate(s)} />
                    {active && !s.is_usable && (
                        <Tooltip title="On here, but the provider is disabled platform-wide or has no key.">
                            <Tag color="orange">Blocked</Tag>
                        </Tooltip>
                    )}
                </Space>
            ),
        },
    ];

    const settingRows = settings.data ?? [];

    // Distinct tenants that have any capability configured. Kept as a list
    // rather than "the one tenant" — see the kill switch below.
    const tenants = [...new Map(
        settingRows.map((s) => [s.tenant, s.tenant_name]),
    ).entries()].map(([id, name]) => ({ id, name }));

    const usageRows = usage.data?.rows ?? [];
    const totalCalls = usageRows.reduce((n, r) => n + r.calls, 0);
    const totalSpend = usageRows.reduce((n, r) => n + Number(r.cost ?? 0), 0);
    // Live data lands around 1e-06 USD for a short call on a cheap model.
    // Two decimal places render that as $0.00, which reads as "free" —
    // the same mistake the cost column already had to be widened to eight
    // places to avoid. Show the small numbers rather than round them away.
    const spendPrecision = totalSpend > 0 && totalSpend < 0.01 ? 6 : 2;

    return (
        <Space orientation="vertical" size={16} style={{ width: '100%' }}>
            <Alert
                type="info"
                showIcon
                icon={<CloudServerOutlined />}
                title="AI proposes, the ledger disposes"
                description={
                    <Paragraph style={{ margin: 0 }}>
                        Nothing generated here posts to the general ledger, approves a
                        payment or changes an appropriation. Every AI output arrives as a
                        draft for a named person to accept. Enabling a provider sends
                        tenant content to a third party &mdash; the badges below say what.
                    </Paragraph>
                }
            />

            {usageRows.length ? (
                <Row gutter={[16, 16]}>
                    <Col xs={24} sm={8}>
                        <Card style={cardStyle} size="small">
                            <Statistic title="Calls this month" value={totalCalls} />
                        </Card>
                    </Col>
                    <Col xs={24} sm={8}>
                        <Card style={cardStyle} size="small">
                            <Statistic title="Spend this month" prefix="$"
                                precision={spendPrecision} value={totalSpend} />
                        </Card>
                    </Col>
                    <Col xs={24} sm={8}>
                        <Card style={cardStyle} size="small">
                            <Statistic title="Providers usable"
                                value={(providers.data ?? []).filter((p) => p.is_usable).length}
                                suffix={`/ ${(providers.data ?? []).length}`} />
                        </Card>
                    </Col>
                </Row>
            ) : null}

            <Card
                style={cardStyle}
                title={<Space><RobotOutlined />Providers</Space>}
                extra={
                    <Button icon={<ReloadOutlined />} onClick={() => providers.refetch()}>
                        Refresh
                    </Button>
                }
            >
                <Table
                    rowKey="id"
                    size="small"
                    loading={providers.isLoading}
                    dataSource={providers.data ?? []}
                    columns={providerColumns as never}
                    pagination={false}
                    locale={{ emptyText: <Empty description="No providers configured yet." /> }}
                />
            </Card>

            <Card
                style={cardStyle}
                title={<Space><ApiOutlined />Tenant capabilities</Space>}
                extra={
                    // A dropdown even for a single tenant. Keying this on
                    // "exactly one tenant" would have hidden the control the
                    // moment a second tenant was configured — i.e. it would
                    // vanish as the platform grew, which is the opposite of
                    // what an incident control should do.
                    tenants.length > 0 && (
                        <Dropdown
                            trigger={['click']}
                            menu={{
                                items: tenants.map((t) => ({
                                    key: String(t.id),
                                    danger: true,
                                    label: `Disable all for ${t.name}`,
                                })),
                                onClick: ({ key }) => {
                                    const t = tenants.find((x) => String(x.id) === key);
                                    if (!t) return;
                                    modal.confirm({
                                        title: `Disable all AI for ${t.name}?`,
                                        content: 'Every capability is switched off '
                                            + 'immediately. Nothing is deleted and it '
                                            + 'can be re-enabled.',
                                        okText: 'Disable all',
                                        okButtonProps: { danger: true },
                                        onOk: () => killSwitch.mutate(t.id),
                                    });
                                },
                            }}
                        >
                            <Button danger icon={<StopOutlined />}
                                loading={killSwitch.isPending}>
                                Kill switch
                            </Button>
                        </Dropdown>
                    )
                }
            >
                <Table
                    rowKey="id"
                    size="small"
                    loading={settings.isLoading}
                    dataSource={settingRows}
                    columns={settingColumns as never}
                    pagination={false}
                    locale={{
                        emptyText: (
                            <Empty description={
                                `No capabilities configured. ${capabilities.data?.length ?? 0} are available.`
                            } />
                        ),
                    }}
                />
            </Card>

            <Modal
                open={!!keyModal}
                title={`API key — ${keyModal?.display_name ?? ''}`}
                onCancel={() => { setKeyModal(null); form.resetFields(); }}
                onOk={() => form.submit()}
                confirmLoading={saveKey.isPending}
                okText="Save key"
            >
                <Alert
                    type="warning"
                    showIcon
                    style={{ marginBottom: 16 }}
                    title="The key is stored encrypted and is never shown again."
                    description="Only the last four characters are displayed afterwards, so you can tell which key is loaded."
                />
                <Form form={form} layout="vertical"
                    onFinish={(v) => keyModal && saveKey.mutate({ id: keyModal.id, api_key: v.api_key })}>
                    <Form.Item
                        name="api_key"
                        label="API key"
                        rules={[{ required: true, message: 'Paste the provider key.' }]}
                    >
                        <Input.Password placeholder="sk-..." autoComplete="off" />
                    </Form.Item>
                </Form>
            </Modal>
        </Space>
    );
}
