import { useState } from 'react';
import { useDialog } from '../../hooks/useDialog';
import { useServiceTickets, useResolveTicket, useAssignTechnician, useServiceDashboard, useTechnicians, useServiceAssets } from './hooks/useService';
import ServiceLayout from './ServiceLayout';
import LoadingScreen from '../../components/common/LoadingScreen';
import { Wrench, CheckCircle, UserCog, AlertTriangle } from 'lucide-react';
import type { ServiceTicket, Technician } from './types';

const ServiceDashboard = () => {
    const { showConfirm } = useDialog();
    const { data: dashboard } = useServiceDashboard();
    const { data: tickets, isLoading } = useServiceTickets();
    const { data: technicians } = useTechnicians();
    const { data: assets } = useServiceAssets();
    const resolveTicket = useResolveTicket();
    const assignTechnician = useAssignTechnician();
    const [selectedTicket, setSelectedTicket] = useState<number | null>(null);

    const ticketsList = tickets?.results || tickets || [];
    
    const openTickets = Array.isArray(ticketsList) ? ticketsList.filter((t: ServiceTicket) => t.status === 'Open') : [];
    const criticalTickets = Array.isArray(ticketsList) ? ticketsList.filter((t: ServiceTicket) => t.priority === 'Critical' && t.status !== 'Closed') : [];

    const priorityColor = (p: string) => {
        switch (p) {
            case 'Critical': return 'var(--color-error)';
            case 'High': return 'var(--color-cta)';
            case 'Medium': return 'var(--color-primary)';
            default: return 'var(--color-text-muted)';
        }
    };

    const statusColor = (s: string) => {
        switch (s) {
            case 'Open': return 'rgba(36, 113, 163, 0.15)';
            case 'In Progress': return 'rgba(251, 191, 36, 0.15)';
            case 'Resolved': return 'rgba(34, 197, 94, 0.15)';
            case 'Closed': return 'rgba(156, 163, 175, 0.15)';
            default: return 'rgba(156, 163, 175, 0.15)';
        }
    };

    const handleResolve = async (id: number) => {
        if (await showConfirm('Mark this ticket as resolved?')) {
            resolveTicket.mutate(id);
        }
    };

    const handleAssign = (ticketId: number, technicianId: number) => {
        assignTechnician.mutate({ id: ticketId, technician_id: technicianId });
        setSelectedTicket(null);
    };

    if (isLoading) {
        return <LoadingScreen message="Loading service dashboard..." />;
    }

    return (
        <ServiceLayout>
            <div style={{ padding: '1.5rem' }}>
                <div style={{ marginBottom: '1.5rem' }}>
                    <h1 style={{ fontSize: 'var(--text-xl)', fontWeight: 700, color: 'var(--color-text)', margin: 0 }}>
                        Service Helpdesk
                    </h1>
                    <p style={{ color: 'var(--color-text-muted)', margin: '0.25rem 0 0 0', fontSize: 'var(--text-sm)' }}>
                        Manage maintenance requests and track resolution SLAs
                    </p>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem', marginBottom: '1.5rem' }}>
                    <div style={{ background: 'var(--color-surface)', borderRadius: '12px', border: '1px solid var(--color-border)', padding: '1.25rem' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                            <div style={{ padding: '0.5rem', background: 'rgba(36, 113, 163, 0.1)', borderRadius: '8px' }}>
                                <Wrench size={20} style={{ color: '#2471a3' }} />
                            </div>
                            <div>
                                <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', margin: 0 }}>Open Tickets</p>
                                <p style={{ fontSize: 'var(--text-xl)', fontWeight: 700, margin: 0, color: 'var(--color-text)' }}>{dashboard?.open_tickets || openTickets.length || 0}</p>
                            </div>
                        </div>
                    </div>
                    
                    <div style={{ background: 'var(--color-surface)', borderRadius: '12px', border: '1px solid var(--color-border)', padding: '1.25rem' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                            <div style={{ padding: '0.5rem', background: 'rgba(239, 68, 68, 0.1)', borderRadius: '8px' }}>
                                <AlertTriangle size={20} style={{ color: '#ef4444' }} />
                            </div>
                            <div>
                                <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', margin: 0 }}>Critical</p>
                                <p style={{ fontSize: 'var(--text-xl)', fontWeight: 700, margin: 0, color: '#ef4444' }}>{criticalTickets.length || 0}</p>
                            </div>
                        </div>
                    </div>

                    <div style={{ background: 'var(--color-surface)', borderRadius: '12px', border: '1px solid var(--color-border)', padding: '1.25rem' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                            <div style={{ padding: '0.5rem', background: 'rgba(34, 197, 94, 0.1)', borderRadius: '8px' }}>
                                <CheckCircle size={20} style={{ color: '#22c55e' }} />
                            </div>
                            <div>
                                <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', margin: 0 }}>Resolved</p>
                                <p style={{ fontSize: 'var(--text-xl)', fontWeight: 700, margin: 0, color: 'var(--color-text)' }}>{dashboard?.resolved_tickets || 0}</p>
                            </div>
                        </div>
                    </div>

                    <div style={{ background: 'var(--color-surface)', borderRadius: '12px', border: '1px solid var(--color-border)', padding: '1.25rem' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                            <div style={{ padding: '0.5rem', background: 'rgba(236, 72, 153, 0.1)', borderRadius: '8px' }}>
                                <UserCog size={20} style={{ color: '#ec4899' }} />
                            </div>
                            <div>
                                <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', margin: 0 }}>Technicians</p>
                                <p style={{ fontSize: 'var(--text-xl)', fontWeight: 700, margin: 0, color: 'var(--color-text)' }}>{dashboard?.technicians_available || 0}</p>
                            </div>
                        </div>
                    </div>
                </div>

                <div style={{ background: 'var(--color-surface)', borderRadius: '12px', border: '1px solid var(--color-border)', overflow: 'hidden' }}>
                    <div style={{ padding: '1rem 1.25rem', borderBottom: '1px solid var(--color-border)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <h2 style={{ fontSize: 'var(--text-base)', fontWeight: 600, margin: 0, color: 'var(--color-text)' }}>Recent Tickets</h2>
                        <a href="/service/tickets" style={{ color: 'var(--color-primary)', fontSize: 'var(--text-sm)', textDecoration: 'none' }}>View All</a>
                    </div>
                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                        <thead>
                            <tr style={{ borderBottom: '1px solid var(--color-border)' }}>
                                <th style={{ padding: '0.75rem 1rem', textAlign: 'left', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)' }}>Ticket</th>
                                <th style={{ padding: '0.75rem 1rem', textAlign: 'left', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)' }}>Subject</th>
                                <th style={{ padding: '0.75rem 1rem', textAlign: 'left', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)' }}>Asset</th>
                                <th style={{ padding: '0.75rem 1rem', textAlign: 'center', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)' }}>Priority</th>
                                <th style={{ padding: '0.75rem 1rem', textAlign: 'center', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)' }}>Status</th>
                                <th style={{ padding: '0.75rem 1rem', textAlign: 'right', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)' }}>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {openTickets.length === 0 ? (
                                <tr>
                                    <td colSpan={6} style={{ padding: '3rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>
                                        <Wrench size={48} style={{ margin: '0 auto 1rem', opacity: 0.5 }} />
                                        <p>No open tickets</p>
                                    </td>
                                </tr>
                            ) : (
                                openTickets.slice(0, 10).map((ticket: ServiceTicket) => (
                                    <tr key={ticket.id} style={{ borderBottom: '1px solid var(--color-border)' }}>
                                        <td style={{ padding: '0.75rem 1rem', fontWeight: 600, fontSize: 'var(--text-sm)' }}>{ticket.ticket_number}</td>
                                        <td style={{ padding: '0.75rem 1rem', maxWidth: '250px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{ticket.subject}</td>
                                        <td style={{ padding: '0.75rem 1rem', fontSize: 'var(--text-sm)' }}>{ticket.asset_name || '-'}</td>
                                        <td style={{ padding: '0.75rem 1rem', textAlign: 'center' }}>
                                            <span style={{
                                                padding: '0.25rem 0.5rem',
                                                borderRadius: '4px',
                                                fontSize: 'var(--text-xs)',
                                                fontWeight: 600,
                                                background: `${priorityColor(ticket.priority)}20`,
                                                color: priorityColor(ticket.priority),
                                            }}>
                                                {ticket.priority}
                                            </span>
                                        </td>
                                        <td style={{ padding: '0.75rem 1rem', textAlign: 'center' }}>
                                            <span style={{
                                                padding: '0.25rem 0.5rem',
                                                borderRadius: '4px',
                                                fontSize: 'var(--text-xs)',
                                                fontWeight: 600,
                                                background: statusColor(ticket.status),
                                                color: ticket.status === 'Open' ? '#2471a3' : ticket.status === 'Resolved' ? '#22c55e' : 'var(--color-text-muted)',
                                            }}>
                                                {ticket.status}
                                            </span>
                                        </td>
                                        <td style={{ padding: '0.75rem 1rem', textAlign: 'right' }}>
                                            {ticket.status === 'Open' && (
                                                <>
                                                    {ticket.technician ? (
                                                        <button
                                                            onClick={() => handleResolve(ticket.id)}
                                                            style={{
                                                                padding: '0.375rem 0.75rem',
                                                                background: 'rgba(34, 197, 94, 0.1)',
                                                                color: '#22c55e',
                                                                border: 'none',
                                                                borderRadius: '6px',
                                                                fontSize: 'var(--text-xs)',
                                                                fontWeight: 600,
                                                                cursor: 'pointer',
                                                                display: 'inline-flex',
                                                                alignItems: 'center',
                                                                gap: '0.25rem',
                                                            }}
                                                        >
                                                            <CheckCircle size={14} />
                                                            Resolve
                                                        </button>
                                                    ) : (
                                                        <button
                                                            onClick={() => setSelectedTicket(ticket.id)}
                                                            style={{
                                                                padding: '0.375rem 0.75rem',
                                                                background: 'rgba(36, 113, 163, 0.1)',
                                                                color: '#2471a3',
                                                                border: 'none',
                                                                borderRadius: '6px',
                                                                fontSize: 'var(--text-xs)',
                                                                fontWeight: 600,
                                                                cursor: 'pointer',
                                                            }}
                                                        >
                                                            Assign
                                                        </button>
                                                    )}
                                                </>
                                            )}
                                        </td>
                                    </tr>
                                ))
                            )}
                        </tbody>
                    </table>
                </div>

                {selectedTicket && (
                    <div style={{
                        position: 'fixed',
                        top: 0,
                        left: 0,
                        right: 0,
                        bottom: 0,
                        background: 'rgba(0,0,0,0.5)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        zIndex: 1000,
                    }} onClick={() => setSelectedTicket(null)}>
                        <div style={{
                            background: 'var(--color-surface)',
                            borderRadius: '12px',
                            padding: '1.5rem',
                            maxWidth: '400px',
                            width: '100%',
                        }} onClick={e => e.stopPropagation()}>
                            <h3 style={{ margin: '0 0 1rem 0', fontSize: 'var(--text-lg)' }}>Assign Technician</h3>
                            <div style={{ maxHeight: '300px', overflowY: 'auto' }}>
                                {technicians?.results?.map((tech: Technician) => (
                                    <button
                                        key={tech.id}
                                        onClick={() => handleAssign(selectedTicket, tech.id)}
                                        style={{
                                            width: '100%',
                                            padding: '0.75rem 1rem',
                                            marginBottom: '0.5rem',
                                            background: 'var(--color-surface)',
                                            border: '1px solid var(--color-border)',
                                            borderRadius: '8px',
                                            textAlign: 'left',
                                            cursor: 'pointer',
                                            display: 'flex',
                                            justifyContent: 'space-between',
                                            alignItems: 'center',
                                        }}
                                    >
                                        <div>
                                            <p style={{ margin: 0, fontWeight: 600, fontSize: 'var(--text-sm)' }}>{tech.name}</p>
                                            <p style={{ margin: 0, fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>{tech.specialization || 'General'}</p>
                                        </div>
                                        <span style={{
                                            padding: '0.25rem 0.5rem',
                                            borderRadius: '4px',
                                            fontSize: 'var(--text-xs)',
                                            background: tech.is_available ? 'rgba(34, 197, 94, 0.1)' : 'rgba(239, 68, 68, 0.1)',
                                            color: tech.is_available ? '#22c55e' : '#ef4444',
                                        }}>
                                            {tech.is_available ? 'Available' : 'Busy'}
                                        </span>
                                    </button>
                                ))}
                            </div>
                            <button
                                onClick={() => setSelectedTicket(null)}
                                style={{
                                    width: '100%',
                                    padding: '0.75rem',
                                    marginTop: '1rem',
                                    background: 'transparent',
                                    border: '1px solid var(--color-border)',
                                    borderRadius: '8px',
                                    color: 'var(--color-text)',
                                    cursor: 'pointer',
                                }}
                            >
                                Cancel
                            </button>
                        </div>
                    </div>
                )}
            </div>
        </ServiceLayout>
    );
};

export default ServiceDashboard;
