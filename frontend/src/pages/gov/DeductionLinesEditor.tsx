/**
 * DeductionLinesEditor — Quot PSE.
 *
 * Shared editor for a Payment Voucher's deduction lines. Each line is chosen
 * from ONE searchable dropdown that lists both Withholding Tax codes and
 * Payment Deduction codes; the chosen setting drives the line's GL account
 * and amount (percentage of gross, or a fixed amount). Nothing on a line is
 * typed by hand, so what posts always matches the configured setting.
 *
 * Used by the PV create form and the DRAFT PV edit-in-place flow, so the
 * behaviour (and the mapping to/from the API) lives in one place.
 */
import { useEffect, useMemo } from 'react';
import { Plus, X } from 'lucide-react';
import SearchableSelect from '../../components/SearchableSelect';
import {
    useWithholdingTaxes,
    usePaymentDeductionCodes,
} from '../../features/accounting/hooks/useAccountingEnhancements';

const fmtNGN = (v: number | string): string => {
    const num = typeof v === 'string' ? parseFloat(v) : v;
    if (isNaN(num)) return '₦0.00';
    return '₦' + num.toLocaleString('en-NG', { minimumFractionDigits: 2 });
};

export type DeductionType =
    | 'WHT' | 'STAMP_DUTY' | 'VAT_WITHHELD'
    | 'HANDLING' | 'INSURANCE' | 'RETENTION' | 'OTHER';

export interface DeductionRow {
    _uid: number;
    selection: string;          // 'wht:<id>' | 'ded:<id>' | '' — the picked setting
    deduction_type: DeductionType;
    description: string;
    withholding_tax: string;    // WHT code FK id (string), '' when none
    deduction_code: string;     // PaymentDeductionCode FK id (string), '' when none
    calc: 'percentage' | 'fixed';
    rate: string;               // percent — informational + recompute basis
    amount: string;             // computed from the setting + gross
    gl_account: string;         // GL FK id (string), derived from the setting
    gl_label: string;           // "code — name" for the read-only GL display
    basis: string;              // "5%" or "₦1,500.00" for display
}

/* eslint-disable @typescript-eslint/no-explicit-any */

export const emptyDeductionRow = (uid: number): DeductionRow => ({
    _uid: uid, selection: '', deduction_type: 'OTHER', description: '',
    withholding_tax: '', deduction_code: '', calc: 'percentage',
    rate: '', amount: '0', gl_account: '', gl_label: '', basis: '',
});

/** Next unused uid for a fresh row. */
export const nextUid = (rows: DeductionRow[]): number =>
    rows.reduce((m, d) => Math.max(m, d._uid), 0) + 1;

/** Apply a chosen setting to a row → derive type / GL / rate / amount. */
export function applySetting(
    row: DeductionRow, value: string, gross: number,
    whtCodes: any[], deductionCodes: any[],
): DeductionRow {
    if (!value) {
        return {
            ...row, selection: '', deduction_type: 'OTHER', description: '',
            withholding_tax: '', deduction_code: '', calc: 'percentage',
            rate: '', amount: '0', gl_account: '', gl_label: '', basis: '',
        };
    }
    const [src, idStr] = value.split(':');
    if (src === 'wht') {
        const w = whtCodes.find((x) => String(x.id) === idStr);
        if (!w) return row;
        const rate = parseFloat(String(w.rate || '0'));
        const amount = gross > 0 ? gross * rate / 100 : 0;
        return {
            ...row, selection: value, deduction_type: 'WHT',
            withholding_tax: idStr, deduction_code: '', calc: 'percentage',
            rate: String(rate), amount: amount.toFixed(2), basis: `${rate}%`,
            gl_account: w.withholding_account ? String(w.withholding_account) : '',
            gl_label: w.withholding_account_display
                ? `${w.withholding_account_display.code} — ${w.withholding_account_display.name}` : '',
            description: `${w.code} ${w.name}`,
        };
    }
    const c = deductionCodes.find((x) => String(x.id) === idStr);
    if (!c) return row;
    const isPct = c.calculation_method === 'percentage';
    const rate = parseFloat(String(c.rate || '0'));
    const fixed = parseFloat(String(c.fixed_amount || '0'));
    const amount = isPct ? (gross > 0 ? gross * rate / 100 : 0) : fixed;
    return {
        ...row, selection: value, deduction_type: c.deduction_type,
        withholding_tax: '', deduction_code: idStr,
        calc: c.calculation_method,
        rate: isPct ? String(rate) : '0', amount: amount.toFixed(2),
        basis: isPct ? `${rate}%` : fmtNGN(fixed),
        gl_account: c.gl_account ? String(c.gl_account) : '',
        gl_label: c.gl_account_code ? `${c.gl_account_code} — ${c.gl_account_name}` : '',
        description: `${c.code} ${c.name}`,
    };
}

