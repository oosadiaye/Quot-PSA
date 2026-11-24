import { useEffect, useMemo, useState } from 'react';
import { ArrowDownCircle, ArrowUpCircle, Banknote, Eye, Landmark, Pencil, Plus, Printer, RotateCcw, Scale, Send, Settings2, Trash2, Wallet } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import PageHeader from '../../../components/PageHeader';
import LoadingScreen from '../../../components/common/LoadingScreen';
import { useCurrency } from '../../../context/CurrencyContext';
import { useToast } from '../../../context/ToastContext';
import { useDebounce } from '../../../hooks/useDebounce';
import { useDialog } from '../../../hooks/useDialog';
import { formatDate } from '@/utils/date';
import AccountingLayout from '../AccountingLayout';
import CashDocumentModal from './CashDocumentModal';
import CashDocumentViewModal from './CashDocumentViewModal';
import CloseDayModal from './CloseDayModal';
import JournalSettingsModal from './JournalSettingsModal';
import { actionsFor, type DraftDocument } from './cashPosting';
import {
    errorSentence, useCashBook, useCashDocuments, useCashJournals, useDeleteCashDocument, usePostCashDocument, useReplenishment,
    useReverseCashDocument, type CashDocument,
} from './hooks/useCashPosting';
import './cashPosting.css';

const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
const monthStart = () => { const d = new Date(); d.setDate(1); return iso(d); };
const PAGE_SIZES = [10, 25, 50, 100];

type Dialog =
    | { kind: 'edit'; document?: CashDocument; preset?: Partial<DraftDocument> }
    | { kind: 'view'; document: CashDocument }
    | { kind: 'close' }
    | { kind: 'settings' }
    | null;

function Stat({ tone, icon, label, value, note }: { tone: string; icon: React.ReactNode; label: string; value: string; note: string }) {
    return (
        <div className={`cash-stat ${tone}`} data-testid={`cash-stat-${label.toLowerCase().replace(/[^a-z]+/g, '-')}`}>
            <span className="cash-stat-label">{icon}{label}</span>
            <strong>{value}</strong>
            <small>{note}</small>
        </div>
    );
}

