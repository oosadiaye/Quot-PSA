import { useState, useCallback } from 'react';
import { Plus, Search, AlertTriangle, CheckCircle } from 'lucide-react';
import PageHeader from '../../../components/PageHeader';
import { useNonConformances, useCreateNonConformance, useCloseNonConformance } from '../hooks/useQuality';
import QualityLayout from '../QualityLayout';
import LoadingScreen from '../../../components/common/LoadingScreen';
import { useFocusTrap } from '../../../hooks/useFocusTrap';

export default function NonConformances() {
    const [searchTerm, setSearchTerm] = useState('');
    const [statusFilter, setStatusFilter] = useState('');
    const [severityFilter, setSeverityFilter] = useState('');
    const [showModal, setShowModal] = useState(false);
    const closeModal = useCallback(() => setShowModal(false), []);
    const modalRef = useFocusTrap(showModal, closeModal);

    const { data: ncrs, isLoading } = useNonConformances({ status: statusFilter, severity: severityFilter });
    const createNCR = useCreateNonConformance();
    const closeMutation = useCloseNonConformance();

    const ncrsList = ncrs?.results || ncrs || [];

    const filteredNCRs = Array.isArray(ncrsList) ? ncrsList.filter((n: any) =>
        n.ncr_number?.toLowerCase().includes(searchTerm.toLowerCase()) ||
        n.title?.toLowerCase().includes(searchTerm.toLowerCase())
    ) : [];

    const [formData, setFormData] = useState({
        ncr_number: '',
        title: '',
        description: '',
        severity: 'Minor',
        source_type: '',
    });

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        createNCR.mutate(formData, {
            onSuccess: () => {
                setShowModal(false);
                setFormData({ ncr_number: '', title: '', description: '', severity: 'Minor', source_type: '' });
            }
        });
    };

    const getStatusBadge = (status: string) => {
        const colors: any = {
            'Open': 'rgba(239, 68, 68, 0.1)',
            'Under Investigation': 'rgba(36, 113, 163, 0.1)',
            'Corrective Action': 'rgba(251, 191, 36, 0.1)',
            'Closed': 'rgba(34, 197, 94, 0.1)',
            'Rejected': 'rgba(156, 163, 175, 0.1)',
        };
        const textColors: any = {
            'Open': '#ef4444',
            'Under Investigation': '#2471a3',
            'Corrective Action': '#fbbf24',
            'Closed': '#22c55e',
            'Rejected': '#9ca3af',
        };
        return (
            <span style={{
                display: 'inline-block',
                padding: '0.25rem 0.75rem',
                borderRadius: '9999px',
                fontSize: 'var(--text-xs)',
                fontWeight: 600,
                background: colors[status] || 'rgba(156, 163, 175, 0.1)',
                color: textColors[status] || '#9ca3af',
            }}>
                {status}
            </span>
        );
    };

    const getSeverityBadge = (severity: string) => {
        const colors: any = {
            'Critical': 'rgba(239, 68, 68, 0.1)',
            'Major': 'rgba(251, 191, 36, 0.1)',
            'Minor': 'rgba(36, 113, 163, 0.1)',
        };
        const textColors: any = {
            'Critical': '#ef4444',
            'Major': '#fbbf24',
            'Minor': '#2471a3',
        };
        return (
            <span style={{
                display: 'inline-block',
                padding: '0.25rem 0.5rem',
                borderRadius: '4px',
                fontSize: 'var(--text-xs)',
                fontWeight: 600,
                background: colors[severity] || 'rgba(156, 163, 175, 0.1)',
                color: textColors[severity] || '#9ca3af',
            }}>
                {severity}
            </span>
        );
    };

    if (isLoading) return <LoadingScreen message="Loading non-conformances..." />;

    return (
        <QualityLayout>
            <div style={{ padding: '1.5rem' }}>
                <PageHeader
                    title="Non-Conformances (NCR)"
                    subtitle="Track and manage non-conformance reports"
                    icon={<AlertTriangle size={22} color="white" />}
                    backButton={false}
                    actions={
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
                            New NCR
                        </button>
                    }
                />

                <div style={{ display: 'flex', gap: '1rem', marginBottom: '1.5rem', flexWrap: 'wrap' }}>
                    <div style={{ flex: 1, minWidth: '200px', position: 'relative' }}>
                        <Search size={18} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: 'var(--color-text-muted)' }} />
                        <input
                            type="text"
                            placeholder="Search NCRs..."
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
                            minWidth: '150px',
                        }}
                    >
                        <option value="">All Status</option>
                        <option value="Open">Open</option>
                        <option value="Under Investigation">Under Investigation</option>
                        <option value="Corrective Action">Corrective Action</option>
                        <option value="Closed">Closed</option>
                        <option value="Rejected">Rejected</option>
                    </select>
                    <select
                        value={severityFilter}
                        onChange={(e) => setSeverityFilter(e.target.value)}
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
                        <option value="">All Severity</option>
                        <option value="Critical">Critical</option>
                        <option value="Major">Major</option>
                        <option value="Minor">Minor</option>
                    </select>
                </div>

                <div style={{ background: 'var(--color-surface)', borderRadius: '12px', border: '1px solid var(--color-border)', overflow: 'hidden' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                        <thead>
                            <tr style={{ borderBottom: '1px solid var(--color-border)' }}>
                                <th style={{ padding: '0.75rem 1rem', textAlign: 'left', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>NCR #</th>
                                <th style={{ padding: '0.75rem 1rem', textAlign: 'left', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Title</th>
                                <th style={{ padding: '0.75rem 1rem', textAlign: 'center', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Severity</th>
                                <th style={{ padding: '0.75rem 1rem', textAlign: 'left', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Source</th>
                                <th style={{ padding: '0.75rem 1rem', textAlign: 'center', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Status</th>
                                <th style={{ padding: '0.75rem 1rem', textAlign: 'right', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {filteredNCRs.length === 0 ? (
                                <tr>
                                    <td colSpan={6} style={{ padding: '3rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>
                                        <AlertTriangle size={48} style={{ margin: '0 auto 1rem', opacity: 0.5 }} />
                                        <p>No non-conformances found</p>
                                    </td>
                                </tr>
                            ) : (
                                filteredNCRs.map((ncr: any) => (
                                    <tr key={ncr.id} style={{ borderBottom: '1px solid var(--color-border)' }}>
                                        <td style={{ padding: '0.75rem 1rem', fontWeight: 600 }}>{ncr.ncr_number}</td>
                                        <td style={{ padding: '0.75rem 1rem' }}>{ncr.title}</td>
                                        <td style={{ padding: '0.75rem 1rem', textAlign: 'center' }}>{getSeverityBadge(ncr.severity)}</td>
                                        <td style={{ padding: '0.75rem 1rem' }}>{ncr.source_type || '-'}</td>
                                        <td style={{ padding: '0.75rem 1rem', textAlign: 'center' }}>{getStatusBadge(ncr.status)}</td>
                                        <td style={{ padding: '0.75rem 1rem', textAlign: 'right' }}>
                                            {(ncr.status === 'Open' || ncr.status === 'Under Investigation' || ncr.status === 'Corrective Action') && (
                                                <button
                                                    onClick={() => closeMutation.mutate({ id: ncr.id })}
                                                    style={{
                                                        padding: '0.375rem 0.75rem',
                                                        background: 'rgba(34, 197, 94, 0.1)',
                                                        color: '#22c55e',
                                                        border: 'none',
                                                        borderRadius: '6px',
                                                        fontSize: 'var(--text-xs)',
                                                        fontWeight: 600,
                                                        cursor: 'pointer',
                                                    }}
                                                >
                                                    Close
                                                </button>
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
                    }} onClick={closeModal} role="presentation">
                        <div ref={modalRef} role="dialog" aria-modal="true" aria-label="Add Non-Conformance" style={{
                            background: 'var(--color-surface)',
                            borderRadius: '12px',
                            padding: '1.5rem',
                            maxWidth: '500px',
                            width: '100%',
                        }} onClick={e => e.stopPropagation()}>
                            <h3 style={{ margin: '0 0 1rem 0' }}>Create Non-Conformance Report</h3>
                            <form onSubmit={handleSubmit}>
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
                                    <div>
                                        <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: 'var(--text-sm)', fontWeight: 500 }}>NCR Number<span className="required-mark"> *</span></label>
                                        <input
                                            type="text"
                                            required
                                            value={formData.ncr_number}
                                            onChange={e => setFormData({ ...formData, ncr_number: e.target.value })}
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
                                    <div>
                                        <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: 'var(--text-sm)', fontWeight: 500 }}>Severity<span className="required-mark"> *</span></label>
                                        <select
                                            required
                                            value={formData.severity}
                                            onChange={e => setFormData({ ...formData, severity: e.target.value })}
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
                                            <option value="Critical">Critical</option>
                                            <option value="Major">Major</option>
                                            <option value="Minor">Minor</option>
                                        </select>
                                    </div>
                                </div>
                                <div style={{ marginBottom: '1rem' }}>
                                    <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: 'var(--text-sm)', fontWeight: 500 }}>Title<span className="required-mark"> *</span></label>
                                    <input
                                        type="text"
                                        required
                                        value={formData.title}
                                        onChange={e => setFormData({ ...formData, title: e.target.value })}
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
                                <div style={{ marginBottom: '1.5rem' }}>
                                    <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: 'var(--text-sm)', fontWeight: 500 }}>Source Type</label>
                                    <input
                                        type="text"
                                        value={formData.source_type}
                                        onChange={e => setFormData({ ...formData, source_type: e.target.value })}
                                        placeholder="e.g., Procurement, Production, Sales"
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
                                        Create
                                    </button>
                                </div>
                            </form>
                        </div>
                    </div>
                )}
            </div>
        </QualityLayout>
    );
}
