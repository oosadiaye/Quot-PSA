/**
 * Approval Rules admin — Quot PSE
 * Route: /admin/approval-rules
 *
 * Shows the active approval matrix: for every document type the
 * engine recognises, which role(s) approve at which amount band,
 * at how many levels. Read-only view for now — admins with the
 * IsAdminUser flag can POST/PATCH through the API; the UI currently
 * surfaces the catalogue so approvers and submitters alike can see
 * the workflow.
 */
import { useQuery } from '@tanstack/react-query';
import {
    CheckCircle2, AlertTriangle, Award, ChevronRight,
    FileText, DollarSign, ArrowRightCircle,
} from 'lucide-react';
import apiClient from '../../api/client';
import { ListPageShell } from '../../components/layout';

interface Level {
    level: number;
    approver_type: string;
    approver_value: string;
    role_name: string | null;
    min_approvers: number;
}

interface Rule {
    id: number;
    min_amount: string;
    max_amount: string | null;
    is_active: boolean;
    levels: Level[];
}

interface Group {
    document_type: string;
    document_type_display: string;
    rules: Rule[];
}

interface SummaryResponse {
    groups: Group[];
    total_rules: number;
    documents_covered: number;
}

const fmtNGN = (v: string | null): string => {
    if (v === null) return 'unlimited';
    const n = parseFloat(v);
    if (!Number.isFinite(n)) return v;
    if (n === 0) return 'NGN 0';
    return 'NGN ' + n.toLocaleString('en-NG', {
        minimumFractionDigits: 0, maximumFractionDigits: 0,
    });
};

const DOCUMENT_META: Record<string, { icon: typeof FileText; color: string; description: string }> = {
    JE:  { icon: FileText, color: '#1e40af', description: 'General-ledger journal postings' },
    VI:  { icon: DollarSign, color: '#9333ea', description: 'Vendor invoice approvals' },
    CI:  { icon: DollarSign, color: '#059669', description: 'Customer invoice approvals' },
    PAY: { icon: ArrowRightCircle, color: '#dc2626', description: 'Outgoing payment authorisations' },
    BGT: { icon: Award, color: '#d97706', description: 'Budget amendment / supplementary appropriation' },
    TRF: { icon: Award, color: '#0891b2', description: 'Budget transfer / virement' },
};

export default function ApprovalRulesPage() {
    const { data, isLoading, error } = useQuery<SummaryResponse>({
        queryKey: ['approval-rules-summary'],
        queryFn: async () =>
            (await apiClient.get('/accounting/approval-rules/summary/')).data,
    });

    return (
        <ListPageShell>
                <div style={{ marginBottom: 24 }}>
                    <h1 style={{
                        fontSize: 24, fontWeight: 800, color: '#1e293b', margin: 0,
                        display: 'flex', alignItems: 'center', gap: 10,
                    }}>
                        <CheckCircle2 size={22} /> Approval Rules
                    </h1>
                    <p style={{ color: '#64748b', fontSize: 14, margin: '4px 0 0' }}>
                        Document workflow matrix — who approves what, at which amount band
                    </p>
                </div>

                {isLoading ? (
                    <div style={{ padding: 40, color: '#94a3b8', textAlign: 'center' }}>
                        Loading approval rules…
                    </div>
                ) : error ? (
                    <div style={{
                        background: '#fef2f2', border: '1px solid #fca5a5',
                        color: '#991b1b', padding: '12px 16px', borderRadius: 8,
                    }}>
                        Failed to load approval rules. Ensure the backend is
                        running and you have an active tenant session.
                    </div>
                ) : !data || data.groups.length === 0 ? (
                    <div style={{
                        background: '#fff', borderRadius: 12,
                        border: '1px solid #e8ecf1', padding: 40, textAlign: 'center',
                    }}>
                        <AlertTriangle size={28} style={{
                            color: '#d97706', marginBottom: 10,
                        }} />
                        <div style={{ fontSize: 15, fontWeight: 700, color: '#1e293b' }}>
                            No approval rules configured
                        </div>
                        <div style={{ fontSize: 13, color: '#64748b', marginTop: 6 }}>
                            Run&nbsp;
                            <code style={{
                                background: '#f1f5f9', padding: '2px 6px', borderRadius: 4,
                            }}>
                                python manage.py tenant_command seed_approval_rules
                            </code>
                            &nbsp;to install the baseline matrix.
                        </div>
                    </div>
                ) : (
                    <>
                        {/* Summary strip */}
                        <div style={{
                            display: 'grid',
                            gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
                            gap: 12, marginBottom: 20,
                        }}>
                            <SummaryCard label="Document types covered" value={data.documents_covered} accent="#1e40af" />
                            <SummaryCard label="Active rules" value={data.total_rules} accent="#059669" />
                            <SummaryCard
                                label="Multi-level rules"
                                value={data.groups.flatMap(g => g.rules).filter(r => r.levels.length > 1).length}
                                accent="#9333ea"
                            />
                        </div>

                        {/* Groups */}
                        {data.groups.map(group => (
                            <GroupCard key={group.document_type} group={group} />
                        ))}
                    </>
                )}

                <div style={{
                    textAlign: 'center', padding: '20px 0',
                    color: '#94a3b8', fontSize: 11,
                }}>
                    Quot PSE IFMIS — Approval Workflow Matrix
                </div>
            </main>
        </div>
    );
}

