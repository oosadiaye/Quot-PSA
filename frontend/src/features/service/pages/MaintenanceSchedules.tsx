import { useState } from 'react';
import { useDialog } from '../../../hooks/useDialog';
import { Plus, Search, CalendarClock, Play, Package } from 'lucide-react';
import { useMaintenanceSchedules, useServiceAssets, useCreateSchedule, useGenerateTicketFromSchedule } from '../hooks/useService';
import ServiceLayout from '../ServiceLayout';
import LoadingScreen from '../../../components/common/LoadingScreen';
import type { MaintenanceSchedule, ServiceAsset } from '../types';

export default function MaintenanceSchedules() {
    const { showConfirm } = useDialog();
    const [searchTerm, setSearchTerm] = useState('');
    const [showModal, setShowModal] = useState(false);
    const [frequencyFilter, setFrequencyFilter] = useState('');
    
    const { data: schedules, isLoading } = useMaintenanceSchedules();
    const { data: assets } = useServiceAssets();
    const createSchedule = useCreateSchedule();
    const generateTicket = useGenerateTicketFromSchedule();

    const schedList = (schedules?.results || schedules || []) as MaintenanceSchedule[];
    const assetsList = (assets?.results || assets || []) as ServiceAsset[];

    const filteredSchedules = Array.isArray(schedList) ? schedList.filter((s: MaintenanceSchedule) => {
        const matchesSearch = s.title?.toLowerCase().includes(searchTerm.toLowerCase()) ||
            s.asset_name?.toLowerCase().includes(searchTerm.toLowerCase());
        const matchesFreq = !frequencyFilter || s.frequency === frequencyFilter;
        return matchesSearch && matchesFreq;
    }) : [];

    const [formData, setFormData] = useState({
        asset: '',
        title: '',
        description: '',
        frequency: 'Monthly',
        next_run_date: '',
    });

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        createSchedule.mutate(formData, {
            onSuccess: () => {
                setShowModal(false);
                setFormData({ asset: '', title: '', description: '', frequency: 'Monthly', next_run_date: '' });
            }
        });
    };

    const handleGenerateTicket = async (id: number) => {
        if (await showConfirm('Generate a maintenance ticket from this schedule?')) {
            generateTicket.mutate(id);
        }
    };

    const frequencyColors: Record<string, string> = {
        'Daily': 'rgba(36, 113, 163, 0.1)',
        'Weekly': 'rgba(34, 197, 94, 0.1)',
        'Monthly': 'rgba(251, 191, 36, 0.1)',
        'Quarterly': 'rgba(236, 72, 153, 0.1)',
        'Yearly': 'rgba(139, 92, 246, 0.1)',
    };

    const frequencyTextColors: Record<string, string> = {
        'Daily': '#2471a3',
        'Weekly': '#22c55e',
        'Monthly': '#fbbf24',
        'Quarterly': '#ec4899',
        'Yearly': '#8b5cf6',
    };

    if (isLoading) return <LoadingScreen message="Loading maintenance schedules..." />;

    return (
        <ServiceLayout>
            <div style={{ padding: '1.5rem' }}>
                <div style={{ marginBottom: '1.5rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div>
                        <h1 style={{ fontSize: 'var(--text-xl)', fontWeight: 700, color: 'var(--color-text)', margin: 0 }}>
                            Maintenance Schedules
                        </h1>
                        <p style={{ color: 'var(--color-text-muted)', margin: '0.25rem 0 0 0', fontSize: 'var(--text-sm)' }}>
                            Schedule recurring maintenance for service assets
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
                        Add Schedule
                    </button>
                </div>

                <div style={{ display: 'flex', gap: '1rem', marginBottom: '1.5rem', flexWrap: 'wrap' }}>
                    <div style={{ flex: 1, minWidth: '200px', position: 'relative' }}>
                        <Search size={18} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: 'var(--color-text-muted)' }} />
                        <input
                            type="text"
                            placeholder="Search schedules..."
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
                        value={frequencyFilter}
                        onChange={(e) => setFrequencyFilter(e.target.value)}
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
                        <option value="">All Frequencies</option>
                        <option value="Daily">Daily</option>
                        <option value="Weekly">Weekly</option>
                        <option value="Monthly">Monthly</option>
                        <option value="Quarterly">Quarterly</option>
                        <option value="Yearly">Yearly</option>
                    </select>
                </div>

                <div style={{ background: 'var(--color-surface)', borderRadius: '12px', border: '1px solid var(--color-border)', overflow: 'hidden' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                        <thead>
                            <tr style={{ borderBottom: '1px solid var(--color-border)' }}>
                                <th style={{ padding: '0.75rem 1rem', textAlign: 'left', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Title</th>
                                <th style={{ padding: '0.75rem 1rem', textAlign: 'left', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Asset</th>
                                <th style={{ padding: '0.75rem 1rem', textAlign: 'center', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Frequency</th>
                                <th style={{ padding: '0.75rem 1rem', textAlign: 'left', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Next Run</th>
                                <th style={{ padding: '0.75rem 1rem', textAlign: 'center', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Status</th>
                                <th style={{ padding: '0.75rem 1rem', textAlign: 'right', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {filteredSchedules.length === 0 ? (
                                <tr>
                                    <td colSpan={6} style={{ padding: '3rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>
                                        <CalendarClock size={48} style={{ margin: '0 auto 1rem', opacity: 0.5 }} />
                                        <p>No maintenance schedules found</p>
                                    </td>
                                </tr>
                            ) : (
                                filteredSchedules.map((schedule: MaintenanceSchedule) => (
                                    <tr key={schedule.id} style={{ borderBottom: '1px solid var(--color-border)' }}>
                                        <td style={{ padding: '0.75rem 1rem', fontWeight: 600 }}>{schedule.title}</td>
                                        <td style={{ padding: '0.75rem 1rem' }}>{schedule.asset_name || '-'}</td>
                                        <td style={{ padding: '0.75rem 1rem', textAlign: 'center' }}>
                                            <span style={{
                                                padding: '0.25rem 0.5rem',
                                                borderRadius: '4px',
                                                fontSize: 'var(--text-xs)',
                                                fontWeight: 600,
                                                background: frequencyColors[schedule.frequency] || 'rgba(156, 163, 175, 0.1)',
                                                color: frequencyTextColors[schedule.frequency] || '#9ca3af',
                                            }}>
                                                {schedule.frequency}
                                            </span>
                                        </td>
                                        <td style={{ padding: '0.75rem 1rem' }}>
                                            {schedule.next_run_date ? new Date(schedule.next_run_date).toLocaleDateString() : '-'}
                                        </td>
                                        <td style={{ padding: '0.75rem 1rem', textAlign: 'center' }}>
                                            <span style={{
                                                padding: '0.25rem 0.5rem',
                                                borderRadius: '4px',
                                                fontSize: 'var(--text-xs)',
                                                fontWeight: 600,
                                                background: schedule.is_active ? 'rgba(34, 197, 94, 0.1)' : 'rgba(239, 68, 68, 0.1)',
                                                color: schedule.is_active ? '#22c55e' : '#ef4444',
                                            }}>
                                                {schedule.is_active ? 'Active' : 'Inactive'}
                                            </span>
                                        </td>
                                        <td style={{ padding: '0.75rem 1rem', textAlign: 'right' }}>
                                            <button
                                                onClick={() => handleGenerateTicket(schedule.id)}
                                                title="Generate ticket now"
                                                style={{
                                                    padding: '0.375rem 0.75rem',
                                                    background: 'rgba(36, 113, 163, 0.1)',
                                                    color: '#2471a3',
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
                                                <Play size={14} />
                                                Generate Ticket
                                            </button>
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
                            <h3 style={{ margin: '0 0 1rem 0' }}>Add Maintenance Schedule</h3>
                            <form onSubmit={handleSubmit}>
                                <div style={{ marginBottom: '1rem' }}>
                                    <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: 'var(--text-sm)', fontWeight: 500 }}>Asset<span className="required-mark"> *</span></label>
                                    <select
                                        required
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
                                        <option value="">Select an asset</option>
                                        {Array.isArray(assetsList) && assetsList.map((a: ServiceAsset) => (
                                            <option key={a.id} value={a.id}>{a.name} ({a.serial_number})</option>
                                        ))}
                                    </select>
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
                                    <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: 'var(--text-sm)', fontWeight: 500 }}>Description</label>
                                    <textarea
                                        value={formData.description}
                                        onChange={e => setFormData({ ...formData, description: e.target.value })}
                                        rows={3}
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
                                        <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: 'var(--text-sm)', fontWeight: 500 }}>Frequency<span className="required-mark"> *</span></label>
                                        <select
                                            required
                                            value={formData.frequency}
                                            onChange={e => setFormData({ ...formData, frequency: e.target.value })}
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
                                            <option value="Daily">Daily</option>
                                            <option value="Weekly">Weekly</option>
                                            <option value="Monthly">Monthly</option>
                                            <option value="Quarterly">Quarterly</option>
                                            <option value="Yearly">Yearly</option>
                                        </select>
                                    </div>
                                    <div>
                                        <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: 'var(--text-sm)', fontWeight: 500 }}>Next Run Date<span className="required-mark"> *</span></label>
                                        <input
                                            type="date"
                                            required
                                            value={formData.next_run_date}
                                            onChange={e => setFormData({ ...formData, next_run_date: e.target.value })}
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
                                        Create Schedule
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
