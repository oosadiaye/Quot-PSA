import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuotations, useSendQuotation, useConvertQuotationToOrder } from '../hooks/useSales';
import { useDialog } from '../../../hooks/useDialog';
import { useBranding, type BrandingInfo } from '../../../context/BrandingContext';
import AccountingLayout from '../../accounting/AccountingLayout';
import LoadingScreen from '../../../components/common/LoadingScreen';
import PageHeader from '../../../components/PageHeader';
import { Plus, Search, Send, ArrowRight, FileText, Pencil, Printer, Download } from 'lucide-react';

// ── Print / Download helpers ─────────────────────────────────────────────────

function buildQuotationHTML(quote: any, brand: BrandingInfo): string {
    const fmt = (n: any) =>
        Number(n || 0).toLocaleString('en-NG', { style: 'currency', currency: 'NGN' });
    const fmtDate = (d: string) =>
        d ? new Date(d).toLocaleDateString('en-GB', { day: '2-digit', month: 'long', year: 'numeric' }) : '—';
    const lines: any[] = quote.lines || [];
    const total = quote.total_amount ?? lines.reduce((s: number, l: any) => s + (Number(l.total_price) || 0), 0);

    const lineRows = lines.map((l: any, i: number) =>
        `<tr>
            <td>${i + 1}</td>
            <td>${l.item_description || '—'}</td>
            <td style="text-align:center">${Number(l.quantity).toLocaleString()}</td>
            <td style="text-align:right">${fmt(l.unit_price)}</td>
            <td style="text-align:center">${l.discount_percent || 0}%</td>
            <td style="text-align:right">${fmt(l.total_price)}</td>
        </tr>`
    ).join('');

    return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<title>Quotation ${quote.quotation_number}</title>
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:'Segoe UI',Arial,sans-serif;font-size:13px;color:#1e293b;padding:40px}
  .hdr{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:32px;padding-bottom:20px;border-bottom:3px solid #191e6a}
  .co{font-size:22px;font-weight:800;color:#191e6a}
  .dt{font-size:28px;font-weight:800;color:#191e6a;text-align:right}
  .dn{font-size:13px;color:#64748b;text-align:right;margin-top:4px}
  .badge{display:inline-block;padding:3px 10px;border-radius:9999px;font-size:11px;font-weight:700;background:rgba(34,197,94,.15);color:#16a34a;margin-top:8px}
  .grid{display:grid;grid-template-columns:1fr 1fr;gap:24px;margin-bottom:28px}
  .box{background:#f8fafc;border-radius:8px;padding:14px 18px}
  .lbl{font-size:11px;font-weight:700;text-transform:uppercase;color:#64748b;letter-spacing:.5px;margin-bottom:6px}
  .val{font-size:14px;font-weight:600;color:#1e293b}
  table{width:100%;border-collapse:collapse;margin-bottom:20px}
  thead tr{background:#191e6a;color:white}
  th{padding:10px 12px;text-align:left;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.4px}
  td{padding:9px 12px;border-bottom:1px solid #e2e8f0}
  tbody tr:nth-child(even){background:#f8fafc}
  .tot{display:flex;justify-content:flex-end;margin-bottom:32px}
  .tot-box{min-width:280px}
  .tr{display:flex;justify-content:space-between;padding:6px 0;font-size:13px;color:#475569;border-bottom:1px solid #e2e8f0}
  .tr.grand{font-size:16px;font-weight:800;color:#191e6a;border-bottom:none;padding-top:10px}
  .footer{margin-top:40px;padding-top:16px;border-top:1px solid #e2e8f0;font-size:11px;color:#94a3b8;text-align:center}
  @media print{body{padding:20px}@page{margin:15mm}}
  @media print and (max-width:480px){body{padding:8px}@page{margin:8mm}th,td{padding:5px 6px;font-size:10px}.hdr{flex-direction:column;gap:8px}.meta{grid-template-columns:1fr 1fr}.tot-box{min-width:auto;width:100%}.tr{font-size:11px}}
</style>
</head>
<body>
  <div class="hdr">
    <div style="display:flex;align-items:center;gap:12px">
      ${brand.logo ? `<img src="${brand.logo}" alt="${brand.name}" style="width:48px;height:48px;object-fit:contain;border-radius:8px" />` : ''}
      <div>
        <div class="co">${brand.name}</div>
        <div style="color:#64748b;margin-top:4px">${brand.tagline || ''}</div>
      </div>
    </div>
    <div>
      <div class="dt">QUOTATION</div>
      <div class="dn">${quote.quotation_number}</div>
      <div><span class="badge">${quote.status}</span></div>
    </div>
  </div>
  <div class="grid">
    <div class="box">
      <div class="lbl">Bill To</div>
      <div class="val">${quote.customer_name || '—'}</div>
    </div>
    <div class="box">
      <div class="lbl">Quotation Date</div>
      <div class="val">${fmtDate(quote.quotation_date)}</div>
      <div style="height:8px"></div>
      <div class="lbl">Valid Until</div>
      <div class="val">${fmtDate(quote.valid_until)}</div>
    </div>
  </div>
  <table>
    <thead>
      <tr>
        <th>#</th><th>Description</th>
        <th style="text-align:center">Qty</th>
        <th style="text-align:right">Unit Price</th>
        <th style="text-align:center">Disc%</th>
        <th style="text-align:right">Total</th>
      </tr>
    </thead>
    <tbody>${lineRows || '<tr><td colspan="6" style="text-align:center;color:#94a3b8;padding:20px">No line items</td></tr>'}</tbody>
  </table>
  <div class="tot">
    <div class="tot-box">
      <div class="tr grand"><span>Total Amount</span><span>${fmt(total)}</span></div>
    </div>
  </div>
  ${quote.notes ? `<div style="margin-bottom:16px"><div class="lbl" style="margin-bottom:6px">Notes</div><div style="color:#475569">${quote.notes}</div></div>` : ''}
  ${quote.terms ? `<div><div class="lbl" style="margin-bottom:6px">Terms &amp; Conditions</div><div style="color:#475569">${quote.terms}</div></div>` : ''}
  <div class="footer">Generated by ${brand.name} — ${new Date().toLocaleString()}</div>
</body>
</html>`;
}

/** Open in new tab and trigger the browser print dialog (Print or Save as PDF) */
function openPrintWindow(quote: any, brand: BrandingInfo) {
    const html = buildQuotationHTML(quote, brand);
    const blob = new Blob([html], { type: 'text/html' });
    const url = URL.createObjectURL(blob);
    const win = window.open(url, '_blank');
    if (!win) { URL.revokeObjectURL(url); return; }
    win.addEventListener('load', () => {
        win.focus();
        win.print();
        URL.revokeObjectURL(url);
    });
}

// ── Component ────────────────────────────────────────────────────────────────
const Quotations = () => {
    const navigate = useNavigate();
    const { showConfirm } = useDialog();
    const { branding } = useBranding();
    const [searchTerm, setSearchTerm] = useState('');
    const [statusFilter, setStatusFilter] = useState('');

    const { data: quotationsData, isLoading } = useQuotations({ status: statusFilter });
    const sendQuotation = useSendQuotation();
    const convertToOrder = useConvertQuotationToOrder();

    const quotations = quotationsData?.results || quotationsData || [];

    const filteredQuotations = Array.isArray(quotations) ? quotations.filter((q: any) =>
        q.quotation_number?.toLowerCase().includes(searchTerm.toLowerCase()) ||
        q.customer_name?.toLowerCase().includes(searchTerm.toLowerCase())
    ) : [];

    const handleSend = async (id: number) => {
        if (await showConfirm('Send this quotation to the customer?')) {
            sendQuotation.mutate(id);
        }
    };

    const handleConvert = async (id: number) => {
        if (await showConfirm('Convert this quotation to a Sales Order?')) {
            convertToOrder.mutate(id, {
                onSuccess: (data: any) => {
                    if (data?.data?.order_id) {
                        navigate(`/sales/orders/${data.data.order_id}`);
                    }
                },
            });
        }
    };

    const getStatusBadge = (status: string) => {
        const colors: Record<string, [string, string]> = {
            'Draft':     ['rgba(156,163,175,0.12)', '#9ca3af'],
            'Sent':      ['rgba(36,113,163,0.12)',  '#2471a3'],
            'Accepted':  ['rgba(34,197,94,0.12)',   '#16a34a'],
            'Rejected':  ['rgba(239,68,68,0.12)',   '#ef4444'],
            'Expired':   ['rgba(245,158,11,0.12)',  '#f59e0b'],
            'Converted': ['rgba(139,92,246,0.12)',  '#8b5cf6'],
        };
        const [bg, color] = colors[status] || colors['Draft'];
        return (
            <span style={{
                display: 'inline-block', padding: '0.25rem 0.75rem',
                borderRadius: '9999px', fontSize: 'var(--text-xs)', fontWeight: 600,
                background: bg, color,
            }}>
                {status}
            </span>
        );
    };

    const actionBtn = (bg: string, color: string): React.CSSProperties => ({
        padding: '0.35rem 0.65rem', borderRadius: '6px', border: 'none',
        background: bg, color, cursor: 'pointer',
        fontSize: 'var(--text-xs)', fontWeight: 600,
        display: 'inline-flex', alignItems: 'center', gap: '0.25rem',
        whiteSpace: 'nowrap' as const,
    });

    if (isLoading) {
        return (
            <AccountingLayout>
                <LoadingScreen message="Loading quotations..." />
            </AccountingLayout>
        );
    }

    return (
        <AccountingLayout>
            <PageHeader
                title="Quotations"
                subtitle="Create and manage sales quotations"
                icon={<FileText size={22} color="white" />}
                actions={
                    <button
                        onClick={() => navigate('/sales/quotations/new')}
                        style={{
                            display: 'flex', alignItems: 'center', gap: '0.5rem',
                            padding: '0.75rem 1.5rem',
                            background: 'rgba(255,255,255,0.2)', color: 'white',
                            border: '1px solid rgba(255,255,255,0.3)', borderRadius: '8px',
                            cursor: 'pointer', fontWeight: 500,
                        }}
                    >
                        <Plus size={20} />
                        New Quotation
                    </button>
                }
            />

            {/* Search & Filter */}
            <div className="glass-card" style={{ marginBottom: '1.5rem', padding: '1rem' }}>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: '1rem' }}>
                    <div style={{ position: 'relative' }}>
                        <Search style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: 'var(--color-text-muted)' }} size={20} />
                        <input
                            type="text"
                            placeholder="Search by quote number or customer..."
                            value={searchTerm}
                            onChange={(e) => setSearchTerm(e.target.value)}
                            style={{
                                width: '100%', paddingLeft: '2.75rem', paddingRight: '1rem',
                                paddingTop: '0.75rem', paddingBottom: '0.75rem',
                                borderRadius: '8px', border: '1px solid var(--color-border)',
                                background: 'var(--color-surface)', color: 'var(--color-text)',
                                fontSize: 'var(--text-sm)',
                            }}
                        />
                    </div>
                    <select
                        value={statusFilter}
                        onChange={(e) => setStatusFilter(e.target.value)}
                        style={{
                            padding: '0.75rem 1rem', borderRadius: '8px',
                            border: '1px solid var(--color-border)',
                            background: 'var(--color-surface)', color: 'var(--color-text)',
                            fontSize: 'var(--text-sm)',
                        }}
                    >
                        <option value="">All Status</option>
                        <option value="Draft">Draft</option>
                        <option value="Sent">Sent</option>
                        <option value="Accepted">Accepted</option>
                        <option value="Rejected">Rejected</option>
                        <option value="Expired">Expired</option>
                        <option value="Converted">Converted</option>
                    </select>
                </div>
            </div>

            {/* Table */}
            <div className="glass-card" style={{ overflow: 'hidden' }}>
                <div style={{ overflowX: 'auto' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                        <thead>
                            <tr style={{ borderBottom: '1px solid var(--color-border)' }}>
                                {['Quote #', 'Customer', 'Date', 'Valid Until', 'Amount', 'Status', 'Actions'].map((h, i) => (
                                    <th key={h} style={{
                                        padding: '0.875rem 1.25rem',
                                        textAlign: i === 4 ? 'right' : i === 5 ? 'center' : i === 6 ? 'right' : 'left',
                                        fontSize: 'var(--text-xs)', fontWeight: 700,
                                        color: 'var(--color-text-muted)', textTransform: 'uppercase', letterSpacing: '0.4px',
                                        background: 'var(--color-surface)',
                                    }}>
                                        {h}
                                    </th>
                                ))}
                            </tr>
                        </thead>
                        <tbody>
                            {filteredQuotations.length > 0 ? (
                                filteredQuotations.map((quote: any, index: number) => {
                                    const isDraft      = quote.status === 'Draft';
                                    const isSent       = quote.status === 'Sent';
                                    const isAccepted   = quote.status === 'Accepted';
                                    const isConverted  = quote.status === 'Converted';

                                    return (
                                        <tr
                                            key={quote.id}
                                            style={{ borderBottom: '1px solid var(--color-border)', animation: `fadeInUp 0.3s ease-out ${index * 0.05}s both` }}
                                        >
                                            <td style={{ padding: '0.875rem 1.25rem', color: 'var(--color-text)', fontWeight: 600 }}>
                                                {quote.quotation_number}
                                            </td>
                                            <td style={{ padding: '0.875rem 1.25rem', color: 'var(--color-text)' }}>
                                                {quote.customer_name}
                                            </td>
                                            <td style={{ padding: '0.875rem 1.25rem', color: 'var(--color-text-muted)', fontSize: 'var(--text-sm)' }}>
                                                {quote.quotation_date ? new Date(quote.quotation_date).toLocaleDateString() : '—'}
                                            </td>
                                            <td style={{ padding: '0.875rem 1.25rem', color: 'var(--color-text-muted)', fontSize: 'var(--text-sm)' }}>
                                                {quote.valid_until ? new Date(quote.valid_until).toLocaleDateString() : '—'}
                                            </td>
                                            <td style={{ padding: '0.875rem 1.25rem', textAlign: 'right', fontWeight: 600, color: 'var(--color-text)', fontSize: 'var(--text-sm)' }}>
                                                {quote.total_amount != null
                                                    ? Number(quote.total_amount).toLocaleString('en-NG', { style: 'currency', currency: 'NGN' })
                                                    : '—'}
                                            </td>
                                            <td style={{ padding: '0.875rem 1.25rem', textAlign: 'center' }}>
                                                {getStatusBadge(quote.status)}
                                            </td>
                                            <td style={{ padding: '0.875rem 1.25rem' }}>
                                                <div style={{ display: 'flex', gap: '0.375rem', justifyContent: 'flex-end', flexWrap: 'wrap' }}>

                                                    {/* Edit: Draft only */}
                                                    {isDraft && (
                                                        <button onClick={() => navigate(`/sales/quotations/${quote.id}`)}
                                                            style={actionBtn('rgba(107,114,128,0.1)', '#6b7280')} title="Edit">
                                                            <Pencil size={12} /> Edit
                                                        </button>
                                                    )}

                                                    {/* Send: Draft or Sent (re-send) */}
                                                    {(isDraft || isSent) && (
                                                        <button onClick={() => handleSend(quote.id)}
                                                            style={actionBtn('rgba(36,113,163,0.1)', '#2471a3')} title="Send to Customer">
                                                            <Send size={12} /> Send
                                                        </button>
                                                    )}

                                                    {/* Print: all statuses */}
                                                    <button onClick={() => openPrintWindow(quote, branding)}
                                                        style={actionBtn('rgba(100,116,139,0.1)', '#475569')} title="Print">
                                                        <Printer size={12} /> Print
                                                    </button>

                                                    {/* PDF download: all statuses — same print window, user saves as PDF */}
                                                    <button onClick={() => openPrintWindow(quote, branding)}
                                                        style={actionBtn('rgba(100,116,139,0.1)', '#475569')} title="Download PDF">
                                                        <Download size={12} /> PDF
                                                    </button>

                                                    {/* Convert to SO: any status except already-converted */}
                                                    {!isConverted && (
                                                        <button onClick={() => handleConvert(quote.id)}
                                                            style={actionBtn(
                                                                isAccepted ? 'var(--color-primary)' : 'rgba(79,70,229,0.12)',
                                                                isAccepted ? 'white' : '#4f46e5'
                                                            )} title="Convert to Sales Order">
                                                            <ArrowRight size={12} /> Convert to SO
                                                        </button>
                                                    )}
                                                </div>
                                            </td>
                                        </tr>
                                    );
                                })
                            ) : (
                                <tr>
                                    <td colSpan={7} style={{ padding: '3rem 1.5rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>
                                        <FileText size={48} style={{ margin: '0 auto 1rem', opacity: 0.5, display: 'block' }} />
                                        <p>No quotations found</p>
                                    </td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>
            </div>
        </AccountingLayout>
    );
};

export default Quotations;