/** The Cash Journal (FBCJ): one cash desk, its book for a period, and the documents posted in it. */
export default function CashPostingPage() {
    const navigate = useNavigate();
    const { formatCurrency } = useCurrency();
    const { addToast } = useToast();
    const { showConfirm, showPrompt } = useDialog();
    const money = (v: string | number) => formatCurrency(Number(v));

    const { data: journals = [], isLoading } = useCashJournals();
    const [journalId, setJournalId] = useState<number | null>(null);
    const [from, setFrom] = useState(monthStart());
    const [to, setTo] = useState(iso(new Date()));
    const [status, setStatus] = useState('');
    const [search, setSearch] = useState('');
    const [page, setPage] = useState(1);
    const [pageSize, setPageSize] = useState(25);
    const [dialog, setDialog] = useState<Dialog>(null);
    const debouncedSearch = useDebounce(search, 300);

    useEffect(() => { if (journalId === null && journals.length) setJournalId(journals[0].id); }, [journals, journalId]);
    useEffect(() => { setPage(1); }, [journalId, from, to, status, debouncedSearch, pageSize]);

    const journal = useMemo(() => journals.find(j => j.id === journalId) ?? null, [journals, journalId]);
    const book = useCashBook(journalId, from, to).data;
    const documents = useCashDocuments({ journal: journalId, from, to, status, search: debouncedSearch, page, pageSize });
    const replenish = useReplenishment(journalId, !!journal && Number(journal.float_amount) > 0).data;
    const postDoc = usePostCashDocument();
    const reverseDoc = useReverseCashDocument();
    const deleteDoc = useDeleteCashDocument();

    const rows = documents.data?.results ?? [];
    const total = documents.data?.count ?? 0;
    const pages = Math.max(1, Math.ceil(total / pageSize));

    const run = async (work: Promise<unknown>, done: string) => {
        try { await work; addToast(done, 'success'); } catch (err) { addToast(errorSentence(err), 'error'); }
    };
    const onPost = async (doc: CashDocument) => {
        if (await showConfirm(`Post ${doc.document_number} for ${money(doc.amount)}? This writes the journal and moves the cash book.`, 'Post cash document')) {
            await run(postDoc.mutateAsync(doc.id), `${doc.document_number} posted.`);
        }
    };
    const onReverse = async (doc: CashDocument) => {
        const reason = await showPrompt(`Why is ${doc.document_number} being reversed?`, 'Reverse cash document');
        if (reason === null) return;
        await run(reverseDoc.mutateAsync({ id: doc.id, reason }), `${doc.document_number} reversed.`);
    };
    const onDelete = async (doc: CashDocument) => {
        if (await showConfirm(`Delete draft ${doc.document_number}?`, 'Delete draft')) await run(deleteDoc.mutateAsync(doc.id), 'Draft deleted.');
    };
    const topUp = () => {
        if (!replenish) return;
        setDialog({ kind: 'edit', preset: { transaction_type: 'BANK_WITHDRAWAL', amount: replenish.amount, description: 'Imprest replenishment' } });
    };

    if (isLoading) return <LoadingScreen message="Loading cash journals..." />;

    const party = (d: CashDocument) => d.offset_account_code ? `${d.offset_account_code} ${d.offset_account_name}` : d.bank_account_name || (d.lines.length ? `${d.lines.length} accounts` : '');

    return (
        <AccountingLayout>
            <PageHeader
                title="Cash Journal"
                subtitle="Post cash and petty cash movements, top up the fund when it runs low."
                icon={<Banknote size={22} />}
                actions={journal && (
                    <div className="cash-header-actions">
                        <button type="button" className="cash-btn ghost" onClick={() => setDialog({ kind: 'settings' })} data-testid="cash-settings"><Settings2 size={15} /> Settings</button>
                        <button type="button" className="cash-btn ghost" onClick={() => setDialog({ kind: 'close' })} data-testid="cash-close-day"><Scale size={15} /> Close day</button>
                        <button type="button" className="cash-btn solid" onClick={() => setDialog({ kind: 'edit' })} data-testid="cash-new"><Plus size={16} /> New cash document</button>
                    </div>
                )}
            />

            {!journal ? (
                <div className="card cash-empty" data-testid="cash-no-journal">
                    <Wallet size={28} />
                    <h3>No cash journal yet</h3>
                    <p>A cash journal is made automatically for each Cash, Petty Cash or Imprest account. Add one in Bank &amp; Cash, then come back here.</p>
                    <button type="button" className="cash-btn primary" onClick={() => navigate('/accounting/tsa-accounts')}>Go to Bank &amp; Cash</button>
                </div>
            ) : (
                <>
                    <div className="cash-filters">
                        <label><span>Cash journal</span>
                            <select value={journal.id} onChange={e => setJournalId(Number(e.target.value))} data-testid="cash-journal-select">
                                {journals.map(j => <option key={j.id} value={j.id}>{j.code} - {j.name} ({money(j.balance)})</option>)}
                            </select>
                        </label>
                        <label><span>From</span><input type="date" value={from} max={to} onChange={e => setFrom(e.target.value)} /></label>
                        <label><span>To</span><input type="date" value={to} min={from} onChange={e => setTo(e.target.value)} /></label>
                        <label><span>Status</span>
                            <select value={status} onChange={e => setStatus(e.target.value)}>
                                <option value="">All</option><option>Draft</option><option>Posted</option><option>Reversed</option>
                            </select>
                        </label>
                    </div>
                    <input className="cash-search" type="search" placeholder="Search number, reference, description" value={search} onChange={e => setSearch(e.target.value)} aria-label="Search cash documents" />

                    <div className="cash-stats">
                        <Stat tone="neutral" icon={<Wallet size={14} />} label="Opening balance" value={money(book?.opening_balance ?? 0)} note={`At ${formatDate(from)}`} />
                        <Stat tone="in" icon={<ArrowDownCircle size={14} />} label="Receipts" value={money(book?.receipts ?? 0)} note="Cash in, posted" />
                        <Stat tone="out" icon={<ArrowUpCircle size={14} />} label="Payments" value={money(book?.payments ?? 0)} note="Cash out, posted" />
                        <Stat tone="balance" icon={<Banknote size={14} />} label="Cash balance" value={money(book?.closing_balance ?? 0)}
                            note={`Available at ${formatDate(to)}${book?.last_closed_date ? ` | closed to ${formatDate(book.last_closed_date)}` : ''}`} />
                        <Stat tone="balance" icon={<Scale size={14} />} label="Balance incl. drafts" value={money(book?.balance_including_drafts ?? 0)}
                            note={book && (Number(book.draft_receipts) || Number(book.draft_payments))
                                ? `${money(book.draft_receipts)} in | ${money(book.draft_payments)} out in drafts` : 'nothing in | nothing out in drafts'} />
                    </div>

                    {replenish && Number(replenish.amount) > 0 && (
                        <div className="cash-topup" role="status" data-testid="cash-topup">
                            <Landmark size={18} />
                            <span>The fund holds {money(replenish.balance)} of its {money(replenish.float_amount)} float. Bring it back up with {money(replenish.amount)} from the bank.</span>
                            <button type="button" className="cash-btn primary" onClick={topUp}>Top up the fund</button>
                        </div>
                    )}

                    <div className="card cash-table-card">
                        <div className="cash-table-title">Cash documents</div>
                        <div className="cash-table-scroll">
                            <table className="cash-table" data-testid="cash-table">
                                <thead>
                                    <tr><th>Document No</th><th>Date</th><th>Transaction</th><th>Account / party</th><th>Reference</th><th>Recipient</th>
                                        <th className="r">Receipts</th><th className="r">Payments</th><th>Status</th><th className="r">Actions</th></tr>
                                </thead>
                                <tbody>
                                    {rows.length === 0 && <tr><td colSpan={10} className="cash-none">{documents.isLoading ? 'Loading...' : 'No cash documents match these filters.'}</td></tr>}
                                    {rows.map(doc => {
                                        const can = actionsFor(doc, journal.last_closed_date);
                                        return (
                                            <tr key={doc.id} data-testid="cash-row">
                                                <td><strong>{doc.document_number}</strong></td>
                                                <td>{formatDate(doc.posting_date)}</td>
                                                <td>{doc.transaction_type_label}</td>
                                                <td>{party(doc)}</td>
                                                <td>{doc.reference || '-'}</td>
                                                <td>{doc.recipient || '-'}</td>
                                                <td className="r mono">{doc.is_receipt ? money(doc.amount) : ''}</td>
                                                <td className="r mono">{doc.is_receipt ? '' : money(doc.amount)}</td>
                                                <td><span className={`cash-status ${doc.status.toLowerCase()}`}>{doc.status}</span></td>
                                                <td className="r">
                                                    <div className="cash-row-actions">
                                                        <button type="button" className="cash-icon-btn" title="View" aria-label={`View ${doc.document_number}`} onClick={() => setDialog({ kind: 'view', document: doc })}><Eye size={15} /></button>
                                                        <button type="button" className="cash-icon-btn" title="Print voucher" aria-label={`Print ${doc.document_number}`} onClick={() => navigate(`/accounting/cash-posting/${doc.id}/print`)}><Printer size={15} /></button>
                                                        {can.canEdit && <button type="button" className="cash-icon-btn" title="Edit" aria-label={`Edit ${doc.document_number}`} onClick={() => setDialog({ kind: 'edit', document: doc })}><Pencil size={15} /></button>}
                                                        {can.canPost && <button type="button" className="cash-icon-btn good" title="Post" aria-label={`Post ${doc.document_number}`} onClick={() => onPost(doc)} data-testid="cash-post"><Send size={15} /></button>}
                                                        {can.canReverse && <button type="button" className="cash-icon-btn" title="Reverse" aria-label={`Reverse ${doc.document_number}`} onClick={() => onReverse(doc)} data-testid="cash-reverse"><RotateCcw size={15} /></button>}
                                                        {can.canDelete && <button type="button" className="cash-icon-btn bad" title="Delete" aria-label={`Delete ${doc.document_number}`} onClick={() => onDelete(doc)}><Trash2 size={15} /></button>}
                                                    </div>
                                                </td>
                                            </tr>
                                        );
                                    })}
                                </tbody>
                            </table>
                        </div>
                    </div>

                    <div className="cash-pager">
                        <label>Show
                            <select value={pageSize} onChange={e => setPageSize(Number(e.target.value))}>{PAGE_SIZES.map(n => <option key={n}>{n}</option>)}</select>
                            per page
                        </label>
                        <span>{total} {total === 1 ? 'document' : 'documents'}</span>
                        <div>
                            <button type="button" className="cash-btn" disabled={page <= 1} onClick={() => setPage(p => p - 1)}>Previous</button>
                            <span className="cash-page">Page {page} of {pages}</span>
                            <button type="button" className="cash-btn" disabled={page >= pages} onClick={() => setPage(p => p + 1)}>Next</button>
                        </div>
                    </div>
                </>
            )}

            {journal && dialog?.kind === 'edit' && (
                <CashDocumentModal journals={journals} journal={journal} document={dialog.document} preset={dialog.preset}
                    onClose={() => setDialog(null)}
                    onSaved={doc => { setDialog(null); addToast(`${doc.document_number} saved as a draft. Post it when the entries are right.`, 'success'); }} />
            )}
            {dialog?.kind === 'view' && <CashDocumentViewModal document={dialog.document} onClose={() => setDialog(null)} />}
            {journal && dialog?.kind === 'close' && (
                <CloseDayModal journal={journal} book={book} onClose={() => setDialog(null)}
                    onDone={() => { setDialog(null); addToast('The day is closed.', 'success'); }} />
            )}
            {journal && dialog?.kind === 'settings' && <JournalSettingsModal journal={journal} onClose={() => setDialog(null)} />}
        </AccountingLayout>
    );
}
