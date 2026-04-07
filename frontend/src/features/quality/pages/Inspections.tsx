import { useState, useCallback } from 'react';
import { Plus, Search, CheckCircle, XCircle, AlertTriangle } from 'lucide-react';
import PageHeader from '../../../components/PageHeader';
import { useQualityInspections, useCreateQualityInspection, useCompleteInspection, useAcceptGRNInspection, useRejectGRNInspection } from '../hooks/useQuality';
import QualityLayout from '../QualityLayout';
import LoadingScreen from '../../../components/common/LoadingScreen';
import { useFocusTrap } from '../../../hooks/useFocusTrap';

export default function Inspections() {
    const [searchTerm, setSearchTerm] = useState('');
    const [statusFilter, setStatusFilter] = useState('');
    const [typeFilter, setTypeFilter] = useState('');
    const [showModal, setShowModal] = useState(false);
    const closeModal = useCallback(() => setShowModal(false), []);
    const modalRef = useFocusTrap(showModal, closeModal);

    const { data: inspections, isLoading } = useQualityInspections({ status: statusFilter, inspection_type: typeFilter });
    const createInspection = useCreateQualityInspection();
    const completeMutation = useCompleteInspection();
    const acceptGRN = useAcceptGRNInspection();
    const rejectGRN = useRejectGRNInspection();

    const inspectionsList = inspections?.results || inspections || [];

    const filteredInspections = Array.isArray(inspectionsList) ? inspectionsList.filter((i: any) =>
        i.inspection_number?.toLowerCase().includes(searchTerm.toLowerCase()) ||
        i.reference_number?.toLowerCase().includes(searchTerm.toLowerCase())
    ) : [];

    const [formData, setFormData] = useState({
        inspection_number: '',
        inspection_type: 'Incoming',
        reference_type: '',
        reference_number: '',
        inspection_date: '',
        notes: '',
    });

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        createInspection.mutate(formData, {
            onSuccess: () => {
                setShowModal(false);
                setFormData({ inspection_number: '', inspection_type: 'Incoming', reference_type: '', reference_number: '', inspection_date: '', notes: '' });
            }
        });
    };

    const getStatusBadge = (status: string) => {
        const colors: any = {
            'Pending': 'rgba(251, 191, 36, 0.1)',
            'In Progress': 'rgba(36, 113, 163, 0.1)',
            'Passed': 'rgba(34, 197, 94, 0.1)',
            'Failed': 'rgba(239, 68, 68, 0.1)',
        };
        const textColors: any = {
            'Pending': '#fbbf24',
            'In Progress': '#2471a3',
            'Passed': '#22c55e',
            'Failed': '#ef4444',
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

    if (isLoading) return <LoadingScreen message="Loading inspections..." />;

    return (
        <QualityLayout>
            <div style={{ padding: '1.5rem' }}>
                <PageHeader
                    title="Quality Inspections"
                    subtitle="Manage quality inspections for incoming, in-process, and final goods"
                    icon={<Search size={22} color="white" />}
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
                            New Inspection
                        </button>
                    }
                />

                <div style={{ display: 'flex', gap: '1rem', marginBottom: '1.5rem', flexWrap: 'wrap' }}>
                    <div style={{ flex: 1, minWidth: '200px', position: 'relative' }}>
                        <Search size={18} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: 'var(--color-text-muted)' }} />
                        <input
                            type="text"
                            placeholder="Search inspections..."
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
                            minWidth: '140px',
                        }}
                    >
                        <option value="">All Status</option>
                        <option value="Pending">Pending</option>
                        <option value="In Progress">In Progress</option>
                        <option value="Passed">Passed</option>
                        <option value="Failed">Failed</option>
                    </select>
                    <select
                        value={typeFilter}
                        onChange={(e) => setTypeFilter(e.target.value)}
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
                        <option value="">All Types</option>
                        <option value="Incoming">Incoming</option>
                        <option value="In-Process">In-Process</option>
                        <option value="Final">Final</option>
                    </select>
                </div>

                <div style={{ background: 'var(--color-surface)', borderRadius: '12px', border: '1px solid var(--color-border)', overflow: 'hidden' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                        <thead>
                            <tr style={{ borderBottom: '1px solid var(--color-border)' }}>
                                <th style={{ padding: '0.75rem 1rem', textAlign: 'left', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Inspection #</th>
                                <th style={{ padding: '0.75rem 1rem', textAlign: 'left', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Type</th>
                                <th style={{ padding: '0.75rem 1rem', textAlign: 'left', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Reference</th>
                                <th style={{ padding: '0.75rem 1rem', textAlign: 'left', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Date</th>
                                <th style={{ padding: '0.75rem 1rem', textAlign: 'center', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Status</th>
                                <th style={{ padding: '0.75rem 1rem', textAlign: 'right', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {filteredInspections.length === 0 ? (
                                <tr>
                                    <td colSpan={6} style={{ padding: '3rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>
                                        <Search size={48} style={{ margin: '0 auto 1rem', opacity: 0.5 }} />
                                        <p>No inspections found</p>
                                    </td>
                                </tr>
                            ) : (
                                filteredInspections.map((inspection: any) => (
                                    <tr key={inspection.id} style={{ borderBottom: '1px solid var(--color-border)' }}>
                                        <td style={{ padding: '0.75rem 1rem', fontWeight: 600 }}>{inspection.inspection_number}</td>
                                        <td style={{ padding: '0.75rem 1rem' }}>{inspection.inspection_type}</td>
                                        <td style={{ padding: '0.75rem 1rem' }}>{inspection.reference_number || '-'}</td>
                                        <td style={{ padding: '0.75rem 1rem' }}>{inspection.inspection_date ? new Date(inspection.inspection_date).toLocaleDateString() : '-'}</td>
                                        <td style={{ padding: '0.75rem 1rem', textAlign: 'center' }}>{getStatusBadge(inspection.status)}</td>
                                        <td style={{ padding: '0.75rem 1rem', textAlign: 'right' }}>
                                            {inspection.status === 'Pending' && (
                                                <button
                                                    onClick={() => completeMutation.mutate(inspection.id)}
                                                    style={{
                                                        padding: '0.375rem 0.75rem',
                                                        background: 'rgba(36, 113, 163, 0.1)',
                                                        color: '#2471a3',
                                                        border: 'none',
                                                        borderRadius: '6px',
                                                        fontSize: 'var(--text-xs)',
                                                        fontWeight: 600,
                                                        cursor: 'pointer',
                                                        marginRight: '0.5rem',
                                                    }}
                                                >
                                                    Complete
                                                </button>
                                            )}
                                            {inspection.status === 'Passed' && inspection.inspection_type === 'Incoming' && (
                                                <button
                                                    onClick={() => acceptGRN.mutate(inspection.id)}
                                                    style={{
                                                        padding: '0.375rem 0.75rem',
                                                        background: 'rgba(34, 197, 94, 0.1)',
                                                        color: '#22c55e',
                                                        border: 'none',
                                                        borderRadius: '6px',
                                                        fontSize: 'var(--text-xs)',
                                                        fontWeight: 600,
                                                        cursor: 'pointer',
                                                        marginRight: '0.5rem',
                                                    }}
                                                >
                                                    Accept GRN
                                                </button>
                                            )}
                                            {inspection.status === 'Failed' && (
                                                <button
                                                    onClick={() => rejectGRN.mutate({ id: inspection.id })}
                                                    style={{
                                                        padding: '0.375rem 0.75rem',
                                                        background: 'rgba(239, 68, 68, 0.1)',
                                                        color: '#ef4444',
                                                        border: 'none',
                                                        borderRadius: '6px',
                                                        fontSize: 'var(--text-xs)',
                                                        fontWeight: 600,
                                                        cursor: 'pointer',
                                                    }}
                                                >
                                                    Create NCR
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
                        <div ref={modalRef} role="dialog" aria-modal="true" aria-label="Add Quality Inspection" style={{
                            background: 'var(--color-surface)',
                            borderRadius: '12px',
                            padding: '1.5rem',
                            maxWidth: '500px',
                            width: '100%',
                        }} onClick={e => e.stopPropagation()}>
                            <h3 style={{ margin: '0 0 1rem 0' }}>Create Quality Inspection</h3>
                            <form onSubmit={handleSubmit}>
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
                                    <div>
                                        <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: 'var(--text-sm)', fontWeight: 500 }}>Inspection Number<span className="required-mark"> *</span></label>
                                        <input
                                            type="text"
                                            required
                                            value={formData.inspection_number}
                                            onChange={e => setFormData({ ...formData, inspection_number: e.target.value })}
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
                                        <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: 'var(--text-sm)', fontWeight: 500 }}>Type<span className="required-mark"> *</span></label>
                                        <select
                                            required
                                            value={formData.inspection_type}
                                            onChange={e => setFormData({ ...formData, inspection_type: e.target.value })}
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
                                            <option value="Incoming">Incoming</option>
                                            <option value="In-Process">In-Process</option>
                                            <option value="Final">Final</option>
                                        </select>
                                    </div>
                                </div>
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
                                    <div>
                                        <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: 'var(--text-sm)', fontWeight: 500 }}>Reference Type</label>
                                        <input
                                            type="text"
                                            value={formData.reference_type}
                                            onChange={e => setFormData({ ...formData, reference_type: e.target.value })}
                                            placeholder="e.g., PO, GRN"
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
                                        <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: 'var(--text-sm)', fontWeight: 500 }}>Date<span className="required-mark"> *</span></label>
                                        <input
                                            type="date"
                                            required
                                            value={formData.inspection_date}
                                            onChange={e => setFormData({ ...formData, inspection_date: e.target.value })}
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
                                </div>
                                <div style={{ marginBottom: '1.5rem' }}>
                                    <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: 'var(--text-sm)', fontWeight: 500 }}>Notes</label>
                                    <textarea
                                        rows={2}
                                        value={formData.notes}
                                        onChange={e => setFormData({ ...formData, notes: e.target.value })}
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
