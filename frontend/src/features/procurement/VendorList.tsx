import { useState, useRef, useEffect } from 'react';
import { useVendors, useCreateVendor, useVendorCategories } from './hooks/useProcurement';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
    ShoppingBag, Star, Phone, Plus, X, Save, LayoutGrid, List, Wallet, Building,
    ChevronDown, Download, Upload, FileSpreadsheet, CheckCircle2, AlertTriangle, Pencil,
    FileText, CreditCard,
} from 'lucide-react';
import apiClient from '../../api/client';
import Sidebar from '../../components/Sidebar';
import LoadingScreen from '../../components/common/LoadingScreen';
import PageHeader from '../../components/PageHeader';
import VendorHistoryModal from './VendorHistoryModal';
import { useCurrency } from '../../context/CurrencyContext';
import { useFiscalYears, useTSAAccounts } from '../../hooks/useGovForms';

const VendorList = () => {
    const [currentPage, setCurrentPage] = useState(1);
    const pageSize = 20;
    const { data: vendorsRaw, isLoading } = useVendors({ page: currentPage, page_size: pageSize });
    const vendors = vendorsRaw?.results || (Array.isArray(vendorsRaw) ? vendorsRaw : []);
    const totalCount = vendorsRaw?.count || vendors.length;
    const totalPages = Math.ceil(totalCount / pageSize);
    const createVendor = useCreateVendor();
    const { data: vendorCategories } = useVendorCategories();
    const { data: fiscalYears } = useFiscalYears();
    const { data: tsaAccounts } = useTSAAccounts();
    const { formatCurrency } = useCurrency();
    const qc = useQueryClient();

    // Check if invoice gate is enabled
    const { data: invoiceGate } = useQuery({
        queryKey: ['vendor-invoice-gate'],
        queryFn: async () => {
            const res = await apiClient.get('/procurement/vendors/invoice_gate_status/');
            return res.data as { enabled: boolean };
        },
    });
    const invoiceGateEnabled = invoiceGate?.enabled ?? true;

    // Pending activation vendors (only fetch when gate is enabled)
    const { data: pendingVendors = [] } = useQuery({
        queryKey: ['vendors-pending'],
        queryFn: async () => {
            const res = await apiClient.get('/procurement/vendors/pending_activation/');
            return Array.isArray(res.data) ? res.data : res.data?.results || [];
        },
        enabled: invoiceGateEnabled,
    });

    // Registration invoice state
    const [regInvoiceModal, setRegInvoiceModal] = useState<any>(null);
    const [generatedRegInvoice, setGeneratedRegInvoice] = useState<any>(null);
    const [regInvoiceForm, setRegInvoiceForm] = useState({ amount: '', tsa_account_id: '', fiscal_year_id: '', notes: '' });
    const [regPaymentRef, setRegPaymentRef] = useState('');

    const [showForm, setShowForm] = useState(false);
    const [editingVendor, setEditingVendor] = useState<any>(null);
    const [historyVendor, setHistoryVendor] = useState<any>(null);
    const [form, setForm] = useState({
        name: '', code: '', tax_id: '', address: '', email: '', phone: '', is_active: false, category: '',
        registration_number: '', registration_fiscal_year: '', expiry_date: '',
        bank_name: '', bank_account_number: '', bank_sort_code: '',
    });
    const [error, setError] = useState('');
    const [viewMode, setViewMode] = useState<'card' | 'list'>('list');
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

    const handleEdit = (vendor: any) => {
        setEditingVendor(vendor);
        setForm({
            name: vendor.name || '', code: vendor.code || '',
            tax_id: vendor.tax_id || '', address: vendor.address || '',
            email: vendor.email || '', phone: vendor.phone || '',
            is_active: vendor.is_active ?? true,
            category: vendor.category ? String(vendor.category) : '',
            registration_number: vendor.registration_number || '',
            registration_fiscal_year: vendor.registration_fiscal_year ? String(vendor.registration_fiscal_year) : '',
            expiry_date: vendor.expiry_date || '',
            bank_name: vendor.bank_name || '',
            bank_account_number: vendor.bank_account_number || '',
            bank_sort_code: vendor.bank_sort_code || '',
        });
        setShowForm(true);
    };

    const resetForm = () => {
        setShowForm(false); setEditingVendor(null); setError('');
        setForm({ name: '', code: '', tax_id: '', address: '', email: '', phone: '', is_active: false, category: '', registration_number: '', registration_fiscal_year: '', expiry_date: '', bank_name: '', bank_account_number: '', bank_sort_code: '' });
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
            const payload = {
                ...form,
                category: parseInt(form.category),
                registration_fiscal_year: form.registration_fiscal_year ? parseInt(form.registration_fiscal_year) : null,
                expiry_date: form.expiry_date || null,
            };
            if (editingVendor) {
                await apiClient.put(`/procurement/vendors/${editingVendor.id}/`, payload);
                flash('Vendor updated successfully');
            } else {
                await createVendor.mutateAsync(payload);
                // The default LIST endpoint hides inactive vendors, so a freshly
                // created supplier won't appear there until activation. Make it
                // explicit where the record is so the user doesn't think
                // creation silently failed.
                if (invoiceGateEnabled) {
                    flash(
                        `Vendor "${payload.name}" created. ` +
                        `Pending registration-invoice payment — see "Pending Activation" section above.`
                    );
                    // Make sure the pending list refetches immediately so the
                    // user sees their new vendor without manual refresh.
                    qc.invalidateQueries({ queryKey: ['vendors-pending'] });
                } else {
                    flash(`Vendor "${payload.name}" created and activated.`);
                }
            }
            resetForm();
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

    // ── Registration invoice handlers ──────────────────────
    const handleGenerateRegInvoice = async () => {
        if (!regInvoiceForm.amount || !regInvoiceForm.tsa_account_id || !regInvoiceForm.fiscal_year_id) return;
        try {
            const res = await apiClient.post(`/procurement/vendors/${regInvoiceModal.id}/generate_registration_invoice/`, regInvoiceForm);
            setGeneratedRegInvoice(res.data);
            flash('Registration invoice generated');
        } catch (err: any) { flash(err?.response?.data?.error || 'Failed to generate invoice', false); }
    };

    const handleConfirmRegPayment = async (invoice: any, vendorId: number) => {
        if (!regPaymentRef) return;
        try {
            const res = await apiClient.post(`/procurement/vendors/${vendorId}/confirm_registration_payment/`, {
                invoice_id: invoice.id, payment_reference: regPaymentRef,
            });
            flash(res.data.status || 'Payment confirmed — vendor activated');
            setRegPaymentRef(''); setGeneratedRegInvoice(null); setRegInvoiceModal(null);
            qc.invalidateQueries({ queryKey: ['vendors-pending'] });
            qc.invalidateQueries({ queryKey: ['vendors'] });
        } catch (err: any) { flash(err?.response?.data?.error || 'Failed', false); }
    };

    const fmtNGN = (v: number | string): string => {
        const num = typeof v === 'string' ? parseFloat(v) : v;
        return '\u20A6' + (isNaN(num) ? 0 : num).toLocaleString('en-NG', { minimumFractionDigits: 2 });
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

                {/* Persistent gate-state banner — explains why new vendors
                    don't immediately appear in the main list when the
                    registration-invoice gate is enabled. Self-dismissing on
                    pages where the gate is off so it doesn't add noise. */}
                {invoiceGateEnabled && !showForm && (
                    <div
                        className="card"
                        style={{
                            marginBottom: '1rem', padding: '0.7rem 1rem',
                            background: '#eff6ff',
                            border: '1px solid #bfdbfe',
                            color: '#1e40af',
                            display: 'flex', alignItems: 'center', gap: '0.6rem',
                            fontSize: 'var(--text-xs)',
                        }}
                    >
                        <FileText size={14} />
                        <span>
                            <strong>Registration-invoice gate is ON.</strong>{' '}
                            New vendors are created in <em>Pending Activation</em>{' '}
                            (yellow section above the main list) until a registration
                            invoice is generated and payment confirmed. Disable the
                            gate in <strong>Settings → Accounting → Vendor
                            Registration Invoice</strong> if you want vendors active
                            immediately on creation.
                        </span>
                    </div>
                )}

                {showForm && (
                    <div className="card animate-fade" style={{ marginBottom: '2rem', padding: '1.5rem' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem' }}>
                            <h2 style={{ fontSize: 'var(--text-lg)', fontWeight: 600, color: 'var(--color-text)', margin: 0 }}>{editingVendor ? 'Edit Vendor' : 'New Vendor'}</h2>
                            <button className="btn btn-outline" style={{ padding: '0.375rem' }} onClick={() => { resetForm(); }}>
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
                                {editingVendor && (
                                <div>
                                    <label className="label">Status</label>
                                    <select value={form.is_active ? 'true' : 'false'} onChange={e => setForm({ ...form, is_active: e.target.value === 'true' })}>
                                        <option value="true">Active</option>
                                        <option value="false">Inactive</option>
                                    </select>
                                </div>
                                )}
                                <div style={{ gridColumn: '1 / -1' }}>
                                    <label className="label">Vendor Category * <span style={{ fontWeight: 400, color: 'var(--color-text-muted)', fontSize: 'var(--text-xs)' }}>— determines AP reconciliation account in GL</span></label>
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

                            {/* Registration & Bank Details */}
                            <div style={{ borderTop: '1px solid var(--color-border, #e2e8f0)', marginTop: '0.5rem', paddingTop: '1rem' }}>
                                <p style={{ fontSize: 'var(--text-xs)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', color: 'var(--color-text-muted)', marginBottom: '0.75rem' }}>
                                    Registration & Banking
                                </p>
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '1rem' }}>
                                    <div>
                                        <label className="label">Registration Number</label>
                                        <input type="text" value={form.registration_number} onChange={e => setForm({ ...form, registration_number: e.target.value })} placeholder="BPP certificate no." />
                                    </div>
                                    <div>
                                        <label className="label">Fiscal Year</label>
                                        <select value={form.registration_fiscal_year} onChange={e => {
                                            const fyId = e.target.value;
                                            const fy = (fiscalYears || []).find((f: any) => String(f.id) === fyId);
                                            setForm({
                                                ...form,
                                                registration_fiscal_year: fyId,
                                                expiry_date: fy ? fy.end_date : form.expiry_date,
                                            });
                                        }}>
                                            <option value="">Select fiscal year...</option>
                                            {(fiscalYears || []).map((fy: any) => (
                                                <option key={fy.id} value={fy.id}>{fy.name || `FY ${fy.year}`}{fy.is_active ? ' (Active)' : ''}</option>
                                            ))}
                                        </select>
                                    </div>
                                    <div>
                                        <label className="label">Expiry Date</label>
                                        <input type="date" value={form.expiry_date} onChange={e => setForm({ ...form, expiry_date: e.target.value })} />
                                    </div>
                                    <div>
                                        <label className="label">Bank Name</label>
                                        <input type="text" value={form.bank_name} onChange={e => setForm({ ...form, bank_name: e.target.value })} placeholder="e.g. First Bank" />
                                    </div>
                                    <div>
                                        <label className="label">Account Number</label>
                                        <input type="text" value={form.bank_account_number} onChange={e => setForm({ ...form, bank_account_number: e.target.value })} placeholder="10-digit NUBAN" />
                                    </div>
                                    <div>
                                        <label className="label">Sort Code</label>
                                        <input type="text" value={form.bank_sort_code} onChange={e => setForm({ ...form, bank_sort_code: e.target.value })} placeholder="e.g. 011" />
                                    </div>
                                </div>
                            </div>
                            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '1.25rem' }}>
                                <button type="button" className="btn btn-outline" onClick={() => { resetForm(); }}>Cancel</button>
                                <button type="submit" className="btn btn-primary" disabled={createVendor.isPending}>
                                    <Save size={16} /> {createVendor.isPending ? 'Saving...' : editingVendor ? 'Update Vendor' : 'Save Vendor'}
                                </button>
                            </div>
                        </form>
                    </div>
                )}

                {/* ── Pending Activation Section (only when invoice gate enabled) ── */}
                {invoiceGateEnabled && pendingVendors.length > 0 && (
                    <div style={{ marginBottom: '1.5rem' }}>
                        <div style={{ padding: '0.625rem 0.875rem', borderRadius: '8px', marginBottom: '0.75rem', background: '#fffbeb', border: '1px solid #fde68a', display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: 'var(--text-xs)', color: '#92400e' }}>
                            <AlertTriangle size={14} /> <strong>{pendingVendors.length}</strong> vendor(s) pending activation — generate registration invoice and confirm payment to activate.
                        </div>
                        <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
                            <div style={{ padding: '0.75rem 1rem', background: 'linear-gradient(135deg, #fef3c7, #fde68a)', borderBottom: '1px solid #fde68a' }}>
                                <h3 style={{ margin: 0, fontSize: 'var(--text-sm)', fontWeight: 700, color: '#92400e' }}>Pending Activation</h3>
                            </div>
                            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 'var(--text-sm)' }}>
                                <thead>
                                    <tr style={{ background: 'var(--color-surface, #f8fafc)', textAlign: 'left' }}>
                                        <th style={thStyle}>Code</th>
                                        <th style={thStyle}>Vendor Name</th>
                                        <th style={thStyle}>Category</th>
                                        <th style={thStyle}>Status</th>
                                        <th style={thStyle}>Actions</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {pendingVendors.map((v: any) => (
                                        <tr key={v.id} style={{ borderBottom: '1px solid var(--color-border)' }}>
                                            <td style={tdStyle}><span style={{ fontWeight: 600 }}>{v.code}</span></td>
                                            <td style={tdStyle}>{v.name}</td>
                                            <td style={tdStyle}>{v.category_name || '-'}</td>
                                            <td style={tdStyle}>
                                                <span style={{ padding: '0.2rem 0.5rem', borderRadius: '12px', fontSize: '0.65rem', fontWeight: 600, background: '#fef3c7', color: '#92400e', border: '1px solid #fde68a' }}>
                                                    PENDING ACTIVATION
                                                </span>
                                            </td>
                                            <td style={tdStyle}>
                                                <button onClick={() => { setRegInvoiceModal(v); setGeneratedRegInvoice(null); setRegInvoiceForm({ amount: '', tsa_account_id: '', fiscal_year_id: '', notes: '' }); }}
                                                    style={{ display: 'flex', alignItems: 'center', gap: '0.25rem', padding: '0.35rem 0.7rem', borderRadius: '6px', border: 'none', cursor: 'pointer', fontSize: 'var(--text-xs)', fontWeight: 600, background: 'linear-gradient(135deg, var(--primary, #191e6a), var(--primary-dark, #0f1240))', color: '#fff' }}>
                                                    <FileText size={12} /> Generate Invoice
                                                </button>
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
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
                                    <div style={{ display: 'flex', gap: '0.4rem' }}>
                                        <button className="btn btn-outline" style={{ padding: '0.3rem 0.6rem', fontSize: 'var(--text-xs)', display: 'flex', alignItems: 'center', gap: '0.25rem' }}
                                            onClick={() => handleEdit(vendor)}>
                                            <Pencil size={12} /> Edit
                                        </button>
                                        <button className="btn btn-outline" style={{ padding: '0.3rem 0.6rem', fontSize: 'var(--text-xs)' }}
                                            onClick={() => setHistoryVendor(vendor)}>
                                            View History
                                        </button>
                                    </div>
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
                                        <th style={thStyle}>Registration #</th>
                                        <th style={thStyle}>Expiry Date</th>
                                        <th style={{ ...thStyle, textAlign: 'right' }}>Balance</th>
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
                                            <td style={tdStyle}>{vendor.registration_number || '-'}</td>
                                            <td style={tdStyle}>{vendor.expiry_date || '-'}</td>
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
                                                <div style={{ display: 'flex', gap: '0.3rem' }}>
                                                    <button className="btn btn-outline" style={{ padding: '0.3rem 0.5rem', fontSize: 'var(--text-xs)', display: 'flex', alignItems: 'center', gap: '0.2rem' }}
                                                        onClick={() => handleEdit(vendor)}>
                                                        <Pencil size={11} /> Edit
                                                    </button>
                                                    <button className="btn btn-outline" style={{ padding: '0.3rem 0.5rem', fontSize: 'var(--text-xs)' }}
                                                        onClick={() => setHistoryVendor(vendor)}>
                                                        History
                                                    </button>
                                                </div>
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

            {/* ── Registration Invoice Generation Modal ─────── */}
            {regInvoiceModal && !generatedRegInvoice && (
                <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', zIndex: 100, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <div className="card" style={{ padding: '1.5rem', width: '100%', maxWidth: 500 }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
                            <h3 style={{ fontSize: 'var(--text-base)', fontWeight: 700, margin: 0 }}>Generate Registration Invoice</h3>
                            <button onClick={() => setRegInvoiceModal(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-text-muted)' }}><X size={18} /></button>
                        </div>
                        <p style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)', marginBottom: '1rem' }}>
                            Vendor: <strong>{regInvoiceModal.name}</strong> ({regInvoiceModal.code})
                        </p>
                        <div style={{ display: 'grid', gap: '0.75rem' }}>
                            <div>
                                <label className="label">Registration Fee (NGN) *</label>
                                <input style={{ fontSize: 'var(--text-base)', fontWeight: 700 }} type="number" step="0.01" min="0.01"
                                    value={regInvoiceForm.amount} onChange={e => setRegInvoiceForm(f => ({ ...f, amount: e.target.value }))} placeholder="e.g. 50000" />
                            </div>
                            <div>
                                <label className="label">TSA Bank Account (pay into) *</label>
                                <select value={regInvoiceForm.tsa_account_id} onChange={e => setRegInvoiceForm(f => ({ ...f, tsa_account_id: e.target.value }))}>
                                    <option value="">Select TSA account...</option>
                                    {(tsaAccounts || []).map((a: any) => <option key={a.id} value={a.id}>{a.account_number} — {a.account_name} ({a.bank})</option>)}
                                </select>
                            </div>
                            <div>
                                <label className="label">Fiscal Year *</label>
                                <select value={regInvoiceForm.fiscal_year_id} onChange={e => setRegInvoiceForm(f => ({ ...f, fiscal_year_id: e.target.value }))}>
                                    <option value="">Select year...</option>
                                    {(fiscalYears || []).map((fy: any) => <option key={fy.id} value={fy.id}>{fy.name || `FY ${fy.year}`}</option>)}
                                </select>
                            </div>
                            <div>
                                <label className="label">Notes</label>
                                <textarea style={{ minHeight: 50 }} value={regInvoiceForm.notes} onChange={e => setRegInvoiceForm(f => ({ ...f, notes: e.target.value }))} placeholder="Optional notes..." />
                            </div>
                        </div>
                        <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'flex-end', marginTop: '1rem' }}>
                            <button onClick={() => setRegInvoiceModal(null)} className="btn btn-outline">Cancel</button>
                            <button onClick={handleGenerateRegInvoice} disabled={!regInvoiceForm.amount || !regInvoiceForm.tsa_account_id || !regInvoiceForm.fiscal_year_id}
                                className="btn btn-primary" style={{ opacity: (!regInvoiceForm.amount || !regInvoiceForm.tsa_account_id || !regInvoiceForm.fiscal_year_id) ? 0.5 : 1 }}>
                                <FileText size={14} /> Generate Invoice
                            </button>
                        </div>
                    </div>
                </div>
            )}

            {/* ── Generated Registration Invoice Preview + Payment ── */}
            {generatedRegInvoice && (
                <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.4)', zIndex: 100, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <div className="card" style={{ padding: '1.5rem', width: '100%', maxWidth: 550 }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
                            <h3 style={{ fontSize: 'var(--text-base)', fontWeight: 700, margin: 0 }}>Registration Invoice</h3>
                            <button onClick={() => { setGeneratedRegInvoice(null); setRegInvoiceModal(null); }} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-text-muted)' }}><X size={18} /></button>
                        </div>

                        <div style={{ background: 'var(--color-surface, #f8fafc)', border: '1px solid var(--color-border)', borderRadius: '8px', padding: '1rem', marginBottom: '1rem' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.75rem' }}>
                                <div>
                                    <div style={{ fontSize: '0.6rem', color: 'var(--color-text-muted)', textTransform: 'uppercase', fontWeight: 600 }}>Invoice Number</div>
                                    <div style={{ fontSize: 'var(--text-base)', fontWeight: 700 }}>{generatedRegInvoice.invoice_number}</div>
                                </div>
                                <div style={{ textAlign: 'right' }}>
                                    <div style={{ fontSize: '0.6rem', color: 'var(--color-text-muted)', textTransform: 'uppercase', fontWeight: 600 }}>Amount</div>
                                    <div style={{ fontSize: 'var(--text-lg)', fontWeight: 700, color: 'var(--primary, #191e6a)' }}>{fmtNGN(generatedRegInvoice.amount)}</div>
                                </div>
                            </div>
                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem', fontSize: 'var(--text-xs)' }}>
                                <div><span style={{ color: 'var(--color-text-muted)' }}>Vendor:</span> <strong>{generatedRegInvoice.vendor_name}</strong></div>
                                <div><span style={{ color: 'var(--color-text-muted)' }}>Type:</span> <strong style={{ color: '#166534' }}>REGISTRATION</strong></div>
                                <div><span style={{ color: 'var(--color-text-muted)' }}>Date:</span> {generatedRegInvoice.invoice_date}</div>
                                <div><span style={{ color: 'var(--color-text-muted)' }}>Fiscal Year:</span> {generatedRegInvoice.fiscal_year}</div>
                            </div>

                            <div style={{ marginTop: '0.75rem', padding: '0.625rem', borderRadius: '6px', background: 'rgba(25,30,106,0.04)', border: '1px solid rgba(25,30,106,0.1)' }}>
                                <div style={{ fontSize: '0.6rem', color: 'var(--color-text-muted)', textTransform: 'uppercase', fontWeight: 600, marginBottom: '0.3rem' }}>Pay To (TSA Bank Account)</div>
                                <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600 }}>{generatedRegInvoice.tsa_account_name}</div>
                                <div style={{ fontSize: 'var(--text-sm)' }}>Account: <strong>{generatedRegInvoice.tsa_account_number}</strong></div>
                                <div style={{ fontSize: 'var(--text-sm)' }}>Bank: {generatedRegInvoice.tsa_bank}</div>
                            </div>
                        </div>

                        {/* Payment Confirmation */}
                        <div style={{ borderTop: '1px solid var(--color-border)', paddingTop: '1rem' }}>
                            <h4 style={{ fontSize: 'var(--text-sm)', fontWeight: 600, margin: '0 0 0.5rem 0' }}>Confirm Payment</h4>
                            <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', margin: '0 0 0.75rem 0' }}>
                                After vendor pays, enter the payment receipt below. This will activate the vendor for <strong>1 year</strong> from today.
                            </p>
                            <div style={{ display: 'flex', gap: '0.5rem' }}>
                                <input placeholder="Payment receipt / teller number" style={{ flex: 1 }}
                                    value={regPaymentRef} onChange={e => setRegPaymentRef(e.target.value)} />
                                <button onClick={() => handleConfirmRegPayment(generatedRegInvoice, regInvoiceModal?.id)}
                                    disabled={!regPaymentRef}
                                    className="btn btn-primary" style={{ background: '#166534', display: 'flex', alignItems: 'center', gap: '0.3rem', opacity: regPaymentRef ? 1 : 0.5 }}>
                                    <CheckCircle2 size={14} /> Confirm & Activate
                                </button>
                            </div>
                            <p style={{ fontSize: '0.6rem', color: 'var(--color-text-muted)', marginTop: '0.5rem' }}>
                                GL Entry: DR TSA Cash {fmtNGN(generatedRegInvoice.amount)} | CR Revenue (Registration Fees) {fmtNGN(generatedRegInvoice.amount)}
                            </p>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
};

export default VendorList;
