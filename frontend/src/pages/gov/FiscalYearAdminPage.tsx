/**
 * FiscalYear admin — Quot PSE
 * Route: /admin/fiscal-years
 *
 * Create, review, and close fiscal years. Surfaces the close-action
 * button (calls the backend YearEndCloseService which posts the
 * closing journal + locks the year).
 */
import { useState } from 'react';
import { useQuery, useQueryClient, useMutation } from '@tanstack/react-query';
import {
    Calendar, Lock, Unlock, AlertTriangle, Plus, Loader2,
} from 'lucide-react';
import Sidebar from '../../components/Sidebar';
import apiClient from '../../api/client';

interface FiscalYear {
    id: number;
    year: number;
    name: string;
    start_date: string;
    end_date: string;
    is_active: boolean;
    status: string;           // Open | Closed | Locked
    closed_date: string | null;
    created_at: string;
}

export default function FiscalYearAdminPage() {
    const qc = useQueryClient();
    const [creating, setCreating] = useState(false);
    const [year, setYear] = useState(new Date().getFullYear() + 1);

    const { data, isLoading } = useQuery<FiscalYear[]>({
        queryKey: ['fiscal-years-admin'],
        queryFn: async () => {
            const res = await apiClient.get('/accounting/fiscal-years/', {
                params: { page_size: 100 },
            });
            return Array.isArray(res.data) ? res.data : (res.data?.results ?? []);
        },
    });

    const createMutation = useMutation({
        mutationFn: async (y: number) => {
            return apiClient.post('/accounting/fiscal-years/', {
                year: y,
                name: `FY ${y}`,
                start_date: `${y}-01-01`,
                end_date: `${y}-12-31`,
                status: 'Open',
                is_active: true,
            });
        },
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ['fiscal-years-admin'] });
            setCreating(false);
        },
    });

    const closeMutation = useMutation({
        mutationFn: async ({ id, force }: { id: number; force: boolean }) => {
            return apiClient.post(
                `/accounting/fiscal-years/${id}/close_year/`,
                { force },
            );
        },
        onSuccess: () => qc.invalidateQueries({ queryKey: ['fiscal-years-admin'] }),
    });

    const reopenMutation = useMutation({
        mutationFn: async (id: number) =>
            apiClient.post(`/accounting/fiscal-years/${id}/reopen_year/`),
        onSuccess: () => qc.invalidateQueries({ queryKey: ['fiscal-years-admin'] }),
    });

    const handleClose = (fy: FiscalYear) => {
        const ok = window.confirm(
            `Close FY ${fy.year}?\n\n` +
            `This posts the closing journal that transfers surplus/deficit ` +
            `to Accumulated Fund and locks the fiscal year. The operation ` +
            `is reversible only via an admin "Re-open Year" action.\n\n` +
            `Proceed?`
        );
        if (!ok) return;
        closeMutation.mutate({ id: fy.id, force: false });
    };

    return (
        <div style={{ background: '#f1f5f9', minHeight: '100vh' }}>
            <Sidebar />
            <main style={{ marginLeft: '260px', padding: '32px' }}>
                <div style={{
                    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                    marginBottom: 20,
                }}>
                    <div>
                        <h1 style={{
                            fontSize: 24, fontWeight: 800, color: '#1e293b', margin: 0,
                            display: 'flex', alignItems: 'center', gap: 10,
                        }}>
                            <Calendar size={22} /> Fiscal Years
                        </h1>
                        <p style={{ color: '#64748b', fontSize: 14, margin: '4px 0 0' }}>
                            Create, review, and close fiscal years. Closing posts the
                            year-end journal and locks all child periods.
                        </p>
                    </div>
                    <button
                        onClick={() => setCreating(true)}
                        style={{
                            display: 'flex', alignItems: 'center', gap: 6,
                            padding: '8px 16px', borderRadius: 8,
                            border: 'none', background: '#1e40af', color: '#fff',
                            cursor: 'pointer', fontSize: 14, fontWeight: 600,
                        }}
                    >
                        <Plus size={16} /> New Fiscal Year
                    </button>
                </div>

                {creating && (
                    <div style={{
                        background: '#fff', borderRadius: 12, padding: 20,
                        border: '1px solid #e8ecf1', marginBottom: 20,
                    }}>
                        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
                            <label style={{ fontSize: 13, fontWeight: 600, color: '#1e293b' }}>
                                Year:
                            </label>
                            <input
                                type="number"
                                value={year}
                                onChange={e => setYear(parseInt(e.target.value) || 0)}
                                style={{
                                    padding: '6px 12px', borderRadius: 6,
                                    border: '1px solid #e2e8f0', fontSize: 14, width: 120,
                                }}
                            />
                            <button
                                onClick={() => createMutation.mutate(year)}
                                disabled={createMutation.isPending}
                                style={{
                                    padding: '6px 16px', borderRadius: 6, border: 'none',
                                    background: '#16a34a', color: '#fff', cursor: 'pointer',
                                    fontSize: 13, fontWeight: 600,
                                }}
                            >
                                {createMutation.isPending ? 'Creating…' : 'Create'}
                            </button>
                            <button
                                onClick={() => setCreating(false)}
                                style={{
                                    padding: '6px 16px', borderRadius: 6,
                                    border: '1px solid #e2e8f0',
                                    background: '#fff', color: '#64748b', cursor: 'pointer',
                                    fontSize: 13,
                                }}
                            >
                                Cancel
                            </button>
                        </div>
                        {createMutation.isError && (
                            <div style={{ marginTop: 8, fontSize: 12, color: '#dc2626' }}>
                                Create failed — see browser console.
                            </div>
                        )}
                    </div>
                )}

                <div style={{
                    background: '#fff', borderRadius: 12,
                    border: '1px solid #e8ecf1', overflow: 'hidden',
                }}>
                    {isLoading ? (
                        <div style={{ padding: 40, textAlign: 'center', color: '#94a3b8' }}>
                            Loading…
                        </div>
                    ) : !data || data.length === 0 ? (
                        <div style={{ padding: 40, textAlign: 'center', color: '#94a3b8' }}>
                            No fiscal years yet. Click "New Fiscal Year" to create one.
                        </div>
                    ) : (
                        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                            <thead>
                                <tr style={{ background: '#f8fafc', borderBottom: '2px solid #e8ecf1' }}>
                                    {['Year', 'Name', 'Period', 'Status', 'Active', 'Closed', 'Actions'].map(h => (
                                        <th key={h} style={{
                                            padding: '10px 14px', textAlign: 'left', fontSize: 11,
                                            fontWeight: 700, color: '#64748b',
                                            textTransform: 'uppercase', letterSpacing: '0.5px',
                                        }}>{h}</th>
                                    ))}
                                </tr>
                            </thead>
                            <tbody>
                                {data
                                    .slice()
                                    .sort((a, b) => (b.year ?? 0) - (a.year ?? 0))
                                    .map(fy => (
                                    <tr key={fy.id} style={{ borderBottom: '1px solid #f1f5f9' }}>
                                        <td style={{
                                            padding: '10px 14px', fontSize: 15,
                                            fontWeight: 800, color: '#1e293b',
                                        }}>
                                            {fy.year}
                                        </td>
                                        <td style={{ padding: '10px 14px', fontSize: 13 }}>
                                            {fy.name}
                                        </td>
                                        <td style={{
                                            padding: '10px 14px', fontSize: 12,
                                            color: '#64748b', fontFamily: 'monospace',
                                        }}>
                                            {fy.start_date} → {fy.end_date}
                                        </td>
                                        <td style={{ padding: '10px 14px' }}>
                                            <StatusPill status={fy.status} />
                                        </td>
                                        <td style={{ padding: '10px 14px', fontSize: 12 }}>
                                            {fy.is_active ? '✓' : '—'}
                                        </td>
                                        <td style={{
                                            padding: '10px 14px', fontSize: 12,
                                            color: '#64748b', fontFamily: 'monospace',
                                        }}>
                                            {fy.closed_date
                                                ? new Date(fy.closed_date).toLocaleDateString('en-NG')
                                                : '—'}
                                        </td>
                                        <td style={{ padding: '10px 14px' }}>
                                            {fy.status === 'Open' ? (
                                                <button
                                                    onClick={() => handleClose(fy)}
                                                    disabled={closeMutation.isPending}
                                                    style={{
                                                        display: 'flex', alignItems: 'center', gap: 4,
                                                        padding: '4px 10px', borderRadius: 6,
                                                        border: '1px solid #fca5a5',
                                                        background: '#fef2f2', color: '#991b1b',
                                                        cursor: 'pointer', fontSize: 12, fontWeight: 600,
                                                    }}
                                                >
                                                    {closeMutation.isPending ? (
                                                        <Loader2 size={11} style={{
                                                            animation: 'spin 1s linear infinite',
                                                        }} />
                                                    ) : (
                                                        <Lock size={11} />
                                                    )}
                                                    Close
                                                </button>
                                            ) : fy.status === 'Closed' ? (
                                                <button
                                                    onClick={() => reopenMutation.mutate(fy.id)}
                                                    style={{
                                                        display: 'flex', alignItems: 'center', gap: 4,
                                                        padding: '4px 10px', borderRadius: 6,
                                                        border: '1px solid #fcd34d',
                                                        background: '#fffbeb', color: '#92400e',
                                                        cursor: 'pointer', fontSize: 12, fontWeight: 600,
                                                    }}
                                                >
                                                    <Unlock size={11} /> Re-open
                                                </button>
                                            ) : (
                                                <span style={{
                                                    fontSize: 11, color: '#94a3b8',
                                                    fontStyle: 'italic',
                                                }}>
                                                    Locked
                                                </span>
                                            )}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    )}
                </div>

                {(closeMutation.isError || reopenMutation.isError) && (
                    <div style={{
                        background: '#fef2f2', border: '1px solid #fca5a5',
                        color: '#991b1b', padding: '10px 14px', borderRadius: 8,
                        fontSize: 13, marginTop: 16,
                        display: 'flex', alignItems: 'center', gap: 8,
                    }}>
                        <AlertTriangle size={16} />
                        Action failed — see browser console for the server error.
                    </div>
                )}

                <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>
            </main>
        </div>
    );
}

function StatusPill({ status }: { status: string }) {
    const meta: Record<string, { bg: string; border: string; color: string }> = {
        Open:   { bg: '#f0fdf4', border: '#86efac', color: '#166534' },
        Closed: { bg: '#fffbeb', border: '#fcd34d', color: '#92400e' },
        Locked: { bg: '#f1f5f9', border: '#cbd5e1', color: '#64748b' },
    };
    const m = meta[status] ?? meta.Open;
    return (
        <span style={{
            padding: '3px 10px', borderRadius: 999, fontSize: 11, fontWeight: 700,
            background: m.bg, color: m.color, border: `1px solid ${m.border}`,
            textTransform: 'uppercase', letterSpacing: '0.5px',
        }}>
            {status}
        </span>
    );
}
