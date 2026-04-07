import { useState } from 'react';
import { Plus, Building2, Link, Settings, Users, ArrowRight, Check, Trash2, Edit2 } from 'lucide-react';
import {
    useCompanies, useCreateCompany, useUpdateCompany, useDeleteCompany,
    useInterCompanyConfigs, useCreateInterCompanyConfig,
    useUpdateCompanyConfig, useDeleteICConfig,
} from '../hooks/useMultiCompany';
import { useCurrencies } from '../hooks/useAccountingEnhancements';
import apiClient from '../../../api/client';
import AccountingLayout from '../AccountingLayout';
import PageHeader from '../../../components/PageHeader';
import LoadingScreen from '../../../components/common/LoadingScreen';
import logger from '../../../utils/logger';
import '../styles/glassmorphism.css';

const BLANK_COMPANY = {
    name: '', company_code: '', company_type: 'Subsidiary', parent_company: '',
    registration_number: '', tax_id: '', currency: '',
    address: '', phone: '', email: '', is_active: true, is_internal: true,
};

const BLANK_CONFIG = {
    company: '', partner_company: '', ar_account: '', ap_account: '',
    expense_account: '', revenue_account: '', auto_post: true, auto_match: true,
};

export default function MultiCompanyPage() {
    const [activeTab, setActiveTab] = useState<'companies' | 'config'>('companies');

    // Company modals
    const [showCompanyModal, setShowCompanyModal] = useState(false);
    const [editingCompany, setEditingCompany] = useState<any>(null);
    const [deleteCompanyId, setDeleteCompanyId] = useState<number | null>(null);
    const [companyForm, setCompanyForm] = useState({ ...BLANK_COMPANY });

    // Config modals
    const [showConfigModal, setShowConfigModal] = useState(false);
    const [editingConfig, setEditingConfig] = useState<any>(null);
    const [deleteConfigId, setDeleteConfigId] = useState<number | null>(null);
    const [configForm, setConfigForm] = useState({ ...BLANK_CONFIG });
    const [glAccounts, setGlAccounts] = useState<any[]>([]);

    // Queries
    const { data: companies, isLoading } = useCompanies({});
    const { data: icConfigs } = useInterCompanyConfigs({});
    const { data: currencies } = useCurrencies();

    // Mutations
    const createCompany = useCreateCompany();
    const updateCompany = useUpdateCompany();
    const deleteCompany = useDeleteCompany();
    const createConfig = useCreateInterCompanyConfig();
    const updateConfig = useUpdateCompanyConfig();
    const deleteConfig = useDeleteICConfig();

    const fetchGlAccounts = async () => {
        try {
            const response = await apiClient.get('/accounting/accounts/', { params: { is_active: true, page_size: 200 } });
            setGlAccounts(response.data.results || response.data);
        } catch (error) {
            logger.error('Failed to fetch accounts:', error);
        }
    };

    // ── Company handlers ──────────────────────────────────────
    const handleOpenCreateCompany = () => {
        setEditingCompany(null);
        setCompanyForm({ ...BLANK_COMPANY });
        setShowCompanyModal(true);
    };

    const handleOpenEditCompany = (company: any) => {
        setEditingCompany(company);
        setCompanyForm({
            name: company.name ?? '',
            company_code: company.company_code ?? '',
            company_type: company.company_type ?? 'Subsidiary',
            parent_company: company.parent_company ? String(company.parent_company) : '',
            registration_number: company.registration_number ?? '',
            tax_id: company.tax_id ?? '',
            currency: company.currency ? String(company.currency) : '',
            address: company.address ?? '',
            phone: company.phone ?? '',
            email: company.email ?? '',
            is_active: company.is_active ?? true,
            is_internal: company.is_internal ?? true,
        });
        setShowCompanyModal(true);
    };

    const handleSubmitCompany = async (e: React.FormEvent) => {
        e.preventDefault();
        try {
            if (editingCompany) {
                await updateCompany.mutateAsync({ id: editingCompany.id, ...companyForm });
            } else {
                await createCompany.mutateAsync(companyForm);
            }
            setShowCompanyModal(false);
            setEditingCompany(null);
            setCompanyForm({ ...BLANK_COMPANY });
        } catch (error) {
            logger.error('Failed to save company:', error);
        }
    };

    const handleDeleteCompany = async () => {
        if (deleteCompanyId == null) return;
        try {
            await deleteCompany.mutateAsync(deleteCompanyId);
            setDeleteCompanyId(null);
        } catch (error) {
            logger.error('Failed to delete company:', error);
        }
    };

    // ── Config handlers ───────────────────────────────────────
    const handleOpenCreateConfig = () => {
        setEditingConfig(null);
        setConfigForm({ ...BLANK_CONFIG });
        fetchGlAccounts();
        setShowConfigModal(true);
    };

    const handleOpenEditConfig = (config: any) => {
        setEditingConfig(config);
        setConfigForm({
            company: config.company ? String(config.company) : '',
            partner_company: config.partner_company ? String(config.partner_company) : '',
            ar_account: config.ar_account ? String(config.ar_account) : '',
            ap_account: config.ap_account ? String(config.ap_account) : '',
            expense_account: config.expense_account ? String(config.expense_account) : '',
            revenue_account: config.revenue_account ? String(config.revenue_account) : '',
            auto_post: config.auto_post ?? true,
            auto_match: config.auto_match ?? true,
        });
        fetchGlAccounts();
        setShowConfigModal(true);
    };

    const handleSubmitConfig = async (e: React.FormEvent) => {
        e.preventDefault();
        try {
            if (editingConfig) {
                await updateConfig.mutateAsync({ id: editingConfig.id, ...configForm });
            } else {
                await createConfig.mutateAsync(configForm);
            }
            setShowConfigModal(false);
            setEditingConfig(null);
            setConfigForm({ ...BLANK_CONFIG });
        } catch (error) {
            logger.error('Failed to save IC config:', error);
        }
    };

    const handleDeleteConfig = async () => {
        if (deleteConfigId == null) return;
        try {
            await deleteConfig.mutateAsync(deleteConfigId);
            setDeleteConfigId(null);
        } catch (error) {
            logger.error('Failed to delete IC config:', error);
        }
    };

    if (isLoading) return <LoadingScreen message="Loading..." />;

    const activeCompanies = companies?.filter((c: any) => c.is_active) || [];
    const isCompanyPending = createCompany.isPending || updateCompany.isPending;
    const isConfigPending = createConfig.isPending || updateConfig.isPending;

    return (
        <AccountingLayout>
            <div>
                <PageHeader
                    title="Multi-Company Management"
                    subtitle="Manage companies and inter-company configurations."
                    icon={<Building2 size={22} />}
                    backButton={false}
                />

                <div style={{ display: 'flex', gap: '1rem', marginBottom: '2rem' }}>
                    <button className={`btn ${activeTab === 'companies' ? 'btn-primary' : 'btn-secondary'}`} onClick={() => setActiveTab('companies')}>
                        <Building2 size={18} /> Companies
                    </button>
                    <button className={`btn ${activeTab === 'config' ? 'btn-primary' : 'btn-secondary'}`} onClick={() => setActiveTab('config')}>
                        <Link size={18} /> IC Config
                    </button>
                </div>

                {/* ── Companies Tab ── */}
                {activeTab === 'companies' && (
                    <div>
                        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '1.5rem' }}>
                            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1rem', flex: 1 }}>
                                <div className="card">
                                    <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Total Companies</p>
                                    <p style={{ fontSize: 'var(--text-xl)', fontWeight: 700 }}>{companies?.length || 0}</p>
                                </div>
                                <div className="card">
                                    <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Active</p>
                                    <p style={{ fontSize: 'var(--text-xl)', fontWeight: 700, color: 'var(--color-success)' }}>{activeCompanies.length}</p>
                                </div>
                                <div className="card">
                                    <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>IC Relations</p>
                                    <p style={{ fontSize: 'var(--text-xl)', fontWeight: 700, color: 'var(--color-primary)' }}>{icConfigs?.length || 0}</p>
                                </div>
                            </div>
                            <button className="btn btn-primary" style={{ marginLeft: '1rem', alignSelf: 'flex-start' }} onClick={handleOpenCreateCompany}>
                                <Plus size={18} /> Add Company
                            </button>
                        </div>

                        <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
                            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                                <thead>
                                    <tr style={{ background: 'var(--color-surface)', textAlign: 'left' }}>
                                        {['Code', 'Name', 'Type', 'Currency', 'Status', 'Actions'].map(h => (
                                            <th key={h} style={{ padding: '1rem 1.5rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase' }}>{h}</th>
                                        ))}
                                    </tr>
                                </thead>
                                <tbody>
                                    {!companies?.length ? (
                                        <tr><td colSpan={6} style={{ padding: '3rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>
                                            No companies. Click "Add Company" to create one.
                                        </td></tr>
                                    ) : companies.map((company: any) => (
                                        <tr key={company.id} style={{ borderBottom: '1px solid var(--color-border)' }}>
                                            <td style={{ padding: '1rem 1.5rem', fontWeight: 600 }}>{company.company_code}</td>
                                            <td style={{ padding: '1rem 1.5rem' }}>{company.name}</td>
                                            <td style={{ padding: '1rem 1.5rem' }}>{company.company_type}</td>
                                            <td style={{ padding: '1rem 1.5rem' }}>{company.currency_code}</td>
                                            <td style={{ padding: '1rem 1.5rem' }}>
                                                <span style={{
                                                    padding: '0.25rem 0.75rem', borderRadius: '9999px', fontSize: 'var(--text-xs)',
                                                    background: company.is_active ? 'rgba(34,197,94,0.1)' : 'rgba(107,114,128,0.1)',
                                                    color: company.is_active ? 'var(--color-success)' : 'var(--color-text-muted)',
                                                }}>
                                                    {company.is_active ? 'Active' : 'Inactive'}
                                                </span>
                                            </td>
                                            <td style={{ padding: '0.75rem 1.5rem' }}>
                                                <div style={{ display: 'flex', gap: '8px' }}>
                                                    <button onClick={() => handleOpenEditCompany(company)} title="Edit" style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#2563eb', padding: '4px' }}>
                                                        <Edit2 size={15} />
                                                    </button>
                                                    <button onClick={() => setDeleteCompanyId(company.id)} title="Delete" style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#ef4444', padding: '4px' }}>
                                                        <Trash2 size={15} />
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

                {/* ── IC Config Tab ── */}
                {activeTab === 'config' && (
                    <div>
                        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '1.5rem' }}>
                            <p style={{ color: 'var(--color-text-muted)' }}>Configure inter-company AR/AP accounts for auto-posting.</p>
                            <button className="btn btn-primary" onClick={handleOpenCreateConfig}>
                                <Plus size={18} /> Add IC Config
                            </button>
                        </div>

                        <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
                            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                                <thead>
                                    <tr style={{ background: 'var(--color-surface)', textAlign: 'left' }}>
                                        {['From Company', 'To Company', 'AR Account', 'AP Account', 'Auto Post', 'Actions'].map(h => (
                                            <th key={h} style={{ padding: '1rem 1.5rem', fontSize: 'var(--text-xs)', fontWeight: 600, textTransform: 'uppercase' }}>{h}</th>
                                        ))}
                                    </tr>
                                </thead>
                                <tbody>
                                    {!icConfigs?.length ? (
                                        <tr><td colSpan={6} style={{ padding: '3rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>
                                            No IC configurations. Click "Add IC Config" to create one.
                                        </td></tr>
                                    ) : icConfigs.map((config: any) => (
                                        <tr key={config.id} style={{ borderBottom: '1px solid var(--color-border)' }}>
                                            <td style={{ padding: '1rem 1.5rem' }}>{config.company_name}</td>
                                            <td style={{ padding: '1rem 1.5rem' }}>
                                                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                                    <ArrowRight size={14} /> {config.partner_company_name}
                                                </div>
                                            </td>
                                            <td style={{ padding: '1rem 1.5rem', fontFamily: 'monospace', fontSize: 'var(--text-sm)' }}>
                                                {config.ar_account_name || '—'}
                                            </td>
                                            <td style={{ padding: '1rem 1.5rem', fontFamily: 'monospace', fontSize: 'var(--text-sm)' }}>
                                                {config.ap_account_name || '—'}
                                            </td>
                                            <td style={{ padding: '1rem 1.5rem' }}>
                                                {config.auto_post ? <Check size={18} style={{ color: 'var(--color-success)' }} /> : '—'}
                                            </td>
                                            <td style={{ padding: '0.75rem 1.5rem' }}>
                                                <div style={{ display: 'flex', gap: '8px' }}>
                                                    <button onClick={() => handleOpenEditConfig(config)} title="Edit" style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#2563eb', padding: '4px' }}>
                                                        <Edit2 size={15} />
                                                    </button>
                                                    <button onClick={() => setDeleteConfigId(config.id)} title="Delete" style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#ef4444', padding: '4px' }}>
                                                        <Trash2 size={15} />
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

                {/* ── Company Modal (Create / Edit) ── */}
                {showCompanyModal && (
                    <div className="modal-overlay" onClick={() => setShowCompanyModal(false)}>
                        <div className="modal" onClick={(e) => e.stopPropagation()}>
                            <div className="modal-header">
                                <h3>{editingCompany ? 'Edit Company' : 'Add Company'}</h3>
                                <button className="btn-close" aria-label="Close" onClick={() => setShowCompanyModal(false)}><span aria-hidden="true">&times;</span></button>
                            </div>
                            <form onSubmit={handleSubmitCompany}>
                                <div className="modal-body" style={{ maxHeight: '70vh', overflowY: 'auto' }}>
                                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
                                        <div>
                                            <label className="form-label">Company Code<span className="required-mark"> *</span></label>
                                            <input type="text" className="input" value={companyForm.company_code}
                                                onChange={(e) => setCompanyForm({ ...companyForm, company_code: e.target.value })} required />
                                        </div>
                                        <div>
                                            <label className="form-label">Name<span className="required-mark"> *</span></label>
                                            <input type="text" className="input" value={companyForm.name}
                                                onChange={(e) => setCompanyForm({ ...companyForm, name: e.target.value })} required />
                                        </div>
                                        <div>
                                            <label className="form-label">Type<span className="required-mark"> *</span></label>
                                            <select className="input" value={companyForm.company_type}
                                                onChange={(e) => setCompanyForm({ ...companyForm, company_type: e.target.value })}>
                                                <option value="Holding">Holding Company</option>
                                                <option value="Subsidiary">Subsidiary</option>
                                                <option value="Branch">Branch</option>
                                                <option value="Division">Division</option>
                                            </select>
                                        </div>
                                        <div>
                                            <label className="form-label">Currency<span className="required-mark"> *</span></label>
                                            <select className="input" value={companyForm.currency}
                                                onChange={(e) => setCompanyForm({ ...companyForm, currency: e.target.value })} required>
                                                <option value="">Select Currency</option>
                                                {currencies?.map((c: any) => <option key={c.id} value={c.id}>{c.code} - {c.name}</option>)}
                                            </select>
                                        </div>
                                        <div>
                                            <label className="form-label">Registration #</label>
                                            <input type="text" className="input" value={companyForm.registration_number}
                                                onChange={(e) => setCompanyForm({ ...companyForm, registration_number: e.target.value })} />
                                        </div>
                                        <div>
                                            <label className="form-label">Tax ID</label>
                                            <input type="text" className="input" value={companyForm.tax_id}
                                                onChange={(e) => setCompanyForm({ ...companyForm, tax_id: e.target.value })} />
                                        </div>
                                        <div style={{ gridColumn: '1 / -1' }}>
                                            <label className="form-label">Address</label>
                                            <textarea className="input" value={companyForm.address}
                                                onChange={(e) => setCompanyForm({ ...companyForm, address: e.target.value })} rows={2} />
                                        </div>
                                        <div>
                                            <label className="form-label">Phone</label>
                                            <input type="text" className="input" value={companyForm.phone}
                                                onChange={(e) => setCompanyForm({ ...companyForm, phone: e.target.value })} />
                                        </div>
                                        <div>
                                            <label className="form-label">Email</label>
                                            <input type="email" className="input" value={companyForm.email}
                                                onChange={(e) => setCompanyForm({ ...companyForm, email: e.target.value })} />
                                        </div>
                                        <div style={{ display: 'flex', gap: '1.5rem', gridColumn: '1 / -1' }}>
                                            <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                                <input type="checkbox" checked={companyForm.is_active}
                                                    onChange={(e) => setCompanyForm({ ...companyForm, is_active: e.target.checked })} />
                                                Active
                                            </label>
                                            <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                                <input type="checkbox" checked={companyForm.is_internal}
                                                    onChange={(e) => setCompanyForm({ ...companyForm, is_internal: e.target.checked })} />
                                                Internal Company
                                            </label>
                                        </div>
                                    </div>
                                </div>
                                <div className="modal-footer">
                                    <button type="button" className="btn btn-secondary" onClick={() => setShowCompanyModal(false)}>Cancel</button>
                                    <button type="submit" className="btn btn-primary" disabled={isCompanyPending}>
                                        {isCompanyPending ? 'Saving...' : (editingCompany ? 'Update Company' : 'Save Company')}
                                    </button>
                                </div>
                            </form>
                        </div>
                    </div>
                )}

                {/* ── IC Config Modal (Create / Edit) ── */}
                {showConfigModal && (
                    <div className="modal-overlay" onClick={() => setShowConfigModal(false)}>
                        <div className="modal" onClick={(e) => e.stopPropagation()}>
                            <div className="modal-header">
                                <h3>{editingConfig ? 'Edit IC Configuration' : 'Add IC Configuration'}</h3>
                                <button className="btn-close" aria-label="Close" onClick={() => setShowConfigModal(false)}><span aria-hidden="true">&times;</span></button>
                            </div>
                            <form onSubmit={handleSubmitConfig}>
                                <div className="modal-body" style={{ maxHeight: '70vh', overflowY: 'auto' }}>
                                    <div style={{ display: 'grid', gap: '1rem' }}>
                                        <div>
                                            <label className="form-label">From Company<span className="required-mark"> *</span></label>
                                            <select className="input" value={configForm.company}
                                                onChange={(e) => setConfigForm({ ...configForm, company: e.target.value })} required>
                                                <option value="">Select Company</option>
                                                {companies?.map((c: any) => <option key={c.id} value={c.id}>{c.name} ({c.company_code})</option>)}
                                            </select>
                                        </div>
                                        <div>
                                            <label className="form-label">To Company<span className="required-mark"> *</span></label>
                                            <select className="input" value={configForm.partner_company}
                                                onChange={(e) => setConfigForm({ ...configForm, partner_company: e.target.value })} required>
                                                <option value="">Select Company</option>
                                                {companies?.filter((c: any) => c.id !== parseInt(configForm.company))
                                                    .map((c: any) => <option key={c.id} value={c.id}>{c.name} ({c.company_code})</option>)}
                                            </select>
                                        </div>
                                        <div>
                                            <label className="form-label">AR Account (Receivable)</label>
                                            <select className="input" value={configForm.ar_account}
                                                onChange={(e) => setConfigForm({ ...configForm, ar_account: e.target.value })}>
                                                <option value="">Select Account</option>
                                                {glAccounts?.filter((a: any) => a.account_type === 'Asset')
                                                    .map((a: any) => <option key={a.id} value={a.id}>{a.code} - {a.name}</option>)}
                                            </select>
                                        </div>
                                        <div>
                                            <label className="form-label">AP Account (Payable)</label>
                                            <select className="input" value={configForm.ap_account}
                                                onChange={(e) => setConfigForm({ ...configForm, ap_account: e.target.value })}>
                                                <option value="">Select Account</option>
                                                {glAccounts?.filter((a: any) => a.account_type === 'Liability')
                                                    .map((a: any) => <option key={a.id} value={a.id}>{a.code} - {a.name}</option>)}
                                            </select>
                                        </div>
                                        <div>
                                            <label className="form-label">Expense Account</label>
                                            <select className="input" value={configForm.expense_account}
                                                onChange={(e) => setConfigForm({ ...configForm, expense_account: e.target.value })}>
                                                <option value="">Select Account</option>
                                                {glAccounts?.filter((a: any) => a.account_type === 'Expense')
                                                    .map((a: any) => <option key={a.id} value={a.id}>{a.code} - {a.name}</option>)}
                                            </select>
                                        </div>
                                        <div>
                                            <label className="form-label">Revenue Account</label>
                                            <select className="input" value={configForm.revenue_account}
                                                onChange={(e) => setConfigForm({ ...configForm, revenue_account: e.target.value })}>
                                                <option value="">Select Account</option>
                                                {glAccounts?.filter((a: any) => a.account_type === 'Income')
                                                    .map((a: any) => <option key={a.id} value={a.id}>{a.code} - {a.name}</option>)}
                                            </select>
                                        </div>
                                        <div style={{ display: 'flex', gap: '1.5rem' }}>
                                            <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                                <input type="checkbox" checked={configForm.auto_post}
                                                    onChange={(e) => setConfigForm({ ...configForm, auto_post: e.target.checked })} />
                                                Auto Post
                                            </label>
                                            <label style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                                <input type="checkbox" checked={configForm.auto_match}
                                                    onChange={(e) => setConfigForm({ ...configForm, auto_match: e.target.checked })} />
                                                Auto Match
                                            </label>
                                        </div>
                                    </div>
                                </div>
                                <div className="modal-footer">
                                    <button type="button" className="btn btn-secondary" onClick={() => setShowConfigModal(false)}>Cancel</button>
                                    <button type="submit" className="btn btn-primary" disabled={isConfigPending}>
                                        {isConfigPending ? 'Saving...' : (editingConfig ? 'Update Config' : 'Save Config')}
                                    </button>
                                </div>
                            </form>
                        </div>
                    </div>
                )}

                {/* ── Delete Company Confirm ── */}
                {deleteCompanyId !== null && (
                    <div className="modal-overlay" onClick={() => setDeleteCompanyId(null)}>
                        <div className="modal" style={{ maxWidth: '420px' }} onClick={(e) => e.stopPropagation()}>
                            <div className="modal-header">
                                <h3>Delete Company?</h3>
                                <button className="btn-close" aria-label="Close" onClick={() => setDeleteCompanyId(null)}><span aria-hidden="true">&times;</span></button>
                            </div>
                            <div className="modal-body">
                                <p style={{ color: 'var(--color-text-muted)', fontSize: '14px' }}>
                                    This will permanently delete this company. Any linked IC configurations and consolidation groups may be affected. This action cannot be undone.
                                </p>
                            </div>
                            <div className="modal-footer">
                                <button className="btn btn-secondary" onClick={() => setDeleteCompanyId(null)}>Cancel</button>
                                <button className="btn" style={{ background: '#dc2626', color: '#fff', border: 'none' }}
                                    onClick={handleDeleteCompany} disabled={deleteCompany.isPending}>
                                    {deleteCompany.isPending ? 'Deleting...' : 'Delete'}
                                </button>
                            </div>
                        </div>
                    </div>
                )}

                {/* ── Delete Config Confirm ── */}
                {deleteConfigId !== null && (
                    <div className="modal-overlay" onClick={() => setDeleteConfigId(null)}>
                        <div className="modal" style={{ maxWidth: '420px' }} onClick={(e) => e.stopPropagation()}>
                            <div className="modal-header">
                                <h3>Delete IC Configuration?</h3>
                                <button className="btn-close" aria-label="Close" onClick={() => setDeleteConfigId(null)}><span aria-hidden="true">&times;</span></button>
                            </div>
                            <div className="modal-body">
                                <p style={{ color: 'var(--color-text-muted)', fontSize: '14px' }}>
                                    This will permanently delete this inter-company configuration. Auto-posting between these companies will stop. This action cannot be undone.
                                </p>
                            </div>
                            <div className="modal-footer">
                                <button className="btn btn-secondary" onClick={() => setDeleteConfigId(null)}>Cancel</button>
                                <button className="btn" style={{ background: '#dc2626', color: '#fff', border: 'none' }}
                                    onClick={handleDeleteConfig} disabled={deleteConfig.isPending}>
                                    {deleteConfig.isPending ? 'Deleting...' : 'Delete'}
                                </button>
                            </div>
                        </div>
                    </div>
                )}
            </div>
        </AccountingLayout>
    );
}