interface RawPVDeduction {
    deduction_type: DeductionType;
    description?: string;
    withholding_tax?: number | null;
    deduction_code?: number | null;
    rate?: string | number;
    amount?: string | number;
    gl_account?: number | null;
    gl_account_code?: string | null;
    gl_account_name?: string | null;
}

/** Map a PV's saved deduction rows back into editable rows (for edit mode). */
export function hydrateDeductions(
    rows: RawPVDeduction[] | undefined,
    whtCodes: any[], deductionCodes: any[],
): DeductionRow[] {
    return (rows || []).map((r, i) => {
        const amount = String(r.amount ?? '0');
        const glLabel = r.gl_account_code ? `${r.gl_account_code} — ${r.gl_account_name ?? ''}` : '';
        const glId = r.gl_account ? String(r.gl_account) : '';
        if (r.withholding_tax) {
            const w = whtCodes.find((x) => x.id === r.withholding_tax);
            const rate = parseFloat(String(r.rate ?? w?.rate ?? '0'));
            return {
                _uid: i + 1, selection: `wht:${r.withholding_tax}`, deduction_type: 'WHT',
                description: r.description ?? '', withholding_tax: String(r.withholding_tax),
                deduction_code: '', calc: 'percentage', rate: String(rate),
                amount, basis: `${rate}%`, gl_account: glId, gl_label: glLabel,
            };
        }
        if (r.deduction_code) {
            const c = deductionCodes.find((x) => x.id === r.deduction_code);
            const isPct = c ? c.calculation_method === 'percentage' : parseFloat(String(r.rate ?? 0)) > 0;
            const rate = parseFloat(String(r.rate ?? c?.rate ?? '0'));
            return {
                _uid: i + 1, selection: `ded:${r.deduction_code}`, deduction_type: r.deduction_type,
                description: r.description ?? '', withholding_tax: '', deduction_code: String(r.deduction_code),
                calc: isPct ? 'percentage' : 'fixed', rate: isPct ? String(rate) : '0',
                amount, basis: isPct ? `${rate}%` : fmtNGN(amount), gl_account: glId, gl_label: glLabel,
            };
        }
        // Legacy line with no linked setting — preserve its GL + amount so a
        // save doesn't silently drop it. Treated as fixed so gross edits leave it.
        return {
            _uid: i + 1, selection: '', deduction_type: r.deduction_type,
            description: r.description ?? '', withholding_tax: '', deduction_code: '',
            calc: 'fixed', rate: '0', amount, basis: fmtNGN(amount),
            gl_account: glId, gl_label: glLabel,
        };
    });
}

/** Build the API payload — keep any line that has a GL account and amount. */
export function serializeDeductions(rows: DeductionRow[]) {
    return rows
        .filter(d => parseFloat(d.amount) > 0 && d.gl_account)
        .map(d => ({
            deduction_type: d.deduction_type,
            description: d.description,
            withholding_tax: d.withholding_tax ? parseInt(d.withholding_tax) : null,
            deduction_code: d.deduction_code ? parseInt(d.deduction_code) : null,
            rate: parseFloat(d.rate || '0') || 0,
            amount: parseFloat(d.amount),
            gl_account: parseInt(d.gl_account),
        }));
}

interface Props {
    gross: number;
    deductions: DeductionRow[];
    setDeductions: React.Dispatch<React.SetStateAction<DeductionRow[]>>;
}

const inputStyle: React.CSSProperties = {
    width: '100%', padding: '0.5rem 0.625rem', borderRadius: '6px',
    border: '2.5px solid var(--color-border)', background: 'var(--color-surface)',
    color: 'var(--color-text)', fontSize: 'var(--text-xs)',
};

