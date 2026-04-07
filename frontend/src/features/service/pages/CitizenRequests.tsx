import { useCitizenRequests, useAcknowledgeCitizenRequest, useConvertToTicket } from '../hooks/useService';
import Sidebar from '../../../components/Sidebar';
import PageHeader from '../../../components/PageHeader';
import { User, CheckCircle, ArrowRight, MapPin, Mail } from 'lucide-react';
import LoadingScreen from '../../../components/common/LoadingScreen';
import type { CitizenRequest } from '../types';

const CitizenRequests = () => {
    const { data: requests, isLoading } = useCitizenRequests();
    const acknowledgeRequest = useAcknowledgeCitizenRequest();
    const convertToTicket = useConvertToTicket();

    const statusColor = (status: string) => {
        switch (status) {
            case 'Resolved': return 'var(--color-success)';
            case 'Closed': return 'var(--color-text-muted)';
            case 'In Progress': return 'var(--color-primary)';
            case 'Acknowledged': return 'var(--color-cta)';
            case 'Submitted': return 'var(--color-warning)';
            default: return 'var(--color-text-muted)';
        }
    };

    return (
        <div style={{ display: 'flex' }}>
            <Sidebar />
            <main style={{ flex: 1, marginLeft: '260px', padding: '2.5rem' }}>
                <PageHeader
                    title="Citizen Requests"
                    subtitle="Public-facing service requests from citizens."
                    icon={<User size={22} color="white" />}
                />

                {isLoading ? (
                    <LoadingScreen message="Loading citizen requests..." fullScreen={false} />
                ) : (
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(450px, 1fr))', gap: '1.5rem' }}>
                        {((requests?.results || requests || []) as CitizenRequest[]).map((cr: CitizenRequest) => (
                            <div key={cr.id} className="card animate-fade">
                                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '1rem' }}>
                                    <span style={{ fontSize: 'var(--text-xs)', fontWeight: 700, color: 'var(--color-text-muted)' }}>{cr.request_number}</span>
                                    <span style={{
                                        padding: '0.2rem 0.6rem', borderRadius: '1rem', fontSize: 'var(--text-xs)', fontWeight: 700,
                                        background: `${statusColor(cr.status)}20`,
                                        color: statusColor(cr.status)
                                    }}>
                                        {cr.status.toUpperCase()}
                                    </span>
                                </div>

                                <h3 style={{ marginBottom: '0.5rem', color: 'var(--color-text)' }}>{cr.subject}</h3>
                                <p style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)', marginBottom: '1rem' }}>{cr.description}</p>

                                <div style={{
                                    display: 'flex',
                                    flexDirection: 'column',
                                    gap: '0.5rem',
                                    padding: '1rem',
                                    background: 'var(--color-surface)',
                                    borderRadius: '0.5rem',
                                    marginBottom: '1rem'
                                }}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: 'var(--text-sm)', color: 'var(--color-text)' }}>
                                        <User size={16} /> {cr.citizen_name}
                                    </div>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)' }}>
                                        <Mail size={16} /> {cr.citizen_email}
                                    </div>
                                    {cr.citizen_phone && (
                                        <div style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)' }}>
                                            📞 {cr.citizen_phone}
                                        </div>
                                    )}
                                    {cr.latitude && cr.longitude && (
                                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)' }}>
                                            <MapPin size={16} /> {cr.latitude}, {cr.longitude}
                                        </div>
                                    )}
                                </div>

                                <div style={{
                                    display: 'flex',
                                    alignItems: 'center',
                                    gap: '0.5rem',
                                    fontSize: 'var(--text-xs)',
                                    color: 'var(--color-text-muted)',
                                    marginBottom: '1rem'
                                }}>
                                    <span style={{
                                        padding: '0.2rem 0.5rem',
                                        background: 'var(--color-border)',
                                        borderRadius: '0.25rem'
                                    }}>
                                        {cr.category}
                                    </span>
                                    <span>•</span>
                                    <span>{new Date(cr.created_at).toLocaleDateString()}</span>
                                </div>

                                <div style={{ display: 'flex', gap: '0.75rem' }}>
                                    {cr.status === 'Submitted' && (
                                        <button
                                            className="btn btn-secondary"
                                            style={{ flex: 1, padding: '0.6rem' }}
                                            onClick={() => acknowledgeRequest.mutate(cr.id)}
                                        >
                                            <CheckCircle size={16} /> Acknowledge
                                        </button>
                                    )}
                                    {(cr.status === 'Acknowledged' || cr.status === 'In Progress') && !cr.related_ticket && (
                                        <button
                                            className="btn btn-primary"
                                            style={{ flex: 1, padding: '0.6rem' }}
                                            onClick={() => convertToTicket.mutate(cr.id)}
                                        >
                                            <ArrowRight size={16} /> Convert to Ticket
                                        </button>
                                    )}
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </main>
        </div>
    );
};

export default CitizenRequests;
