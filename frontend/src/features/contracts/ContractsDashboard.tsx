import { FileText, AlertTriangle, Scale, TrendingUp, ArrowRight } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import PageHeader from '../../components/PageHeader';
import LoadingScreen from '../../components/common/LoadingScreen';
import { ListPageShell, SectionCard } from '../../components/layout';
import { useCurrency } from '../../context/CurrencyContext';
import { useContracts } from './hooks/useContracts';
import { useIPCs } from './hooks/useIPCs';
import { useVariations } from './hooks/useVariations';
import { useIsMobile } from '../../design';

const ACTIVE_STATUSES = ['ACTIVE', 'IN_PROGRESS'];

interface MetricCard {
    name: string;
    value: number;
    suffix?: string;
    formatter?: (v: number) => string;
    icon: LucideIcon;
    accent: string;
    desc: string;
}

const ContractsDashboard = () => {
    const navigate = useNavigate();
    const { formatCurrency } = useCurrency();
    const isMobile = useIsMobile();

    const { data: contracts, isLoading: loadingContracts } = useContracts({ page_size: 500 });
    const { data: ipcs, isLoading: loadingIPCs } = useIPCs({
        status__in: 'SUBMITTED,CERTIFIER_REVIEWED,APPROVED,VOUCHER_RAISED',
        page_size: 500,
    });
    const { data: variations, isLoading: loadingVars } = useVariations({
        status__in: 'SUBMITTED,REVIEWED',
        page_size: 500,
    });

    if (loadingContracts || loadingIPCs || loadingVars) {
        return <LoadingScreen message="Loading contract metrics..." />;
    }

    const rows = contracts?.results ?? [];
    const active = rows.filter((c) => ACTIVE_STATUSES.includes(c.status));
    const totalCeiling = active.reduce((s, c) => s + Number(c.contract_ceiling || 0), 0);
    const totalCertified = active.reduce(
        (s, c) => s + Number(c.cumulative_gross_certified || 0),
        0,
    );
    const utilizationPct = totalCeiling > 0 ? (totalCertified / totalCeiling) * 100 : 0;

    const metrics: MetricCard[] = [
        {
            name: 'Active Contracts',
            value: active.length,
            icon: FileText,
            accent: '#2563eb',
            desc: 'Currently executing',
        },
        {
            name: 'Pending IPCs',
            value: ipcs?.count ?? 0,
            icon: AlertTriangle,
            accent: '#f59e0b',
            desc: 'Awaiting workflow action',
        },
        {
            name: 'Ceiling Utilization',
            value: utilizationPct,
            suffix: '%',
            formatter: (v) => v.toFixed(1),
            icon: Scale,
            accent: utilizationPct > 85 ? '#dc2626' : '#16a34a',
            desc: 'Certified ÷ ceiling across active contracts',
        },
        {
            name: 'Total Ceiling',
            value: totalCeiling,
            formatter: (v) => formatCurrency(v),
            icon: TrendingUp,
            accent: '#7c3aed',
            desc: 'Sum of active contract ceilings',
        },
    ];

    const sections = [
        {
            title: 'Contract Management',
            description: 'Register awards and maintain the contract register.',
            links: [
                { name: 'All Contracts', path: '/contracts', icon: FileText, desc: 'Browse the contract register' },
                { name: 'New Contract', path: '/contracts/new', icon: FileText, desc: 'Register a new award' },
            ],
        },
        {
            title: 'Payments & Variations',
            description: 'Certify milestone payments and approve change orders.',
            links: [
                { name: 'Interim Payment Certificates', path: '/contracts/ipcs', icon: Scale, desc: 'IPC workflow queue' },
                { name: 'Variations', path: '/contracts/variations', icon: TrendingUp, desc: 'Change orders by tier' },
            ],
        },
    ];

    return (
        <ListPageShell>
            <PageHeader
                title="Contracts & Milestone Payments"
                subtitle="Ceiling-safe IPC workflow with tiered variation approval"
                icon={<FileText size={22} style={{ color: 'rgba(255,255,255,0.85)' }} />}
                backButton={false}
            />

            <div
                style={{
                    display: 'grid',
                    gridTemplateColumns: isMobile
                        ? '1fr'
                        : 'repeat(auto-fit, minmax(240px, 1fr))',
                    gap: 14,
                    marginBottom: 20,
                }}
            >
                {metrics.map((m) => {
                    const Icon = m.icon;
                    const display = m.formatter
                        ? m.formatter(m.value)
                        : `${m.value}${m.suffix ?? ''}`;
                    return (
                        <div
                            key={m.name}
                            style={{
                                background: '#ffffff',
                                border: '1px solid rgba(26,35,126,0.08)',
                                borderRadius: 14,
                                padding: 18,
                                boxShadow: '0 1px 3px rgba(15,23,42,0.04)',
                                position: 'relative',
                                overflow: 'hidden',
                            }}
                        >
                            <div
                                style={{
                                    position: 'absolute',
                                    top: 0,
                                    left: 0,
                                    right: 0,
                                    height: 3,
                                    background: m.accent,
                                }}
                            />
                            <div
                                style={{
                                    display: 'flex',
                                    alignItems: 'center',
                                    gap: 10,
                                    marginBottom: 10,
                                }}
                            >
                                <div
                                    style={{
                                        width: 36,
                                        height: 36,
                                        borderRadius: 10,
                                        background: `${m.accent}1a`,
                                        display: 'flex',
                                        alignItems: 'center',
                                        justifyContent: 'center',
                                    }}
                                >
                                    <Icon size={18} style={{ color: m.accent }} />
                                </div>
                                <span
                                    style={{
                                        color: '#64748b',
                                        fontSize: 12,
                                        fontWeight: 700,
                                        textTransform: 'uppercase',
                                        letterSpacing: '0.5px',
                                    }}
                                >
                                    {m.name}
                                </span>
                            </div>
                            <div
                                style={{
                                    fontSize: 26,
                                    fontWeight: 800,
                                    color: '#0b1320',
                                    fontVariantNumeric: 'tabular-nums',
                                    lineHeight: 1.15,
                                }}
                            >
                                {display}
                                {m.formatter ? '' : m.suffix ?? ''}
                            </div>
                            <div style={{ fontSize: 12.5, color: '#94a3b8', marginTop: 4 }}>
                                {m.desc}
                            </div>
                        </div>
                    );
                })}
            </div>

            {sections.map((s) => (
                <SectionCard key={s.title} title={s.title} subtitle={s.description}>
                    <div
                        style={{
                            display: 'grid',
                            gridTemplateColumns: isMobile
                                ? '1fr'
                                : 'repeat(auto-fit, minmax(260px, 1fr))',
                            gap: 12,
                        }}
                    >
                        {s.links.map((l) => {
                            const Icon = l.icon;
                            return (
                                <button
                                    key={l.path}
                                    type="button"
                                    onClick={() => navigate(l.path)}
                                    style={{
                                        display: 'flex',
                                        alignItems: 'center',
                                        gap: 12,
                                        padding: 14,
                                        borderRadius: 12,
                                        border: '1px solid #e2e8f0',
                                        background: '#f8fafc',
                                        textAlign: 'left',
                                        cursor: 'pointer',
                                        fontFamily: 'inherit',
                                        transition:
                                            'transform 120ms ease, box-shadow 120ms ease, background 120ms ease, border-color 120ms ease',
                                    }}
                                    onMouseEnter={(e) => {
                                        e.currentTarget.style.background = '#ffffff';
                                        e.currentTarget.style.borderColor = '#242a88';
                                        e.currentTarget.style.boxShadow =
                                            '0 6px 18px rgba(36,42,136,0.08)';
                                        e.currentTarget.style.transform = 'translateY(-1px)';
                                    }}
                                    onMouseLeave={(e) => {
                                        e.currentTarget.style.background = '#f8fafc';
                                        e.currentTarget.style.borderColor = '#e2e8f0';
                                        e.currentTarget.style.boxShadow = 'none';
                                        e.currentTarget.style.transform = 'translateY(0)';
                                    }}
                                >
                                    <div
                                        style={{
                                            width: 40,
                                            height: 40,
                                            borderRadius: 10,
                                            background:
                                                'linear-gradient(135deg, #242a88, #2e35a0)',
                                            display: 'flex',
                                            alignItems: 'center',
                                            justifyContent: 'center',
                                            flexShrink: 0,
                                        }}
                                    >
                                        <Icon size={18} style={{ color: '#ffffff' }} />
                                    </div>
                                    <div style={{ flex: 1, minWidth: 0 }}>
                                        <div
                                            style={{
                                                fontWeight: 600,
                                                color: '#0b1320',
                                                fontSize: 14,
                                            }}
                                        >
                                            {l.name}
                                        </div>
                                        <div
                                            style={{
                                                fontSize: 12.5,
                                                color: '#64748b',
                                                marginTop: 2,
                                            }}
                                        >
                                            {l.desc}
                                        </div>
                                    </div>
                                    <ArrowRight size={16} style={{ color: '#94a3b8' }} />
                                </button>
                            );
                        })}
                    </div>
                </SectionCard>
            ))}
        </ListPageShell>
    );
};

export default ContractsDashboard;
