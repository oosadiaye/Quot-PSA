import { useState } from 'react';
import { Plus, Search, Package, Calendar, Edit, Trash2 } from 'lucide-react';
import { useServiceAssets, useCreateServiceAsset, useUpdateServiceAsset } from '../hooks/useService';
import ServiceLayout from '../ServiceLayout';
import LoadingScreen from '../../../components/common/LoadingScreen';
import type { ServiceAsset } from '../types';

export default function ServiceAssets() {
    const [searchTerm, setSearchTerm] = useState('');
    const [showModal, setShowModal] = useState(false);
    const [editAsset, setEditAsset] = useState<ServiceAsset | null>(null);

    const { data: assets, isLoading } = useServiceAssets();
    const createAsset = useCreateServiceAsset();
    const updateAsset = useUpdateServiceAsset();

    const assetsList = (assets?.results || assets || []) as ServiceAsset[];

    const filteredAssets = Array.isArray(assetsList) ? assetsList.filter((a: ServiceAsset) =>
        a.name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
        a.serial_number?.toLowerCase().includes(searchTerm.toLowerCase())
    ) : [];

    const [formData, setFormData] = useState({
        name: '',
        serial_number: '',
        purchase_date: '',
        warranty_expiry: '',
    });

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        if (editAsset) {
            updateAsset.mutate({ id: editAsset.id, ...formData }, {
                onSuccess: () => {
                    setShowModal(false);
                    setEditAsset(null);
                    setFormData({ name: '', serial_number: '', purchase_date: '', warranty_expiry: '' });
                }
            });
        } else {
            createAsset.mutate(formData, {
                onSuccess: () => {
                    setShowModal(false);
                    setFormData({ name: '', serial_number: '', purchase_date: '', warranty_expiry: '' });
                }
            });
        }
    };

    const openEdit = (asset: ServiceAsset) => {
        setEditAsset(asset);
        setFormData({
            name: asset.name,
            serial_number: asset.serial_number,
            purchase_date: asset.purchase_date || '',
            warranty_expiry: asset.warranty_expiry || '',
        });
        setShowModal(true);
    };

    const isWarrantyExpired = (expiryDate: string) => {
        if (!expiryDate) return false;
        return new Date(expiryDate) < new Date();
    };

    if (isLoading) return <LoadingScreen message="Loading service assets..." />;

    return (
        <ServiceLayout>
            <div style={{ padding: '1.5rem' }}>
                <div style={{ marginBottom: '1.5rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div>
                        <h1 style={{ fontSize: 'var(--text-xl)', fontWeight: 700, color: 'var(--color-text)', margin: 0 }}>
                            Service Assets
                        </h1>
                        <p style={{ color: 'var(--color-text-muted)', margin: '0.25rem 0 0 0', fontSize: 'var(--text-sm)' }}>
                            Track and manage assets for maintenance
                        </p>
                    </div>
                    <button
                        onClick={() => { setShowModal(true); setEditAsset(null); setFormData({ name: '', serial_number: '', purchase_date: '', warranty_expiry: '' }); }}
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
                        Add Asset
                    </button>
                </div>

                <div style={{ marginBottom: '1.5rem', position: 'relative', maxWidth: '400px' }}>
                    <Search size={18} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: 'var(--color-text-muted)' }} />
                    <input
                        type="text"
                        placeholder="Search assets..."
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

                <div style={{ background: 'var(--color-surface)', borderRadius: '12px', border: '1px solid var(--color-border)', overflow: 'hidden' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                        <thead>
                            <tr style={{ borderBottom: '1px solid var(--color-border)' }}>
                                <th style={{ padding: '0.75rem 1rem', textAlign: 'left', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Asset Name</th>
                                <th style={{ padding: '0.75rem 1rem', textAlign: 'left', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Serial Number</th>
                                <th style={{ padding: '0.75rem 1rem', textAlign: 'left', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Purchase Date</th>
                                <th style={{ padding: '0.75rem 1rem', textAlign: 'left', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Warranty Expiry</th>
                                <th style={{ padding: '0.75rem 1rem', textAlign: 'center', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Status</th>
                                <th style={{ padding: '0.75rem 1rem', textAlign: 'right', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Actions</th>
                            </tr>
                        </thead>
                        <tbody>
                            {filteredAssets.length === 0 ? (
                                <tr>
                                    <td colSpan={6} style={{ padding: '3rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>
                                        <Package size={48} style={{ margin: '0 auto 1rem', opacity: 0.5 }} />
                                        <p>No service assets found</p>
                                    </td>
                                </tr>
                            ) : (
                                filteredAssets.map((asset: ServiceAsset) => (
                                    <tr key={asset.id} style={{ borderBottom: '1px solid var(--color-border)' }}>
                                        <td style={{ padding: '0.75rem 1rem', fontWeight: 600 }}>{asset.name}</td>
                                        <td style={{ padding: '0.75rem 1rem', fontFamily: 'monospace', fontSize: 'var(--text-sm)' }}>{asset.serial_number}</td>
                                        <td style={{ padding: '0.75rem 1rem' }}>{asset.purchase_date ? new Date(asset.purchase_date).toLocaleDateString() : '-'}</td>
                                        <td style={{ padding: '0.75rem 1rem' }}>{asset.warranty_expiry ? new Date(asset.warranty_expiry).toLocaleDateString() : '-'}</td>
                                        <td style={{ padding: '0.75rem 1rem', textAlign: 'center' }}>
                                            {asset.warranty_expiry ? (
                                                <span style={{
                                                    padding: '0.25rem 0.5rem',
                                                    borderRadius: '4px',
                                                    fontSize: 'var(--text-xs)',
                                                    fontWeight: 600,
                                                    background: isWarrantyExpired(asset.warranty_expiry) ? 'rgba(239, 68, 68, 0.1)' : 'rgba(34, 197, 94, 0.1)',
                                                    color: isWarrantyExpired(asset.warranty_expiry) ? '#ef4444' : '#22c55e',
                                                }}>
                                                    {isWarrantyExpired(asset.warranty_expiry) ? 'Expired' : 'Active'}
                                                </span>
                                            ) : (
                                                <span style={{
                                                    padding: '0.25rem 0.5rem',
                                                    borderRadius: '4px',
                                                    fontSize: 'var(--text-xs)',
                                                    fontWeight: 600,
                                                    background: 'rgba(156, 163, 175, 0.1)',
                                                    color: '#9ca3af',
                                                }}>N/A</span>
                                            )}
                                        </td>
                                        <td style={{ padding: '0.75rem 1rem', textAlign: 'right' }}>
                                            <button
                                                onClick={() => openEdit(asset)}
                                                style={{
                                                    padding: '0.375rem',
                                                    background: 'transparent',
                                                    border: 'none',
                                                    cursor: 'pointer',
                                                    color: 'var(--color-text-muted)',
                                                }}
                                            >
                                                <Edit size={16} />
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
                            <h3 style={{ margin: '0 0 1rem 0' }}>{editAsset ? 'Edit Asset' : 'Add New Asset'}</h3>
                            <form onSubmit={handleSubmit}>
                                <div style={{ marginBottom: '1rem' }}>
                                    <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: 'var(--text-sm)', fontWeight: 500 }}>Asset Name<span className="required-mark"> *</span></label>
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
                                <div style={{ marginBottom: '1rem' }}>
                                    <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: 'var(--text-sm)', fontWeight: 500 }}>Serial Number<span className="required-mark"> *</span></label>
                                    <input
                                        type="text"
                                        required
                                        value={formData.serial_number}
                                        onChange={e => setFormData({ ...formData, serial_number: e.target.value })}
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
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1.5rem' }}>
                                    <div>
                                        <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: 'var(--text-sm)', fontWeight: 500 }}>Purchase Date</label>
                                        <input
                                            type="date"
                                            value={formData.purchase_date}
                                            onChange={e => setFormData({ ...formData, purchase_date: e.target.value })}
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
                                        <label style={{ display: 'block', marginBottom: '0.5rem', fontSize: 'var(--text-sm)', fontWeight: 500 }}>Warranty Expiry</label>
                                        <input
                                            type="date"
                                            value={formData.warranty_expiry}
                                            onChange={e => setFormData({ ...formData, warranty_expiry: e.target.value })}
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
                                        {editAsset ? 'Update' : 'Create'}
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
