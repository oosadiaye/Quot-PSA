import { useState } from 'react';
import {
    Plus, Trash2, Play, RefreshCw, CheckCircle2, XCircle,
    Clock, ChevronRight, BarChart3, Users, Calendar,
} from 'lucide-react';
import {
    useConsolidationGroups, useCreateConsolidationGroup,
    useDeleteConsolidationGroup, useConsolidationRuns,
    useRunConsolidation, useConsolidations, useCompanies,
} from '../hooks/useMultiCompany';
import AccountingLayout from '../AccountingLayout';
import LoadingScreen from '../../../components/common/LoadingScreen';
import logger from '../../../utils/logger';
import '../styles/glassmorphism.css';

const inputStyle: React.CSSProperties = {
    width: '100%', padding: '8px 12px',
    border: '2.5px solid #d1d5db', borderRadius: '8px',
    fontSize: '14px', outline: 'none', background: '#fafbfc', color: '#1e293b',
};

const selectStyle: React.CSSProperties = { ...inputStyle, cursor: 'pointer' };

const STATUS_CONFIG: Record<string, { color: string; bg: string; icon: JSX.Element }> = {
    pending:    { color: '#92400e', bg: '#fef3c7', icon: <Clock size={12} /> },
    running:    { color: '#1e40af', bg: '#dbeafe', icon: <RefreshCw size={12} /> },
    completed:  { color: '#065f46', bg: '#d1fae5', icon: <CheckCircle2 size={12} /> },
    failed:     { color: '#991b1b', bg: '#fee2e2', icon: <XCircle size={12} /> },
    draft:      { color: '#374151', bg: '#f3f4f6', icon: <Clock size={12} /> },
};

function StatusBadge({ status }: { status: string }) {
    const cfg = STATUS_CONFIG[status?.toLowerCase()] ?? STATUS_CONFIG.draft;
    return (
        <span style={{
            display: 'inline-flex', alignItems: 'center', gap: '4px',
            padding: '2px 8px', borderRadius: '12px', fontSize: '12px',
            fontWeight: 600, color: cfg.color, background: cfg.bg,
        }}>
            {cfg.icon}{status}
        </span>
    );
}

