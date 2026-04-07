import { useState, useCallback } from 'react';
import { Plus, Search, BadgeCheck } from 'lucide-react';
import PageHeader from '../../../components/PageHeader';
import { useSupplierQuality, useCreateSupplierQuality, useVendors } from '../hooks/useQuality';
import QualityLayout from '../QualityLayout';
import LoadingScreen from '../../../components/common/LoadingScreen';
import { useFocusTrap } from '../../../hooks/useFocusTrap';

export default function SupplierQuality() {
    const [searchTerm, setSearchTerm] = useState('');
    const [ratingFilter, setRatingFilter] = useState('');
    const [showModal, setShowModal] = useState(false);
    const closeModal = useCallback(() => setShowModal(false), []);
    const modalRef = useFocusTrap(showModal, closeModal);

    const { data: supplierQual, isLoading } = useSupplierQuality({ rating: ratingFilter });
    const { data: vendors } = useVendors({ is_active: true });
    const createQuality = useCreateSupplierQuality();

    const supplierList = supplierQual?.results || supplierQual || [];
    const vendorsList = vendors?.results || vendors || [];

    const filteredSuppliers = Array.isArray(supplierList) ? supplierList.filter((s: any) =>
        s.vendor_name?.toLowerCase().includes(searchTerm.toLowerCase())
    ) : [];

    const [formData, setFormData] = useState({
        vendor: '', evaluation_date: '', quality_score: '', delivery_score: '', rating: 'Good', comments: ''
    });

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        const total = (parseFloat(formData.quality_score) + parseFloat(formData.delivery_score)) / 2;
        createQuality.mutate({
            ...formData,
            quality_score: parseFloat(formData.quality_score),
            delivery_score: parseFloat(formData.delivery_score),
            overall_score: total,
        }, { onSuccess: () => { setShowModal(false); setFormData({ vendor: '', evaluation_date: '', quality_score: '', delivery_score: '', rating: 'Good', comments: '' }); } });
    };

    const getRatingBadge = (rating: string) => {
        const colors: any = { 'Excellent': 'rgba(34, 197, 94, 0.1)', 'Good': 'rgba(36, 113, 163, 0.1)', 'Average': 'rgba(251, 191, 36, 0.1)', 'Poor': 'rgba(239, 68, 68, 0.1)' };
        const textColors: any = { 'Excellent': '#22c55e', 'Good': '#2471a3', 'Average': '#fbbf24', 'Poor': '#ef4444' };
        return <span style={{ display: 'inline-block', padding: '0.25rem 0.75rem', borderRadius: '9999px', fontSize: 'var(--text-xs)', fontWeight: 600, background: colors[rating] || 'rgba(156, 163, 175, 0.1)', color: textColors[rating] || '#9ca3af' }}>{rating}</span>;
    };

    if (isLoading) return <LoadingScreen message="Loading supplier quality..." />;

    return (
        <QualityLayout>
            <div style={{ padding: '1.5rem' }}>
                <PageHeader
                    title="Supplier Quality"
                    subtitle="Evaluate and track supplier quality performance"
                    icon={<BadgeCheck size={22} color="white" />}
                    backButton={false}
                    actions={
                        <button onClick={() => setShowModal(true)} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.625rem 1.25rem', background: 'var(--color-primary)', color: 'white', border: 'none', borderRadius: '8px', fontWeight: 600, cursor: 'pointer' }}>
                            <Plus size={18} /> New Evaluation
                        </button>
                    }
                />

                <div style={{ display: 'flex', gap: '1rem', marginBottom: '1.5rem', flexWrap: 'wrap' }}>
                    <div style={{ flex: 1, minWidth: '200px', position: 'relative' }}>
                        <Search size={18} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: 'var(--color-text-muted)' }} />
                        <input type="text" placeholder="Search suppliers..." value={searchTerm} onChange={(e) => setSearchTerm(e.target.value)} style={{ width: '100%', padding: '0.625rem 0.75rem 0.625rem 2.5rem', border: '1px solid var(--color-border)', borderRadius: '8px', background: 'var(--color-surface)', color: 'var(--color-text)', fontSize: 'var(--text-sm)' }} />
                    </div>
                    <select value={ratingFilter} onChange={(e) => setRatingFilter(e.target.value)} style={{ padding: '0.625rem 1rem', border: '1px solid var(--color-border)', borderRadius: '8px', background: 'var(--color-surface)', color: 'var(--color-text)', fontSize: 'var(--text-sm)', minWidth: '140px' }}>
                        <option value="">All Ratings</option>
                        <option value="Excellent">Excellent</option>
                        <option value="Good">Good</option>
                        <option value="Average">Average</option>
                        <option value="Poor">Poor</option>
                    </select>
                </div>

                <div style={{ background: 'var(--color-surface)', borderRadius: '12px', border: '1px solid var(--color-border)', overflow: 'hidden' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                        <thead>
                            <tr style={{ borderBottom: '1px solid var(--color-border)' }}>
                                <th style={{ padding: '0.75rem 1rem', textAlign: 'left', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Vendor</th>
                                <th style={{ padding: '0.75rem 1rem', textAlign: 'left', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Evaluation Date</th>
                                <th style={{ padding: '0.75rem 1rem', textAlign: 'right', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Quality Score</th>
                                <th style={{ padding: '0.75rem 1rem', textAlign: 'right', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Delivery Score</th>
                                <th style={{ padding: '0.75rem 1rem', textAlign: 'right', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Overall</th>
                                <th style={{ padding: '0.75rem 1rem', textAlign: 'center', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Rating</th>
                            </tr>
                        </thead>
                        <tbody>
                            {filteredSuppliers.length === 0 ? (
                                <tr><td colSpan={6} style={{ padding: '3rem', textAlign: 'center', color: 'var(--color-text-muted)' }}><BadgeCheck size={48} style={{ margin: '0 auto 1rem', opacity: 0.5 }} /><p>No supplier quality records found</p></td></tr>
                            ) : (
                                filteredSuppliers.map((record: any) => (
                                    <tr key={record.id} style={{ borderBottom: '1px solid var(--color-border)' }}>
                                        <td style={{ padding: '0.75rem 1rem', fontWeight: 600 }}>{record.vendor_name}</td>
                                        <td style={{ padding: '0.75rem 1rem' }}>{record.evaluation_date ? new Date(record.evaluation_date).toLocaleDateString() : '-'}</td>
                                        <td style={{ padding: '0.75rem 1rem', textAlign: 'right', fontFamily: 'monospace' }}>{parseFloat(record.quality_score || 0).toFixed(1)}%</td>
                                        <td style={{ padding: '0.75rem 1rem', textAlign: 'right', fontFamily: 'monospace' }}>{parseFloat(record.delivery_score || 0).toFixed(1)}%</td>
                                        <td style={{ padding: '0.75rem 1rem', textAlign: 'right', fontFamily: 'monospace', fontWeight: 600 }}>{parseFloat(record.overall_score || 0).toFixed(1)}%</td>
                                        <td style={{ padding: '0.75rem 1rem', textAlign: 'center' }}>{getRatingBadge(record.rating)}</td>
                                    </tr>
                                ))
                            )}
                        </tbody>
                    </table>
                </div>

                {showModal && (
                    <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }} onClick={closeModal} role="presentation">
                        <div ref={modalRef} role="dialog" aria-modal="true" aria-labelledby="supplier-eval-dialog-title" style={{ background: 'var(--color-surface)', borderRadius: '12px', padding: '1.5rem', maxWidth: '450px', width: '100%' }} onClick={e => e.stopPropagation()}>
                            <h3 id="supplier-eval-dialog-title" style={{ margin: '0 0 1rem 0' }}>New Supplier Evaluation</h3>
                            <form onSubmit={handleSubmit}>
                                <div style={{ marginBottom: '1rem' }}>
                                    <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: 'var(--text-sm)', fontWeight: 500 }}>Vendor<span className="required-mark"> *</span></label>
                                    <select required value={formData.vendor} onChange={e => setFormData({ ...formData, vendor: e.target.value })} style={{ width: '100%', padding: '0.625rem', border: '1px solid var(--color-border)', borderRadius: '8px', background: 'var(--color-surface)', color: 'var(--color-text)', fontSize: 'var(--text-sm)' }}>
                                        <option value="">Select vendor</option>
                                        {Array.isArray(vendorsList) && vendorsList.map((v: any) => <option key={v.id} value={v.id}>{v.name}</option>)}
                                    </select>
                                </div>
                                <div style={{ marginBottom: '1rem' }}>
                                    <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: 'var(--text-sm)', fontWeight: 500 }}>Evaluation Date<span className="required-mark"> *</span></label>
                                    <input type="date" required value={formData.evaluation_date} onChange={e => setFormData({ ...formData, evaluation_date: e.target.value })} style={{ width: '100%', padding: '0.625rem', border: '1px solid var(--color-border)', borderRadius: '8px', background: 'var(--color-surface)', color: 'var(--color-text)', fontSize: 'var(--text-sm)' }} />
                                </div>
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
                                    <div><label style={{ display: 'block', marginBottom: '0.5rem', fontSize: 'var(--text-sm)', fontWeight: 500 }}>Quality Score<span className="required-mark"> *</span></label><input type="number" required min="0" max="100" step="0.01" value={formData.quality_score} onChange={e => setFormData({ ...formData, quality_score: e.target.value })} style={{ width: '100%', padding: '0.625rem', border: '1px solid var(--color-border)', borderRadius: '8px', background: 'var(--color-surface)', color: 'var(--color-text)', fontSize: 'var(--text-sm)' }} /></div>
                                    <div><label style={{ display: 'block', marginBottom: '0.5rem', fontSize: 'var(--text-sm)', fontWeight: 500 }}>Delivery Score<span className="required-mark"> *</span></label><input type="number" required min="0" max="100" step="0.01" value={formData.delivery_score} onChange={e => setFormData({ ...formData, delivery_score: e.target.value })} style={{ width: '100%', padding: '0.625rem', border: '1px solid var(--color-border)', borderRadius: '8px', background: 'var(--color-surface)', color: 'var(--color-text)', fontSize: 'var(--text-sm)' }} /></div>
                                </div>
                                <div style={{ marginBottom: '1rem' }}>
                                    <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: 'var(--text-sm)', fontWeight: 500 }}>Rating<span className="required-mark"> *</span></label>
                                    <select required value={formData.rating} onChange={e => setFormData({ ...formData, rating: e.target.value })} style={{ width: '100%', padding: '0.625rem', border: '1px solid var(--color-border)', borderRadius: '8px', background: 'var(--color-surface)', color: 'var(--color-text)', fontSize: 'var(--text-sm)' }}>
                                        <option value="Excellent">Excellent</option>
                                        <option value="Good">Good</option>
                                        <option value="Average">Average</option>
                                        <option value="Poor">Poor</option>
                                    </select>
                                </div>
                                <div style={{ marginBottom: '1.5rem' }}>
                                    <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: 'var(--text-sm)', fontWeight: 500 }}>Comments</label>
                                    <textarea rows={2} value={formData.comments} onChange={e => setFormData({ ...formData, comments: e.target.value })} style={{ width: '100%', padding: '0.625rem', border: '1px solid var(--color-border)', borderRadius: '8px', background: 'var(--color-surface)', color: 'var(--color-text)', fontSize: 'var(--text-sm)', resize: 'vertical' }} />
                                </div>
                                <div style={{ display: 'flex', gap: '1rem', justifyContent: 'flex-end' }}>
                                    <button type="button" onClick={() => setShowModal(false)} style={{ padding: '0.625rem 1.25rem', background: 'transparent', border: '1px solid var(--color-border)', borderRadius: '8px', color: 'var(--color-text)', cursor: 'pointer' }}>Cancel</button>
                                    <button type="submit" style={{ padding: '0.625rem 1.25rem', background: 'var(--color-primary)', border: 'none', borderRadius: '8px', color: 'white', fontWeight: 600, cursor: 'pointer' }}>Create</button>
                                </div>
                            </form>
                        </div>
                    </div>
                )}
            </div>
        </QualityLayout>
    );
}