export function DeductionLinesEditor({ gross, deductions, setDeductions }: Props) {
    const { data: whtData } = useWithholdingTaxes({ is_active: true });
    const whtCodes: any[] = Array.isArray(whtData) ? whtData : (whtData?.results ?? []);
    const { data: dedData } = usePaymentDeductionCodes({ is_active: true });
    const deductionCodes: any[] = Array.isArray(dedData) ? dedData : (dedData?.results ?? []);

    // One flat, searchable option list: WHT codes first, then deduction codes.
    const options = useMemo(() => ([
        ...whtCodes.map((w) => ({
            value: `wht:${w.id}`,
            label: `${w.code} — ${w.name}`,
            sublabel: `Withholding Tax · ${parseFloat(String(w.rate || '0'))}%`,
        })),
        ...deductionCodes.map((c) => ({
            value: `ded:${c.id}`,
            label: `${c.code} — ${c.name}`,
            sublabel: `${c.deduction_type_display} · ${c.calculation_method === 'fixed' ? fmtNGN(c.fixed_amount) : parseFloat(String(c.rate || '0')) + '%'}`,
        })),
    ]), [whtCodes, deductionCodes]);

    // Recompute every percentage line when gross changes; fixed lines stay.
    useEffect(() => {
        setDeductions(prev => prev.map(d => {
            if (!d.selection || d.calc !== 'percentage') return d;
            const rate = parseFloat(d.rate || '0');
            return { ...d, amount: (gross > 0 ? gross * rate / 100 : 0).toFixed(2) };
        }));
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [gross]);

    const add = () => setDeductions(prev => [...prev, emptyDeductionRow(nextUid(prev))]);
    const remove = (uid: number) => setDeductions(prev => prev.filter(d => d._uid !== uid));
    const select = (uid: number, value: string) =>
        setDeductions(prev => prev.map(d => d._uid === uid ? applySetting(d, value, gross, whtCodes, deductionCodes) : d));

    return (
        <div style={{ border: '1px solid var(--color-border)', borderRadius: '8px', padding: '0.75rem', background: 'rgba(0,0,0,0.02)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                <span style={{ fontSize: '0.7rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.04em', color: 'var(--color-text-muted)' }}>
                    Deduction Lines · GL &amp; amount posted from the setting
                </span>
                <button type="button" onClick={add} style={{
                    display: 'flex', alignItems: 'center', gap: '0.25rem',
                    padding: '0.3rem 0.55rem', fontSize: '0.7rem', borderRadius: '6px',
                    border: '1px solid var(--color-border)', background: 'var(--color-surface)',
                    cursor: 'pointer', color: 'var(--color-text)',
                }}>
                    <Plus size={12} /> Add Deduction
                </button>
            </div>
            {deductions.length === 0 ? (
                <p style={{ fontSize: '0.7rem', color: 'var(--color-text-muted)', margin: '0.5rem 0 0' }}>
                    No deductions. Add a line and pick a Withholding Tax or Payment
                    Deduction setting — its GL account and rate/amount post automatically.
                </p>
            ) : (
                <div style={{
                    display: 'grid', gridTemplateColumns: '2.4fr 0.7fr 1fr 1.8fr auto',
                    gap: '0.4rem', padding: '0 0.1rem', fontSize: '0.6rem', fontWeight: 700,
                    textTransform: 'uppercase', letterSpacing: '0.04em', color: 'var(--color-text-muted)',
                }}>
                    <span>Deduction setting</span>
                    <span style={{ textAlign: 'center' }}>Basis</span>
                    <span style={{ textAlign: 'right' }}>Amount</span>
                    <span>GL account</span>
                    <span />
                </div>
            )}
            {deductions.map(d => (
                <div key={d._uid} style={{
                    display: 'grid', gridTemplateColumns: '2.4fr 0.7fr 1fr 1.8fr auto',
                    gap: '0.4rem', marginTop: '0.4rem', alignItems: 'center',
                }}>
                    <SearchableSelect
                        options={options}
                        value={d.selection}
                        onChange={(v) => select(d._uid, v)}
                        placeholder="Search WHT or deduction setting…"
                    />
                    <div style={{ fontSize: '0.72rem', fontWeight: 600, textAlign: 'center', color: 'var(--color-text-muted)' }}>
                        {d.selection ? d.basis : '—'}
                    </div>
                    <div style={{
                        ...inputStyle, fontSize: '0.72rem', fontWeight: 700,
                        background: 'rgba(234,179,8,0.06)', color: '#ca8a04',
                        display: 'flex', alignItems: 'center', justifyContent: 'flex-end',
                    }}>
                        {fmtNGN(d.amount)}
                    </div>
                    <div style={{
                        fontSize: '0.68rem', display: 'flex', alignItems: 'center',
                        overflow: 'hidden', whiteSpace: 'nowrap', textOverflow: 'ellipsis',
                        color: d.gl_label ? 'var(--color-text)' : '#ef4444',
                    }} title={d.gl_label || 'The selected setting has no GL account'}>
                        {d.gl_label || 'No GL on setting'}
                    </div>
                    <button type="button" onClick={() => remove(d._uid)} title="Remove deduction" style={{
                        padding: '0.3rem', border: 'none', background: 'none', cursor: 'pointer',
                        color: '#ef4444', display: 'flex', alignItems: 'center', justifyContent: 'center',
                    }}>
                        <X size={14} />
                    </button>
                </div>
            ))}
        </div>
    );
}
