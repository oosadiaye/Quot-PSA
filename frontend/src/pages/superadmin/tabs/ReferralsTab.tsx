import { useState, useMemo } from 'react';
import {
  Card, Table, Tag, Button, Space, Modal, Form, Input, InputNumber, Select,
  App, Skeleton, Typography, Row, Col, Tabs, Badge, Statistic, Popconfirm,
  Divider, DatePicker, Tooltip,
} from 'antd';
import {
  Users, UserPlus, Pencil, Trash2, Link2, RefreshCw, Search, CheckCircle,
  XCircle, DollarSign, CreditCard, ArrowRightLeft, Ban, Eye,
} from 'lucide-react';
import { useCurrency } from '../../../context/CurrencyContext';
import {
  useReferrers, useCreateReferrer, useUpdateReferrer, useDeleteReferrer,
  useReferrals, useCreateReferral,
  useCommissions, useUpdateCommission,
  usePayouts, useCreatePayout, useUpdatePayout,
} from '../hooks/useSuperAdmin';
import { useTenants } from '../hooks/useSuperAdmin';
import type { Referrer, Referral, Commission, CommissionPayout } from '../../../api/superadmin';

const { Text, Title } = Typography;

// ── Theme constants ──────────────────────────────────────────────────────────
const COLORS = {
  primary: '#2471a3',
  navy: '#0f3460',
  lightBlue: '#5dade2',
  green: '#52c41a',
  orange: '#faad14',
  purple: '#722ed1',
  red: '#cf1322',
};

const cardStyle: React.CSSProperties = {
  borderRadius: 12,
  border: 'none',
  boxShadow: '0 2px 8px rgba(0, 0, 0, 0.06), 0 1px 2px rgba(0, 0, 0, 0.04)',
};

const statCardStyle = (borderColor: string): React.CSSProperties => ({
  borderRadius: 10,
  borderLeft: `4px solid ${borderColor}`,
});

// ── Helper: mask bank account ────────────────────────────────────────────────
const maskAccount = (acc: string) => {
  if (!acc) return '-';
  if (acc.length <= 4) return acc;
  return '****' + acc.slice(-4);
};

// ── Helper: format date ──────────────────────────────────────────────────────
const fmtDate = (v: string | null | undefined) => {
  if (!v) return '-';
  return new Date(v).toLocaleDateString();
};

const fmtDayjs = (d: any): string => {
  if (!d) return '';
  if (typeof d === 'string') return d;
  if (d.$d) return d.$d.toISOString().split('T')[0];
  return d.toISOString().split('T')[0];
};

// ── Status color maps ────────────────────────────────────────────────────────
const referralStatusColor: Record<string, string> = {
  Pending: 'orange',
  Trial: 'processing',
  Active: 'green',
  Cancelled: 'red',
  Expired: 'default',
};

const commissionStatusColor: Record<string, string> = {
  Pending: 'orange',
  Approved: 'blue',
  Paid: 'green',
  Cancelled: 'red',
};

const payoutStatusColor: Record<string, string> = {
  Draft: 'default',
  Processing: 'processing',
  Completed: 'success',
  Failed: 'error',
};

// ═══════════════════════════════════════════════════════════════════════════════
// MAIN COMPONENT
// ═══════════════════════════════════════════════════════════════════════════════

