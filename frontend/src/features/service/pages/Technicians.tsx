import { useState } from 'react';
import { Plus, Search, UserCog, CheckCircle, XCircle, Edit } from 'lucide-react';
import { useTechnicians, useCreateTechnician, useUpdateTechnician } from '../hooks/useService';
import ServiceLayout from '../ServiceLayout';
import LoadingScreen from '../../../components/common/LoadingScreen';
import type { Technician } from '../types';

export default function Technicians() {
    const [searchTerm, setSearchTerm] = useState('');
    const [showModal, setShowModal] = useState(false);
    const [editTech, setEditTech] = useState<Technician | null>(null);
    const [availabilityFilter, setAvailabilityFilter] = useState('');

    const { data: technicians, isLoading } = useTechnicians();
    const createTech = useCreateTechnician();
    const updateTech = useUpdateTechnician();

    const techsList = (technicians?.results || technicians || []) as Technician[];

    const filteredTechs = Array.isArray(techsList) ? techsList.filter((t: Technician) => {
        const matchesSearch = t.name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
            t.employee_code?.toLowerCase().includes(searchTerm.toLowerCase());
        const matchesAvail = !availabilityFilter || 
            (availabilityFilter === 'available' && t.is_available) ||
            (availabilityFilter === 'unavailable' && !t.is_available);
        return matchesSearch && matchesAvail;
    }) : [];

    const [formData, setFormData] = useState({
        name: '',
        employee_code: '',
        email: '',
        phone: '',
        specialization: '',
        is_available: true,
    });

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        if (editTech) {
            updateTech.mutate({ id: editTech.id, ...formData }, {
                onSuccess: () => {
                    setShowModal(false);
                    setEditTech(null);
                    setFormData({ name: '', employee_code: '', email: '', phone: '', specialization: '', is_available: true });
                }
            });
        } else {
            createTech.mutate(formData, {
                onSuccess: () => {
                    setShowModal(false);
                    setFormData({ name: '', employee_code: '', email: '', phone: '', specialization: '', is_available: true });
                }
            });
        }
    };

    const openEdit = (tech: Technician) => {
        setEditTech(tech);
        setFormData({
            name: tech.name,
            employee_code: tech.employee_code,
            email: tech.email,
            phone: tech.phone,
            specialization: tech.specialization || '',
            is_available: tech.is_available,
        });
        setShowModal(true);
    };

    const toggleAvailability = (tech: Technician) => {
        updateTech.mutate({ id: tech.id, is_available: !tech.is_available });
    };

    if (isLoading) return <LoadingScreen message="Loading technicians..." />;

    return (
        <ServiceLayout>
            <div style={{ padding: '1.5rem' }}>
                <div style={{ marginBottom: '1.5rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div>
                        <h1 style={{ fontSize: 'var(--text-xl)', fontWeight: 700, color: 'var(--color-text)', margin: 0 }}>
                            Technicians
                        </h1>
                        <p style={{ color: 'var(--color-text-muted)', margin: '0.25rem 0 0 0', fontSize: 'var(--text-sm)' }}>
                            Manage service technicians and resources
                        </p>
                    </div>
                    <button
                        onClick={() => { setShowModal(true); setEditTech(null); setFormData({ name: '', employee_code: '', email: '', phone: '', specialization: '', is_available: true }); }}
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
                        Add Technician
                    </button>
                </div>

                <div style={{ display: 'flex', gap: '1rem', marginBottom: '1.5rem', flexWrap: 'wrap' }}>
                    <div style={{ flex: 1, minWidth: '200px', position: 'relative' }}>
                        <Search size={18} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: 'var(--color-text-muted)' }} />
                        <input
                            type="text"
                            placeholder="Search technicians..."
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
                        value={availabilityFilter}
                        onChange={(e) => setAvailabilityFilter(e.target.value)}
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
                        <option value="available">Available</option>
                        <option value="unavailable">Unavailable</option>
                    </select>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: '1rem' }}>
                    {filteredTechs.length === 0 ? (
                        <div style={{ gridColumn: '1 / -1', padding: '3rem', textAlign: 'center', color: 'var(--color-text-muted)', background: 'var(--color-surface)', borderRadius: '12px', border: '1px solid var(--color-border)' }}>
                            <UserCog size={48} style={{ margin: '0 auto 1rem', opacity: 0.5 }} />
                            <p>No technicians found</p>
                        </div>
                    ) : (
                        filteredTechs.map((tech: Technician) => (
                            <div key={tech.id} style={{ background: 'var(--color-surface)', borderRadius: '12px', border: '1px solid var(--color-border)', padding: '1.25rem' }}>
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1rem' }}>
                                    <div>
                                        <h3 style={{ margin: 0, fontSize: 'var(--text-base)', fontWeight: 600 }}>{tech.name}</h3>
                                        <p style={{ margin: '0.25rem 0 0 0', fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>{tech.employee_code}</p>
                                    </div>
                                    <span style={{
                                        padding: '0.25rem 0.5rem',
                                        borderRadius: '4px',
                                        fontSize: 'var(--text-xs)',
                                        fontWeight: 600,
                                        background: tech.is_available ? 'rgba(34, 197, 94, 0.1)' : 'rgba(239, 68, 68, 0.1)',
                                        color: tech.is_available ? '#22c55e' : '#ef4444',
                                    }}>
                                        {tech.is_available ? 'Available' : 'Busy'}
                                    </span>
                                </div>
                                <div style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)', marginBottom: '1rem' }}>
                                    <p style={{ margin: '0.25rem 0' }}>{tech.email}</p>
                                    <p style={{ margin: '0.25rem 0' }}>{tech.phone}</p>
                                    {tech.specialization && <p style={{ margin: '0.25rem 0' }}><strong>Specialization:</strong> {tech.specialization}</p>}
                                </div>
                                <div style={{ display: 'flex', gap: '0.5rem', borderTop: '1px solid var(--color-border)', paddingTop: '1rem' }}>
                                    <button
                                        onClick={() => toggleAvailability(tech)}
                                        style={{
                                            flex: 1,
                                            padding: '0.5rem',
                                            background: tech.is_available ? 'rgba(239, 68, 68, 0.1)' : 'rgba(34, 197, 94, 0.1)',
                                            color: tech.is_available ? '#ef4444' : '#22c55e',
                                            border: 'none',
                                            borderRadius: '6px',
                                            fontSize: 'var(--text-xs)',
                                            fontWeight: 600,
                                            cursor: 'pointer',
                                            display: 'flex',
                                            alignItems: 'center',
                                            justifyContent: 'center',
                                            gap: '0.25rem',
                                        }}
                                    >
                                        {tech.is_available ? <XCircle size={14} /> : <CheckCircle size={14} />}
                                        {tech.is_available ? 'Mark Busy' : 'Mark Available'}
                                    </button>
                                    <button
                                        onClick={() => openEdit(tech)}
                                        style={{
                                            padding: '0.5rem 0.75rem',
                                            background: 'transparent',
                                            border: '1px solid var(--color-border)',
                                            borderRadius: '6px',
                                            cursor: 'pointer',
                                            color: 'var(--color-text-muted)',
                                        }}
                                    >
                                        <Edit size={14} />
                                    </button>
                                </div>
                            </div>
                        ))
                    )}
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
                            <h3 style={{ margin: '0 0 1rem 0' }}>{editTech ? 'Edit Technician' : 'Add New Technician'}</h3>
                            <form onSubmit={handleSubmit}>
                                <div style={{ marginBottom: '1rem' }}>
                                    <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: 'var(--text-sm)', fontWeight: 500 }}>Name<span className="required-mark"> *</span></label>
                                    <input
                                        type="text"
                                        required
                                        value={formData.name}
                                        onChange={e => setFormData({ ...formData, name: e.target.value })}
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
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
                                    <div>
                                        <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: 'var(--text-sm)', fontWeight: 500 }}>Employee ID<span className="required-mark"> *</span></label>
                                        <input
                                            type="text"
                                            required
                                            value={formData.employee_code}
                                            onChange={e => setFormData({ ...formData, employee_code: e.target.value })}
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
                                        <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: 'var(--text-sm)', fontWeight: 500 }}>Specialization</label>
                                        <input
                                            type="text"
                                            value={formData.specialization}
                                            onChange={e => setFormData({ ...formData, specialization: e.target.value })}
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
                                <div style={{ marginBottom: '1rem' }}>
                                    <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: 'var(--text-sm)', fontWeight: 500 }}>Email<span className="required-mark"> *</span></label>
                                    <input
                                        type="email"
                                        required
                                        value={formData.email}
                                        onChange={e => setFormData({ ...formData, email: e.target.value })}
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
                                <div style={{ marginBottom: '1.5rem' }}>
                                    <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: 'var(--text-sm)', fontWeight: 500 }}>Phone<span className="required-mark"> *</span></label>
                                    <input
                                        type="text"
                                        required
                                        value={formData.phone}
                                        onChange={e => setFormData({ ...formData, phone: e.target.value })}
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
                                        {editTech ? 'Update' : 'Create'}
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
