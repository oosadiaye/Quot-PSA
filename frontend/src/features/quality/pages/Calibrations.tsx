import { useState, useCallback } from 'react';
import { Plus, Search, Gauge } from 'lucide-react';
import PageHeader from '../../../components/PageHeader';
import { useCalibrationRecords, useCreateCalibrationRecord, useCalibrateEquipment } from '../hooks/useQuality';
import QualityLayout from '../QualityLayout';
import LoadingScreen from '../../../components/common/LoadingScreen';
import { useFocusTrap } from '../../../hooks/useFocusTrap';

export default function Calibrations() {
    const [searchTerm, setSearchTerm] = useState('');
    const [statusFilter, setStatusFilter] = useState('');
    const [showModal, setShowModal] = useState(false);
    const closeModal = useCallback(() => setShowModal(false), []);
    const modalRef = useFocusTrap(showModal, closeModal);

    const { data: calibrations, isLoading } = useCalibrationRecords({ status: statusFilter });
    const createRecord = useCreateCalibrationRecord();
    const calibrateMutation = useCalibrateEquipment();

    const calibrationsList = calibrations?.results || calibrations || [];

    const filteredCalibrations = Array.isArray(calibrationsList) ? calibrationsList.filter((c: any) =>
        c.equipment_name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
        c.equipment_code?.toLowerCase().includes(searchTerm.toLowerCase())
    ) : [];

    const [formData, setFormData] = useState({
        equipment_name: '', equipment_code: '', equipment_type: 'Measuring', manufacturer: '', model_number: '', serial_number: '', calibration_interval_months: 12
    });

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        createRecord.mutate(formData, { onSuccess: () => { setShowModal(false); setFormData({ equipment_name: '', equipment_code: '', equipment_type: 'Measuring', manufacturer: '', model_number: '', serial_number: '', calibration_interval_months: 12 }); } });
    };

    const getStatusBadge = (status: string) => {
        const colors: any = { 'Calibrated': 'rgba(34, 197, 94, 0.1)', 'Due': 'rgba(251, 191, 36, 0.1)', 'Overdue': 'rgba(239, 68, 68, 0.1)', 'Out of Service': 'rgba(156, 163, 175, 0.1)' };
        const textColors: any = { 'Calibrated': '#22c55e', 'Due': '#fbbf24', 'Overdue': '#ef4444', 'Out of Service': '#9ca3af' };
        return <span style={{ display: 'inline-block', padding: '0.25rem 0.75rem', borderRadius: '9999px', fontSize: 'var(--text-xs)', fontWeight: 600, background: colors[status] || 'rgba(156, 163, 175, 0.1)', color: textColors[status] || '#9ca3af' }}>{status}</span>;
    };

    if (isLoading) return <LoadingScreen message="Loading calibrations..." />;

    return (
        <QualityLayout>
            <div style={{ padding: '1.5rem' }}>
                <PageHeader
                    title="Calibrations"
                    subtitle="Manage equipment calibration records"
                    icon={<Gauge size={22} color="white" />}
                    backButton={false}
                    actions={
                        <button onClick={() => setShowModal(true)} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.625rem 1.25rem', background: 'var(--color-primary)', color: 'white', border: 'none', borderRadius: '8px', fontWeight: 600, cursor: 'pointer' }}>
                            <Plus size={18} /> New Record
                        </button>
                    }
                />

                <div style={{ display: 'flex', gap: '1rem', marginBottom: '1.5rem', flexWrap: 'wrap' }}>
                    <div style={{ flex: 1, minWidth: '200px', position: 'relative' }}>
                        <Search size={18} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: 'var(--color-text-muted)' }} />
                        <input type="text" placeholder="Search equipment..." value={searchTerm} onChange={(e) => setSearchTerm(e.target.value)} style={{ width: '100%', padding: '0.625rem 0.75rem 0.625rem 2.5rem', border: '1px solid var(--color-border)', borderRadius: '8px', background: 'var(--color-surface)', color: 'var(--color-text)', fontSize: 'var(--text-sm)' }} />
                    </div>
                    <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} style={{ padding: '0.625rem 1rem', border: '1px solid var(--color-border)', borderRadius: '8px', background: 'var(--color-surface)', color: 'var(--color-text)', fontSize: 'var(--text-sm)', minWidth: '140px' }}>
                        <option value="">All Status</option>
                        <option value="Calibrated">Calibrated</option>
                        <option value="Due">Due</option>
                        <option value="Overdue">Overdue</option>
                        <option value="Out of Service">Out of Service</option>
                    </select>
                </div>

                <div style={{ background: 'var(--color-surface)', borderRadius: '12px', border: '1px solid var(--color-border)', overflow: 'hidden' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                        <thead>
                            <tr style={{ borderBottom: '1px solid var(--color-border)' }}>
                                <th style={{ padding: '0.75rem 1rem', textAlign: 'left', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Code</th>
                                <th style={{ padding: '0.75rem 1rem', textAlign: 'left', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Equipment</th>
                                <th style={{ padding: '0.75rem 1rem', textAlign: 'left', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Type</th>
                                <th style={{ padding: '0.75rem 1rem', textAlign: 'left', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Last Cal.</th>
                                <th style={{ padding: '0.75rem 1rem', textAlign: 'left', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Next Cal.</th>
                                <th style={{ padding: '0.75rem 1rem', textAlign: 'center', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Status</th>
                                <th style={{ padding: '0.75rem 1rem', textAlign: 'right', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {filteredCalibrations.length === 0 ? (
                                <tr><td colSpan={7} style={{ padding: '3rem', textAlign: 'center', color: 'var(--color-text-muted)' }}><Gauge size={48} style={{ margin: '0 auto 1rem', opacity: 0.5 }} /><p>No calibration records found</p></td></tr>
                            ) : (
                                filteredCalibrations.map((record: any) => (
                                    <tr key={record.id} style={{ borderBottom: '1px solid var(--color-border)' }}>
                                        <td style={{ padding: '0.75rem 1rem', fontWeight: 600 }}>{record.equipment_code}</td>
                                        <td style={{ padding: '0.75rem 1rem' }}>{record.equipment_name}</td>
                                        <td style={{ padding: '0.75rem 1rem' }}>{record.equipment_type}</td>
                                        <td style={{ padding: '0.75rem 1rem' }}>{record.last_calibration_date ? new Date(record.last_calibration_date).toLocaleDateString() : '-'}</td>
                                        <td style={{ padding: '0.75rem 1rem' }}>{record.next_calibration_date ? new Date(record.next_calibration_date).toLocaleDateString() : '-'}</td>
                                        <td style={{ padding: '0.75rem 1rem', textAlign: 'center' }}>{getStatusBadge(record.status)}</td>
                                        <td style={{ padding: '0.75rem 1rem', textAlign: 'right' }}>
                                            {record.status !== 'Out of Service' && (
                                                <button onClick={() => calibrateMutation.mutate(record.id)} style={{ padding: '0.375rem 0.75rem', background: 'rgba(34, 197, 94, 0.1)', color: '#22c55e', border: 'none', borderRadius: '6px', fontSize: 'var(--text-xs)', fontWeight: 600, cursor: 'pointer' }}>Calibrate</button>
                                            )}
                                        </td>
                                    </tr>
                                ))
                            )}
                        </tbody>
                    </table>
                </div>

                {showModal && (
                    <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }} onClick={closeModal} role="presentation">
                        <div ref={modalRef} role="dialog" aria-modal="true" aria-label="Add Calibration Record" style={{ background: 'var(--color-surface)', borderRadius: '12px', padding: '1.5rem', maxWidth: '450px', width: '100%' }} onClick={e => e.stopPropagation()}>
                            <h3 style={{ margin: '0 0 1rem 0' }}>Add Calibration Record</h3>
                            <form onSubmit={handleSubmit}>
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
                                    <div><label style={{ display: 'block', marginBottom: '0.5rem', fontSize: 'var(--text-sm)', fontWeight: 500 }}>Equipment Name<span className="required-mark"> *</span></label><input type="text" required value={formData.equipment_name} onChange={e => setFormData({ ...formData, equipment_name: e.target.value })} style={{ width: '100%', padding: '0.625rem', border: '1px solid var(--color-border)', borderRadius: '8px', background: 'var(--color-surface)', color: 'var(--color-text)', fontSize: 'var(--text-sm)' }} /></div>
                                    <div><label style={{ display: 'block', marginBottom: '0.5rem', fontSize: 'var(--text-sm)', fontWeight: 500 }}>Equipment Code<span className="required-mark"> *</span></label><input type="text" required value={formData.equipment_code} onChange={e => setFormData({ ...formData, equipment_code: e.target.value })} style={{ width: '100%', padding: '0.625rem', border: '1px solid var(--color-border)', borderRadius: '8px', background: 'var(--color-surface)', color: 'var(--color-text)', fontSize: 'var(--text-sm)' }} /></div>
                                </div>
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
                                    <div><label style={{ display: 'block', marginBottom: '0.5rem', fontSize: 'var(--text-sm)', fontWeight: 500 }}>Type<span className="required-mark"> *</span></label><select required value={formData.equipment_type} onChange={e => setFormData({ ...formData, equipment_type: e.target.value })} style={{ width: '100%', padding: '0.625rem', border: '1px solid var(--color-border)', borderRadius: '8px', background: 'var(--color-surface)', color: 'var(--color-text)', fontSize: 'var(--text-sm)' }}><option value="Measuring">Measuring</option><option value="Testing">Testing</option><option value="Production">Production</option></select></div>
                                    <div><label style={{ display: 'block', marginBottom: '0.5rem', fontSize: 'var(--text-sm)', fontWeight: 500 }}>Interval (months)</label><input type="number" value={formData.calibration_interval_months} onChange={e => setFormData({ ...formData, calibration_interval_months: parseInt(e.target.value) })} style={{ width: '100%', padding: '0.625rem', border: '1px solid var(--color-border)', borderRadius: '8px', background: 'var(--color-surface)', color: 'var(--color-text)', fontSize: 'var(--text-sm)' }} /></div>
                                </div>
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1.5rem' }}>
                                    <div><label style={{ display: 'block', marginBottom: '0.5rem', fontSize: 'var(--text-sm)', fontWeight: 500 }}>Manufacturer</label><input type="text" value={formData.manufacturer} onChange={e => setFormData({ ...formData, manufacturer: e.target.value })} style={{ width: '100%', padding: '0.625rem', border: '1px solid var(--color-border)', borderRadius: '8px', background: 'var(--color-surface)', color: 'var(--color-text)', fontSize: 'var(--text-sm)' }} /></div>
                                    <div><label style={{ display: 'block', marginBottom: '0.5rem', fontSize: 'var(--text-sm)', fontWeight: 500 }}>Model Number</label><input type="text" value={formData.model_number} onChange={e => setFormData({ ...formData, model_number: e.target.value })} style={{ width: '100%', padding: '0.625rem', border: '1px solid var(--color-border)', borderRadius: '8px', background: 'var(--color-surface)', color: 'var(--color-text)', fontSize: 'var(--text-sm)' }} /></div>
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