export default function ReferralsTab() {
  const { message } = App.useApp();
  const { formatCurrency } = useCurrency();
  const [activeTab, setActiveTab] = useState('referrers');

  // ── Referrer state ─────────────────────────────────────────────────────────
  const [referrerSearch, setReferrerSearch] = useState('');
  const [referrerStatusFilter, setReferrerStatusFilter] = useState<string | undefined>();
  const [referrerModalOpen, setReferrerModalOpen] = useState(false);
  const [editingReferrer, setEditingReferrer] = useState<Referrer | null>(null);
  const [referrerForm] = Form.useForm();

  // ── Referral state ─────────────────────────────────────────────────────────
  const [referralStatusFilter, setReferralStatusFilter] = useState<string | undefined>();
  const [referralReferrerFilter, setReferralReferrerFilter] = useState<number | undefined>();
  const [referralModalOpen, setReferralModalOpen] = useState(false);
  const [referralForm] = Form.useForm();

  // ── Commission state ───────────────────────────────────────────────────────
  const [commStatusFilter, setCommStatusFilter] = useState<string | undefined>();
  const [commReferrerFilter, setCommReferrerFilter] = useState<number | undefined>();

  // ── Payout state ───────────────────────────────────────────────────────────
  const [payoutStatusFilter, setPayoutStatusFilter] = useState<string | undefined>();
  const [payoutModalOpen, setPayoutModalOpen] = useState(false);
  const [payoutForm] = Form.useForm();
  const [completePayoutModal, setCompletePayoutModal] = useState<CommissionPayout | null>(null);
  const [completePayoutForm] = Form.useForm();

  // ── Data queries ───────────────────────────────────────────────────────────
  const referrerQueryParams = useMemo(() => ({
    ...(referrerSearch ? { search: referrerSearch } : {}),
    ...(referrerStatusFilter ? { is_active: referrerStatusFilter } : {}),
  }), [referrerSearch, referrerStatusFilter]);

  const { data: referrers = [], isLoading: loadingReferrers } = useReferrers(
    Object.keys(referrerQueryParams).length > 0 ? referrerQueryParams : undefined,
  );
  const { data: referrals = [], isLoading: loadingReferrals } = useReferrals(
    referralStatusFilter || referralReferrerFilter
      ? { status: referralStatusFilter, referrer_id: referralReferrerFilter }
      : undefined,
  );
  const { data: commissions = [], isLoading: loadingCommissions } = useCommissions(
    commStatusFilter || commReferrerFilter
      ? { status: commStatusFilter, referrer_id: commReferrerFilter }
      : undefined,
  );
  const { data: payouts = [], isLoading: loadingPayouts } = usePayouts(
    payoutStatusFilter ? { status: payoutStatusFilter } : undefined,
  );
  const { data: tenants = [] } = useTenants();

  // ── Mutations ──────────────────────────────────────────────────────────────
  const createReferrerMut = useCreateReferrer();
  const updateReferrerMut = useUpdateReferrer();
  const deleteReferrerMut = useDeleteReferrer();
  const createReferralMut = useCreateReferral();
  const updateCommissionMut = useUpdateCommission();
  const createPayoutMut = useCreatePayout();
  const updatePayoutMut = useUpdatePayout();

  // ── Stats ──────────────────────────────────────────────────────────────────
  const totalReferrers = referrers.length;
  const activeReferrers = referrers.filter((r) => r.is_active).length;
  const totalReferralsCount = referrals.length;
  const totalCommissionsEarned = commissions.reduce(
    (sum, c) => sum + parseFloat(c.commission_amount || '0'), 0,
  );

  // ═════════════════════════════════════════════════════════════════════════════
  // REFERRER HANDLERS
  // ═════════════════════════════════════════════════════════════════════════════

  const openAddReferrer = () => {
    setEditingReferrer(null);
    referrerForm.resetFields();
    setReferrerModalOpen(true);
  };

  const openEditReferrer = (r: Referrer) => {
    setEditingReferrer(r);
    referrerForm.setFieldsValue(r);
    setReferrerModalOpen(true);
  };

  const handleSaveReferrer = async (values: any) => {
    try {
      if (editingReferrer) {
        await updateReferrerMut.mutateAsync({ id: editingReferrer.id, data: values });
        message.success('Referrer updated');
      } else {
        await createReferrerMut.mutateAsync(values);
        message.success('Referrer created');
      }
      setReferrerModalOpen(false);
      referrerForm.resetFields();
      setEditingReferrer(null);
    } catch (err: any) {
      message.error(err?.response?.data?.error || `Failed to ${editingReferrer ? 'update' : 'create'} referrer`);
    }
  };

  const handleToggleReferrer = async (r: Referrer) => {
    try {
      await updateReferrerMut.mutateAsync({ id: r.id, data: { is_active: !r.is_active } });
      message.success(`Referrer ${r.is_active ? 'deactivated' : 'activated'}`);
    } catch {
      message.error('Failed to update referrer status');
    }
  };

  const handleDeleteReferrer = async (id: number) => {
    try {
      await deleteReferrerMut.mutateAsync(id);
      message.success('Referrer deleted');
    } catch {
      message.error('Failed to delete referrer');
    }
  };

  const generateCode = () => {
    const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
    let code = 'REF-';
    for (let i = 0; i < 6; i++) code += chars.charAt(Math.floor(Math.random() * chars.length));
    referrerForm.setFieldValue('referrer_code', code);
  };

  // ═════════════════════════════════════════════════════════════════════════════
  // REFERRAL HANDLERS
  // ═════════════════════════════════════════════════════════════════════════════

  const handleCreateReferral = async (values: any) => {
    try {
      await createReferralMut.mutateAsync(values);
      message.success('Referral linked');
      setReferralModalOpen(false);
      referralForm.resetFields();
    } catch (err: any) {
      message.error(err?.response?.data?.error || 'Failed to create referral');
    }
  };

  // ═════════════════════════════════════════════════════════════════════════════
  // COMMISSION HANDLERS
  // ═════════════════════════════════════════════════════════════════════════════

  const handleCommissionAction = async (id: number, action: 'approve' | 'reject') => {
    try {
      await updateCommissionMut.mutateAsync({ id, data: { action } });
      message.success(`Commission ${action === 'approve' ? 'approved' : 'rejected'}`);
    } catch {
      message.error(`Failed to ${action} commission`);
    }
  };

  // ═════════════════════════════════════════════════════════════════════════════
  // PAYOUT HANDLERS
  // ═════════════════════════════════════════════════════════════════════════════

  const handleCreatePayout = async (values: any) => {
    try {
      await createPayoutMut.mutateAsync({
        referrer_id: values.referrer_id,
        period_start: fmtDayjs(values.period_start),
        period_end: fmtDayjs(values.period_end),
        notes: values.notes || '',
      });
      message.success('Payout created');
      setPayoutModalOpen(false);
      payoutForm.resetFields();
    } catch (err: any) {
      message.error(err?.response?.data?.error || 'Failed to create payout');
    }
  };

  const handlePayoutAction = async (id: number, action: string, extra?: Record<string, string>) => {
    try {
      await updatePayoutMut.mutateAsync({ id, data: { action, ...extra } });
      message.success(`Payout ${action === 'process' ? 'processing' : action === 'complete' ? 'completed' : 'updated'}`);
    } catch {
      message.error(`Failed to ${action} payout`);
    }
  };

  const handleCompletePayout = async (values: any) => {
    if (!completePayoutModal) return;
    await handlePayoutAction(completePayoutModal.id, 'complete', {
      payout_reference: values.payout_reference || '',
      payment_method: values.payment_method || '',
      notes: values.notes || '',
    });
    setCompletePayoutModal(null);
    completePayoutForm.resetFields();
  };

  // ═════════════════════════════════════════════════════════════════════════════
  // COLUMN DEFINITIONS
  // ═════════════════════════════════════════════════════════════════════════════

  // ── Referrers columns ──────────────────────────────────────────────────────
  const referrerColumns = [
    {
      title: 'Name',
      key: 'name',
      render: (_: any, r: Referrer) => (
        <div>
          <Text strong>{r.contact_name}</Text>
          {r.company_name && <div><Text type="secondary" style={{ fontSize: 12 }}>{r.company_name}</Text></div>}
        </div>
      ),
      sorter: (a: Referrer, b: Referrer) => a.contact_name.localeCompare(b.contact_name),
    },
    {
      title: 'Email',
      dataIndex: 'email',
      key: 'email',
      ellipsis: true,
    },
    {
      title: 'Phone',
      dataIndex: 'phone',
      key: 'phone',
      render: (v: string) => v || '-',
    },
    {
      title: 'Referral Code',
      dataIndex: 'referrer_code',
      key: 'code',
      render: (v: string) => (
        <Tag color="blue" style={{ fontFamily: 'monospace', fontWeight: 600 }}>{v}</Tag>
      ),
    },
    {
      title: 'Bank Account',
      key: 'bank',
      render: (_: any, r: Referrer) => (
        <Tooltip title={r.bank_name || 'No bank info'}>
          <Text type="secondary">{r.bank_name ? `${r.bank_name} ${maskAccount(r.bank_account)}` : '-'}</Text>
        </Tooltip>
      ),
    },
    {
      title: 'Referrals',
      dataIndex: 'total_referrals',
      key: 'referrals',
      align: 'center' as const,
      render: (v: number | undefined) => v ?? 0,
      sorter: (a: Referrer, b: Referrer) => (a.total_referrals ?? 0) - (b.total_referrals ?? 0),
    },
    {
      title: 'Total Earned',
      dataIndex: 'total_commission',
      key: 'total_earned',
      render: (v: string | undefined) => (
        <Text strong style={{ color: COLORS.green }}>
          {formatCurrency(parseFloat(v || '0'))}
        </Text>
      ),
      sorter: (a: Referrer, b: Referrer) => parseFloat(a.total_commission || '0') - parseFloat(b.total_commission || '0'),
    },
    {
      title: 'Status',
      dataIndex: 'is_active',
      key: 'status',
      render: (v: boolean) => (
        <Badge status={v ? 'success' : 'default'} text={v ? 'Active' : 'Inactive'} />
      ),
      filters: [
        { text: 'Active', value: true },
        { text: 'Inactive', value: false },
      ],
      onFilter: (val: any, record: Referrer) => record.is_active === val,
    },
    {
      title: 'Actions',
      key: 'actions',
      width: 200,
      render: (_: any, r: Referrer) => (
        <Space size="small">
          <Tooltip title="Edit">
            <Button size="small" type="text" icon={<Pencil size={14} />} onClick={() => openEditReferrer(r)} />
          </Tooltip>
          <Tooltip title={r.is_active ? 'Deactivate' : 'Activate'}>
            <Popconfirm
              title={`${r.is_active ? 'Deactivate' : 'Activate'} this referrer?`}
              onConfirm={() => handleToggleReferrer(r)}
            >
              <Button
                size="small"
                type="text"
                icon={r.is_active ? <Ban size={14} /> : <CheckCircle size={14} />}
                style={{ color: r.is_active ? COLORS.orange : COLORS.green }}
              />
            </Popconfirm>
          </Tooltip>
          <Tooltip title="Delete">
            <Popconfirm title="Delete this referrer? This cannot be undone." onConfirm={() => handleDeleteReferrer(r.id)}>
              <Button size="small" type="text" danger icon={<Trash2 size={14} />} />
            </Popconfirm>
          </Tooltip>
        </Space>
      ),
    },
  ];

  // ── Referrals columns ──────────────────────────────────────────────────────
  const referralColumns = [
    {
      title: 'Referrer',
      dataIndex: 'referrer_name',
      key: 'referrer',
      render: (v: string, r: Referral) => (
        <div>
          <Text strong>{v}</Text>
          <div><Tag style={{ fontFamily: 'monospace', fontSize: 11 }}>{r.referrer_code}</Tag></div>
        </div>
      ),
      sorter: (a: Referral, b: Referral) => a.referrer_name.localeCompare(b.referrer_name),
    },
    {
      title: 'Tenant',
      dataIndex: 'tenant_name',
      key: 'tenant',
      render: (v: string) => <Tag color="blue">{v}</Tag>,
    },
    {
      title: 'Referral Date',
      dataIndex: 'referred_at',
      key: 'date',
      render: (v: string) => fmtDate(v),
      sorter: (a: Referral, b: Referral) => new Date(a.referred_at).getTime() - new Date(b.referred_at).getTime(),
    },
    {
      title: 'Converted',
      dataIndex: 'converted_at',
      key: 'converted',
      render: (v: string | null) => fmtDate(v),
    },
    {
      title: 'Source',
      dataIndex: 'source',
      key: 'source',
      render: (v: string) => v || '-',
    },
    {
      title: 'Status',
      dataIndex: 'status',
      key: 'status',
      render: (v: string) => <Tag color={referralStatusColor[v] || 'default'}>{v}</Tag>,
      filters: [
        { text: 'Pending', value: 'Pending' },
        { text: 'Trial', value: 'Trial' },
        { text: 'Active', value: 'Active' },
        { text: 'Cancelled', value: 'Cancelled' },
        { text: 'Expired', value: 'Expired' },
      ],
      onFilter: (val: any, record: Referral) => record.status === val,
    },
  ];

  // ── Commissions columns ────────────────────────────────────────────────────
  const commissionColumns = [
    {
      title: 'Referrer',
      dataIndex: 'referrer_name',
      key: 'referrer',
      render: (v: string) => <Text strong>{v}</Text>,
    },
    {
      title: 'Tenant',
      dataIndex: 'tenant_name',
      key: 'tenant',
      render: (v: string) => <Tag color="blue">{v}</Tag>,
    },
    {
      title: 'Sale Amount',
      dataIndex: 'sale_amount',
      key: 'sale',
      render: (v: string) => formatCurrency(parseFloat(v || '0')),
      sorter: (a: Commission, b: Commission) => parseFloat(a.sale_amount) - parseFloat(b.sale_amount),
    },
    {
      title: 'Commission',
      dataIndex: 'commission_amount',
      key: 'commission',
      render: (v: string) => (
        <Text strong style={{ color: COLORS.green }}>{formatCurrency(parseFloat(v || '0'))}</Text>
      ),
      sorter: (a: Commission, b: Commission) => parseFloat(a.commission_amount) - parseFloat(b.commission_amount),
    },
    {
      title: 'Rate',
      key: 'rate',
      render: (_: any, r: Commission) => (
        <Text type="secondary">{r.commission_rate}% ({r.commission_type})</Text>
      ),
    },
    {
      title: 'Period',
      dataIndex: 'sale_date',
      key: 'period',
      render: (v: string) => fmtDate(v),
      sorter: (a: Commission, b: Commission) => new Date(a.sale_date).getTime() - new Date(b.sale_date).getTime(),
    },
    {
      title: 'Status',
      dataIndex: 'status',
      key: 'status',
      render: (v: string) => <Tag color={commissionStatusColor[v] || 'default'}>{v}</Tag>,
    },
    {
      title: 'Actions',
      key: 'actions',
      width: 180,
      render: (_: any, r: Commission) => {
        if (r.status !== 'Pending') return <Text type="secondary">-</Text>;
        return (
          <Space size="small">
            <Tooltip title="Approve">
              <Button
                size="small"
                type="primary"
                ghost
                icon={<CheckCircle size={14} />}
                onClick={() => handleCommissionAction(r.id, 'approve')}
                loading={updateCommissionMut.isPending}
              >
                Approve
              </Button>
            </Tooltip>
            <Tooltip title="Reject">
              <Popconfirm title="Reject this commission?" onConfirm={() => handleCommissionAction(r.id, 'reject')}>
                <Button
                  size="small"
                  danger
                  ghost
                  icon={<XCircle size={14} />}
                >
                  Reject
                </Button>
              </Popconfirm>
            </Tooltip>
          </Space>
        );
      },
    },
  ];

  // ── Payouts columns ────────────────────────────────────────────────────────
  const payoutColumns = [
    {
      title: 'Referrer',
      dataIndex: 'referrer_name',
      key: 'referrer',
      render: (v: string) => <Text strong>{v}</Text>,
    },
    {
      title: 'Amount',
      dataIndex: 'total_commissions',
      key: 'amount',
      render: (v: string) => (
        <Text strong style={{ color: COLORS.primary }}>{formatCurrency(parseFloat(v || '0'))}</Text>
      ),
      sorter: (a: CommissionPayout, b: CommissionPayout) =>
        parseFloat(a.total_commissions) - parseFloat(b.total_commissions),
    },
    {
      title: 'Commissions',
      dataIndex: 'commissions_count',
      key: 'count',
      align: 'center' as const,
    },
    {
      title: 'Period',
      key: 'period',
      render: (_: any, r: CommissionPayout) => `${fmtDate(r.period_start)} - ${fmtDate(r.period_end)}`,
    },
    {
      title: 'Status',
      dataIndex: 'status',
      key: 'status',
      render: (v: string) => <Tag color={payoutStatusColor[v] || 'default'}>{v}</Tag>,
    },
    {
      title: 'Payment Method',
      dataIndex: 'payment_method',
      key: 'method',
      render: (v: string) => v || '-',
    },
    {
      title: 'Reference',
      dataIndex: 'payout_reference',
      key: 'ref',
      render: (v: string) => v ? <Text copyable style={{ fontFamily: 'monospace', fontSize: 12 }}>{v}</Text> : '-',
    },
    {
      title: 'Payout Date',
      dataIndex: 'payout_date',
      key: 'date',
      render: (v: string | null) => fmtDate(v),
    },
    {
      title: 'Actions',
      key: 'actions',
      width: 200,
      render: (_: any, r: CommissionPayout) => {
        if (r.status === 'Completed' || r.status === 'Failed') return <Text type="secondary">-</Text>;
        return (
          <Space size="small">
            {r.status === 'Draft' && (
              <Button
                size="small"
                type="primary"
                ghost
                icon={<ArrowRightLeft size={14} />}
                onClick={() => handlePayoutAction(r.id, 'process')}
                loading={updatePayoutMut.isPending}
              >
                Process
              </Button>
            )}
            {r.status === 'Processing' && (
              <Button
                size="small"
                type="primary"
                icon={<CheckCircle size={14} />}
                onClick={() => {
                  setCompletePayoutModal(r);
                  completePayoutForm.resetFields();
                }}
              >
                Complete
              </Button>
            )}
            {(r.status === 'Draft' || r.status === 'Processing') && (
              <Popconfirm title="Mark this payout as failed?" onConfirm={() => handlePayoutAction(r.id, 'fail')}>
                <Button size="small" danger ghost icon={<XCircle size={14} />}>Fail</Button>
              </Popconfirm>
            )}
          </Space>
        );
      },
    },
  ];

  // ═════════════════════════════════════════════════════════════════════════════
  // RENDER
  // ═════════════════════════════════════════════════════════════════════════════

  if (loadingReferrers && loadingReferrals && loadingCommissions && loadingPayouts) {
    return <Skeleton active paragraph={{ rows: 12 }} />;
  }

  return (
    <Card style={cardStyle}>
      {/* ── Header ──────────────────────────────────────────────────────────── */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Title level={5} style={{ margin: 0, color: COLORS.navy }}>
          <Users size={18} style={{ marginRight: 8, verticalAlign: 'text-bottom' }} />
          Referral & Commission Management
        </Title>
      </div>

      {/* ── Stats Cards ─────────────────────────────────────────────────────── */}
      <Row gutter={[16, 16]} style={{ marginBottom: 20 }}>
        <Col xs={12} sm={6}>
          <Card size="small" style={statCardStyle(COLORS.primary)}>
            <Statistic
              title="Total Referrers"
              value={totalReferrers}
              prefix={<Users size={16} />}
              styles={{ content: { color: COLORS.primary } }}
            />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card size="small" style={statCardStyle(COLORS.green)}>
            <Statistic
              title="Active Referrers"
              value={activeReferrers}
              styles={{ content: { color: COLORS.green } }}
            />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card size="small" style={statCardStyle(COLORS.lightBlue)}>
            <Statistic
              title="Total Referrals"
              value={totalReferralsCount}
              prefix={<Link2 size={16} />}
              styles={{ content: { color: COLORS.lightBlue } }}
            />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card size="small" style={statCardStyle(COLORS.purple)}>
            <Statistic
              title="Total Commissions"
              value={totalCommissionsEarned}
              formatter={(v) => formatCurrency(Number(v))}
              prefix={<DollarSign size={16} />}
              styles={{ content: { color: COLORS.purple } }}
            />
          </Card>
        </Col>
      </Row>

      {/* ── Sub-Tabs ────────────────────────────────────────────────────────── */}
      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        type="card"
        items={[

          // ═══════════════════════════════════════════════════════════════════
          // SUB-TAB 1: REFERRERS
          // ═══════════════════════════════════════════════════════════════════
          {
            key: 'referrers',
            label: (
              <span><Users size={14} style={{ marginRight: 6, verticalAlign: 'text-bottom' }} />Referrers ({referrers.length})</span>
            ),
            children: (
              <div>
                {/* Filters + Add button */}
                <div style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12, marginBottom: 16 }}>
                  <Space wrap>
                    <Input
                      placeholder="Search by name or email..."
                      prefix={<Search size={14} />}
                      allowClear
                      style={{ width: 260 }}
                      value={referrerSearch}
                      onChange={(e) => setReferrerSearch(e.target.value)}
                    />
                    <Select
                      placeholder="Status"
                      allowClear
                      style={{ width: 130 }}
                      value={referrerStatusFilter}
                      onChange={setReferrerStatusFilter}
                      options={[
                        { value: 'true', label: 'Active' },
                        { value: 'false', label: 'Inactive' },
                      ]}
                    />
                  </Space>
                  <Button
                    type="primary"
                    icon={<UserPlus size={14} />}
                    onClick={openAddReferrer}
                    style={{ background: COLORS.primary }}
                  >
                    Add Referrer
                  </Button>
                </div>

                <Table
                  columns={referrerColumns}
                  dataSource={referrers}
                  rowKey="id"
                  size="middle"
                  loading={loadingReferrers}
                  pagination={{ pageSize: 10, showTotal: (t) => `${t} referrers`, showSizeChanger: true }}
                  scroll={{ x: 1100 }}
                />
              </div>
            ),
          },

          // ═══════════════════════════════════════════════════════════════════
          // SUB-TAB 2: REFERRALS
          // ═══════════════════════════════════════════════════════════════════
          {
            key: 'referrals',
            label: (
              <span><Link2 size={14} style={{ marginRight: 6, verticalAlign: 'text-bottom' }} />Referrals ({referrals.length})</span>
            ),
            children: (
              <div>
                {/* Filters + Link button */}
                <div style={{ display: 'flex', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12, marginBottom: 16 }}>
                  <Space wrap>
                    <Select
                      placeholder="Filter by Status"
                      allowClear
                      style={{ width: 160 }}
                      value={referralStatusFilter}
                      onChange={setReferralStatusFilter}
                      options={[
                        { value: 'Pending', label: 'Pending' },
                        { value: 'Trial', label: 'Trial' },
                        { value: 'Active', label: 'Active' },
                        { value: 'Cancelled', label: 'Cancelled' },
                        { value: 'Expired', label: 'Expired' },
                      ]}
                    />
                    <Select
                      placeholder="Filter by Referrer"
                      allowClear
                      showSearch
                      style={{ width: 220 }}
                      value={referralReferrerFilter}
                      onChange={setReferralReferrerFilter}
                      filterOption={(input, opt) => (opt?.label as string || '').toLowerCase().includes(input.toLowerCase())}
                      options={referrers.map((r) => ({ value: r.id, label: `${r.contact_name} (${r.referrer_code})` }))}
                    />
                  </Space>
                  <Button
                    type="primary"
                    icon={<Link2 size={14} />}
                    onClick={() => { referralForm.resetFields(); setReferralModalOpen(true); }}
                    style={{ background: COLORS.primary }}
                  >
                    Link Referral
                  </Button>
                </div>

                <Table
                  columns={referralColumns}
                  dataSource={referrals}
                  rowKey="id"
                  size="middle"
                  loading={loadingReferrals}
                  pagination={{ pageSize: 10, showTotal: (t) => `${t} referrals`, showSizeChanger: true }}
                  scroll={{ x: 900 }}
                />
              </div>
            ),
          },

          // ═══════════════════════════════════════════════════════════════════
          // SUB-TAB 3: COMMISSIONS & PAYOUTS
          // ═══════════════════════════════════════════════════════════════════
          {
            key: 'commissions-payouts',
            label: (
              <span><DollarSign size={14} style={{ marginRight: 6, verticalAlign: 'text-bottom' }} />Commissions & Payouts</span>
            ),
            children: (
              <div>
                {/* ── COMMISSIONS SECTION ──────────────────────────────── */}
                <div style={{ marginBottom: 8 }}>
                  <Title level={5} style={{ color: COLORS.navy, marginBottom: 12 }}>
                    <DollarSign size={16} style={{ marginRight: 6, verticalAlign: 'text-bottom' }} />
                    Commissions
                  </Title>
                  <Space wrap style={{ marginBottom: 12 }}>
                    <Select
                      placeholder="Filter by Status"
                      allowClear
                      style={{ width: 160 }}
                      value={commStatusFilter}
                      onChange={setCommStatusFilter}
                      options={[
                        { value: 'Pending', label: 'Pending' },
                        { value: 'Approved', label: 'Approved' },
                        { value: 'Paid', label: 'Paid' },
                        { value: 'Cancelled', label: 'Cancelled' },
                      ]}
                    />
                    <Select
                      placeholder="Filter by Referrer"
                      allowClear
                      showSearch
                      style={{ width: 220 }}
                      value={commReferrerFilter}
                      onChange={setCommReferrerFilter}
                      filterOption={(input, opt) => (opt?.label as string || '').toLowerCase().includes(input.toLowerCase())}
                      options={referrers.map((r) => ({ value: r.id, label: r.contact_name }))}
                    />
                  </Space>
                </div>

                <Table
                  columns={commissionColumns}
                  dataSource={commissions}
                  rowKey="id"
                  size="middle"
                  loading={loadingCommissions}
                  pagination={{ pageSize: 10, showTotal: (t) => `${t} commissions`, showSizeChanger: true }}
                  scroll={{ x: 1100 }}
                  style={{ marginBottom: 32 }}
                />

                <Divider />

                {/* ── PAYOUTS SECTION ──────────────────────────────────── */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                  <Title level={5} style={{ color: COLORS.navy, margin: 0 }}>
                    <CreditCard size={16} style={{ marginRight: 6, verticalAlign: 'text-bottom' }} />
                    Payouts
                  </Title>
                  <Space>
                    <Select
                      placeholder="Filter by Status"
                      allowClear
                      style={{ width: 160 }}
                      value={payoutStatusFilter}
                      onChange={setPayoutStatusFilter}
                      options={[
                        { value: 'Draft', label: 'Draft' },
                        { value: 'Processing', label: 'Processing' },
                        { value: 'Completed', label: 'Completed' },
                        { value: 'Failed', label: 'Failed' },
                      ]}
                    />
                    <Button
                      type="primary"
                      icon={<CreditCard size={14} />}
                      onClick={() => { payoutForm.resetFields(); setPayoutModalOpen(true); }}
                      style={{ background: COLORS.primary }}
                    >
                      Record Payout
                    </Button>
                  </Space>
                </div>

                <Table
                  columns={payoutColumns}
                  dataSource={payouts}
                  rowKey="id"
                  size="middle"
                  loading={loadingPayouts}
                  pagination={{ pageSize: 10, showTotal: (t) => `${t} payouts`, showSizeChanger: true }}
                  scroll={{ x: 1200 }}
                />
              </div>
            ),
          },
        ]}
      />

      {/* ═══════════════════════════════════════════════════════════════════════
          MODAL: Add / Edit Referrer
          ═══════════════════════════════════════════════════════════════════════ */}
      <Modal
        title={editingReferrer ? 'Edit Referrer' : 'Add Referrer'}
        open={referrerModalOpen}
        onCancel={() => { setReferrerModalOpen(false); referrerForm.resetFields(); setEditingReferrer(null); }}
        footer={null}
        width={620}
        destroyOnHidden
      >
        <Form form={referrerForm} layout="vertical" onFinish={handleSaveReferrer}>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item label="Contact Name" name="contact_name" rules={[{ required: true, message: 'Required' }]}>
                <Input placeholder="John Doe" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item label="Email" name="email" rules={[{ required: true, type: 'email', message: 'Valid email required' }]}>
                <Input placeholder="john@example.com" />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item label="Phone" name="phone">
                <Input placeholder="+1234567890" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item label="Company" name="company_name">
                <Input placeholder="Company Name" />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item label="Bank Name" name="bank_name">
                <Input placeholder="Bank Name" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item label="Bank Account" name="bank_account">
                <Input placeholder="Account Number" />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item label="Referral Code" name="referrer_code" rules={[{ required: true, message: 'Required' }]}>
                <Input
                  placeholder="REF-XXXXXX"
                  style={{ fontFamily: 'monospace' }}
                  addonAfter={
                    <Button type="link" size="small" onClick={generateCode} style={{ padding: 0, height: 'auto' }}>
                      Auto-Generate
                    </Button>
                  }
                />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item label="Type" name="referrer_type" rules={[{ required: true }]} initialValue="Partner">
                <Select
                  options={[
                    { value: 'Partner', label: 'Business Partner' },
                    { value: 'Affiliate', label: 'Affiliate Marketer' },
                    { value: 'Employee', label: 'Employee' },
                    { value: 'Reseller', label: 'Reseller' },
                  ]}
                />
              </Form.Item>
            </Col>
          </Row>
          <Row gutter={16}>
            <Col span={8}>
              <Form.Item label="Commission Rate" name="commission_rate" rules={[{ required: true }]} initialValue={10}>
                <InputNumber min={0} max={100} style={{ width: '100%' }} addonAfter="%" />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item label="Commission Type" name="commission_type" initialValue="Percentage">
                <Select
                  options={[
                    { value: 'Percentage', label: 'Percentage' },
                    { value: 'Fixed', label: 'Fixed Amount' },
                  ]}
                />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item label="Payment Schedule" name="payment_schedule" initialValue="Monthly">
                <Select
                  options={[
                    { value: 'Monthly', label: 'Monthly' },
                    { value: 'Quarterly', label: 'Quarterly' },
                    { value: 'OnDemand', label: 'On Demand' },
                  ]}
                />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item label="Address" name="address">
            <Input.TextArea rows={2} placeholder="Address (optional)" />
          </Form.Item>
          <Form.Item style={{ marginBottom: 0 }}>
            <Button
              type="primary"
              htmlType="submit"
              block
              loading={createReferrerMut.isPending || updateReferrerMut.isPending}
              style={{ background: COLORS.primary }}
            >
              {editingReferrer ? 'Update Referrer' : 'Create Referrer'}
            </Button>
          </Form.Item>
        </Form>
      </Modal>

      {/* ═══════════════════════════════════════════════════════════════════════
          MODAL: Link Referral
          ═══════════════════════════════════════════════════════════════════════ */}
      <Modal
        title="Link Referral"
        open={referralModalOpen}
        onCancel={() => { setReferralModalOpen(false); referralForm.resetFields(); }}
        footer={null}
        width={480}
        destroyOnHidden
      >
        <Form form={referralForm} layout="vertical" onFinish={handleCreateReferral}>
          <Form.Item label="Referrer" name="referrer_id" rules={[{ required: true, message: 'Select a referrer' }]}>
            <Select
              placeholder="Select Referrer"
              showSearch
              filterOption={(input, opt) => (opt?.label as string || '').toLowerCase().includes(input.toLowerCase())}
              options={referrers.filter((r) => r.is_active).map((r) => ({
                value: r.id,
                label: `${r.contact_name} (${r.referrer_code})`,
              }))}
            />
          </Form.Item>
          <Form.Item label="Tenant" name="tenant_id" rules={[{ required: true, message: 'Select a tenant' }]}>
            <Select
              placeholder="Select Tenant"
              showSearch
              filterOption={(input, opt) => (opt?.label as string || '').toLowerCase().includes(input.toLowerCase())}
              options={(tenants as any[]).map((t: any) => ({
                value: t.id,
                label: t.name,
              }))}
            />
          </Form.Item>
          <Form.Item label="Source" name="source">
            <Input placeholder="e.g. website, email campaign, direct" />
          </Form.Item>
          <Form.Item style={{ marginBottom: 0 }}>
            <Button
              type="primary"
              htmlType="submit"
              block
              loading={createReferralMut.isPending}
              style={{ background: COLORS.primary }}
            >
              Link Referral
            </Button>
          </Form.Item>
        </Form>
      </Modal>

      {/* ═══════════════════════════════════════════════════════════════════════
          MODAL: Record Payout
          ═══════════════════════════════════════════════════════════════════════ */}
      <Modal
        title="Record Payout"
        open={payoutModalOpen}
        onCancel={() => { setPayoutModalOpen(false); payoutForm.resetFields(); }}
        footer={null}
        width={480}
        destroyOnHidden
      >
        <Form form={payoutForm} layout="vertical" onFinish={handleCreatePayout}>
          <Form.Item label="Referrer" name="referrer_id" rules={[{ required: true, message: 'Select a referrer' }]}>
            <Select
              placeholder="Select Referrer"
              showSearch
              filterOption={(input, opt) => (opt?.label as string || '').toLowerCase().includes(input.toLowerCase())}
              options={referrers.filter((r) => r.is_active).map((r) => ({
                value: r.id,
                label: `${r.contact_name} (${r.referrer_code})`,
              }))}
            />
          </Form.Item>
          <Row gutter={16}>
            <Col span={12}>
              <Form.Item label="Period Start" name="period_start" rules={[{ required: true }]}>
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item label="Period End" name="period_end" rules={[{ required: true }]}>
                <DatePicker style={{ width: '100%' }} />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item label="Notes" name="notes">
            <Input.TextArea rows={2} placeholder="Optional notes" />
          </Form.Item>
          <Form.Item style={{ marginBottom: 0 }}>
            <Button
              type="primary"
              htmlType="submit"
              block
              loading={createPayoutMut.isPending}
              style={{ background: COLORS.primary }}
            >
              Create Payout
            </Button>
          </Form.Item>
        </Form>
      </Modal>

      {/* ═══════════════════════════════════════════════════════════════════════
          MODAL: Complete Payout
          ═══════════════════════════════════════════════════════════════════════ */}
      <Modal
        title="Complete Payout"
        open={!!completePayoutModal}
        onCancel={() => { setCompletePayoutModal(null); completePayoutForm.resetFields(); }}
        footer={null}
        width={460}
        destroyOnHidden
      >
        {completePayoutModal && (
          <div style={{ marginBottom: 16 }}>
            <Text type="secondary">
              Completing payout for <Text strong>{completePayoutModal.referrer_name}</Text>{' '}
              | Amount: <Text strong style={{ color: COLORS.green }}>{formatCurrency(parseFloat(completePayoutModal.total_commissions))}</Text>
            </Text>
          </div>
        )}
        <Form form={completePayoutForm} layout="vertical" onFinish={handleCompletePayout}>
          <Form.Item label="Payment Method" name="payment_method" rules={[{ required: true }]}>
            <Select
              placeholder="Select method"
              options={[
                { value: 'Bank Transfer', label: 'Bank Transfer' },
                { value: 'Check', label: 'Check' },
                { value: 'PayPal', label: 'PayPal' },
                { value: 'Cash', label: 'Cash' },
                { value: 'Other', label: 'Other' },
              ]}
            />
          </Form.Item>
          <Form.Item label="Payment Reference" name="payout_reference" rules={[{ required: true }]}>
            <Input placeholder="e.g. transaction ID, check number" style={{ fontFamily: 'monospace' }} />
          </Form.Item>
          <Form.Item label="Notes" name="notes">
            <Input.TextArea rows={2} placeholder="Optional notes" />
          </Form.Item>
          <Form.Item style={{ marginBottom: 0 }}>
            <Button
              type="primary"
              htmlType="submit"
              block
              loading={updatePayoutMut.isPending}
              style={{ background: COLORS.green }}
            >
              Mark as Completed
            </Button>
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  );
}
