/**
 * Appropriation admin — Quot PSE
 * Route: /budget/appropriations
 *
 * Lists the full appropriation register with filter + inline drawer
 * to create a new appropriation across all six NCoA dimensions
 * (administrative, economic, functional, programme, fund, geographic).
 */
import { useMemo, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
    Award, Plus, X, Search, AlertTriangle,
} from 'lucide-react';
import apiClient from '../../api/client';
import { ListPageShell } from '../../components/layout';

interface Appropriation {
    id: number;
    fiscal_year: number;
    fiscal_year_label: string;
    administrative: number;
    administrative_code: string;
    administrative_name: string;
    economic: number;
    economic_code: string;
    economic_name: string;
    functional: number;
    functional_code: string;
    functional_name: string;
    programme: number;
    programme_code: string;
    programme_name: string;
    fund: number;
    fund_code: string;
    fund_name: string;
    geographic: number | null;
    geographic_code: string | null;
    geographic_name: string | null;
    amount_approved: string;
    appropriation_type: string;
    status: string;
    total_committed: string;
    total_expended: string;
    available_balance: string;
    execution_rate: number;
}

interface Segment {
    id: number;
    code: string;
    name: string;
}

const fmtNGN = (v: string | number) => {
    const n = typeof v === 'string' ? parseFloat(v) : v;
    return 'NGN ' + (Number.isFinite(n) ? n : 0).toLocaleString('en-NG', {
        minimumFractionDigits: 2, maximumFractionDigits: 2,
    });
};

const STATUS_COLORS: Record<string, string> = {
    DRAFT: '#64748b', SUBMITTED: '#d97706', APPROVED: '#1e40af',
    ENACTED: '#059669', ACTIVE: '#16a34a', CLOSED: '#6b7280',
};

async function fetchSegments(endpoint: string): Promise<Segment[]> {
    const res = await apiClient.get(endpoint, {
        params: { page_size: 500, is_active: true },
    });
    return Array.isArray(res.data) ? res.data : (res.data?.results ?? []);
}

