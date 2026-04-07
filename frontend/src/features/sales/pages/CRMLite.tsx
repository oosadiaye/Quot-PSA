import { useState, useMemo } from 'react';
import {
    useLeads, useOpportunities, useSalesForecast,
    useCreateLead, useUpdateLead, useDeleteLead,
    useCreateOpportunity, useUpdateOpportunity, useDeleteOpportunity,
    useCustomers,
} from '../hooks/useSales';
import SalesLayout from '../layout/SalesLayout';
import LoadingScreen from '../../../components/common/LoadingScreen';
import { Plus, UserPlus, Briefcase, BarChart2, Pencil, Trash2, ArrowRight, TrendingUp, X } from 'lucide-react';
import { useCurrency } from '../../../context/CurrencyContext';

// ─── Constants ────────────────────────────────────────────────────────────────

const LEAD_STATUSES = ['New', 'Contacted', 'Qualified', 'Proposal Sent', 'Negotiation', 'Won', 'Lost'];
const LEAD_SOURCES  = ['Website', 'Referral', 'Cold Call', 'Email Campaign', 'Social Media', 'Trade Show', 'Other'];

const OPP_STAGES = [
    { value: 'Prospecting',   label: 'Prospecting',  probability: 10 },
    { value: 'Qualification', label: 'Qualification', probability: 20 },
    { value: 'Proposal',      label: 'Proposal',      probability: 40 },
    { value: 'Negotiation',   label: 'Negotiation',   probability: 70 },
    { value: 'Closed_Won',    label: 'Closed Won',    probability: 100 },
    { value: 'Closed_Lost',   label: 'Closed Lost',   probability: 0 },
];

const STATUS_COLORS: Record<string, string> = {
    New: '#3b82f6', Contacted: '#f59e0b', Qualified: '#8b5cf6',
    'Proposal Sent': '#06b6d4', Negotiation: '#f97316', Won: '#10b981', Lost: '#ef4444',
    Prospecting: '#3b82f6', Qualification: '#8b5cf6', Proposal: '#06b6d4',
    Closed_Won: '#10b981', Closed_Lost: '#ef4444',
};

const stageBg = (stage: string) => `${STATUS_COLORS[stage] ?? '#6b7280'}18`;
const stageColor = (stage: string) => STATUS_COLORS[stage] ?? '#6b7280';

// ─── Types ────────────────────────────────────────────────────────────────────

const emptyLead = () => ({ name: '', company: '', email: '', phone: '', source: '', status: 'New', estimated_value: '', notes: '' });
const emptyOpp  = () => ({ name: '', customer: '', lead: '', stage: 'Prospecting', probability: 10, expected_close_date: '', expected_value: '', notes: '' });

// ─── Shared field style ───────────────────────────────────────────────────────

const fieldStyle: React.CSSProperties = {
    width: '100%', padding: '0.625rem 0.75rem', borderRadius: '8px',
    border: '1px solid var(--color-border)', background: 'var(--color-surface)',
    color: 'var(--color-text)', fontSize: 'var(--text-sm)', boxSizing: 'border-box',
};

const labelStyle: React.CSSProperties = {
    display: 'block', fontWeight: 600, fontSize: 'var(--text-xs)',
    textTransform: 'uppercase', letterSpacing: '0.04em',
    color: 'var(--color-text-muted)', marginBottom: '0.375rem',
};

const Field = ({ label, children, half }: { label: string; children: React.ReactNode; half?: boolean }) => (
    <div style={{ gridColumn: half ? 'span 1' : 'span 2' }}>
        <label style={labelStyle}>{label}</label>
        {children}
    </div>
);

// ─── Component ────────────────────────────────────────────────────────────────

