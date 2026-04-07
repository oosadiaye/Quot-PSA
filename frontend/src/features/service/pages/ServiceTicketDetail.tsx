import { useParams, useNavigate } from 'react-router-dom';
import { useState } from 'react';
import { useDialog } from '../../../hooks/useDialog';
import { ArrowLeft, CheckCircle, Clock, Shield, User, AlertTriangle } from 'lucide-react';
import { useServiceTicket, useResolveTicket, useAssignTechnician, useTechnicians } from '../hooks/useService';
import ServiceLayout from '../ServiceLayout';
import LoadingScreen from '../../../components/common/LoadingScreen';
import type { ServiceTicket, Technician } from '../types';

const priorityColor = (p: string) => {
    switch (p) {
        case 'Critical': return '#ef4444';
        case 'High': return '#f97316';
        case 'Medium': return '#2471a3';
        default: return '#9ca3af';
    }
};

const statusColor = (s: string) => {
    switch (s) {
        case 'Open': return '#2471a3';
        case 'In Progress': return '#fbbf24';
        case 'Resolved': return '#22c55e';
        case 'Closed': return '#9ca3af';
        default: return '#9ca3af';
    }
};

const formatDate = (d: string | null) => {
    if (!d) return '-';
    return new Date(d).toLocaleString();
};

const formatMinutes = (minutes: number) => {
    if (minutes < 60) return `${minutes}m`;
    const h = Math.floor(minutes / 60);
    const m = minutes % 60;
    return m > 0 ? `${h}h ${m}m` : `${h}h`;
};