export default function AppropriationAdminPage() {
    const qc = useQueryClient();
    const [filter, setFilter] = useState('');
    const [creating, setCreating] = useState(false);

    const { data, isLoading } = useQuery<Appropriation[]>({
        queryKey: ['appropriations-admin'],
        queryFn: async () => {
            const res = await apiClient.get('/budget/appropriations/', {
                params: { page_size: 500 },
            });
            return Array.isArray(res.data) ? res.data : (res.data?.results ?? []);
        },
    });

    const rows = data ?? [];

    const filtered = useMemo(() => {
        if (!filter.trim()) return rows;
        const needle = filter.trim().toLowerCase();
        return rows.filter(r =>
            (r.administrative_name ?? '').toLowerCase().includes(needle) ||
            (r.administrative_code ?? '').toLowerCase().includes(needle) ||
            (r.economic_name ?? '').toLowerCase().includes(needle) ||
            (r.economic_code ?? '').toLowerCase().includes(needle) ||
            (r.programme_name ?? '').toLowerCase().includes(needle) ||
            (r.geographic_name ?? '').toLowerCase().includes(needle) ||
            (r.status ?? '').toLowerCase().includes(needle)
        );
    }, [rows, filter]);

    return (
        <ListPageShell>
                <div style={{
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                    marginBottom: 20,
                }}>
                    <div>
                        <h1 style={{
                            fontSize: 24, fontWeight: 800, color: '#1e293b', margin: 0,
                            display: 'flex', alignItems: 'center', gap: 10,
                        }}>
                            <Award size={22} /> Budget Appropriations
                        </h1>
                        <p style={{ color: '#64748b', fontSize: 14, margin: '4px 0 0' }}>
                            Full appropriation register — create, review, and activate
                            budget allocations across all six NCoA dimensions.
                        </p>
                    </div>
                    <button
                        onClick={() => setCreating(true)}
                        style={{
                            display: 'flex', alignItems: 'center', gap: 6,
                            padding: '8px 16px', borderRadius: 8, border: 'none',
                            background: '#1e40af', color: '#fff',
                            cursor: 'pointer', fontSize: 14, fontWeight: 600,
                        }}
                    >
                        <Plus size={16} /> New Appropriation
                    </button>
                </div>

                {/* Filter bar */}
                <div style={{
                    background: '#fff', borderRadius: 12, border: '1px solid #e8ecf1',
                    padding: '10px 16px', marginBottom: 16,
                    display: 'flex', alignItems: 'center', gap: 10,
                }}>
                    <Search size={16} style={{ color: '#94a3b8' }} />
                    <input
                        value={filter}
                        onChange={e => setFilter(e.target.value)}
                        placeholder="Filter by MDA / economic / programme / geographic / status…"
                        style={{
                            flex: 1, padding: '8px 10px',
                            border: '1px solid #e2e8f0', borderRadius: 8,
                            fontSize: 14, outline: 'none',
                        }}
                    />
                    <div style={{ fontSize: 12, color: '#64748b', whiteSpace: 'nowrap' }}>
                        {rows.length > 0
                            ? `${filtered.length} of ${rows.length}`
                            : ''}
                    </div>
                </div>

                {/* Table */}
                <div style={{
                    background: '#fff', borderRadius: 12, border: '1px solid #e8ecf1',
                    overflow: 'hidden',
                }}>
                    {isLoading ? (
                        <div style={{ padding: 40, textAlign: 'center', color: '#94a3b8' }}>
                            Loading…
                        </div>
                    ) : filtered.length === 0 ? (
                        <div style={{ padding: 40, textAlign: 'center', color: '#94a3b8' }}>
                            {filter ? `No appropriations match "${filter}".` : 'No appropriations yet.'}
                        </div>
                    ) : (
                        <div style={{ overflowX: 'auto' }}>
                            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 1200 }}>
                                <thead>
                                    <tr style={{ background: '#f8fafc', borderBottom: '2px solid #e8ecf1' }}>
                                        {['FY', 'MDA', 'Economic', 'Functional', 'Programme', 'Fund', 'Geographic', 'Approved', 'Committed', 'Expended', 'Status'].map((h, i) => (
                                            <th key={h} style={{
                                                padding: '10px 12px',
                                                textAlign: i >= 7 && i !== 10 ? 'right' : 'left',
                                                fontSize: 11, fontWeight: 700, color: '#64748b',
                                                textTransform: 'uppercase', letterSpacing: '0.5px',
                                                whiteSpace: 'nowrap',
                                            }}>{h}</th>
                                        ))}
                                    </tr>
                                </thead>
                                <tbody>
                                    {filtered.map(r => (
                                        <tr key={r.id} style={{ borderBottom: '1px solid #f1f5f9' }}>
                                            <td style={{
                                                padding: '10px 12px', fontSize: 13,
                                                fontWeight: 700, color: '#1e293b',
                                            }}>
                                                {r.fiscal_year_label || r.fiscal_year}
                                            </td>
                                            <CellBrief
                                                code={r.administrative_code}
                                                name={r.administrative_name}
                                            />
                                            <CellBrief
                                                code={r.economic_code}
                                                name={r.economic_name}
                                            />
                                            <CellBrief
                                                code={r.functional_code}
                                                name={r.functional_name}
                                            />
                                            <CellBrief
                                                code={r.programme_code}
                                                name={r.programme_name}
                                            />
                                            <CellBrief
                                                code={r.fund_code}
                                                name={r.fund_name}
                                            />
                                            <CellBrief
                                                code={r.geographic_code}
                                                name={r.geographic_name}
                                            />
                                            <td style={{
                                                padding: '10px 12px', fontSize: 13,
                                                textAlign: 'right', fontFamily: 'monospace', fontWeight: 600,
                                            }}>
                                                {fmtNGN(r.amount_approved)}
                                            </td>
                                            <td style={{
                                                padding: '10px 12px', fontSize: 13,
                                                textAlign: 'right', fontFamily: 'monospace',
                                                color: '#d97706',
                                            }}>
                                                {fmtNGN(r.total_committed)}
                                            </td>
                                            <td style={{
                                                padding: '10px 12px', fontSize: 13,
                                                textAlign: 'right', fontFamily: 'monospace',
                                                color: '#16a34a',
                                            }}>
                                                {fmtNGN(r.total_expended)}
                                            </td>
                                            <td style={{ padding: '10px 12px' }}>
                                                <span style={{
                                                    padding: '3px 10px', borderRadius: 999,
                                                    fontSize: 11, fontWeight: 700,
                                                    background: `${STATUS_COLORS[r.status] ?? '#64748b'}14`,
                                                    color: STATUS_COLORS[r.status] ?? '#64748b',
                                                    border: `1px solid ${STATUS_COLORS[r.status] ?? '#64748b'}30`,
                                                    textTransform: 'uppercase',
                                                    letterSpacing: '0.5px',
                                                }}>
                                                    {r.status}
                                                </span>
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    )}
                </div>

                {creating && (
                    <CreateDrawer
                        onClose={() => setCreating(false)}
                        onCreated={() => {
                            qc.invalidateQueries({ queryKey: ['appropriations-admin'] });
                            setCreating(false);
                        }}
                    />
                )}
            </main>
        </div>
    );
}

function CellBrief({ code, name }: { code: string | null; name: string | null }) {
    if (!code && !name) return <td style={{ padding: '10px 12px', color: '#94a3b8' }}>—</td>;
    return (
        <td style={{ padding: '10px 12px', fontSize: 13, minWidth: 140 }}>
            <div style={{ fontWeight: 500, color: '#1e293b' }}>{name}</div>
            <div style={{
                fontSize: 10, color: '#94a3b8', fontFamily: 'monospace',
                marginTop: 1,
            }}>
                {code}
            </div>
        </td>
    );
}

interface CreateDrawerProps {
    onClose: () => void;
    onCreated: () => void;
}

function CreateDrawer({ onClose, onCreated }: CreateDrawerProps) {
    const [formErr, setFormErr] = useState<string | null>(null);
    const [fiscalYearId, setFiscalYearId] = useState<string>('');
    const [adminSeg, setAdminSeg] = useState<string>('');
    const [econSeg, setEconSeg] = useState<string>('');
    const [funcSeg, setFuncSeg] = useState<string>('');
    const [progSeg, setProgSeg] = useState<string>('');
    const [fundSeg, setFundSeg] = useState<string>('');
    const [geoSeg, setGeoSeg] = useState<string>('');
    const [amount, setAmount] = useState('');
    const [apType, setApType] = useState('ORIGINAL');
    const [status, setStatus] = useState('ACTIVE');

    const { data: fys } = useQuery<any[]>({
        queryKey: ['fiscal-years-for-create'],
        queryFn: async () => {
            const res = await apiClient.get('/accounting/fiscal-years/', {
                params: { page_size: 100 },
            });
            return Array.isArray(res.data) ? res.data : (res.data?.results ?? []);
        },
    });
    const { data: admins } = useQuery<Segment[]>({
        queryKey: ['admin-segs'],
        queryFn: () => fetchSegments('/accounting/ncoa/administrative/'),
    });
    const { data: econs } = useQuery<Segment[]>({
        queryKey: ['econ-segs'],
        queryFn: () => fetchSegments('/accounting/ncoa/economic/'),
    });
    const { data: funcs } = useQuery<Segment[]>({
        queryKey: ['func-segs'],
        queryFn: () => fetchSegments('/accounting/ncoa/functional/'),
    });
    const { data: progs } = useQuery<Segment[]>({
        queryKey: ['prog-segs'],
        queryFn: () => fetchSegments('/accounting/ncoa/programme/'),
    });
    const { data: funds } = useQuery<Segment[]>({
        queryKey: ['fund-segs'],
        queryFn: () => fetchSegments('/accounting/ncoa/fund/'),
    });
    const { data: geos } = useQuery<Segment[]>({
        queryKey: ['geo-segs'],
        queryFn: () => fetchSegments('/accounting/ncoa/geographic/'),
    });

    const createMutation = useMutation({
        mutationFn: async () => {
            setFormErr(null);
            if (!fiscalYearId || !adminSeg || !econSeg || !funcSeg ||
                !progSeg || !fundSeg || !amount) {
                throw new Error('All segments (except geographic) + amount are required.');
            }
            const body: Record<string, any> = {
                fiscal_year: parseInt(fiscalYearId),
                administrative: parseInt(adminSeg),
                economic: parseInt(econSeg),
                functional: parseInt(funcSeg),
                programme: parseInt(progSeg),
                fund: parseInt(fundSeg),
                amount_approved: amount,
                appropriation_type: apType,
                status,
            };
            if (geoSeg) body.geographic = parseInt(geoSeg);
            return apiClient.post('/budget/appropriations/', body);
        },
        onSuccess: onCreated,
        onError: (err: any) => {
            setFormErr(
                err?.response?.data
                    ? JSON.stringify(err.response.data)
                    : err?.message || 'Create failed',
            );
        },
    });

    const selectStyle: React.CSSProperties = {
        width: '100%', padding: '8px 10px', borderRadius: 6,
        border: '1px solid #e2e8f0', fontSize: 13,
    };

    return (
        <div style={{
            position: 'fixed', inset: 0, background: 'rgba(15, 23, 42, 0.5)',
            display: 'flex', justifyContent: 'flex-end', zIndex: 9998,
        }}>
            <div style={{
                width: 560, maxWidth: '100%', background: '#fff', overflow: 'auto',
                boxShadow: '-4px 0 20px rgba(0,0,0,0.15)', padding: '24px 28px',
            }}>
                <div style={{
                    display: 'flex', justifyContent: 'space-between',
                    alignItems: 'center', marginBottom: 20,
                }}>
                    <h3 style={{
                        margin: 0, fontSize: 18, fontWeight: 800, color: '#1e293b',
                    }}>
                        New Appropriation
                    </h3>
                    <button
                        onClick={onClose}
                        style={{
                            padding: 6, border: 'none', background: 'transparent',
                            cursor: 'pointer', color: '#64748b',
                        }}
                    >
                        <X size={20} />
                    </button>
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                    <LabeledSelect label="Fiscal Year *" value={fiscalYearId} onChange={setFiscalYearId}>
                        <option value="">Select…</option>
                        {(fys ?? []).map(fy => (
                            <option key={fy.id} value={fy.id}>
                                FY {fy.year ?? fy.id} — {fy.name ?? ''}
                            </option>
                        ))}
                    </LabeledSelect>

                    <LabeledSelect label="MDA (administrative) *" value={adminSeg} onChange={setAdminSeg}>
                        <option value="">Select…</option>
                        {(admins ?? []).map(s => (
                            <option key={s.id} value={s.id}>{s.code} — {s.name}</option>
                        ))}
                    </LabeledSelect>

                    <LabeledSelect label="Economic *" value={econSeg} onChange={setEconSeg}>
                        <option value="">Select…</option>
                        {(econs ?? []).map(s => (
                            <option key={s.id} value={s.id}>{s.code} — {s.name}</option>
                        ))}
                    </LabeledSelect>

                    <LabeledSelect label="Functional (COFOG) *" value={funcSeg} onChange={setFuncSeg}>
                        <option value="">Select…</option>
                        {(funcs ?? []).map(s => (
                            <option key={s.id} value={s.id}>{s.code} — {s.name}</option>
                        ))}
                    </LabeledSelect>

                    <LabeledSelect label="Programme *" value={progSeg} onChange={setProgSeg}>
                        <option value="">Select…</option>
                        {(progs ?? []).map(s => (
                            <option key={s.id} value={s.id}>{s.code} — {s.name}</option>
                        ))}
                    </LabeledSelect>

                    <LabeledSelect label="Fund *" value={fundSeg} onChange={setFundSeg}>
                        <option value="">Select…</option>
                        {(funds ?? []).map(s => (
                            <option key={s.id} value={s.id}>{s.code} — {s.name}</option>
                        ))}
                    </LabeledSelect>

                    <LabeledSelect label="Geographic (optional)" value={geoSeg} onChange={setGeoSeg}>
                        <option value="">— none (statewide) —</option>
                        {(geos ?? []).map(s => (
                            <option key={s.id} value={s.id}>{s.code} — {s.name}</option>
                        ))}
                    </LabeledSelect>

                    <div>
                        <label style={{ fontSize: 12, fontWeight: 600, color: '#64748b' }}>
                            Amount Approved (NGN) *
                        </label>
                        <input
                            value={amount}
                            onChange={e => setAmount(e.target.value)}
                            placeholder="e.g. 50000000"
                            style={selectStyle}
                        />
                    </div>

                    <LabeledSelect label="Appropriation Type" value={apType} onChange={setApType}>
                        <option value="ORIGINAL">Original</option>
                        <option value="SUPPLEMENTARY">Supplementary</option>
                        <option value="VIREMENT">Virement</option>
                    </LabeledSelect>

                    <LabeledSelect label="Status" value={status} onChange={setStatus}>
                        <option value="DRAFT">Draft</option>
                        <option value="SUBMITTED">Submitted</option>
                        <option value="APPROVED">Approved</option>
                        <option value="ENACTED">Enacted</option>
                        <option value="ACTIVE">Active</option>
                    </LabeledSelect>

                    {formErr && (
                        <div style={{
                            background: '#fef2f2', border: '1px solid #fca5a5',
                            color: '#991b1b', padding: '10px 14px', borderRadius: 8,
                            fontSize: 12, fontFamily: 'monospace',
                            whiteSpace: 'pre-wrap', wordBreak: 'break-word',
                            maxHeight: 160, overflow: 'auto',
                        }}>
                            <AlertTriangle size={14} style={{ verticalAlign: 'middle', marginRight: 4 }} />
                            {formErr}
                        </div>
                    )}

                    <div style={{ display: 'flex', gap: 10, marginTop: 8 }}>
                        <button
                            onClick={() => createMutation.mutate()}
                            disabled={createMutation.isPending}
                            style={{
                                flex: 1, padding: '10px 16px', borderRadius: 8,
                                border: 'none', background: '#16a34a', color: '#fff',
                                cursor: 'pointer', fontSize: 14, fontWeight: 600,
                            }}
                        >
                            {createMutation.isPending ? 'Creating…' : 'Create Appropriation'}
                        </button>
                        <button
                            onClick={onClose}
                            style={{
                                padding: '10px 16px', borderRadius: 8,
                                border: '1px solid #e2e8f0',
                                background: '#fff', color: '#64748b',
                                cursor: 'pointer', fontSize: 14,
                            }}
                        >
                            Cancel
                        </button>
                    </div>
                </div>
        </ListPageShell>
    );
}

interface LabeledSelectProps {
    label: string;
    value: string;
    onChange: (v: string) => void;
    children: React.ReactNode;
}

function LabeledSelect({ label, value, onChange, children }: LabeledSelectProps) {
    return (
        <div>
            <label style={{
                fontSize: 12, fontWeight: 600, color: '#64748b',
                display: 'block', marginBottom: 4,
            }}>
                {label}
            </label>
            <select
                value={value}
                onChange={e => onChange(e.target.value)}
                style={{
                    width: '100%', padding: '8px 10px', borderRadius: 6,
                    border: '1px solid #e2e8f0', fontSize: 13, background: '#fff',
                }}
            >
                {children}
            </select>
        </div>
    );
}