const CRMLite = () => {
    const [tab, setTab] = useState<'leads' | 'opportunities' | 'forecast'>('leads');
    const { formatCurrency } = useCurrency();

    // ── Data
    const { data: leadsRaw,  isLoading: leadsLoading }  = useLeads();
    const { data: oppsRaw,   isLoading: oppLoading }    = useOpportunities();
    const { data: forecastData }                         = useSalesForecast();
    const { data: customersRaw }                        = useCustomers();

    const leads       = useMemo(() => (leadsRaw as any)?.results ?? leadsRaw ?? [], [leadsRaw]) as any[];
    const opps        = useMemo(() => (oppsRaw as any)?.results  ?? oppsRaw  ?? [], [oppsRaw])  as any[];
    const customers   = useMemo(() => (customersRaw as any)?.results ?? customersRaw ?? [], [customersRaw]) as any[];

    // ── Mutations
    const createLead   = useCreateLead();
    const updateLead   = useUpdateLead();
    const deleteLead   = useDeleteLead();
    const createOpp    = useCreateOpportunity();
    const updateOpp    = useUpdateOpportunity();
    const deleteOpp    = useDeleteOpportunity();

    // ── Modal state
    type ModalMode = 'lead' | 'opp' | null;
    const [modalMode, setModalMode]   = useState<ModalMode>(null);
    const [editId, setEditId]         = useState<number | null>(null);
    const [leadForm, setLeadForm]     = useState(emptyLead());
    const [oppForm, setOppForm]       = useState(emptyOpp());
    const [saving, setSaving]         = useState(false);
    const [error, setError]           = useState('');
    const [deleteConfirm, setDeleteConfirm] = useState<{ type: 'lead' | 'opp'; id: number; name: string } | null>(null);

    const isEditing = editId !== null;

    // ── Open modals
    const openCreateLead = () => { setLeadForm(emptyLead()); setEditId(null); setError(''); setModalMode('lead'); };
    const openCreateOpp  = () => { setOppForm(emptyOpp());   setEditId(null); setError(''); setModalMode('opp'); };

    const openEditLead = (lead: any) => {
        setLeadForm({
            name: lead.name ?? '', company: lead.company ?? '', email: lead.email ?? '',
            phone: lead.phone ?? '', source: lead.source ?? '', status: lead.status ?? 'New',
            estimated_value: lead.estimated_value ?? '', notes: lead.notes ?? '',
        });
        setEditId(lead.id); setError(''); setModalMode('lead');
    };

    const openEditOpp = (opp: any) => {
        setOppForm({
            name: opp.name ?? '', customer: String(opp.customer ?? ''), lead: String(opp.lead ?? ''),
            stage: opp.stage ?? 'Prospecting', probability: opp.probability ?? 10,
            expected_close_date: opp.expected_close_date ?? '', expected_value: opp.expected_value ?? '',
            notes: opp.notes ?? '',
        });
        setEditId(opp.id); setError(''); setModalMode('opp');
    };

    // ── Convert lead → opportunity
    const convertLead = (lead: any) => {
        setOppForm({
            name: lead.name, customer: '', lead: String(lead.id),
            stage: 'Prospecting', probability: 10,
            expected_close_date: '', expected_value: lead.estimated_value ?? '',
            notes: lead.notes ?? '',
        });
        setEditId(null); setError(''); setModalMode('opp');
    };

    // ── Save handlers
    const saveLead = async (e: React.FormEvent) => {
        e.preventDefault();
        setSaving(true); setError('');
        try {
            const payload = { ...leadForm, estimated_value: parseFloat(leadForm.estimated_value as any) || 0 };
            if (isEditing) await updateLead.mutateAsync({ id: editId!, data: payload });
            else           await createLead.mutateAsync(payload);
            setModalMode(null);
        } catch (err: any) {
            const d = err.response?.data;
            setError(d?.detail ?? d?.name?.[0] ?? d?.email?.[0] ?? JSON.stringify(d) ?? 'Save failed');
        } finally { setSaving(false); }
    };

    const saveOpp = async (e: React.FormEvent) => {
        e.preventDefault();
        setSaving(true); setError('');
        try {
            const payload = {
                name: oppForm.name,
                customer: Number(oppForm.customer),
                lead: oppForm.lead ? Number(oppForm.lead) : null,
                stage: oppForm.stage,
                probability: Number(oppForm.probability),
                expected_close_date: oppForm.expected_close_date || null,
                expected_value: parseFloat(oppForm.expected_value as any) || 0,
                notes: oppForm.notes,
            };
            if (isEditing) await updateOpp.mutateAsync({ id: editId!, data: payload });
            else           await createOpp.mutateAsync(payload);
            setModalMode(null);
        } catch (err: any) {
            const d = err.response?.data;
            setError(d?.detail ?? d?.name?.[0] ?? d?.customer?.[0] ?? JSON.stringify(d) ?? 'Save failed');
        } finally { setSaving(false); }
    };

    // ── Delete handlers
    const confirmDelete = async () => {
        if (!deleteConfirm) return;
        try {
            if (deleteConfirm.type === 'lead') await deleteLead.mutateAsync(deleteConfirm.id);
            else                               await deleteOpp.mutateAsync(deleteConfirm.id);
            setDeleteConfirm(null);
        } catch (err: any) {
            const d = err.response?.data;
            setError(d?.detail ?? d?.message ?? 'Delete failed — record may have dependent data');
            setDeleteConfirm(null);
        }
    };

    if (leadsLoading || oppLoading) return <LoadingScreen message="Loading CRM data..." />;

    // ── Forecast stats
    const forecast   = forecastData as any;
    const breakdown  = forecast?.stage_breakdown ?? {};
    const activeStages = OPP_STAGES.filter(s => s.value !== 'Closed_Won' && s.value !== 'Closed_Lost');

    return (
        <SalesLayout title="CRM Lite" description="Track leads, opportunities, and sales pipeline">

            {/* ── Tab bar */}
            <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1.5rem', borderBottom: '2px solid var(--color-border)', paddingBottom: '0' }}>
                {([
                    { key: 'leads',        label: 'Leads',        icon: <UserPlus size={15} />,  count: leads.length },
                    { key: 'opportunities',label: 'Opportunities', icon: <Briefcase size={15} />, count: opps.length },
                    { key: 'forecast',     label: 'Pipeline',     icon: <BarChart2 size={15} />,  count: null },
                ] as const).map(t => (
                    <button key={t.key} onClick={() => setTab(t.key)}
                        style={{
                            display: 'inline-flex', alignItems: 'center', gap: '0.4rem',
                            padding: '0.625rem 1rem', border: 'none', background: 'none', cursor: 'pointer',
                            fontSize: 'var(--text-sm)', fontWeight: 600,
                            color: tab === t.key ? 'var(--color-primary)' : 'var(--color-text-muted)',
                            borderBottom: tab === t.key ? '2px solid var(--color-primary)' : '2px solid transparent',
                            marginBottom: '-2px',
                        }}>
                        {t.icon} {t.label}
                        {t.count !== null && (
                            <span style={{ fontSize: 'var(--text-xs)', fontWeight: 700, background: tab === t.key ? 'var(--color-primary)' : 'var(--color-border)', color: tab === t.key ? '#fff' : 'var(--color-text-muted)', borderRadius: '20px', padding: '0.1rem 0.45rem' }}>
                                {t.count}
                            </span>
                        )}
                    </button>
                ))}
                <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center' }}>
                    {tab === 'leads' && (
                        <button className="btn btn-primary" onClick={openCreateLead} style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem', fontSize: 'var(--text-sm)' }}>
                            <Plus size={14} /> Add Lead
                        </button>
                    )}
                    {tab === 'opportunities' && (
                        <button className="btn btn-primary" onClick={openCreateOpp} style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem', fontSize: 'var(--text-sm)' }}>
                            <Plus size={14} /> Add Opportunity
                        </button>
                    )}
                </div>
            </div>

            {/* ── LEADS TAB */}
            {tab === 'leads' && (
                <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                        <thead>
                            <tr style={{ background: 'var(--color-surface)' }}>
                                {['Name', 'Company', 'Email', 'Phone', 'Source', 'Status', 'Est. Value', ''].map(h => (
                                    <th key={h} style={{ padding: '0.75rem 1rem', fontSize: 'var(--text-xs)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.04em', color: 'var(--color-text-muted)', textAlign: 'left', borderBottom: '2px solid var(--color-border)', whiteSpace: 'nowrap' }}>{h}</th>
                                ))}
                            </tr>
                        </thead>
                        <tbody>
                            {leads.length === 0 ? (
                                <tr><td colSpan={8} style={{ padding: '4rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>
                                    <UserPlus size={40} style={{ display: 'block', margin: '0 auto 0.75rem', opacity: 0.2 }} />
                                    <p style={{ margin: 0 }}>No leads yet. Add your first lead to start tracking prospects.</p>
                                </td></tr>
                            ) : leads.map((lead: any) => (
                                <tr key={lead.id}
                                    style={{ borderBottom: '1px solid var(--color-border)', transition: 'background 0.12s' }}
                                    onMouseEnter={e => (e.currentTarget.style.background = 'var(--color-surface)')}
                                    onMouseLeave={e => (e.currentTarget.style.background = '')}>
                                    <td style={{ padding: '0.875rem 1rem', fontWeight: 600 }}>{lead.name}</td>
                                    <td style={{ padding: '0.875rem 1rem', color: 'var(--color-text-muted)' }}>{lead.company || '—'}</td>
                                    <td style={{ padding: '0.875rem 1rem', fontSize: 'var(--text-sm)' }}>{lead.email || '—'}</td>
                                    <td style={{ padding: '0.875rem 1rem', fontSize: 'var(--text-sm)', whiteSpace: 'nowrap' }}>{lead.phone || '—'}</td>
                                    <td style={{ padding: '0.875rem 1rem', fontSize: 'var(--text-sm)' }}>{lead.source || '—'}</td>
                                    <td style={{ padding: '0.875rem 1rem' }}>
                                        <span style={{ padding: '0.2rem 0.6rem', borderRadius: '20px', fontSize: 'var(--text-xs)', fontWeight: 700, background: stageBg(lead.status), color: stageColor(lead.status), whiteSpace: 'nowrap' }}>
                                            {lead.status}
                                        </span>
                                    </td>
                                    <td style={{ padding: '0.875rem 1rem', fontWeight: 600, color: 'var(--color-primary)', whiteSpace: 'nowrap' }}>
                                        {formatCurrency(parseFloat(lead.estimated_value || 0))}
                                    </td>
                                    <td style={{ padding: '0.875rem 1rem', whiteSpace: 'nowrap' }}>
                                        <div style={{ display: 'flex', gap: '0.375rem' }}>
                                            <button title="Convert to Opportunity" onClick={() => convertLead(lead)}
                                                style={{ border: 'none', background: 'rgba(59,130,246,0.1)', color: '#3b82f6', borderRadius: '6px', padding: '0.3rem 0.5rem', cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: '0.25rem', fontSize: 'var(--text-xs)', fontWeight: 600 }}>
                                                <ArrowRight size={12} /> Convert
                                            </button>
                                            <button title="Edit" onClick={() => openEditLead(lead)}
                                                style={{ border: 'none', background: 'var(--color-surface)', borderRadius: '6px', padding: '0.35rem 0.5rem', cursor: 'pointer', color: 'var(--color-text-muted)', display: 'inline-flex' }}>
                                                <Pencil size={13} />
                                            </button>
                                            <button title="Delete" onClick={() => setDeleteConfirm({ type: 'lead', id: lead.id, name: lead.name })}
                                                style={{ border: 'none', background: 'rgba(239,68,68,0.08)', borderRadius: '6px', padding: '0.35rem 0.5rem', cursor: 'pointer', color: '#ef4444', display: 'inline-flex' }}>
                                                <Trash2 size={13} />
                                            </button>
                                        </div>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}

            {/* ── OPPORTUNITIES TAB */}
            {tab === 'opportunities' && (
                <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                        <thead>
                            <tr style={{ background: 'var(--color-surface)' }}>
                                {['Name', 'Customer', 'Stage', 'Probability', 'Close Date', 'Value', 'Weighted', ''].map(h => (
                                    <th key={h} style={{ padding: '0.75rem 1rem', fontSize: 'var(--text-xs)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.04em', color: 'var(--color-text-muted)', textAlign: 'left', borderBottom: '2px solid var(--color-border)', whiteSpace: 'nowrap' }}>{h}</th>
                                ))}
                            </tr>
                        </thead>
                        <tbody>
                            {opps.length === 0 ? (
                                <tr><td colSpan={8} style={{ padding: '4rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>
                                    <Briefcase size={40} style={{ display: 'block', margin: '0 auto 0.75rem', opacity: 0.2 }} />
                                    <p style={{ margin: 0 }}>No opportunities yet. Add one or convert a lead.</p>
                                </td></tr>
                            ) : opps.map((opp: any) => {
                                const weighted = parseFloat(opp.expected_value || 0) * (opp.probability / 100);
                                return (
                                    <tr key={opp.id}
                                        style={{ borderBottom: '1px solid var(--color-border)', transition: 'background 0.12s' }}
                                        onMouseEnter={e => (e.currentTarget.style.background = 'var(--color-surface)')}
                                        onMouseLeave={e => (e.currentTarget.style.background = '')}>
                                        <td style={{ padding: '0.875rem 1rem', fontWeight: 600 }}>{opp.name}</td>
                                        <td style={{ padding: '0.875rem 1rem', fontSize: 'var(--text-sm)' }}>{opp.customer_name || '—'}</td>
                                        <td style={{ padding: '0.875rem 1rem' }}>
                                            <span style={{ padding: '0.2rem 0.6rem', borderRadius: '20px', fontSize: 'var(--text-xs)', fontWeight: 700, background: stageBg(opp.stage), color: stageColor(opp.stage), whiteSpace: 'nowrap' }}>
                                                {OPP_STAGES.find(s => s.value === opp.stage)?.label ?? opp.stage}
                                            </span>
                                        </td>
                                        <td style={{ padding: '0.875rem 1rem', fontWeight: 600 }}>{opp.probability}%</td>
                                        <td style={{ padding: '0.875rem 1rem', fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)' }}>{opp.expected_close_date || '—'}</td>
                                        <td style={{ padding: '0.875rem 1rem', fontWeight: 600, color: 'var(--color-primary)', whiteSpace: 'nowrap' }}>{formatCurrency(parseFloat(opp.expected_value || 0))}</td>
                                        <td style={{ padding: '0.875rem 1rem', fontWeight: 600, color: '#10b981', whiteSpace: 'nowrap' }}>{formatCurrency(weighted)}</td>
                                        <td style={{ padding: '0.875rem 1rem' }}>
                                            <div style={{ display: 'flex', gap: '0.375rem' }}>
                                                <button title="Edit" onClick={() => openEditOpp(opp)}
                                                    style={{ border: 'none', background: 'var(--color-surface)', borderRadius: '6px', padding: '0.35rem 0.5rem', cursor: 'pointer', color: 'var(--color-text-muted)', display: 'inline-flex' }}>
                                                    <Pencil size={13} />
                                                </button>
                                                <button title="Delete" onClick={() => setDeleteConfirm({ type: 'opp', id: opp.id, name: opp.name })}
                                                    style={{ border: 'none', background: 'rgba(239,68,68,0.08)', borderRadius: '6px', padding: '0.35rem 0.5rem', cursor: 'pointer', color: '#ef4444', display: 'inline-flex' }}>
                                                    <Trash2 size={13} />
                                                </button>
                                            </div>
                                        </td>
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                </div>
            )}

            {/* ── FORECAST / PIPELINE TAB */}
            {tab === 'forecast' && (
                <div>
                    {/* KPI strip */}
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1rem', marginBottom: '2rem' }}>
                        {[
                            { label: 'Total Pipeline Value',  value: formatCurrency(forecast?.total_value ?? 0),       color: 'var(--color-primary)', bg: 'rgba(59,130,246,0.1)' },
                            { label: 'Weighted Forecast',     value: formatCurrency(forecast?.weighted_forecast ?? 0),  color: '#10b981', bg: 'rgba(16,185,129,0.12)' },
                            { label: 'Active Opportunities',  value: forecast?.total_opportunities ?? opps.length,      color: '#f59e0b', bg: 'rgba(245,158,11,0.12)' },
                        ].map(({ label, value, color, bg }) => (
                            <div key={label} className="card" style={{ padding: '1.25rem 1.5rem' }}>
                                <div style={{ width: 38, height: 38, borderRadius: '10px', background: bg, display: 'flex', alignItems: 'center', justifyContent: 'center', color, marginBottom: '0.75rem' }}>
                                    <TrendingUp size={20} />
                                </div>
                                <div style={{ fontSize: 'var(--text-xs)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--color-text-muted)', marginBottom: '0.25rem' }}>{label}</div>
                                <div style={{ fontSize: '1.5rem', fontWeight: 700, color, lineHeight: 1 }}>{value}</div>
                            </div>
                        ))}
                    </div>

                    {/* Stage pipeline */}
                    <h3 style={{ fontSize: 'var(--text-base)', fontWeight: 700, marginBottom: '1rem', color: 'var(--color-text)' }}>Pipeline by Stage</h3>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1rem', marginBottom: '2rem' }}>
                        {activeStages.map(stage => {
                            const s = breakdown[stage.value] ?? {};
                            const count    = s.count ?? 0;
                            const value    = s.total_value ?? 0;
                            const weighted = s.weighted_value ?? 0;
                            return (
                                <div key={stage.value} className="card" style={{ padding: '1.25rem', borderTop: `3px solid ${stageColor(stage.value)}` }}>
                                    <div style={{ fontSize: 'var(--text-xs)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.04em', color: stageColor(stage.value), marginBottom: '0.5rem' }}>{stage.label}</div>
                                    <div style={{ fontSize: '1.4rem', fontWeight: 700, marginBottom: '0.25rem' }}>{count}</div>
                                    <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>Total: {formatCurrency(value)}</div>
                                    <div style={{ fontSize: 'var(--text-xs)', color: '#10b981', fontWeight: 600 }}>Weighted: {formatCurrency(weighted)}</div>
                                    <div style={{ marginTop: '0.75rem', height: '4px', background: 'var(--color-border)', borderRadius: '2px', overflow: 'hidden' }}>
                                        <div style={{ height: '100%', width: `${stage.probability}%`, background: stageColor(stage.value), borderRadius: '2px' }} />
                                    </div>
                                    <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', marginTop: '0.25rem' }}>{stage.probability}% probability</div>
                                </div>
                            );
                        })}
                    </div>

                    {/* Won / Lost summary */}
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                        {[{ value: 'Closed_Won', label: 'Closed Won', color: '#10b981', bg: 'rgba(16,185,129,0.1)' },
                          { value: 'Closed_Lost', label: 'Closed Lost', color: '#ef4444', bg: 'rgba(239,68,68,0.08)' }].map(stage => {
                            const s = breakdown[stage.value] ?? {};
                            return (
                                <div key={stage.value} className="card" style={{ padding: '1.25rem', borderLeft: `3px solid ${stage.color}` }}>
                                    <div style={{ fontSize: 'var(--text-sm)', fontWeight: 700, color: stage.color, marginBottom: '0.5rem' }}>{stage.label}</div>
                                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                                        <div><div style={{ fontSize: '1.25rem', fontWeight: 700 }}>{s.count ?? 0}</div><div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>deals</div></div>
                                        <div style={{ textAlign: 'right' }}><div style={{ fontSize: '1.1rem', fontWeight: 700, color: stage.color }}>{formatCurrency(s.total_value ?? 0)}</div><div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>total value</div></div>
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                </div>
            )}

            {/* ══ LEAD MODAL ══════════════════════════════════════════════════════ */}
            {modalMode === 'lead' && (
                <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000, padding: '1rem' }}>
                    <div className="card" style={{ width: '100%', maxWidth: '600px', padding: '2rem', maxHeight: '90vh', overflowY: 'auto' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
                            <h2 style={{ margin: 0, fontSize: '1.1rem', fontWeight: 700 }}>{isEditing ? 'Edit Lead' : 'Add Lead'}</h2>
                            <button onClick={() => setModalMode(null)} style={{ border: 'none', background: 'none', cursor: 'pointer', color: 'var(--color-text-muted)' }}><X size={20} /></button>
                        </div>
                        <form onSubmit={saveLead}>
                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                                <Field label="Name *"><input style={fieldStyle} value={leadForm.name} onChange={e => setLeadForm({ ...leadForm, name: e.target.value })} required /></Field>
                                <Field label="Company" half><input style={fieldStyle} value={leadForm.company} onChange={e => setLeadForm({ ...leadForm, company: e.target.value })} /></Field>
                                <Field label="Email" half><input type="email" style={fieldStyle} value={leadForm.email} onChange={e => setLeadForm({ ...leadForm, email: e.target.value })} /></Field>
                                <Field label="Phone" half><input style={fieldStyle} value={leadForm.phone} onChange={e => setLeadForm({ ...leadForm, phone: e.target.value })} /></Field>
                                <Field label="Source" half>
                                    <select style={fieldStyle} value={leadForm.source} onChange={e => setLeadForm({ ...leadForm, source: e.target.value })}>
                                        <option value="">Select Source</option>
                                        {LEAD_SOURCES.map(s => <option key={s} value={s}>{s}</option>)}
                                    </select>
                                </Field>
                                <Field label="Status" half>
                                    <select style={fieldStyle} value={leadForm.status} onChange={e => setLeadForm({ ...leadForm, status: e.target.value })}>
                                        {LEAD_STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
                                    </select>
                                </Field>
                                <Field label="Estimated Value" half>
                                    <input type="number" style={fieldStyle} value={leadForm.estimated_value} onChange={e => setLeadForm({ ...leadForm, estimated_value: e.target.value })} min="0" step="0.01" />
                                </Field>
                                <Field label="Notes">
                                    <textarea style={{ ...fieldStyle, resize: 'vertical', minHeight: '80px' }} value={leadForm.notes} onChange={e => setLeadForm({ ...leadForm, notes: e.target.value })} />
                                </Field>
                            </div>
                            {error && <p style={{ color: 'var(--color-error)', fontSize: 'var(--text-sm)', margin: '1rem 0 0' }}>{error}</p>}
                            <div style={{ display: 'flex', gap: '0.75rem', marginTop: '1.5rem' }}>
                                <button type="button" className="btn btn-outline" onClick={() => setModalMode(null)} style={{ flex: 1 }}>Cancel</button>
                                <button type="submit" className="btn btn-primary" disabled={saving} style={{ flex: 1 }}>{saving ? 'Saving…' : isEditing ? 'Save Changes' : 'Add Lead'}</button>
                            </div>
                        </form>
                    </div>
                </div>
            )}

            {/* ══ OPPORTUNITY MODAL ═══════════════════════════════════════════════ */}
            {modalMode === 'opp' && (
                <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000, padding: '1rem' }}>
                    <div className="card" style={{ width: '100%', maxWidth: '600px', padding: '2rem', maxHeight: '90vh', overflowY: 'auto' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
                            <h2 style={{ margin: 0, fontSize: '1.1rem', fontWeight: 700 }}>{isEditing ? 'Edit Opportunity' : 'Add Opportunity'}</h2>
                            <button onClick={() => setModalMode(null)} style={{ border: 'none', background: 'none', cursor: 'pointer', color: 'var(--color-text-muted)' }}><X size={20} /></button>
                        </div>
                        <form onSubmit={saveOpp}>
                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                                <Field label="Opportunity Name *">
                                    <input style={fieldStyle} value={oppForm.name} onChange={e => setOppForm({ ...oppForm, name: e.target.value })} required />
                                </Field>
                                <Field label="Customer *" half>
                                    <select style={fieldStyle} value={oppForm.customer} onChange={e => setOppForm({ ...oppForm, customer: e.target.value })} required>
                                        <option value="">Select Customer</option>
                                        {customers.map((c: any) => <option key={c.id} value={c.id}>{c.name}</option>)}
                                    </select>
                                </Field>
                                <Field label="From Lead" half>
                                    <select style={fieldStyle} value={oppForm.lead} onChange={e => setOppForm({ ...oppForm, lead: e.target.value })}>
                                        <option value="">None</option>
                                        {leads.map((l: any) => <option key={l.id} value={l.id}>{l.name}</option>)}
                                    </select>
                                </Field>
                                <Field label="Stage" half>
                                    <select style={fieldStyle} value={oppForm.stage} onChange={e => {
                                        const found = OPP_STAGES.find(s => s.value === e.target.value);
                                        setOppForm({ ...oppForm, stage: e.target.value, probability: found?.probability ?? oppForm.probability });
                                    }}>
                                        {OPP_STAGES.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
                                    </select>
                                </Field>
                                <Field label="Probability (%)" half>
                                    <input type="number" style={fieldStyle} value={oppForm.probability} onChange={e => setOppForm({ ...oppForm, probability: Number(e.target.value) })} min="0" max="100" />
                                </Field>
                                <Field label="Expected Value" half>
                                    <input type="number" style={fieldStyle} value={oppForm.expected_value} onChange={e => setOppForm({ ...oppForm, expected_value: e.target.value })} min="0" step="0.01" />
                                </Field>
                                <Field label="Expected Close Date" half>
                                    <input type="date" style={fieldStyle} value={oppForm.expected_close_date} onChange={e => setOppForm({ ...oppForm, expected_close_date: e.target.value })} />
                                </Field>
                                <Field label="Notes">
                                    <textarea style={{ ...fieldStyle, resize: 'vertical', minHeight: '80px' }} value={oppForm.notes} onChange={e => setOppForm({ ...oppForm, notes: e.target.value })} />
                                </Field>
                            </div>
                            {error && <p style={{ color: 'var(--color-error)', fontSize: 'var(--text-sm)', margin: '1rem 0 0' }}>{error}</p>}
                            <div style={{ display: 'flex', gap: '0.75rem', marginTop: '1.5rem' }}>
                                <button type="button" className="btn btn-outline" onClick={() => setModalMode(null)} style={{ flex: 1 }}>Cancel</button>
                                <button type="submit" className="btn btn-primary" disabled={saving} style={{ flex: 1 }}>{saving ? 'Saving…' : isEditing ? 'Save Changes' : 'Add Opportunity'}</button>
                            </div>
                        </form>
                    </div>
                </div>
            )}

            {/* ══ DELETE CONFIRM ══════════════════════════════════════════════════ */}
            {deleteConfirm && (
                <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1001 }}>
                    <div className="card" style={{ padding: '2rem', maxWidth: '400px', width: '100%', textAlign: 'center' }}>
                        <Trash2 size={36} style={{ color: '#ef4444', marginBottom: '1rem' }} />
                        <h3 style={{ margin: '0 0 0.5rem' }}>Delete {deleteConfirm.type === 'lead' ? 'Lead' : 'Opportunity'}?</h3>
                        <p style={{ color: 'var(--color-text-muted)', margin: '0 0 1.5rem', fontSize: 'var(--text-sm)' }}>
                            "<strong>{deleteConfirm.name}</strong>" will be permanently deleted.
                        </p>
                        <div style={{ display: 'flex', gap: '0.75rem' }}>
                            <button className="btn btn-outline" onClick={() => setDeleteConfirm(null)} style={{ flex: 1 }}>Cancel</button>
                            <button className="btn" onClick={confirmDelete}
                                disabled={deleteLead.isPending || deleteOpp.isPending}
                                style={{ flex: 1, background: '#ef4444', color: '#fff', border: 'none', opacity: (deleteLead.isPending || deleteOpp.isPending) ? 0.6 : 1 }}>
                                {(deleteLead.isPending || deleteOpp.isPending) ? 'Deleting…' : 'Delete'}
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </SalesLayout>
    );
};

export default CRMLite;
