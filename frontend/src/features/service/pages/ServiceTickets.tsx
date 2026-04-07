import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useDialog } from '../../../hooks/useDialog';
import { Plus, Search, Ticket, CheckCircle, Clock, UserCog } from 'lucide-react';
import { useServiceTickets, useCreateTicket, useResolveTicket, useAssignTechnician, useTechnicians, useServiceAssets } from '../hooks/useService';
import ServiceLayout from '../ServiceLayout';
import LoadingScreen from '../../../components/common/LoadingScreen';
import type { ServiceTicket, Technician, ServiceAsset } from '../types';

export default function ServiceTickets() {
    const navigate = useNavigate();
    const { showConfirm } = useDialog();
    const [searchTerm, setSearchTerm] = useState('');
    const [statusFilter, setStatusFilter] = useState('');
    const [priorityFilter, setPriorityFilter] = useState('');
    const [showModal, setShowModal] = useState(false);

    const { data: tickets, isLoading } = useServiceTickets({ status: statusFilter, priority: priorityFilter });
    const { data: technicians } = useTechnicians();
    const { data: assets } = useServiceAssets();
    const createTicket = useCreateTicket();
    const resolveTicket = useResolveTicket();
    const assignTechnician = useAssignTechnician();

    const ticketsList = (tickets?.results || tickets || []) as ServiceTicket[];
    const techsList = (technicians?.results || technicians || []) as Technician[];
    const assetsList = (assets?.results || assets || []) as ServiceAsset[];

    const filteredTickets = Array.isArray(ticketsList) ? ticketsList.filter((t: ServiceTicket) => {
        const matchesSearch = t.ticket_number?.toLowerCase().includes(searchTerm.toLowerCase()) ||
            t.subject?.toLowerCase().includes(searchTerm.toLowerCase());
        return matchesSearch;
    }) : [];

    const [formData, setFormData] = useState({
        subject: '',
        description: '',
        priority: 'Medium',
        asset: '',
    });

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        createTicket.mutate(formData, {
            onSuccess: () => {
                setShowModal(false);
                setFormData({ subject: '', description: '', priority: 'Medium', asset: '' });
            }
        });
    };

    const handleResolve = async (id: number) => {
        if (await showConfirm('Mark this ticket as resolved?')) {
            resolveTicket.mutate(id);
        }
    };

    const handleAssign = (ticketId: number, techId: number) => {
        assignTechnician.mutate({ id: ticketId, technician_id: techId });
    };

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

    if (isLoading) return <LoadingScreen message="Loading tickets..." />;

    return (
        <ServiceLayout>
            <div style={{ padding: '1.5rem' }}>
                <div style={{ marginBottom: '1.5rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div>
                        <h1 style={{ fontSize: 'var(--text-xl)', fontWeight: 700, color: 'var(--color-text)', margin: 0 }}>
                            Service Tickets
                        </h1>
                        <p style={{ color: 'var(--color-text-muted)', margin: '0.25rem 0 0 0', fontSize: 'var(--text-sm)' }}>
                            Manage maintenance and service requests
                        </p>
                    </div>
                    <button
                        onClick={() => setShowModal(true)}
                        style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: '0.5rem',
                            padding: '0.625rem 1.25rem',
                            background: 'var(--color-primary)',
                            color: 'white',
                            border: 'none',
                            borderRadius: '8px',
                            fontWeight: 600,
                            cursor: 'pointer',
                        }}
                    >
                        <Plus size={18} />
                        Create Ticket
                    </button>
                </div>

                <div style={{ display: 'flex', gap: '1rem', marginBottom: '1.5rem', flexWrap: 'wrap' }}>
                    <div style={{ flex: 1, minWidth: '200px', position: 'relative' }}>
                        <Search size={18} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: 'var(--color-text-muted)' }} />
                        <input
                            type="text"
                            placeholder="Search tickets..."
                            value={searchTerm}
                            onChange={(e) => setSearchTerm(e.target.value)}
                            style={{
                                width: '100%',
                                padding: '0.625rem 0.75rem 0.625rem 2.5rem',
                                border: '1px solid var(--color-border)',
                                borderRadius: '8px',
                                background: 'var(--color-surface)',
                                color: 'var(--color-text)',
                                fontSize: 'var(--text-sm)',
                            }}
                        />
                    </div>
                    <select
                        value={statusFilter}
                        onChange={(e) => setStatusFilter(e.target.value)}
                        style={{
                            padding: '0.625rem 1rem',
                            border: '1px solid var(--color-border)',
                            borderRadius: '8px',
                            background: 'var(--color-surface)',
                            color: 'var(--color-text)',
                            fontSize: 'var(--text-sm)',
                            minWidth: '130px',
                        }}
                    >
                        <option value="">All Status</option>
                        <option value="Open">Open</option>
                        <option value="In Progress">In Progress</option>
                        <option value="Resolved">Resolved</option>
                        <option value="Closed">Closed</option>
                    </select>
                    <select
                        value={priorityFilter}
                        onChange={(e) => setPriorityFilter(e.target.value)}
                        style={{
                            padding: '0.625rem 1rem',
                            border: '1px solid var(--color-border)',
                            borderRadius: '8px',
                            background: 'var(--color-surface)',
                            color: 'var(--color-text)',
                            fontSize: 'var(--text-sm)',
                            minWidth: '130px',
                        }}
                    >
                        <option value="">All Priority</option>
                        <option value="Critical">Critical</option>
                        <option value="High">High</option>
                        <option value="Medium">Medium</option>
                        <option value="Low">Low</option>
                    </select>
                </div>

                <div style={{ background: 'var(--color-surface)', borderRadius: '12px', border: '1px solid var(--color-border)', overflow: 'hidden' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                        <thead>
                            <tr style={{ borderBottom: '1px solid var(--color-border)' }}>
                                <th style={{ padding: '0.75rem 1rem', textAlign: 'left', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Ticket #</th>
                                <th style={{ padding: '0.75rem 1rem', textAlign: 'left', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Subject</th>
                                <th style={{ padding: '0.75rem 1rem', textAlign: 'left', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Asset</th>
                                <th style={{ padding: '0.75rem 1rem', textAlign: 'center', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Priority</th>
                                <th style={{ padding: '0.75rem 1rem', textAlign: 'center', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Status</th>
                                <th style={{ padding: '0.75rem 1rem', textAlign: 'left', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Technician</th>
                                <th style={{ padding: '0.75rem 1rem', textAlign: 'right', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {filteredTickets.length === 0 ? (
                                <tr>
                                    <td colSpan={7} style={{ padding: '3rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>
                                        <Ticket size={48} style={{ margin: '0 auto 1rem', opacity: 0.5 }} />
                                        <p>No tickets found</p>
                                    </td>
                                </tr>
                            ) : (
                                filteredTickets.map((ticket: ServiceTicket) => (
                                    <tr key={ticket.id} style={{ borderBottom: '1px solid var(--color-border)' }}>
                                        <td style={{ padding: '0.75rem 1rem', fontWeight: 600, fontFamily: 'monospace' }}>
                                            <span
                                                onClick={() => navigate(`/service/tickets/${ticket.id}`)}
                                                style={{ cursor: 'pointer', color: 'var(--color-primary)' }}
                                            >
                                                {ticket.ticket_number}
                                            </span>
                                        </td>
                                        <td style={{ padding: '0.75rem 1rem', maxWidth: '200px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{ticket.subject}</td>
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
                                                background: `${statusColor(ticket.status)}20`,
                                                color: statusColor(ticket.status),
                                            }}>
                                                {ticket.status}
                                            </span>
                                        </td>
                                        <td style={{ padding: '0.75rem 1rem', fontSize: 'var(--text-sm)' }}>{ticket.technician_name || 'Unassigned'}</td>
                                        <td style={{ padding: '0.75rem 1rem', textAlign: 'right' }}>
                                            {ticket.status !== 'Resolved' && ticket.status !== 'Closed' && (
                                                <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}>
                                                    {!ticket.technician && (
                                                        <select
                                                            onChange={(e) => {
                                                                if (e.target.value) {
                                                                    handleAssign(ticket.id, parseInt(e.target.value));
                                                                    e.target.value = '';
                                                                }
                                                            }}
                                                            style={{
                                                                padding: '0.375rem 0.5rem',
                                                                fontSize: 'var(--text-xs)',
                                                                border: '1px solid var(--color-border)',
                                                                borderRadius: '4px',
                                                                background: 'var(--color-surface)',
                                                                color: 'var(--color-text)',
                                                            }}
                                                        >
                                                            <option value="">Assign</option>
                                                            {Array.isArray(techsList) && techsList.filter((t: Technician) => t.is_available).map((tech: Technician) => (
                                                                <option key={tech.id} value={tech.id}>{tech.name}</option>
                                                            ))}
                                                        </select>
                                                    )}
                                                    <button
                                                        onClick={() => handleResolve(ticket.id)}
                                                        style={{
                                                            padding: '0.375rem 0.5rem',
                                                            background: 'rgba(34, 197, 94, 0.1)',
                                                            color: '#22c55e',
                                                            border: 'none',
                                                            borderRadius: '4px',
                                                            fontSize: 'var(--text-xs)',
                                                            fontWeight: 600,
                                                            cursor: 'pointer',
                                                            display: 'flex',
                                                            alignItems: 'center',
                                                            gap: '0.25rem',
                                                        }}
                                                    >
                                                        <CheckCircle size={12} />
                                                        Resolve
                                                    </button>
                                                </div>
                                            )}
                                        </td>
                                    </tr>
                                ))
                            )}
                        </tbody>
                    </table>
                </div>

                {showModal && (
                    <div style={{
                        position: 'fixed',
                        top: 0, left: 0, right: 0, bottom: 0,
                        background: 'rgba(0,0,0,0.5)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        zIndex: 1000,
                    }} onClick={() => setShowModal(false)}>
                        <div style={{
                            background: 'var(--color-surface)',
                            borderRadius: '12px',
                            padding: '1.5rem',
                            maxWidth: '500px',
                            width: '100%',
                        }} onClick={e => e.stopPropagation()}>
                            <h3 style={{ margin: '0 0 1rem 0' }}>Create New Ticket</h3>
                            <form onSubmit={handleSubmit}>
                                <div style={{ marginBottom: '1rem' }}>
                                    <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: 'var(--text-sm)', fontWeight: 500 }}>Subject<span className="required-mark"> *</span></label>
                                    <input
                                        type="text"
                                        required
                                        value={formData.subject}
                                        onChange={e => setFormData({ ...formData, subject: e.target.value })}
                                        style={{
                                            width: '100%',
                                            padding: '0.625rem',
                                            border: '1px solid var(--color-border)',
                                            borderRadius: '8px',
                                            background: 'var(--color-surface)',
                                            color: 'var(--color-text)',
                                            fontSize: 'var(--text-sm)',
                                        }}
                                    />
                                </div>
                                <div style={{ marginBottom: '1rem' }}>
                                    <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: 'var(--text-sm)', fontWeight: 500 }}>Description<span className="required-mark"> *</span></label>
                                    <textarea
                                        required
                                        rows={3}
                                        value={formData.description}
                                        onChange={e => setFormData({ ...formData, description: e.target.value })}
                                        style={{
                                            width: '100%',
                                            padding: '0.625rem',
                                            border: '1px solid var(--color-border)',
                                            borderRadius: '8px',
                                            background: 'var(--color-surface)',
                                            color: 'var(--color-text)',
                                            fontSize: 'var(--text-sm)',
                                            resize: 'vertical',
                                        }}
                                    />
                                </div>
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1.5rem' }}>
                                    <div>
                                        <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: 'var(--text-sm)', fontWeight: 500 }}>Priority<span className="required-mark"> *</span></label>
                                        <select
                                            required
                                            value={formData.priority}
                                            onChange={e => setFormData({ ...formData, priority: e.target.value })}
                                            style={{
                                                width: '100%',
                                                padding: '0.625rem',
                                                border: '1px solid var(--color-border)',
                                                borderRadius: '8px',
                                                background: 'var(--color-surface)',
                                                color: 'var(--color-text)',
                                                fontSize: 'var(--text-sm)',
                                            }}
                                        >
                                            <option value="Low">Low</option>
                                            <option value="Medium">Medium</option>
                                            <option value="High">High</option>
                                            <option value="Critical">Critical</option>
                                        </select>
                                    </div>
                                    <div>
                                        <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: 'var(--text-sm)', fontWeight: 500 }}>Asset</label>
                                        <select
                                            value={formData.asset}
                                            onChange={e => setFormData({ ...formData, asset: e.target.value })}
                                            style={{
                                                width: '100%',
                                                padding: '0.625rem',
                                                border: '1px solid var(--color-border)',
                                                borderRadius: '8px',
                                                background: 'var(--color-surface)',
                                                color: 'var(--color-text)',
                                                fontSize: 'var(--text-sm)',
                                            }}
                                        >
                                            <option value="">Select asset (optional)</option>
                                            {Array.isArray(assetsList) && assetsList.map((a: ServiceAsset) => (
                                                <option key={a.id} value={a.id}>{a.name}</option>
                                            ))}
                                        </select>
                                    </div>
                                </div>
                                <div style={{ display: 'flex', gap: '1rem', justifyContent: 'flex-end' }}>
                                    <button
                                        type="button"
                                        onClick={() => setShowModal(false)}
                                        style={{
                                            padding: '0.625rem 1.25rem',
                                            background: 'transparent',
                                            border: '1px solid var(--color-border)',
                                            borderRadius: '8px',
                                            color: 'var(--color-text)',
                                            cursor: 'pointer',
                                        }}
                                    >
                                        Cancel
                                    </button>
                                    <button
                                        type="submit"
                                        style={{
                                            padding: '0.625rem 1.25rem',
                                            background: 'var(--color-primary)',
                                            border: 'none',
                                            borderRadius: '8px',
                                            color: 'white',
                                            fontWeight: 600,
                                            cursor: 'pointer',
                                        }}
                                    >
                                        Create Ticket
                                    </button>
                                </div>
                            </form>
                        </div>
                    </div>
                )}
            </div>
        </ServiceLayout>
    );
}