export default function ServiceTicketDetail() {
    const { id } = useParams<{ id: string }>();
    const navigate = useNavigate();
    const { showConfirm } = useDialog();
    const { data: ticket, isLoading } = useServiceTicket(id || '');
    const { data: technicians } = useTechnicians();
    const resolveTicket = useResolveTicket();
    const assignTechnician = useAssignTechnician();
    const [assignId, setAssignId] = useState('');

    const techsList = (technicians?.results || technicians || []) as Technician[];

    const handleResolve = async () => {
        if (ticket && await showConfirm('Mark this ticket as resolved?')) {
            resolveTicket.mutate(ticket.id);
        }
    };

    const handleAssign = () => {
        if (ticket && assignId) {
            assignTechnician.mutate({ id: ticket.id, technician_id: parseInt(assignId) });
            setAssignId('');
        }
    };

    if (isLoading) return <LoadingScreen message="Loading ticket..." />;
    if (!ticket) return (
        <ServiceLayout>
            <div style={{ padding: '3rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>
                Ticket not found.
            </div>
        </ServiceLayout>
    );

    const t = ticket as ServiceTicket;
    const sla = t.sla;

    return (
        <ServiceLayout>
            <div style={{ padding: '1.5rem', maxWidth: '960px' }}>
                {/* Header */}
                <button
                    onClick={() => navigate('/service/tickets')}
                    style={{
                        display: 'flex', alignItems: 'center', gap: '0.4rem',
                        background: 'none', border: 'none', color: 'var(--color-primary)',
                        cursor: 'pointer', padding: 0, fontSize: 'var(--text-sm)', marginBottom: '1.25rem',
                    }}
                >
                    <ArrowLeft size={16} /> Back to Tickets
                </button>

                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1.5rem' }}>
                    <div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.5rem' }}>
                            <span style={{ fontFamily: 'monospace', fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>{t.ticket_number}</span>
                            <span style={{
                                padding: '0.2rem 0.6rem', borderRadius: '4px', fontSize: 'var(--text-xs)', fontWeight: 600,
                                background: `${statusColor(t.status)}20`, color: statusColor(t.status),
                            }}>{t.status}</span>
                            <span style={{
                                padding: '0.2rem 0.6rem', borderRadius: '4px', fontSize: 'var(--text-xs)', fontWeight: 600,
                                background: `${priorityColor(t.priority)}20`, color: priorityColor(t.priority),
                            }}>{t.priority}</span>
                        </div>
                        <h1 style={{ fontSize: 'var(--text-xl)', fontWeight: 700, color: 'var(--color-text)', margin: 0 }}>{t.subject}</h1>
                    </div>
                    {t.status !== 'Resolved' && t.status !== 'Closed' && (
                        <button
                            onClick={handleResolve}
                            style={{
                                display: 'flex', alignItems: 'center', gap: '0.4rem',
                                padding: '0.5rem 1rem', background: 'rgba(34, 197, 94, 0.1)',
                                color: '#22c55e', border: 'none', borderRadius: '8px',
                                fontWeight: 600, cursor: 'pointer', fontSize: 'var(--text-sm)',
                            }}
                        >
                            <CheckCircle size={16} /> Resolve
                        </button>
                    )}
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px', gap: '1.5rem' }}>
                    {/* Left column: details */}
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
                        {/* Description */}
                        <div style={{
                            background: 'var(--color-surface)', border: '1px solid var(--color-border)',
                            borderRadius: '12px', padding: '1.25rem',
                        }}>
                            <h3 style={{ fontSize: 'var(--text-sm)', fontWeight: 600, marginBottom: '0.75rem', color: 'var(--color-text)' }}>Description</h3>
                            <p style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)', margin: 0, lineHeight: 1.6, whiteSpace: 'pre-wrap' }}>
                                {t.description}
                            </p>
                        </div>

                        {/* Timeline */}
                        <div style={{
                            background: 'var(--color-surface)', border: '1px solid var(--color-border)',
                            borderRadius: '12px', padding: '1.25rem',
                        }}>
                            <h3 style={{ fontSize: 'var(--text-sm)', fontWeight: 600, marginBottom: '1rem', color: 'var(--color-text)', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                                <Clock size={16} /> Timeline
                            </h3>
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                                {[
                                    { label: 'Created', value: t.created_at, active: true },
                                    { label: 'Started', value: t.started_at, active: !!t.started_at },
                                    { label: 'Resolved', value: t.resolved_at, active: !!t.resolved_at },
                                ].map((step, i) => (
                                    <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                                        <div style={{
                                            width: '8px', height: '8px', borderRadius: '50%',
                                            background: step.active ? 'var(--color-primary)' : 'var(--color-border)',
                                        }} />
                                        <span style={{ fontSize: 'var(--text-xs)', fontWeight: 500, color: 'var(--color-text)', minWidth: '70px' }}>{step.label}</span>
                                        <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>{formatDate(step.value)}</span>
                                    </div>
                                ))}
                            </div>
                        </div>

                        {/* SLA Panel */}
                        {sla && (
                            <div style={{
                                background: 'var(--color-surface)', border: '1px solid var(--color-border)',
                                borderRadius: '12px', padding: '1.25rem',
                            }}>
                                <h3 style={{ fontSize: 'var(--text-sm)', fontWeight: 600, marginBottom: '1rem', color: 'var(--color-text)', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                                    <Shield size={16} /> SLA Tracking
                                </h3>
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                                    <div style={{
                                        padding: '1rem', borderRadius: '8px',
                                        background: sla.is_response_met ? 'rgba(34,197,94,0.08)' : sla.first_response_at ? 'rgba(239,68,68,0.08)' : 'rgba(59,130,246,0.05)',
                                        border: `1px solid ${sla.is_response_met ? 'rgba(34,197,94,0.2)' : sla.first_response_at ? 'rgba(239,68,68,0.2)' : 'var(--color-border)'}`,
                                    }}>
                                        <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', marginBottom: '0.25rem' }}>Response SLA</div>
                                        <div style={{ fontSize: 'var(--text-base)', fontWeight: 700, color: 'var(--color-text)' }}>
                                            {formatMinutes(sla.response_time_limit)}
                                        </div>
                                        <div style={{ fontSize: 'var(--text-xs)', marginTop: '0.25rem', display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                                            {sla.first_response_at ? (
                                                sla.is_response_met ? (
                                                    <span style={{ color: '#22c55e' }}><CheckCircle size={12} style={{ verticalAlign: 'middle' }} /> Met</span>
                                                ) : (
                                                    <span style={{ color: '#ef4444' }}><AlertTriangle size={12} style={{ verticalAlign: 'middle' }} /> Breached</span>
                                                )
                                            ) : (
                                                <span style={{ color: 'var(--color-text-muted)' }}>Waiting</span>
                                            )}
                                        </div>
                                    </div>
                                    <div style={{
                                        padding: '1rem', borderRadius: '8px',
                                        background: sla.is_resolution_met ? 'rgba(34,197,94,0.08)' : t.resolved_at ? 'rgba(239,68,68,0.08)' : 'rgba(59,130,246,0.05)',
                                        border: `1px solid ${sla.is_resolution_met ? 'rgba(34,197,94,0.2)' : t.resolved_at ? 'rgba(239,68,68,0.2)' : 'var(--color-border)'}`,
                                    }}>
                                        <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', marginBottom: '0.25rem' }}>Resolution SLA</div>
                                        <div style={{ fontSize: 'var(--text-base)', fontWeight: 700, color: 'var(--color-text)' }}>
                                            {formatMinutes(sla.resolution_time_limit)}
                                        </div>
                                        <div style={{ fontSize: 'var(--text-xs)', marginTop: '0.25rem', display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                                            {t.resolved_at ? (
                                                sla.is_resolution_met ? (
                                                    <span style={{ color: '#22c55e' }}><CheckCircle size={12} style={{ verticalAlign: 'middle' }} /> Met</span>
                                                ) : (
                                                    <span style={{ color: '#ef4444' }}><AlertTriangle size={12} style={{ verticalAlign: 'middle' }} /> Breached</span>
                                                )
                                            ) : (
                                                <span style={{ color: 'var(--color-text-muted)' }}>Waiting</span>
                                            )}
                                        </div>
                                    </div>
                                </div>
                                {sla.first_response_at && (
                                    <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', marginTop: '0.75rem' }}>
                                        First response: {formatDate(sla.first_response_at)}
                                    </div>
                                )}
                            </div>
                        )}
                    </div>

                    {/* Right column: details sidebar */}
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
                        {/* Info card */}
                        <div style={{
                            background: 'var(--color-surface)', border: '1px solid var(--color-border)',
                            borderRadius: '12px', padding: '1.25rem',
                        }}>
                            <h3 style={{ fontSize: 'var(--text-sm)', fontWeight: 600, marginBottom: '1rem', color: 'var(--color-text)' }}>Details</h3>
                            {[
                                { label: 'Asset', value: t.asset_name || '-' },
                                { label: 'Serial', value: t.asset_serial || '-' },
                                { label: 'Due Date', value: t.due_date ? new Date(t.due_date).toLocaleDateString() : '-' },
                            ].map((item, i) => (
                                <div key={i} style={{ display: 'flex', justifyContent: 'space-between', padding: '0.5rem 0', borderBottom: '1px solid var(--color-border)', fontSize: 'var(--text-xs)' }}>
                                    <span style={{ color: 'var(--color-text-muted)' }}>{item.label}</span>
                                    <span style={{ color: 'var(--color-text)', fontWeight: 500 }}>{item.value}</span>
                                </div>
                            ))}
                        </div>

                        {/* Technician */}
                        <div style={{
                            background: 'var(--color-surface)', border: '1px solid var(--color-border)',
                            borderRadius: '12px', padding: '1.25rem',
                        }}>
                            <h3 style={{ fontSize: 'var(--text-sm)', fontWeight: 600, marginBottom: '0.75rem', color: 'var(--color-text)', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                                <User size={16} /> Assigned Technician
                            </h3>
                            {t.technician_name ? (
                                <div style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text)', fontWeight: 500 }}>
                                    {t.technician_name}
                                </div>
                            ) : (
                                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>Unassigned</div>
                            )}
                            {t.status !== 'Resolved' && t.status !== 'Closed' && (
                                <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.75rem' }}>
                                    <select
                                        value={assignId}
                                        onChange={(e) => setAssignId(e.target.value)}
                                        style={{
                                            flex: 1, padding: '0.5rem', fontSize: 'var(--text-xs)',
                                            border: '1px solid var(--color-border)', borderRadius: '6px',
                                            background: 'var(--color-surface)', color: 'var(--color-text)',
                                        }}
                                    >
                                        <option value="">{t.technician_name ? 'Reassign...' : 'Assign...'}</option>
                                        {techsList.filter((tech) => tech.is_available).map((tech) => (
                                            <option key={tech.id} value={tech.id}>{tech.name}</option>
                                        ))}
                                    </select>
                                    <button
                                        onClick={handleAssign}
                                        disabled={!assignId}
                                        style={{
                                            padding: '0.5rem 0.75rem', fontSize: 'var(--text-xs)', fontWeight: 600,
                                            background: assignId ? 'var(--color-primary)' : 'var(--color-border)',
                                            color: assignId ? 'white' : 'var(--color-text-muted)',
                                            border: 'none', borderRadius: '6px', cursor: assignId ? 'pointer' : 'default',
                                        }}
                                    >
                                        Assign
                                    </button>
                                </div>
                            )}
                        </div>
                    </div>
                </div>
            </div>
        </ServiceLayout>
    );
}
