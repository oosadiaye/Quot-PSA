import { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useRecurringJournal, useCreateRecurringJournal, useUpdateRecurringJournal } from './hooks/useRecurringJournal';
import { useDimensions } from './hooks/useJournal';
import { useCurrency } from '../../context/CurrencyContext';
import AccountingLayout from './AccountingLayout';
import PageHeader from '../../components/PageHeader';
import { Save, X, Plus, Trash2, Calendar, Clock } from 'lucide-react';
import LoadingScreen from '../../components/common/LoadingScreen';

let _rjLineUid = 0;
const nextRjLineUid = () => String(++_rjLineUid);

interface RecurringJournalLine {
    _uid: string;
    account: string;
    description: string;
    debit: number;
    credit: number;
}

interface RecurringJournalPayload {
    name: string;
    description: string;
    frequency: string;
    start_date: string;
    start_type: string;
    scheduled_posting_date: string | null;
    end_date: string | null;
    is_active: boolean;
    auto_post: boolean;
    use_month_end_default: boolean;
    auto_reverse_on_month_start: boolean;
    code_prefix: string;
    fund?: string;
    function?: string;
    program?: string;
    geo?: string;
    lines: RecurringJournalLine[];
}

const RecurringJournalForm = () => {
    const navigate = useNavigate();
    const { id } = useParams();
    const isEdit = Boolean(id);
    const { data: journal, isLoading } = useRecurringJournal(Number(id));
    const { data: dims } = useDimensions();
    const { formatCurrency } = useCurrency();
    const createMutation = useCreateRecurringJournal();
    const updateMutation = useUpdateRecurringJournal();
    const [formError, setFormError] = useState('');

    const [formData, setFormData] = useState({
        name: '',
        description: '',
        frequency: 'monthly',
        start_date: new Date().toISOString().split('T')[0],
        start_type: 'now',
        scheduled_posting_date: '',
        end_date: '',
        is_active: true,
        auto_post: false,
        use_month_end_default: false,
        auto_reverse_on_month_start: false,
        code_prefix: 'REC',
        fund: '',
        function: '',
        program: '',
        geo: '',
    });

    const [lines, setLines] = useState([
        { _uid: nextRjLineUid(), account: '', description: '', debit: '0', credit: '0' },
        { _uid: nextRjLineUid(), account: '', description: '', debit: '0', credit: '0' },
    ]);

    useEffect(() => {
        if (journal && isEdit) {
            setFormData({
                name: journal.name || '',
                description: journal.description || '',
                frequency: journal.frequency || 'monthly',
                start_date: journal.start_date || '',
                start_type: journal.start_type || 'now',
                scheduled_posting_date: journal.scheduled_posting_date || '',
                end_date: journal.end_date || '',
                is_active: journal.is_active ?? true,
                auto_post: journal.auto_post ?? false,
                use_month_end_default: journal.use_month_end_default ?? false,
                auto_reverse_on_month_start: journal.auto_reverse_on_month_start ?? false,
                code_prefix: journal.code_prefix || 'REC',
                fund: journal.fund || '',
                function: journal.function || '',
                program: journal.program || '',
                geo: journal.geo || '',
            });
            if (journal.lines) {
                setLines(journal.lines.map((l: any) => ({
                    _uid: nextRjLineUid(),
                    account: l.account,
                    description: l.description,
                    debit: String(l.debit),
                    credit: String(l.credit),
                })));
            }
        }
    }, [journal, isEdit]);

    const totalDebit = lines.reduce((sum, l) => sum + parseFloat(l.debit || '0'), 0);
    const totalCredit = lines.reduce((sum, l) => sum + parseFloat(l.credit || '0'), 0);
    const isBalanced = Math.abs(totalDebit - totalCredit) < 0.01 && totalDebit > 0;

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!isBalanced) return;

        const payload: RecurringJournalPayload = {
            ...formData,
            end_date: formData.end_date || null,
            scheduled_posting_date: formData.scheduled_posting_date || null,
            lines: lines.map(l => ({
                ...l,
                debit: parseFloat(l.debit),
                credit: parseFloat(l.credit),
            })),
            ...(formData.fund ? { fund: formData.fund } : {}),
            ...(formData.function ? { function: formData.function } : {}),
            ...(formData.program ? { program: formData.program } : {}),
            ...(formData.geo ? { geo: formData.geo } : {}),
        };

        try {
            setFormError('');
            if (isEdit) {
                await updateMutation.mutateAsync({ id: Number(id), data: payload });
            } else {
                await createMutation.mutateAsync(payload);
            }
            navigate('/accounting/recurring-journals');
        } catch (err: any) {
            const data = err.response?.data;
            if (data) {
                const messages = typeof data === 'string' ? data : Object.values(data).flat().join(' ');
                setFormError(messages || 'Error saving recurring journal.');
            } else {
                setFormError(err.message || 'Error saving recurring journal.');
            }
        }
    };

    const addLine = () => setLines([...lines, { _uid: nextRjLineUid(), account: '', description: '', debit: '0', credit: '0' }]);
    const removeLine = (idx: number) => setLines(lines.filter((_, i) => i !== idx));
    const updateLine = (idx: number, field: string, value: string) => {
        const newLines = [...lines];
        (newLines[idx] as any)[field] = value;
        setLines(newLines);
    };

    if (isEdit && isLoading) return <LoadingScreen message="Loading..." />;

    return (
        <AccountingLayout>
            <form onSubmit={handleSubmit}>
                <PageHeader
                    title={isEdit ? 'Edit Recurring Journal' : 'New Recurring Journal Template'}
                    subtitle="Create a template for automatic journal generation"
                    icon={<Calendar size={22} />}
                    actions={
                        <div style={{ display: 'flex', gap: '0.75rem' }}>
                            <button type="button" className="btn btn-outline" onClick={() => navigate('/accounting/recurring-journals')}>
                                <X size={18} /> Cancel
                            </button>
                            <button type="submit" className="btn btn-primary" disabled={!isBalanced || createMutation.isPending || updateMutation.isPending}>
                                <Save size={18} /> {isEdit ? 'Update' : 'Create'} Template
                            </button>
                        </div>
                    }
                />

                {formError && (
                    <div style={{ padding: '0.75rem 1rem', background: '#fee2e2', color: '#dc2626', borderRadius: '8px', marginBottom: '1.5rem', fontSize: 'var(--text-sm)' }}>
                        {formError}
                    </div>
                )}

                <div className="card" style={{ marginBottom: '2rem' }}>
                    <h3 style={{ marginBottom: '1.5rem' }}>Basic Information</h3>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1.5rem' }}>
                        <div>
                            <label className="label">Template Name<span className="required-mark"> *</span></label>
                            <input type="text" value={formData.name} onChange={e => setFormData({ ...formData, name: e.target.value })} required placeholder="e.g., Monthly Rent Accrual" />
                        </div>
                        <div>
                            <label className="label">Code Prefix</label>
                            <input type="text" value={formData.code_prefix} onChange={e => setFormData({ ...formData, code_prefix: e.target.value })} placeholder="REC" />
                        </div>
                        <div>
                            <label className="label">Frequency<span className="required-mark"> *</span></label>
                            <select value={formData.frequency} onChange={e => setFormData({ ...formData, frequency: e.target.value })}>
                                <option value="daily">Daily</option>
                                <option value="weekly">Weekly</option>
                                <option value="biweekly">Bi-Weekly</option>
                                <option value="monthly">Monthly</option>
                                <option value="quarterly">Quarterly</option>
                                <option value="annually">Annually</option>
                            </select>
                        </div>
                        <div>
                            <label className="label">Start Date<span className="required-mark"> *</span></label>
                            <input type="date" value={formData.start_date} onChange={e => setFormData({ ...formData, start_date: e.target.value })} required />
                        </div>
                        <div>
                            <label className="label">End Date</label>
                            <input type="date" value={formData.end_date} onChange={e => setFormData({ ...formData, end_date: e.target.value })} />
                        </div>
                        <div>
                            <label className="label">Start Type</label>
                            <select value={formData.start_type} onChange={e => setFormData({ ...formData, start_type: e.target.value })}>
                                <option value="now">Start Now</option>
                                <option value="scheduled">Schedule Future</option>
                            </select>
                        </div>
                        {formData.start_type === 'scheduled' && (
                            <div>
                                <label className="label">Scheduled Posting Date</label>
                                <input type="date" value={formData.scheduled_posting_date} onChange={e => setFormData({ ...formData, scheduled_posting_date: e.target.value })} />
                            </div>
                        )}
                    </div>
                    <div style={{ marginTop: '1rem' }}>
                        <label className="label">Description</label>
                        <input type="text" value={formData.description} onChange={e => setFormData({ ...formData, description: e.target.value })} placeholder="Describe this recurring journal" />
                    </div>
                </div>

                <div className="card" style={{ marginBottom: '2rem' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
                        <h3>Options</h3>
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', gap: '1.25rem' }}>
                        <label style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', cursor: 'pointer', padding: '0.5rem 0' }}>
                            <input type="checkbox" checked={formData.is_active} onChange={e => setFormData({ ...formData, is_active: e.target.checked })} />
                            <span style={{ fontSize: 'var(--text-sm)', color: 'var(--text-primary)' }}>Active (template can be used for generation)</span>
                        </label>
                        <label style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', cursor: 'pointer', padding: '0.5rem 0' }}>
                            <input type="checkbox" checked={formData.auto_post} onChange={e => setFormData({ ...formData, auto_post: e.target.checked })} />
                            <span style={{ fontSize: 'var(--text-sm)', color: 'var(--text-primary)' }}>Auto-post when generated</span>
                        </label>
                        <label style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', cursor: 'pointer', padding: '0.5rem 0' }}>
                            <input type="checkbox" checked={formData.use_month_end_default} onChange={e => setFormData({ ...formData, use_month_end_default: e.target.checked })} />
                            <span style={{ fontSize: 'var(--text-sm)', color: 'var(--text-primary)' }}>Use month-end default dates (posting = last day of month)</span>
                        </label>
                        <label style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', cursor: 'pointer', padding: '0.5rem 0' }}>
                            <input type="checkbox" checked={formData.auto_reverse_on_month_start} onChange={e => setFormData({ ...formData, auto_reverse_on_month_start: e.target.checked })} />
                            <span style={{ fontSize: 'var(--text-sm)', color: 'var(--text-primary)' }}>Auto-reverse on 1st day of next month</span>
                        </label>
                    </div>
                </div>

                {dims && (
                    <div className="card" style={{ marginBottom: '2rem' }}>
                        <h3 style={{ marginBottom: '1.5rem' }}>Dimensions</h3>
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1rem' }}>
                            <div>
                                <label className="label">Fund</label>
                                <select value={formData.fund} onChange={e => setFormData({ ...formData, fund: e.target.value })}>
                                    <option value="">Select Fund</option>
                                    {dims.funds?.map((f: any) => <option key={f.id} value={f.id}>{f.code} - {f.name}</option>)}
                                </select>
                            </div>
                            <div>
                                <label className="label">Function</label>
                                <select value={formData.function} onChange={e => setFormData({ ...formData, function: e.target.value })}>
                                    <option value="">Select Function</option>
                                    {dims.functions?.map((f: any) => <option key={f.id} value={f.id}>{f.code} - {f.name}</option>)}
                                </select>
                            </div>
                            <div>
                                <label className="label">Program</label>
                                <select value={formData.program} onChange={e => setFormData({ ...formData, program: e.target.value })}>
                                    <option value="">Select Program</option>
                                    {dims.programs?.map((p: any) => <option key={p.id} value={p.id}>{p.code} - {p.name}</option>)}
                                </select>
                            </div>
                            <div>
                                <label className="label">Geo</label>
                                <select value={formData.geo} onChange={e => setFormData({ ...formData, geo: e.target.value })}>
                                    <option value="">Select Geo</option>
                                    {dims.geos?.map((g: any) => <option key={g.id} value={g.id}>{g.code} - {g.name}</option>)}
                                </select>
                            </div>
                        </div>
                    </div>
                )}

                <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                        <thead>
                            <tr style={{ background: 'var(--background)', textAlign: 'left' }}>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)' }}>GL Account</th>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)' }}>Description</th>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', width: '150px' }}>Debit</th>
                                <th style={{ padding: '1rem', fontSize: 'var(--text-xs)', width: '150px' }}>Credit</th>
                                <th style={{ padding: '1rem', width: '50px' }}></th>
                            </tr>
                        </thead>
                        <tbody>
                            {lines.map((line, idx) => (
                                <tr key={line._uid} style={{ borderBottom: '1px solid var(--border)' }}>
                                    <td style={{ padding: '0.75rem' }}>
                                        <select value={line.account} onChange={e => updateLine(idx, 'account', e.target.value)} required>
                                            <option value="">Select Account</option>
                                            {dims?.accounts?.map((a: any) => <option key={a.id} value={a.id}>{a.code} - {a.name}</option>)}
                                        </select>
                                    </td>
                                    <td style={{ padding: '0.75rem' }}>
                                        <input type="text" value={line.description} onChange={e => updateLine(idx, 'description', e.target.value)} placeholder="Line description" />
                                    </td>
                                    <td style={{ padding: '0.75rem' }}>
                                        <input type="number" step="0.01" value={line.debit} onChange={e => updateLine(idx, 'debit', e.target.value)} />
                                    </td>
                                    <td style={{ padding: '0.75rem' }}>
                                        <input type="number" step="0.01" value={line.credit} onChange={e => updateLine(idx, 'credit', e.target.value)} />
                                    </td>
                                    <td style={{ padding: '0.75rem' }}>
                                        {lines.length > 2 && (
                                            <button type="button" onClick={() => removeLine(idx)} style={{ color: 'var(--error)', background: 'none', border: 'none', cursor: 'pointer' }}>
                                                <Trash2 size={18} />
                                            </button>
                                        )}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                        <tfoot>
                            <tr style={{ background: 'var(--surface)' }}>
                                <td style={{ padding: '1rem' }}>
                                    <button type="button" className="btn btn-outline" style={{ fontSize: 'var(--text-xs)' }} onClick={addLine}>
                                        <Plus size={14} /> Add Line
                                    </button>
                                </td>
                                <td style={{ padding: '1rem', fontWeight: 700, textAlign: 'right', borderTop: '2px solid var(--border)' }}>{formatCurrency(totalDebit)}</td>
                                <td style={{ padding: '1rem', fontWeight: 700, textAlign: 'right', borderTop: '2px solid var(--border)' }}>{formatCurrency(totalCredit)}</td>
                                <td colSpan={2} style={{ padding: '1rem' }}>
                                    {!isBalanced && totalDebit > 0 && (
                                        <div style={{ color: 'var(--error)', fontSize: 'var(--text-xs)' }}>Entry is not balanced</div>
                                    )}
                                </td>
                            </tr>
                        </tfoot>
                    </table>
                </div>
            </form>
            <style>{`
                .label {
                    display: block; 
                    margin-bottom: 0.5rem; 
                    font-size: 0.75rem; 
                    font-weight: 600; 
                    text-transform: uppercase; 
                    color: var(--text-muted);
                }
            `}</style>
        </AccountingLayout>
    );
};

export default RecurringJournalForm;
