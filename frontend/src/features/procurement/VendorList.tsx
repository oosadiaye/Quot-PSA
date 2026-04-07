import { useState, useRef, useEffect } from 'react';
import { useVendors, useCreateVendor, useVendorCategories } from './hooks/useProcurement';
import {
    ShoppingBag, Star, Phone, Plus, X, Save, LayoutGrid, List, Wallet, Building,
    ChevronDown, Download, Upload, FileSpreadsheet, CheckCircle2, AlertTriangle,
} from 'lucide-react';
import Sidebar from '../../components/Sidebar';
import LoadingScreen from '../../components/common/LoadingScreen';
import PageHeader from '../../components/PageHeader';
import VendorHistoryModal from './VendorHistoryModal';
import { useCurrency } from '../../context/CurrencyContext';

const VendorList = () => {
    const [currentPage, setCurrentPage] = useState(1);
    const pageSize = 20;
    const { data: vendorsRaw, isLoading } = useVendors({ page: currentPage, page_size: pageSize });
    const vendors = vendorsRaw?.results || (Array.isArray(vendorsRaw) ? vendorsRaw : []);
    const totalCount = vendorsRaw?.count || vendors.length;
    const totalPages = Math.ceil(totalCount / pageSize);
    const createVendor = useCreateVendor();
    const { data: vendorCategories } = useVendorCategories();
    const { formatCurrency } = useCurrency();
    const [showForm, setShowForm] = useState(false);
    const [historyVendor, setHistoryVendor] = useState<any>(null);
    const [form, setForm] = useState({
        name: '', code: '', tax_id: '', address: '', email: '', phone: '', is_active: true, category: '',
    });
    const [error, setError] = useState('');
    const [viewMode, setViewMode] = useState<'card' | 'list'>('card');
    const [actionsOpen, setActionsOpen] = useState(false);
    const [importing, setImporting] = useState(false);
    const [toast, setToast] = useState<{ msg: string; ok: boolean } | null>(null);
    const actionsRef = useRef<HTMLDivElement>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);

    useEffect(() => {
        const handleClickOutside = (e: MouseEvent) => {
            if (actionsRef.current && !actionsRef.current.contains(e.target as Node)) setActionsOpen(false);
        };
        document.addEventListener('mousedown', handleClickOutside);
        return () => document.removeEventListener('mousedown', handleClickOutside);
    }, []);

    const flash = (msg: string, ok = true) => {
        setToast({ msg, ok });
        setTimeout(() => setToast(null), 4000);
    };

    const csvQuote = (val: string) => `"${String(val).replace(/"/g, '""')}"`;

    const parseCSVRow = (line: string): string[] => {
        const result: string[] = [];
        let current = '';
        let inQuotes = false;
        for (let i = 0; i < line.length; i++) {
            const ch = line[i];
            if (inQuotes) {
                if (ch === '"' && line[i + 1] === '"') { current += '"'; i++; }
                else if (ch === '"') { inQuotes = false; }
                else { current += ch; }
            } else {
                if (ch === '"') { inQuotes = true; }
                else if (ch === ',') { result.push(current.trim()); current = ''; }
                else { current += ch; }
            }
        }
        result.push(current.trim());
        return result;
    };

    const handleDownloadTemplate = () => {
        setActionsOpen(false);
        const headers = ['name', 'code', 'tax_id', 'email', 'phone', 'address', 'is_active'];
        const sample = ['TechCorp Solutions', 'VND-001', 'TIN-12345678', 'info@techcorp.com', '+234-801-234-5678', '15 Marina Road, Lagos', 'true'];
        const csv = [headers.map(csvQuote).join(','), sample.map(csvQuote).join(',')].join('\n');
        const blob = new Blob([csv], { type: 'text/csv' });
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url; a.download = 'supplier_bulk_template.csv'; a.click();
        window.URL.revokeObjectURL(url);
    };

    const handleExportVendors = async () => {
        setActionsOpen(false);
        try {
            const { data } = await (await import('../../api/client')).default.get('/procurement/vendors/', { params: { page_size: 99999 } });
            const allVendors = data.results || data || [];
            if (!allVendors.length) { flash('No suppliers to export.', false); return; }
            const headers = ['Code', 'Name', 'Tax ID', 'Email', 'Phone', 'Address', 'Status', 'Current Balance'];
            const rows = allVendors.map((v: any) => [
                v.code, v.name, v.tax_id || '', v.email || '', v.phone || '', v.address || '',
                v.is_active ? 'Active' : 'Inactive', v.current_balance || '0',
            ].map(csvQuote).join(','));
            const csv = [headers.map(csvQuote).join(','), ...rows].join('\n');
            const blob = new Blob([csv], { type: 'text/csv' });
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url; a.download = `suppliers_${new Date().toISOString().split('T')[0]}.csv`; a.click();
            window.URL.revokeObjectURL(url);
            flash(`Exported ${allVendors.length} supplier(s).`);
        } catch { flash('Failed to export suppliers.', false); }
    };

    const handleImportCSV = async (e: React.ChangeEvent<HTMLInputElement>) => {
        setActionsOpen(false);
        const file = e.target.files?.[0];
        if (!file) return;
        setImporting(true);
        try {
            const text = await file.text();
            const lines = text.split('\n').map(l => l.trim()).filter(Boolean);
            if (lines.length < 2) { flash('CSV must have a header row and at least one data row.', false); setImporting(false); return; }
            const headers = parseCSVRow(lines[0]);
            let created = 0;
            let errors = 0;
            const errorDetails: string[] = [];
            for (let i = 1; i < lines.length; i++) {
                const values = parseCSVRow(lines[i]);
                const row: Record<string, any> = {};
                headers.forEach((h, idx) => { row[h] = values[idx] || ''; });
                if (!row.name || !row.code) { errors++; errorDetails.push(`Row ${i + 1}: name and code are required`); continue; }
                try {
                    await createVendor.mutateAsync({
                        name: row.name,
                        code: row.code,
                        tax_id: row.tax_id || '',
                        email: row.email || '',
                        phone: row.phone || '',
                        address: row.address || '',
                        is_active: row.is_active !== 'false' && row.is_active !== 'Inactive',
                    });
                    created++;
                } catch (err: any) {
                    errors++;
                    const data = err?.response?.data;
                    const msg = data ? Object.values(data).flat().join('; ') : 'Unknown error';
                    errorDetails.push(`Row ${i + 1} (${row.code}): ${msg}`);
                }
            }
            if (created > 0 && errors === 0) {
                flash(`Successfully imported ${created} supplier(s).`);
            } else if (created > 0) {
                flash(`Imported ${created} supplier(s), ${errors} failed. ${errorDetails.slice(0, 3).join(' | ')}`, false);
            } else {
                flash(`Import failed. ${errorDetails.slice(0, 3).join(' | ')}`, false);
            }
        } catch {
            flash('Failed to parse CSV file.', false);
        } finally {
            setImporting(false);
            if (fileInputRef.current) fileInputRef.current.value = '';
        }
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError('');
        if (!form.name.trim() || !form.code.trim()) {
            setError('Name and Code are required.');
            return;
        }
        if (!form.category) {
            setError('Vendor Category is required.');
            return;
        }
        try {
            await createVendor.mutateAsync({
                ...form,
                category: parseInt(form.category),
            });
            setShowForm(false);
            setForm({ name: '', code: '', tax_id: '', address: '', email: '', phone: '', is_active: true, category: '' });
        } catch (err: any) {
            const data = err?.response?.data;
            if (data?.detail) {
                setError(data.detail);
            } else if (data && typeof data === 'object') {
                const msgs = Object.entries(data).map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(', ') : v}`);
                setError(msgs.join(' | '));
            } else {
                setError(err?.message || 'Failed to create vendor.');
            }
        }
    };

    const thStyle: React.CSSProperties = {
        padding: '0.75rem 1rem', fontSize: 'var(--text-xs)', fontWeight: 700,
        textTransform: 'uppercase', letterSpacing: '0.05em',
        color: 'var(--color-text-muted)', whiteSpace: 'nowrap',
    };
    const tdStyle: React.CSSProperties = {
        padding: '0.75rem 1rem', color: 'var(--color-text)', whiteSpace: 'nowrap',
    };

    if (isLoading) {
        return <LoadingScreen message="Loading suppliers..." />;
    }

    return (
        <div style={{ display: 'flex' }}>
            <Sidebar />
            <main style={{ flex: 1, marginLeft: '260px', padding: '2.5rem' }}>
                {/* Toast */}
                {toast && (
                    <div style={{
                        position: 'fixed', top: '20px', right: '24px', zIndex: 1100,
                        background: toast.ok ? '#d1fae5' : '#fee2e2',
                        border: `1px solid ${toast.ok ? '#6ee7b7' : '#fca5a5'}`,
                        borderRadius: '10px', padding: '12px 18px', display: 'flex', alignItems: 'center', gap: '10px',
                        color: toast.ok ? '#065f46' : '#991b1b', boxShadow: '0 4px 24px rgba(0,0,0,0.12)',
                        fontSize: '13px', fontWeight: 500, maxWidth: '420px',
                    }}>
                        {toast.ok ? <CheckCircle2 size={16} /> : <AlertTriangle size={16} />}
                        {toast.msg}
                        <button onClick={() => setToast(null)} style={{ marginLeft: 'auto', background: 'none', border: 'none', cursor: 'pointer', color: 'inherit' }}><X size={14} /></button>
                    </div>
                )}

                <input ref={fileInputRef} type="file" accept=".csv" style={{ display: 'none' }} onChange={handleImportCSV} />

                <PageHeader
                    title="Supplier Master"
                    subtitle="Manage your organization's verified vendors and service providers."
                    icon={<Building size={22} />}
                    actions={
                        <>
                            <div style={{ display: 'flex', border: '1px solid rgba(255,255,255,0.3)', borderRadius: '8px', overflow: 'hidden' }}>
                                <button type="button" onClick={() => setViewMode('card')}
                                    style={{
                                        padding: '0.5rem 0.75rem', border: 'none', cursor: 'pointer',
                                        background: viewMode === 'card' ? 'rgba(255,255,255,0.25)' : 'transparent',
                                        color: 'white',
                                    }}>
                                    <LayoutGrid size={18} />
                                </button>
                                <button type="button" onClick={() => setViewMode('list')}
                                    style={{
                                        padding: '0.5rem 0.75rem', border: 'none', cursor: 'pointer',
                                        borderLeft: '1px solid rgba(255,255,255,0.3)',
                                        background: viewMode === 'list' ? 'rgba(255,255,255,0.25)' : 'transparent',
                                        color: 'white',
                                    }}>
                                    <List size={18} />
                                </button>
                            </div>

                            {/* Actions Dropdown */}
                            <div ref={actionsRef} style={{ position: 'relative' }}>
                                <button onClick={() => setActionsOpen(!actionsOpen)} style={{
                                    display: 'flex', alignItems: 'center', gap: '6px',
                                    padding: '0.6rem 1rem', borderRadius: '8px',
                                    background: 'rgba(255,255,255,0.15)', border: '1px solid rgba(255,255,255,0.25)',
                                    color: 'white', cursor: 'pointer', fontSize: '13px', fontWeight: 600,
                                }}>
                                    Actions <ChevronDown size={14} style={{ transition: 'transform 0.2s', transform: actionsOpen ? 'rotate(180deg)' : '' }} />
                                </button>
                                {actionsOpen && (
                                    <div style={{
                                        position: 'absolute', right: 0, top: 'calc(100% + 6px)', minWidth: '230px',
                                        background: '#fff', borderRadius: '10px', border: '1px solid #e2e8f0',
                                        boxShadow: '0 8px 24px rgba(0,0,0,0.12)', zIndex: 50, overflow: 'hidden',
                                    }}>
                                        <button onClick={handleDownloadTemplate} style={{
                                            width: '100%', display: 'flex', alignItems: 'center', gap: '10px',
                                            padding: '11px 14px', background: 'none', border: 'none', cursor: 'pointer',
                                            fontSize: '13px', color: '#1e293b', transition: 'background 0.15s',
                                        }}
                                            onMouseEnter={e => (e.currentTarget.style.background = '#f8fafc')}
                                            onMouseLeave={e => (e.currentTarget.style.background = 'none')}>
                                            <FileSpreadsheet size={15} color="#4f46e5" />
                                            <div style={{ textAlign: 'left' }}>
                                                <span style={{ fontWeight: 600, display: 'block' }}>Download Template</span>
                                                <span style={{ fontSize: '11px', color: '#94a3b8' }}>CSV for bulk supplier import</span>
                                            </div>
                                        </button>
                                        <div style={{ height: '1px', background: '#e2e8f0' }} />
                                        <button onClick={() => { setActionsOpen(false); fileInputRef.current?.click(); }} disabled={importing} style={{
                                            width: '100%', display: 'flex', alignItems: 'center', gap: '10px',
                                            padding: '11px 14px', background: 'none', border: 'none', cursor: 'pointer',
                                            fontSize: '13px', color: '#1e293b', transition: 'background 0.15s',
                                            opacity: importing ? 0.5 : 1,
                                        }}
                                            onMouseEnter={e => (e.currentTarget.style.background = '#f8fafc')}
                                            onMouseLeave={e => (e.currentTarget.style.background = 'none')}>
                                            <Upload size={15} color="#4f46e5" />
                                            <div style={{ textAlign: 'left' }}>
                                                <span style={{ fontWeight: 600, display: 'block' }}>{importing ? 'Importing…' : 'Import Suppliers'}</span>
                                                <span style={{ fontSize: '11px', color: '#94a3b8' }}>Bulk create from CSV file</span>
                                            </div>
                                        </button>
                                        <div style={{ height: '1px', background: '#e2e8f0' }} />
                                        <button onClick={handleExportVendors} style={{
                                            width: '100%', display: 'flex', alignItems: 'center', gap: '10px',
                                            padding: '11px 14px', background: 'none', border: 'none', cursor: 'pointer',
                                            fontSize: '13px', color: '#1e293b', transition: 'background 0.15s',
                                            opacity: vendors?.length ? 1 : 0.5,
                                            pointerEvents: vendors?.length ? 'auto' : 'none',
                                        }}
                                            onMouseEnter={e => (e.currentTarget.style.background = '#f8fafc')}
                                            onMouseLeave={e => (e.currentTarget.style.background = 'none')}>
                                            <Download size={15} color="#4f46e5" />
                                            <div style={{ textAlign: 'left' }}>
                                                <span style={{ fontWeight: 600, display: 'block' }}>Export Suppliers</span>
                                                <span style={{ fontSize: '11px', color: '#94a3b8' }}>Download as CSV</span>
                                            </div>
                                        </button>
                                    </div>
                                )}
                            </div>

                            <button className="btn btn-primary" onClick={() => setShowForm(true)}
                                style={{ background: 'rgba(255,255,255,0.18)', color: 'white', border: '1px solid rgba(255,255,255,0.25)' }}>
                                <Plus size={18} /> Add New Vendor
                            </button>
                        </>
                    }
                />

                {showForm && (
                    <div className="card animate-fade" style={{ marginBottom: '2rem', padding: '1.5rem' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem' }}>
                            <h2 style={{ fontSize: 'var(--text-lg)', fontWeight: 600, color: 'var(--color-text)', margin: 0 }}>New Vendor</h2>
                            <button className="btn btn-outline" style={{ padding: '0.375rem' }} onClick={() => { setShowForm(false); setError(''); setForm({ name: '', code: '', tax_id: '', address: '', email: '', phone: '', is_active: true, category: '' }); }}>
                                <X size={18} />
                            </button>
                        </div>

                        {error && (
                            <div style={{ padding: '0.75rem 1rem', marginBottom: '1rem', borderRadius: '8px', background: 'rgba(239,68,68,0.1)', color: 'var(--color-error)', fontSize: 'var(--text-sm)' }}>
                                {error}
                            </div>
                        )}

                        <form onSubmit={handleSubmit}>
                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                                <div>
                                    <label className="label">Vendor Name *</label>
                                    <input type="text" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} placeholder="Enter vendor name" required />
                                </div>
                                <div>
                                    <label className="label">Vendor Code *</label>
                                    <input type="text" value={form.code} onChange={e => setForm({ ...form, code: e.target.value })} placeholder="e.g. VND-001" required />
                                </div>
                                <div>
                                    <label className="label">Email</label>
                                    <input type="email" value={form.email} onChange={e => setForm({ ...form, email: e.target.value })} placeholder="vendor@example.com" />
                                </div>
                                <div>
                                    <label className="label">Phone</label>
                                    <input type="text" value={form.phone} onChange={e => setForm({ ...form, phone: e.target.value })} placeholder="+234..." />
                                </div>
                                <div>
                                    <label className="label">Tax ID</label>
                                    <input type="text" value={form.tax_id} onChange={e => setForm({ ...form, tax_id: e.target.value })} placeholder="Tax identification number" />
                                </div>
                                <div>
                                    <label className="label">Status</label>
                                    <select value={form.is_active ? 'true' : 'false'} onChange={e => setForm({ ...form, is_active: e.target.value === 'true' })}>
                                        <option value="true">Active</option>
                                        <option value="false">Inactive</option>
                                    </select>
                                </div>
                                <div style={{ gridColumn: '1 / -1' }}>
                                    <label className="label">Vendor Category *</label>
                                    <select
                                        value={form.category}
                                        onChange={e => setForm({ ...form, category: e.target.value })}
                                        required
                                    >
                                        <option value="">Select a category...</option>
                                        {(vendorCategories || []).filter((c: any) => c.is_active).map((cat: any) => (
                                            <option key={cat.id} value={cat.id}>{cat.name} ({cat.code})</option>
                                        ))}
                                    </select>
                                </div>
                                <div style={{ gridColumn: '1 / -1' }}>
                                    <label className="label">Address</label>
                                    <textarea value={form.address} onChange={e => setForm({ ...form, address: e.target.value })} placeholder="Full address" rows={2} style={{ resize: 'vertical' }} />
                                </div>
                            </div>
                            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '1.25rem' }}>
                                <button type="button" className="btn btn-outline" onClick={() => { setShowForm(false); setError(''); setForm({ name: '', code: '', tax_id: '', address: '', email: '', phone: '', is_active: true, category: '' }); }}>Cancel</button>
                                <button type="submit" className="btn btn-primary" disabled={createVendor.isPending}>
                                    <Save size={16} /> {createVendor.isPending ? 'Saving...' : 'Save Vendor'}
                                </button>
                            </div>
                        </form>
                    </div>
                )}

                {viewMode === 'card' ? (
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(350px, 1fr))', gap: '1.5rem' }}>
                        {vendors?.map((vendor: any) => (
                            <div key={vendor.id} className="card animate-fade" style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                                    <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
                                        <div style={{
                                            width: '48px', height: '48px', background: 'var(--color-primary)',
                                            borderRadius: '12px', color: 'white'
                                        }} className="flex-center">
                                            <ShoppingBag size={24} />
                                        </div>
                                        <div>
                                            <h3 style={{ fontSize: 'var(--text-lg)', color: 'var(--color-text)' }}>{vendor.name}</h3>
                                            <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', fontWeight: 600 }}>{vendor.code}</span>
                                            {vendor.category_name && (
                                                <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', fontWeight: 500, display: 'block' }}>
                                                    {vendor.category_name}
                                                </span>
                                            )}
                                        </div>
                                    </div>
                                    <Star size={18} style={{ color: 'var(--color-cta)' }} />
                                </div>
                                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', fontSize: 'var(--text-sm)' }}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--color-text-muted)' }}>
                                        <Phone size={14} /> {vendor.phone || 'No phone provided'}
                                    </div>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                        <Wallet size={14} style={{ color: 'var(--color-text-muted)' }} />
                                        <span style={{ fontWeight: 600, color: Number(vendor.current_balance) > 0 ? 'var(--color-error)' : 'var(--color-success)' }}>
                                            {formatCurrency(Number(vendor.current_balance || 0))}
                                        </span>
                                        <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>balance</span>
                                    </div>
                                </div>
                                <div style={{ borderTop: '1px solid var(--color-border)', paddingTop: '1rem', display: 'flex', justifyContent: 'space-between' }}>
                                    <span style={{
                                        padding: '0.25rem 0.5rem', borderRadius: '4px', fontSize: 'var(--text-xs)', fontWeight: 600,
                                        background: vendor.is_active ? 'rgba(34, 197, 94, 0.15)' : 'rgba(239, 68, 68, 0.15)',
                                        color: vendor.is_active ? 'var(--color-success)' : 'var(--color-error)'
                                    }}>
                                        {vendor.is_active ? 'Active' : 'Inactive'}
                                    </span>
                                    <button className="btn btn-outline" style={{ padding: '0.3rem 0.6rem', fontSize: 'var(--text-xs)' }}
                                        onClick={() => setHistoryVendor(vendor)}>
                                        View History
                                    </button>
                                </div>
                            </div>
                        ))}
                    </div>
                ) : (
                    <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
                        <div style={{ overflowX: 'auto' }}>
                            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--text-sm)' }}>
                                <thead>
                                    <tr style={{ background: 'var(--color-surface, #f8fafc)', textAlign: 'left' }}>
                                        <th style={thStyle}>Code</th>
                                        <th style={thStyle}>Name</th>
                                        <th style={thStyle}>Category</th>
                                        <th style={thStyle}>Tax ID</th>
                                        <th style={thStyle}>Phone</th>
                                        <th style={{ ...thStyle, textAlign: 'right' }}>Current Balance</th>
                                        <th style={thStyle}>Status</th>
                                        <th style={thStyle}></th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {vendors?.map((vendor: any) => (
                                        <tr key={vendor.id} style={{ borderBottom: '1px solid var(--color-border)' }}>
                                            <td style={tdStyle}><span style={{ fontWeight: 600 }}>{vendor.code}</span></td>
                                            <td style={tdStyle}>{vendor.name}</td>
                                            <td style={tdStyle}>{vendor.category_name || '-'}</td>
                                            <td style={tdStyle}>{vendor.tax_id || '-'}</td>
                                            <td style={tdStyle}>{vendor.phone || '-'}</td>
                                            <td style={{ ...tdStyle, textAlign: 'right', fontWeight: 600, color: Number(vendor.current_balance) > 0 ? 'var(--color-error)' : 'var(--color-text)' }}>
                                                {formatCurrency(Number(vendor.current_balance || 0))}
                                            </td>
                                            <td style={tdStyle}>
                                                <span style={{
                                                    padding: '0.2rem 0.5rem', borderRadius: '4px', fontSize: 'var(--text-xs)', fontWeight: 600,
                                                    background: vendor.is_active ? 'rgba(34, 197, 94, 0.15)' : 'rgba(239, 68, 68, 0.15)',
                                                    color: vendor.is_active ? 'var(--color-success)' : 'var(--color-error)',
                                                }}>
                                                    {vendor.is_active ? 'Active' : 'Inactive'}
                                                </span>
                                            </td>
                                            <td style={tdStyle}>
                                                <button className="btn btn-outline" style={{ padding: '0.3rem 0.6rem', fontSize: 'var(--text-xs)' }}
                                                    onClick={() => setHistoryVendor(vendor)}>
                                                    View History
                                                </button>
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </div>
                )}
            </main>
            <style>{`
                .label {
                    display: block;
                    margin-bottom: 0.5rem;
                    font-size: 0.75rem;
                    font-weight: 600;
                    text-transform: uppercase;
                    color: var(--color-text-muted);
                }
            `}</style>

            {totalPages > 1 && (
                <div style={{ display: 'flex', justifyContent: 'center', gap: '0.5rem', marginTop: '1rem', alignItems: 'center', marginLeft: '260px' }}>
                    <button className="btn btn-outline" disabled={currentPage <= 1} onClick={() => setCurrentPage(p => p - 1)}>Previous</button>
                    <span style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)' }}>Page {currentPage} of {totalPages}</span>
                    <button className="btn btn-outline" disabled={currentPage >= totalPages} onClick={() => setCurrentPage(p => p + 1)}>Next</button>
                </div>
            )}

            {historyVendor && (
                <VendorHistoryModal vendor={historyVendor} onClose={() => setHistoryVendor(null)} />
            )}
        </div>
    );
};

export default VendorList;
