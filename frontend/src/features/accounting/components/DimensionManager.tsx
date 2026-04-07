import React, { useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, Edit2, Trash2, Search, Download, Upload, FileDown, Layers } from 'lucide-react';
import type { Dimension, DimensionFormData, DimensionType, BulkImportResult } from '../hooks/useDimensions';
import { downloadDimensionTemplate, exportDimensions } from '../hooks/useDimensions';
import PageHeader from '../../../components/PageHeader';
import LoadingScreen from '../../../components/common/LoadingScreen';
import { useDialog } from '../../../hooks/useDialog';
import '../styles/glassmorphism.css';

interface DimensionManagerProps {
    title: string;
    dimensionType: DimensionType;
    dimensions: Dimension[] | undefined;
    isLoading: boolean;
    onCreate: (data: DimensionFormData) => void;
    onUpdate: (id: number, data: DimensionFormData) => void;
    onDelete: (id: number) => void;
    onBulkImport: (file: File) => Promise<BulkImportResult>;
    isCreating?: boolean;
    isUpdating?: boolean;
    isImporting?: boolean;
}

const DimensionManager: React.FC<DimensionManagerProps> = ({
    title,
    dimensionType,
    dimensions,
    isLoading,
    onCreate,
    onUpdate,
    onDelete,
    onBulkImport,
    isCreating,
    isUpdating,
    isImporting,
}) => {
    const { showAlert, showConfirm } = useDialog();
    const [searchTerm, setSearchTerm] = useState('');
    const [showForm, setShowForm] = useState(false);
    const [editingId, setEditingId] = useState<number | null>(null);
    const [formData, setFormData] = useState<DimensionFormData>({
        code: '',
        name: '',
        description: '',
        is_active: true,
    });
    const [importResult, setImportResult] = useState<BulkImportResult | null>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);

    const filteredDimensions = (Array.isArray(dimensions) ? dimensions : [])?.filter(
        (dim) =>
            dim.code.toLowerCase().includes(searchTerm.toLowerCase()) ||
            dim.name.toLowerCase().includes(searchTerm.toLowerCase())
    );

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        if (editingId) {
            onUpdate(editingId, formData);
        } else {
            onCreate(formData);
        }
        resetForm();
    };

    const handleEdit = (dimension: Dimension) => {
        setEditingId(dimension.id);
        setFormData({
            code: dimension.code,
            name: dimension.name,
            description: dimension.description || '',
            is_active: dimension.is_active,
        });
        setShowForm(true);
    };

    const handleDelete = async (id: number, name: string) => {
        if (await showConfirm(`Delete "${name}"? This action cannot be undone.`)) {
            onDelete(id);
        }
    };

    const resetForm = () => {
        setFormData({
            code: '',
            name: '',
            description: '',
            is_active: true,
        });
        setEditingId(null);
        setShowForm(false);
    };

    const handleDownloadTemplate = async () => {
        try {
            await downloadDimensionTemplate(dimensionType);
        } catch {
            showAlert('Failed to download template. Please try again.');
        }
    };

    const handleExport = async (format: 'csv' | 'xlsx' = 'csv') => {
        if (!dimensions || dimensions.length === 0) {
            showAlert('No data to export', 'warning');
            return;
        }
        try {
            await exportDimensions(dimensionType, format);
        } catch {
            showAlert('Failed to export data. Please try again.');
        }
    };

    const handleImport = async (event: React.ChangeEvent<HTMLInputElement>) => {
        const file = event.target.files?.[0];
        if (!file) return;

        try {
            const result = await onBulkImport(file);
            setImportResult(result);
        } catch {
            showAlert('Failed to import file. Please check the format and try again.');
        }

        if (fileInputRef.current) {
            fileInputRef.current.value = '';
        }
    };

    if (isLoading) {
        return <LoadingScreen message={`Loading ${title.toLowerCase()}...`} />;
    }

    return (
        <div>
            {/* Import Result Banner */}
            {importResult && (
                <div
                    className="glass-card"
                    style={{
                        marginBottom: '1.5rem',
                        padding: '1.25rem 1.5rem',
                        background: importResult.errors.length > 0 ? 'rgba(251, 191, 36, 0.1)' : 'rgba(34, 197, 94, 0.1)',
                        border: `1px solid ${importResult.errors.length > 0 ? 'rgba(251, 191, 36, 0.3)' : 'rgba(34, 197, 94, 0.3)'}`,
                        animation: 'fadeInUp 0.3s ease-out',
                    }}
                >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                        <div>
                            <h3 style={{ fontSize: 'var(--text-base)', fontWeight: 600, color: 'var(--color-text)', marginBottom: '0.5rem' }}>
                                Import Complete
                            </h3>
                            <div style={{ display: 'flex', gap: '1.5rem', fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)' }}>
                                <span>Created: <strong style={{ color: '#22c55e' }}>{importResult.created}</strong></span>
                                <span>Updated: <strong style={{ color: '#2471a3' }}>{importResult.updated}</strong></span>
                                <span>Skipped: <strong style={{ color: '#a1a1aa' }}>{importResult.skipped}</strong></span>
                                {importResult.errors.length > 0 && (
                                    <span>Errors: <strong style={{ color: '#ef4444' }}>{importResult.errors.length}</strong></span>
                                )}
                            </div>
                            {importResult.errors.length > 0 && (
                                <div style={{ marginTop: '0.75rem', fontSize: 'var(--text-xs)', color: '#ef4444' }}>
                                    {importResult.errors.slice(0, 5).map((err, i) => (
                                        <div key={i}>{err}</div>
                                    ))}
                                    {importResult.errors.length > 5 && (
                                        <div style={{ color: 'var(--color-text-muted)' }}>
                                            ...and {importResult.errors.length - 5} more errors
                                        </div>
                                    )}
                                </div>
                            )}
                        </div>
                        <button
                            onClick={() => setImportResult(null)}
                            style={{
                                background: 'none',
                                border: 'none',
                                color: 'var(--color-text-muted)',
                                cursor: 'pointer',
                                fontSize: 'var(--text-lg)',
                                lineHeight: 1,
                            }}
                        >
                            ×
                        </button>
                    </div>
                </div>
            )}

            <PageHeader
                title={title}
                subtitle={`Manage ${title.toLowerCase()} for multi-dimensional accounting`}
                icon={<Layers size={22} />}
                actions={
                    <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
                        <button
                            onClick={handleDownloadTemplate}
                            className="glass-button"
                            style={{
                                display: 'flex', alignItems: 'center', gap: '0.5rem',
                                padding: '0.75rem 1.5rem', background: 'var(--color-surface)',
                                color: 'var(--color-text)', border: '1px solid var(--color-border)',
                                borderRadius: '8px', cursor: 'pointer', fontWeight: 500,
                            }}
                            title="Download Import Template (CSV)"
                        >
                            <FileDown size={20} /> Template
                        </button>
                        <button
                            onClick={() => handleExport('csv')}
                            className="glass-button"
                            style={{
                                display: 'flex', alignItems: 'center', gap: '0.5rem',
                                padding: '0.75rem 1.5rem', background: 'var(--color-surface)',
                                color: 'var(--color-text)', border: '1px solid var(--color-border)',
                                borderRadius: '8px', cursor: 'pointer', fontWeight: 500,
                            }}
                            title="Export to CSV"
                        >
                            <Download size={20} /> CSV
                        </button>
                        <button
                            onClick={() => handleExport('xlsx')}
                            className="glass-button"
                            style={{
                                display: 'flex', alignItems: 'center', gap: '0.5rem',
                                padding: '0.75rem 1.5rem', background: 'var(--color-surface)',
                                color: 'var(--color-text)', border: '1px solid var(--color-border)',
                                borderRadius: '8px', cursor: 'pointer', fontWeight: 500,
                            }}
                            title="Export to Excel"
                        >
                            <Download size={20} /> Excel
                        </button>
                        <input
                            ref={fileInputRef}
                            type="file"
                            accept=".csv,.xlsx"
                            onChange={handleImport}
                            style={{ display: 'none' }}
                        />
                        <button
                            onClick={() => fileInputRef.current?.click()}
                            disabled={isImporting}
                            className="glass-button"
                            style={{
                                display: 'flex', alignItems: 'center', gap: '0.5rem',
                                padding: '0.75rem 1.5rem', background: 'var(--color-surface)',
                                color: 'var(--color-text)', border: '1px solid var(--color-border)',
                                borderRadius: '8px', cursor: isImporting ? 'not-allowed' : 'pointer',
                                fontWeight: 500, opacity: isImporting ? 0.6 : 1,
                            }}
                            title="Import from CSV or Excel"
                        >
                            <Upload size={20} /> {isImporting ? 'Importing...' : 'Import'}
                        </button>
                        <button
                            onClick={() => setShowForm(!showForm)}
                            className="glass-button"
                            style={{
                                display: 'flex', alignItems: 'center', gap: '0.5rem',
                                padding: '0.75rem 1.5rem', background: 'var(--color-primary)',
                                color: 'white', border: 'none', borderRadius: '8px',
                                cursor: 'pointer', fontWeight: 500, transition: 'all 0.2s',
                            }}
                        >
                            <Plus size={20} /> Add New
                        </button>
                    </div>
                }
            />

            {/* Form */}
            {showForm && (
                <div className="glass-card" style={{ marginBottom: '2rem', padding: '1.5rem', animation: 'fadeInUp 0.3s ease-out' }}>
                    <h2 style={{ fontSize: 'var(--text-lg)', fontWeight: 600, color: 'var(--color-text)', marginBottom: '1.5rem' }}>
                        {editingId ? 'Edit' : 'Create New'} {title.slice(0, -1)}
                    </h2>
                    <form onSubmit={handleSubmit}>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '1rem', marginBottom: '1rem' }}>
                            <div>
                                <label style={{ display: 'block', fontSize: 'var(--text-sm)', fontWeight: 500, color: 'var(--color-text-muted)', marginBottom: '0.5rem' }}>
                                    Code *
                                </label>
                                <input
                                    type="text"
                                    required
                                    value={formData.code}
                                    onChange={(e) => setFormData({ ...formData, code: e.target.value })}
                                    style={{
                                        width: '100%',
                                        padding: '0.75rem',
                                        borderRadius: '8px',
                                        border: '1px solid var(--color-border)',
                                        background: 'var(--color-surface)',
                                        color: 'var(--color-text)',
                                        fontSize: 'var(--text-sm)',
                                    }}
                                    placeholder="Enter code"
                                />
                            </div>
                            <div>
                                <label style={{ display: 'block', fontSize: 'var(--text-sm)', fontWeight: 500, color: 'var(--color-text-muted)', marginBottom: '0.5rem' }}>
                                    Name *
                                </label>
                                <input
                                    type="text"
                                    required
                                    value={formData.name}
                                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                                    style={{
                                        width: '100%',
                                        padding: '0.75rem',
                                        borderRadius: '8px',
                                        border: '1px solid var(--color-border)',
                                        background: 'var(--color-surface)',
                                        color: 'var(--color-text)',
                                        fontSize: 'var(--text-sm)',
                                    }}
                                    placeholder="Enter name"
                                />
                            </div>
                        </div>
                        <div style={{ marginBottom: '1rem' }}>
                            <label style={{ display: 'block', fontSize: 'var(--text-sm)', fontWeight: 500, color: 'var(--color-text-muted)', marginBottom: '0.5rem' }}>
                                Description
                            </label>
                            <textarea
                                value={formData.description}
                                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                                style={{
                                    width: '100%',
                                    padding: '0.75rem',
                                    borderRadius: '8px',
                                    border: '1px solid var(--color-border)',
                                    background: 'var(--color-surface)',
                                    color: 'var(--color-text)',
                                    fontSize: 'var(--text-sm)',
                                    minHeight: '80px',
                                }}
                                placeholder="Enter description"
                            />
                        </div>
                        <div style={{ marginBottom: '1.5rem', display: 'flex', alignItems: 'center' }}>
                            <input
                                type="checkbox"
                                id="is_active"
                                checked={formData.is_active}
                                onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
                                style={{ width: '16px', height: '16px', accentColor: 'var(--color-primary)' }}
                            />
                            <label htmlFor="is_active" style={{ marginLeft: '0.5rem', fontSize: 'var(--text-sm)', color: 'var(--color-text)' }}>
                                Active
                            </label>
                        </div>
                        <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'flex-end' }}>
                            <button
                                type="button"
                                onClick={resetForm}
                                style={{
                                    padding: '0.75rem 1.5rem',
                                    borderRadius: '8px',
                                    border: '1px solid var(--color-border)',
                                    background: 'var(--color-surface)',
                                    color: 'var(--color-text)',
                                    cursor: 'pointer',
                                    fontWeight: 500,
                                }}
                            >
                                Cancel
                            </button>
                            <button
                                type="submit"
                                disabled={isCreating || isUpdating}
                                style={{
                                    padding: '0.75rem 1.5rem',
                                    borderRadius: '8px',
                                    border: 'none',
                                    background: 'var(--color-primary)',
                                    color: 'white',
                                    cursor: isCreating || isUpdating ? 'not-allowed' : 'pointer',
                                    fontWeight: 500,
                                    opacity: isCreating || isUpdating ? 0.6 : 1,
                                }}
                            >
                                {isCreating || isUpdating ? 'Saving...' : editingId ? 'Update' : 'Create'}
                            </button>
                        </div>
                    </form>
                </div>
            )}

            {/* Search */}
            <div className="glass-card" style={{ marginBottom: '1.5rem', padding: '1rem' }}>
                <div style={{ position: 'relative' }}>
                    <Search style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: 'var(--color-text-muted)' }} size={20} />
                    <input
                        type="text"
                        placeholder="Search by code or name..."
                        value={searchTerm}
                        onChange={(e) => setSearchTerm(e.target.value)}
                        style={{
                            width: '100%',
                            paddingLeft: '2.75rem',
                            paddingRight: '1rem',
                            paddingTop: '0.75rem',
                            paddingBottom: '0.75rem',
                            borderRadius: '8px',
                            border: '1px solid var(--color-border)',
                            background: 'var(--color-surface)',
                            color: 'var(--color-text)',
                            fontSize: 'var(--text-sm)',
                        }}
                    />
                </div>
            </div>

            {/* Table */}
            <div className="glass-card" style={{ overflow: 'hidden' }}>
                <div style={{ overflowX: 'auto' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                        <thead>
                            <tr style={{ borderBottom: '1px solid var(--color-border)' }}>
                                <th style={{ padding: '1rem 1.5rem', textAlign: 'left', fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)' }}>
                                    Code
                                </th>
                                <th style={{ padding: '1rem 1.5rem', textAlign: 'left', fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)' }}>
                                    Name
                                </th>
                                <th style={{ padding: '1rem 1.5rem', textAlign: 'left', fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)' }}>
                                    Description
                                </th>
                                <th style={{ padding: '1rem 1.5rem', textAlign: 'left', fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)' }}>
                                    Status
                                </th>
                                <th style={{ padding: '1rem 1.5rem', textAlign: 'right', fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)' }}>
                                    Actions
                                </th>
                            </tr>
                        </thead>
                        <tbody>
                            {filteredDimensions && filteredDimensions.length > 0 ? (
                                filteredDimensions.map((dimension, index) => (
                                    <tr
                                        key={dimension.id}
                                        style={{
                                            borderBottom: '1px solid var(--color-border)',
                                            animation: `fadeInUp 0.3s ease-out ${index * 0.05}s both`,
                                        }}
                                    >
                                        <td style={{ padding: '1rem 1.5rem', color: 'var(--color-text)', fontWeight: 500 }}>
                                            {dimension.code}
                                        </td>
                                        <td style={{ padding: '1rem 1.5rem', color: 'var(--color-text)' }}>
                                            {dimension.name}
                                        </td>
                                        <td style={{ padding: '1rem 1.5rem', color: 'var(--color-text-muted)', fontSize: 'var(--text-sm)' }}>
                                            {dimension.description || '-'}
                                        </td>
                                        <td style={{ padding: '1rem 1.5rem' }}>
                                            <span
                                                style={{
                                                    display: 'inline-block',
                                                    padding: '0.25rem 0.75rem',
                                                    borderRadius: '9999px',
                                                    fontSize: 'var(--text-xs)',
                                                    fontWeight: 500,
                                                    background: dimension.is_active ? 'rgba(34, 197, 94, 0.1)' : 'rgba(239, 68, 68, 0.1)',
                                                    color: dimension.is_active ? '#22c55e' : '#ef4444',
                                                }}
                                            >
                                                {dimension.is_active ? 'Active' : 'Inactive'}
                                            </span>
                                        </td>
                                        <td style={{ padding: '1rem 1.5rem' }}>
                                            <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}>
                                                <button
                                                    onClick={() => handleEdit(dimension)}
                                                    style={{
                                                        padding: '0.5rem',
                                                        borderRadius: '8px',
                                                        border: 'none',
                                                        background: 'var(--color-surface)',
                                                        color: 'var(--color-primary)',
                                                        cursor: 'pointer',
                                                        transition: 'all 0.2s',
                                                    }}
                                                    title="Edit"
                                                >
                                                    <Edit2 size={16} />
                                                </button>
                                                <button
                                                    onClick={() => handleDelete(dimension.id, dimension.name)}
                                                    style={{
                                                        padding: '0.5rem',
                                                        borderRadius: '8px',
                                                        border: 'none',
                                                        background: 'rgba(239, 68, 68, 0.1)',
                                                        color: '#ef4444',
                                                        cursor: 'pointer',
                                                        transition: 'all 0.2s',
                                                    }}
                                                    title="Delete"
                                                >
                                                    <Trash2 size={16} />
                                                </button>
                                            </div>
                                        </td>
                                    </tr>
                                ))
                            ) : (
                                <tr>
                                    <td colSpan={5} style={{ padding: '3rem 1.5rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>
                                        No {title.toLowerCase()} found
                                    </td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    );
};

export default DimensionManager;