interface SummaryCardProps {
    label: string;
    value: number;
    accent: string;
}

function SummaryCard({ label, value, accent }: SummaryCardProps) {
    return (
        <div style={{
            background: '#fff', borderRadius: 12,
            border: `1px solid ${accent}33`, padding: 16,
        }}>
            <div style={{
                fontSize: 11, fontWeight: 700, color: accent,
                textTransform: 'uppercase', letterSpacing: '0.5px',
            }}>
                {label}
            </div>
            <div style={{
                fontSize: 24, fontWeight: 800, color: '#1e293b', marginTop: 4,
                fontFamily: 'monospace',
            }}>
                {value}
        </ListPageShell>
    );
}

interface GroupCardProps {
    group: Group;
}

function GroupCard({ group }: GroupCardProps) {
    const meta = DOCUMENT_META[group.document_type] ?? DOCUMENT_META.JE;
    const Icon = meta.icon;

    return (
        <div style={{
            background: '#fff', borderRadius: 12,
            border: '1px solid #e8ecf1', padding: 20, marginBottom: 16,
        }}>
            <div style={{
                display: 'flex', alignItems: 'center', gap: 10,
                marginBottom: 16,
            }}>
                <div style={{
                    padding: 8, borderRadius: 8,
                    background: `${meta.color}14`, color: meta.color,
                }}>
                    <Icon size={18} />
                </div>
                <div>
                    <h2 style={{
                        margin: 0, fontSize: 15, fontWeight: 800, color: '#1e293b',
                    }}>
                        {group.document_type_display}
                        <span style={{
                            marginLeft: 8, fontSize: 11, fontWeight: 600,
                            background: '#f1f5f9', color: '#64748b',
                            padding: '2px 8px', borderRadius: 999,
                            fontFamily: 'monospace',
                        }}>
                            {group.document_type}
                        </span>
                    </h2>
                    <div style={{ fontSize: 12, color: '#64748b', marginTop: 2 }}>
                        {meta.description}
                    </div>
                </div>
            </div>

            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                    <tr style={{ borderBottom: '1px solid #e8ecf1' }}>
                        <th style={{
                            padding: '8px 10px', textAlign: 'left', fontSize: 11,
                            fontWeight: 700, color: '#64748b', textTransform: 'uppercase',
                            letterSpacing: '0.5px',
                        }}>Amount Band</th>
                        <th style={{
                            padding: '8px 10px', textAlign: 'left', fontSize: 11,
                            fontWeight: 700, color: '#64748b', textTransform: 'uppercase',
                            letterSpacing: '0.5px',
                        }}>Approval Chain</th>
                        <th style={{
                            padding: '8px 10px', textAlign: 'right', fontSize: 11,
                            fontWeight: 700, color: '#64748b', textTransform: 'uppercase',
                            letterSpacing: '0.5px',
                        }}>Levels</th>
                    </tr>
                </thead>
                <tbody>
                    {group.rules.map(rule => (
                        <tr key={rule.id} style={{ borderBottom: '1px solid #f1f5f9' }}>
                            <td style={{ padding: '10px', fontSize: 13 }}>
                                <span style={{
                                    fontFamily: 'monospace', fontWeight: 600, color: '#1e293b',
                                }}>
                                    {fmtNGN(rule.min_amount)}
                                </span>
                                {' '}
                                <span style={{ color: '#94a3b8' }}>→</span>
                                {' '}
                                <span style={{
                                    fontFamily: 'monospace', fontWeight: 600, color: '#1e293b',
                                }}>
                                    {rule.max_amount === null ? 'unlimited' : fmtNGN(rule.max_amount)}
                                </span>
                            </td>
                            <td style={{ padding: '10px', fontSize: 13 }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                                    {rule.levels.map((lvl, i) => (
                                        <span key={lvl.level} style={{
                                            display: 'inline-flex', alignItems: 'center', gap: 4,
                                        }}>
                                            {i > 0 && (
                                                <ChevronRight size={14} style={{ color: '#94a3b8' }} />
                                            )}
                                            <span style={{
                                                padding: '4px 10px', borderRadius: 999,
                                                background: '#eff6ff', color: '#1e40af',
                                                fontSize: 12, fontWeight: 600,
                                                border: '1px solid #bfdbfe',
                                            }}>
                                                L{lvl.level}: {lvl.role_name ?? lvl.approver_value}
                                                {lvl.min_approvers > 1 && (
                                                    <span style={{
                                                        marginLeft: 4, fontSize: 10, color: '#64748b',
                                                    }}>
                                                        ×{lvl.min_approvers}
                                                    </span>
                                                )}
                                            </span>
                                        </span>
                                    ))}
                                </div>
                            </td>
                            <td style={{
                                padding: '10px', textAlign: 'right', fontSize: 13,
                                fontWeight: 700, color: '#1e293b',
                            }}>
                                {rule.levels.length}
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}