export default function ConsolidationPage() {
    const [activeTab, setActiveTab] = useState<'groups' | 'runs' | 'results'>('groups');
    const [showGroupModal, setShowGroupModal] = useState(false);
    const [showRunModal, setShowRunModal] = useState(false);
    const [selectedGroup, setSelectedGroup] = useState<any>(null);
    const [deleteConfirm, setDeleteConfirm] = useState<number | null>(null);

    const [groupForm, setGroupForm] = useState({
        name: '', code: '', description: '', currency: 'USD',
        member_companies: [] as string[],
        parent_company: '',
    });

    const [runForm, setRunForm] = useState({
        group_id: '', period_id: '',
    });

    const { data: groups, isLoading } = useConsolidationGroups({});
    const { data: runs } = useConsolidationRuns({});
    const { data: consolidations } = useConsolidations({});
    const { data: companies } = useCompanies({});
    const createGroup = useCreateConsolidationGroup();
    const deleteGroup = useDeleteConsolidationGroup();
    const runConsolidation = useRunConsolidation();

    const handleCreateGroup = async (e: React.FormEvent) => {
        e.preventDefault();
        try {
            await createGroup.mutateAsync(groupForm);
            setShowGroupModal(false);
            setGroupForm({ name: '', code: '', description: '', currency: 'USD', member_companies: [], parent_company: '' });
        } catch (err) {
            logger.error('Failed to create consolidation group:', err);
        }
    };

    const handleRunConsolidation = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!runForm.group_id || !runForm.period_id) return;
        try {
            await runConsolidation.mutateAsync({
                group_id: Number(runForm.group_id),
                period_id: Number(runForm.period_id),
            });
            setShowRunModal(false);
            setRunForm({ group_id: '', period_id: '' });
            setActiveTab('runs');
        } catch (err) {
            logger.error('Failed to run consolidation:', err);
        }
    };

    const handleDeleteGroup = async (id: number) => {
        try {
            await deleteGroup.mutateAsync(id);
            setDeleteConfirm(null);
        } catch (err) {
            logger.error('Failed to delete group:', err);
        }
    };

    const toggleMember = (companyId: string) => {
        setGroupForm(prev => ({
            ...prev,
            member_companies: prev.member_companies.includes(companyId)
                ? prev.member_companies.filter(id => id !== companyId)
                : [...prev.member_companies, companyId],
        }));
    };

    if (isLoading) return <LoadingScreen message="Loading consolidation data..." />;

    const tabs = [
        { key: 'groups', label: 'Consolidation Groups', icon: <Users size={15} /> },
        { key: 'runs', label: 'Run History', icon: <Calendar size={15} /> },
        { key: 'results', label: 'Consolidated Statements', icon: <BarChart3 size={15} /> },
    ];

    const summaryStats = [
        { label: 'Groups', value: groups?.length ?? 0, color: '#2563eb' },
        { label: 'Total Runs', value: runs?.length ?? 0, color: '#7c3aed' },
        { label: 'Completed', value: runs?.filter((r: any) => r.status === 'completed').length ?? 0, color: '#059669' },
        { label: 'Statements', value: consolidations?.length ?? 0, color: '#d97706' },
    ];

    return (
        <AccountingLayout>
            <div style={{ padding: '24px', background: '#eef2f7', minHeight: '100vh' }}>
                {/* Header */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '24px' }}>
                    <div>
                        <h1 style={{ fontSize: '22px', fontWeight: 700, color: '#1e293b', margin: 0 }}>
                            Consolidation
                        </h1>
                        <p style={{ color: '#64748b', fontSize: '14px', margin: '4px 0 0' }}>
                            Manage consolidation groups, run consolidations, and view combined financials
                        </p>
                    </div>
                    <div style={{ display: 'flex', gap: '10px' }}>
                        <button
                            onClick={() => setShowRunModal(true)}
                            style={{
                                display: 'flex', alignItems: 'center', gap: '6px',
                                padding: '9px 16px', borderRadius: '8px', border: 'none',
                                background: '#7c3aed', color: '#fff', fontWeight: 600,
                                fontSize: '14px', cursor: 'pointer',
                            }}
                        >
                            <Play size={14} /> Run Consolidation
                        </button>
                        <button
                            onClick={() => setShowGroupModal(true)}
                            style={{
                                display: 'flex', alignItems: 'center', gap: '6px',
                                padding: '9px 16px', borderRadius: '8px', border: 'none',
                                background: '#191e6a', color: '#fff', fontWeight: 600,
                                fontSize: '14px', cursor: 'pointer',
                            }}
                        >
                            <Plus size={14} /> New Group
                        </button>
                    </div>
                </div>

                {/* Summary Cards */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '16px', marginBottom: '24px' }}>
                    {summaryStats.map(s => (
                        <div key={s.label} style={{
                            background: '#fff', borderRadius: '12px', padding: '16px 20px',
                            boxShadow: '0 1px 3px rgba(0,0,0,0.06)',
                        }}>
                            <p style={{ margin: 0, fontSize: '12px', color: '#94a3b8', fontWeight: 500 }}>{s.label}</p>
                            <p style={{ margin: '4px 0 0', fontSize: '28px', fontWeight: 700, color: s.color }}>{s.value}</p>
                        </div>
                    ))}
                </div>

                {/* Tabs */}
                <div style={{ display: 'flex', gap: '4px', background: '#fff', padding: '6px', borderRadius: '10px', marginBottom: '20px', boxShadow: '0 1px 3px rgba(0,0,0,0.06)', width: 'fit-content' }}>
                    {tabs.map(tab => (
                        <button
                            key={tab.key}
                            onClick={() => setActiveTab(tab.key as any)}
                            style={{
                                display: 'flex', alignItems: 'center', gap: '6px',
                                padding: '8px 16px', borderRadius: '8px', border: 'none',
                                background: activeTab === tab.key ? '#191e6a' : 'transparent',
                                color: activeTab === tab.key ? '#fff' : '#64748b',
                                fontWeight: activeTab === tab.key ? 600 : 400,
                                fontSize: '14px', cursor: 'pointer',
                                transition: 'all 0.15s ease',
                            }}
                        >
                            {tab.icon} {tab.label}
                        </button>
                    ))}
                </div>

                {/* Tab Content */}
                <div style={{ background: '#fff', borderRadius: '12px', boxShadow: '0 1px 3px rgba(0,0,0,0.06)', overflow: 'hidden' }}>

                    {/* ── Groups Tab ── */}
                    {activeTab === 'groups' && (
                        <div>
                            {(!groups || groups.length === 0) ? (
                                <div style={{ padding: '60px', textAlign: 'center' }}>
                                    <Users size={40} color="#cbd5e1" />
                                    <p style={{ color: '#94a3b8', marginTop: '12px' }}>No consolidation groups yet. Create one to get started.</p>
                                    <button onClick={() => setShowGroupModal(true)} style={{
                                        marginTop: '16px', padding: '10px 20px', borderRadius: '8px',
                                        background: '#191e6a', color: '#fff', border: 'none',
                                        fontWeight: 600, cursor: 'pointer',
                                    }}>
                                        Create Group
                                    </button>
                                </div>
                            ) : (
                                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '16px', padding: '20px' }}>
                                    {groups.map((group: any) => (
                                        <div key={group.id} style={{
                                            border: '1.5px solid #e2e8f0', borderRadius: '12px',
                                            padding: '20px', position: 'relative',
                                            background: '#fafbfc',
                                        }}>
                                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                                                <div>
                                                    <h3 style={{ margin: 0, fontSize: '15px', fontWeight: 700, color: '#1e293b' }}>{group.name}</h3>
                                                    <p style={{ margin: '2px 0 0', fontSize: '12px', color: '#94a3b8' }}>{group.code}</p>
                                                </div>
                                                <div style={{ display: 'flex', gap: '8px' }}>
                                                    <button
                                                        onClick={() => { setSelectedGroup(group); setRunForm(f => ({ ...f, group_id: String(group.id) })); setShowRunModal(true); }}
                                                        title="Run Consolidation"
                                                        style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#7c3aed', padding: '4px' }}
                                                    >
                                                        <Play size={16} />
                                                    </button>
                                                    <button
                                                        onClick={() => setDeleteConfirm(group.id)}
                                                        title="Delete Group"
                                                        style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#ef4444', padding: '4px' }}
                                                    >
                                                        <Trash2 size={16} />
                                                    </button>
                                                </div>
                                            </div>
                                            {group.description && (
                                                <p style={{ margin: '10px 0 0', fontSize: '13px', color: '#64748b' }}>{group.description}</p>
                                            )}
                                            <div style={{ marginTop: '14px', display: 'flex', gap: '12px', fontSize: '12px', color: '#64748b' }}>
                                                <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                                                    <Users size={12} />
                                                    {group.member_companies?.length ?? 0} members
                                                </span>
                                                <span>Currency: {group.currency}</span>
                                            </div>
                                            {group.member_companies?.length > 0 && (
                                                <div style={{ marginTop: '12px', display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                                                    {group.member_companies.slice(0, 4).map((cId: any) => {
                                                        const c = companies?.find((co: any) => co.id === cId || co.id === Number(cId));
                                                        return (
                                                            <span key={cId} style={{
                                                                fontSize: '11px', padding: '2px 8px', borderRadius: '10px',
                                                                background: '#eff6ff', color: '#1d4ed8', fontWeight: 500,
                                                            }}>
                                                                {c?.name ?? `Company ${cId}`}
                                                            </span>
                                                        );
                                                    })}
                                                    {group.member_companies.length > 4 && (
                                                        <span style={{ fontSize: '11px', padding: '2px 8px', borderRadius: '10px', background: '#f1f5f9', color: '#64748b' }}>
                                                            +{group.member_companies.length - 4} more
                                                        </span>
                                                    )}
                                                </div>
                                            )}
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    )}

                    {/* ── Run History Tab ── */}
                    {activeTab === 'runs' && (
                        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                            <thead>
                                <tr style={{ background: '#f4f7fb', borderBottom: '1px solid #e2e8f0' }}>
                                    {['Group', 'Period', 'Status', 'Started', 'Completed', 'Started By'].map(h => (
                                        <th key={h} style={{ padding: '12px 16px', textAlign: 'left', fontSize: '12px', fontWeight: 600, color: '#64748b', textTransform: 'uppercase' }}>{h}</th>
                                    ))}
                                </tr>
                            </thead>
                            <tbody>
                                {(!runs || runs.length === 0) ? (
                                    <tr><td colSpan={6} style={{ padding: '60px', textAlign: 'center', color: '#94a3b8' }}>
                                        No consolidation runs yet. Run a consolidation to see history here.
                                    </td></tr>
                                ) : runs.map((run: any) => (
                                    <tr key={run.id} style={{ borderBottom: '1px solid #f1f5f9' }}>
                                        <td style={{ padding: '12px 16px', fontSize: '14px', fontWeight: 600, color: '#1e293b' }}>
                                            {run.group_name ?? run.group}
                                        </td>
                                        <td style={{ padding: '12px 16px', fontSize: '13px', color: '#475569' }}>
                                            {run.period_name ?? run.period}
                                        </td>
                                        <td style={{ padding: '12px 16px' }}>
                                            <StatusBadge status={run.status} />
                                        </td>
                                        <td style={{ padding: '12px 16px', fontSize: '13px', color: '#475569' }}>
                                            {run.started_at ? new Date(run.started_at).toLocaleString() : '—'}
                                        </td>
                                        <td style={{ padding: '12px 16px', fontSize: '13px', color: '#475569' }}>
                                            {run.completed_at ? new Date(run.completed_at).toLocaleString() : '—'}
                                        </td>
                                        <td style={{ padding: '12px 16px', fontSize: '13px', color: '#475569' }}>
                                            {run.started_by_name ?? run.started_by ?? '—'}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    )}

                    {/* ── Results Tab ── */}
                    {activeTab === 'results' && (
                        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                            <thead>
                                <tr style={{ background: '#f4f7fb', borderBottom: '1px solid #e2e8f0' }}>
                                    {['Group', 'Period', 'Total Assets', 'Total Revenue', 'Net Income', 'Status'].map(h => (
                                        <th key={h} style={{ padding: '12px 16px', textAlign: 'left', fontSize: '12px', fontWeight: 600, color: '#64748b', textTransform: 'uppercase' }}>{h}</th>
                                    ))}
                                </tr>
                            </thead>
                            <tbody>
                                {(!consolidations || consolidations.length === 0) ? (
                                    <tr><td colSpan={6} style={{ padding: '60px', textAlign: 'center', color: '#94a3b8' }}>
                                        No consolidated statements yet. Run a consolidation to generate statements.
                                    </td></tr>
                                ) : consolidations.map((c: any) => (
                                    <tr key={c.id} style={{ borderBottom: '1px solid #f1f5f9' }}>
                                        <td style={{ padding: '12px 16px', fontSize: '14px', fontWeight: 600, color: '#1e293b' }}>
                                            {c.group_name ?? c.group}
                                        </td>
                                        <td style={{ padding: '12px 16px', fontSize: '13px', color: '#475569' }}>
                                            {c.period_name ?? c.period}
                                        </td>
                                        <td style={{ padding: '12px 16px', fontSize: '13px', color: '#475569', textAlign: 'right' }}>
                                            {c.total_assets != null ? Number(c.total_assets).toLocaleString(undefined, { minimumFractionDigits: 2 }) : '—'}
                                        </td>
                                        <td style={{ padding: '12px 16px', fontSize: '13px', color: '#475569', textAlign: 'right' }}>
                                            {c.total_revenue != null ? Number(c.total_revenue).toLocaleString(undefined, { minimumFractionDigits: 2 }) : '—'}
                                        </td>
                                        <td style={{ padding: '12px 16px', fontSize: '13px', fontWeight: 600, color: c.net_income >= 0 ? '#059669' : '#dc2626', textAlign: 'right' }}>
                                            {c.net_income != null ? Number(c.net_income).toLocaleString(undefined, { minimumFractionDigits: 2 }) : '—'}
                                        </td>
                                        <td style={{ padding: '12px 16px' }}>
                                            <StatusBadge status={c.status ?? 'completed'} />
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    )}
                </div>
            </div>

            {/* ── Create Group Modal ── */}
            {showGroupModal && (
                <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
                    <div style={{ background: '#fff', borderRadius: '16px', padding: '28px', width: '560px', maxHeight: '85vh', overflowY: 'auto' }}>
                        <h2 style={{ margin: '0 0 20px', fontSize: '18px', fontWeight: 700, color: '#1e293b' }}>New Consolidation Group</h2>
                        <form onSubmit={handleCreateGroup}>
                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: '16px' }}>
                                <div>
                                    <label style={{ fontSize: '13px', fontWeight: 600, color: '#374151', display: 'block', marginBottom: '6px' }}>Group Name *</label>
                                    <input style={inputStyle} required placeholder="e.g. DTSG Global Group"
                                        value={groupForm.name} onChange={e => setGroupForm(f => ({ ...f, name: e.target.value }))} />
                                </div>
                                <div>
                                    <label style={{ fontSize: '13px', fontWeight: 600, color: '#374151', display: 'block', marginBottom: '6px' }}>Code *</label>
                                    <input style={inputStyle} required placeholder="e.g. DTSG-GRP"
                                        value={groupForm.code} onChange={e => setGroupForm(f => ({ ...f, code: e.target.value }))} />
                                </div>
                            </div>
                            <div style={{ marginBottom: '16px' }}>
                                <label style={{ fontSize: '13px', fontWeight: 600, color: '#374151', display: 'block', marginBottom: '6px' }}>Reporting Currency</label>
                                <input style={inputStyle} placeholder="USD"
                                    value={groupForm.currency} onChange={e => setGroupForm(f => ({ ...f, currency: e.target.value }))} />
                            </div>
                            <div style={{ marginBottom: '16px' }}>
                                <label style={{ fontSize: '13px', fontWeight: 600, color: '#374151', display: 'block', marginBottom: '6px' }}>Description</label>
                                <textarea style={{ ...inputStyle, height: '72px', resize: 'vertical' }} placeholder="Optional description"
                                    value={groupForm.description} onChange={e => setGroupForm(f => ({ ...f, description: e.target.value }))} />
                            </div>
                            <div style={{ marginBottom: '20px' }}>
                                <label style={{ fontSize: '13px', fontWeight: 600, color: '#374151', display: 'block', marginBottom: '8px' }}>
                                    Member Companies
                                </label>
                                <div style={{ border: '1.5px solid #e2e8f0', borderRadius: '8px', maxHeight: '180px', overflowY: 'auto', padding: '8px' }}>
                                    {(!companies || companies.length === 0) ? (
                                        <p style={{ margin: 0, fontSize: '13px', color: '#94a3b8', textAlign: 'center', padding: '16px 0' }}>
                                            No companies found. Add companies in the Multi-Company module.
                                        </p>
                                    ) : companies.map((co: any) => (
                                        <label key={co.id} style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '6px 8px', borderRadius: '6px', cursor: 'pointer' }}>
                                            <input
                                                type="checkbox"
                                                checked={groupForm.member_companies.includes(String(co.id))}
                                                onChange={() => toggleMember(String(co.id))}
                                            />
                                            <span style={{ fontSize: '13px', color: '#1e293b' }}>{co.name}</span>
                                            <span style={{ fontSize: '11px', color: '#94a3b8', marginLeft: 'auto' }}>{co.company_code}</span>
                                        </label>
                                    ))}
                                </div>
                            </div>
                            <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end' }}>
                                <button type="button" onClick={() => setShowGroupModal(false)} style={{
                                    padding: '9px 18px', borderRadius: '8px', border: '1.5px solid #e2e8f0',
                                    background: '#fff', color: '#374151', fontWeight: 600, cursor: 'pointer',
                                }}>Cancel</button>
                                <button type="submit" disabled={createGroup.isPending} style={{
                                    padding: '9px 18px', borderRadius: '8px', border: 'none',
                                    background: '#191e6a', color: '#fff', fontWeight: 600, cursor: 'pointer',
                                }}>
                                    {createGroup.isPending ? 'Creating...' : 'Create Group'}
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}

            {/* ── Run Consolidation Modal ── */}
            {showRunModal && (
                <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
                    <div style={{ background: '#fff', borderRadius: '16px', padding: '28px', width: '460px' }}>
                        <h2 style={{ margin: '0 0 8px', fontSize: '18px', fontWeight: 700, color: '#1e293b' }}>Run Consolidation</h2>
                        <p style={{ margin: '0 0 20px', fontSize: '13px', color: '#64748b' }}>
                            This will process all member company journals and generate elimination entries.
                        </p>
                        <form onSubmit={handleRunConsolidation}>
                            <div style={{ marginBottom: '16px' }}>
                                <label style={{ fontSize: '13px', fontWeight: 600, color: '#374151', display: 'block', marginBottom: '6px' }}>Consolidation Group *</label>
                                <select style={selectStyle} required
                                    value={runForm.group_id}
                                    onChange={e => setRunForm(f => ({ ...f, group_id: e.target.value }))}>
                                    <option value="">Select group...</option>
                                    {groups?.map((g: any) => (
                                        <option key={g.id} value={g.id}>{g.name}</option>
                                    ))}
                                </select>
                            </div>
                            <div style={{ marginBottom: '24px' }}>
                                <label style={{ fontSize: '13px', fontWeight: 600, color: '#374151', display: 'block', marginBottom: '6px' }}>
                                    Period ID *
                                    <span style={{ fontSize: '11px', color: '#94a3b8', fontWeight: 400, marginLeft: '8px' }}>Enter the fiscal period ID to consolidate</span>
                                </label>
                                <input style={inputStyle} required type="number" placeholder="e.g. 12"
                                    value={runForm.period_id}
                                    onChange={e => setRunForm(f => ({ ...f, period_id: e.target.value }))} />
                            </div>
                            <div style={{ background: '#fffbeb', border: '1px solid #fcd34d', borderRadius: '8px', padding: '12px', marginBottom: '20px' }}>
                                <p style={{ margin: 0, fontSize: '13px', color: '#92400e' }}>
                                    <strong>Note:</strong> Running consolidation will aggregate journals from all member companies, apply intercompany eliminations, and generate a consolidated statement. Existing runs for this period will be updated.
                                </p>
                            </div>
                            <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end' }}>
                                <button type="button" onClick={() => { setShowRunModal(false); setSelectedGroup(null); }} style={{
                                    padding: '9px 18px', borderRadius: '8px', border: '1.5px solid #e2e8f0',
                                    background: '#fff', color: '#374151', fontWeight: 600, cursor: 'pointer',
                                }}>Cancel</button>
                                <button type="submit" disabled={runConsolidation.isPending} style={{
                                    display: 'flex', alignItems: 'center', gap: '6px',
                                    padding: '9px 18px', borderRadius: '8px', border: 'none',
                                    background: '#7c3aed', color: '#fff', fontWeight: 600, cursor: 'pointer',
                                }}>
                                    <Play size={14} />
                                    {runConsolidation.isPending ? 'Running...' : 'Run Consolidation'}
                                </button>
                            </div>
                        </form>
                    </div>
                </div>
            )}

            {/* ── Delete Confirm Modal ── */}
            {deleteConfirm !== null && (
                <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
                    <div style={{ background: '#fff', borderRadius: '16px', padding: '28px', width: '400px' }}>
                        <h2 style={{ margin: '0 0 12px', fontSize: '18px', fontWeight: 700, color: '#1e293b' }}>Delete Group?</h2>
                        <p style={{ margin: '0 0 24px', fontSize: '14px', color: '#64748b' }}>
                            This will permanently delete this consolidation group. Existing run history may be affected. This action cannot be undone.
                        </p>
                        <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end' }}>
                            <button onClick={() => setDeleteConfirm(null)} style={{
                                padding: '9px 18px', borderRadius: '8px', border: '1.5px solid #e2e8f0',
                                background: '#fff', color: '#374151', fontWeight: 600, cursor: 'pointer',
                            }}>Cancel</button>
                            <button onClick={() => handleDeleteGroup(deleteConfirm)} disabled={deleteGroup.isPending} style={{
                                padding: '9px 18px', borderRadius: '8px', border: 'none',
                                background: '#dc2626', color: '#fff', fontWeight: 600, cursor: 'pointer',
                            }}>
                                {deleteGroup.isPending ? 'Deleting...' : 'Delete'}
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </AccountingLayout>
    );
}
