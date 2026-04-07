import React, { useState } from 'react';
import { useActiveBudgetPeriod } from '../hooks/useBudgetPeriods';
import { useBudgetAnalytics } from '../hooks/useBudgetAnalytics';
import { useCurrency } from '../../../../context/CurrencyContext';
import PageHeader from '../../../../components/PageHeader';
import LoadingScreen from '../../../../components/common/LoadingScreen';
import {
    DollarSign,
    Lock,
    CheckCircle,
    AlertTriangle,
    AlertCircle,
    BarChart3,
    List,
    Wallet,
} from 'lucide-react';
import '../../styles/glassmorphism.css';

export const BudgetDashboard: React.FC = () => {
    const { activePeriod, isLoading: isPeriodLoading } = useActiveBudgetPeriod();
    const [selectedPeriodId, setSelectedPeriodId] = useState<number | null>(null);
    const [utilizationView, setUtilizationView] = useState<'gauge' | 'list'>('gauge');

    const { formatCurrency: formatCurrencyCtx, currencySymbol } = useCurrency();

    const periodId = selectedPeriodId || activePeriod?.id || null;

    const {
        summary,
        utilization,
        alerts,
        topSpending,
        isLoading,
        refetchAll,
    } = useBudgetAnalytics(periodId);

    const formatCurrency = (value: string | number) => {
        const num = typeof value === 'string' ? parseFloat(value) : value;
        return new Intl.NumberFormat('en-NG', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        }).format(num);
    };

    const getUtilizationColor = (percent: number) => {
        if (percent >= 95) return '#ef4444';
        if (percent >= 80) return '#f59e0b';
        if (percent >= 60) return '#2471a3';
        return '#22c55e';
    };

    const getStatusBadge = (percent: number) => {
        let bg = 'rgba(34, 197, 94, 0.1)';
        let color = '#22c55e';
        if (percent >= 95) { bg = 'rgba(239, 68, 68, 0.1)'; color = '#ef4444'; }
        else if (percent >= 80) { bg = 'rgba(245, 158, 11, 0.1)'; color = '#f59e0b'; }
        else if (percent >= 60) { bg = 'rgba(36, 113, 163, 0.1)'; color = '#2471a3'; }
        return (
            <span style={{
                display: 'inline-block',
                padding: '0.25rem 0.75rem',
                borderRadius: '9999px',
                fontSize: 'var(--text-xs)',
                fontWeight: 500,
                background: bg,
                color,
            }}>
                {percent.toFixed(1)}%
            </span>
        );
    };

    if (isPeriodLoading || isLoading) {
        return <LoadingScreen message="Loading budget dashboard..." />;
    }

    if (!periodId) {
        return (
            <div className="glass-card" style={{ padding: '2rem', textAlign: 'center' }}>
                <AlertTriangle size={48} style={{ margin: '0 auto 1rem', opacity: 0.5, display: 'block', color: '#f59e0b' }} />
                <h3 style={{ color: 'var(--color-text)', marginBottom: '0.5rem' }}>No Active Budget Period</h3>
                <p style={{ color: 'var(--color-text-muted)', margin: 0 }}>
                    Please create and activate a budget period to view the dashboard.
                </p>
            </div>
        );
    }

    const summaryCards = [
        {
            title: 'Total Budget',
            value: formatCurrency(summary?.total_revised || summary?.total_allocated || 0),
            icon: <DollarSign size={20} />,
            color: '#1e40af',
            bg: 'linear-gradient(135deg, rgba(30,64,175,0.12), rgba(59,130,246,0.08))',
        },
        {
            title: 'Committed',
            value: formatCurrency(summary?.total_encumbered || 0),
            icon: <Lock size={20} />,
            color: '#f59e0b',
            bg: 'linear-gradient(135deg, rgba(245,158,11,0.12), rgba(251,191,36,0.08))',
        },
        {
            title: 'Expended',
            value: formatCurrency(summary?.total_expended || 0),
            icon: <CheckCircle size={20} />,
            color: '#2471a3',
            bg: 'linear-gradient(135deg, rgba(59,130,246,0.12), rgba(96,165,250,0.08))',
        },
        {
            title: 'Available',
            value: formatCurrency(summary?.total_available || 0),
            icon: <Wallet size={20} />,
            color: '#22c55e',
            bg: 'linear-gradient(135deg, rgba(34,197,94,0.12), rgba(74,222,128,0.08))',
        },
    ];

    return (
        <div>
            <PageHeader
                title="Budget Monitoring Dashboard"
                subtitle="Real-time budget status and performance analytics"
                icon={<BarChart3 size={22} />}
                backButton={false}
                actions={
                    <select
                        value={periodId || ''}
                        onChange={(e) => setSelectedPeriodId(Number(e.target.value) || null)}
                        style={{
                            padding: '0.75rem 1rem',
                            borderRadius: '8px',
                            border: '1px solid var(--color-border)',
                            background: 'var(--color-surface)',
                            color: 'var(--color-text)',
                            fontSize: 'var(--text-sm)',
                            minWidth: '200px',
                        }}
                    >
                        {activePeriod && (
                            <option value={activePeriod.id}>
                                FY{activePeriod.fiscal_year} - {activePeriod.period_type}
                            </option>
                        )}
                    </select>
                }
            />

            {/* Summary Cards */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '1rem', marginBottom: '1.5rem' }}>
                {summaryCards.map((card, i) => (
                    <div
                        key={card.title}
                        className="glass-card"
                        style={{
                            padding: '1.25rem',
                            animation: `fadeInUp 0.3s ease-out ${i * 0.05}s both`,
                        }}
                    >
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.75rem' }}>
                            <div style={{
                                width: '36px',
                                height: '36px',
                                borderRadius: '8px',
                                background: card.bg,
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                color: card.color,
                            }}>
                                {card.icon}
                            </div>
                            <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', fontWeight: 500 }}>
                                {card.title}
                            </span>
                        </div>
                        <div style={{ fontSize: 'var(--text-xl)', fontWeight: 700, color: card.color }}>
                            {currencySymbol}{card.value}
                        </div>
                    </div>
                ))}
            </div>

            {/* Utilization + Alerts Row */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '1rem', marginBottom: '1.5rem' }}>
                {/* Utilization by Account Type */}
                <div className="glass-card" style={{ padding: '1.5rem' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem' }}>
                        <h3 style={{ fontSize: 'var(--text-base)', fontWeight: 600, color: 'var(--color-text)', margin: 0 }}>
                            Budget Utilization by Account Type
                        </h3>
                        <div style={{ display: 'flex', gap: '2px', background: 'var(--color-surface)', borderRadius: '6px', padding: '2px' }}>
                            <button
                                onClick={() => setUtilizationView('gauge')}
                                style={{
                                    padding: '0.375rem 0.625rem',
                                    borderRadius: '4px',
                                    border: 'none',
                                    background: utilizationView === 'gauge' ? 'var(--color-primary, #1e40af)' : 'transparent',
                                    color: utilizationView === 'gauge' ? 'white' : 'var(--color-text-muted)',
                                    cursor: 'pointer',
                                    display: 'flex',
                                    alignItems: 'center',
                                }}
                            >
                                <BarChart3 size={14} />
                            </button>
                            <button
                                onClick={() => setUtilizationView('list')}
                                style={{
                                    padding: '0.375rem 0.625rem',
                                    borderRadius: '4px',
                                    border: 'none',
                                    background: utilizationView === 'list' ? 'var(--color-primary, #1e40af)' : 'transparent',
                                    color: utilizationView === 'list' ? 'white' : 'var(--color-text-muted)',
                                    cursor: 'pointer',
                                    display: 'flex',
                                    alignItems: 'center',
                                }}
                            >
                                <List size={14} />
                            </button>
                        </div>
                    </div>

                    {utilization && utilization.length > 0 ? (
                        utilizationView === 'gauge' ? (
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                                {utilization.map((item: any, index: number) => {
                                    const barColor = getUtilizationColor(item.utilization_percentage);
                                    const used = parseFloat(item.encumbered) + parseFloat(item.expended);
                                    return (
                                        <div key={item.account_type ?? index}>
                                            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.375rem' }}>
                                                <span style={{ fontSize: 'var(--text-sm)', fontWeight: 500, color: 'var(--color-text)' }}>
                                                    {item.account_type_display || item.account_type}
                                                </span>
                                                <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>
                                                    {item.utilization_percentage.toFixed(1)}%
                                                </span>
                                            </div>
                                            <div style={{
                                                width: '100%',
                                                height: '8px',
                                                borderRadius: '4px',
                                                background: 'var(--color-border, rgba(0,0,0,0.06))',
                                                overflow: 'hidden',
                                            }}>
                                                <div style={{
                                                    width: `${Math.min(item.utilization_percentage, 100)}%`,
                                                    height: '100%',
                                                    borderRadius: '4px',
                                                    background: barColor,
                                                    transition: 'width 0.6s ease',
                                                }} />
                                            </div>
                                            <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '0.25rem' }}>
                                                <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>
                                                    {currencySymbol}{formatCurrency(used)} / {currencySymbol}{formatCurrency(item.allocated)}
                                                </span>
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>
                        ) : (
                            <div style={{ overflowX: 'auto' }}>
                                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                                    <thead>
                                        <tr style={{ borderBottom: '1px solid var(--color-border)' }}>
                                            <th style={{ padding: '0.75rem 1rem', textAlign: 'left', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text)' }}>Account Type</th>
                                            <th style={{ padding: '0.75rem 1rem', textAlign: 'right', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text)' }}>Allocated</th>
                                            <th style={{ padding: '0.75rem 1rem', textAlign: 'right', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text)' }}>Committed</th>
                                            <th style={{ padding: '0.75rem 1rem', textAlign: 'right', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text)' }}>Expended</th>
                                            <th style={{ padding: '0.75rem 1rem', textAlign: 'right', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text)' }}>Available</th>
                                            <th style={{ padding: '0.75rem 1rem', textAlign: 'right', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text)' }}>Utilization</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {utilization.map((item: any, index: number) => (
                                            <tr
                                                key={item.account_type}
                                                style={{
                                                    borderBottom: '1px solid var(--color-border)',
                                                    animation: `fadeInUp 0.3s ease-out ${index * 0.05}s both`,
                                                }}
                                            >
                                                <td style={{ padding: '0.75rem 1rem', color: 'var(--color-text)', fontWeight: 500, fontSize: 'var(--text-sm)' }}>
                                                    {item.account_type_display || item.account_type}
                                                </td>
                                                <td style={{ padding: '0.75rem 1rem', textAlign: 'right', color: 'var(--color-text)', fontSize: 'var(--text-sm)' }}>
                                                    {currencySymbol}{formatCurrency(item.allocated)}
                                                </td>
                                                <td style={{ padding: '0.75rem 1rem', textAlign: 'right', color: 'var(--color-text)', fontSize: 'var(--text-sm)' }}>
                                                    {currencySymbol}{formatCurrency(item.encumbered)}
                                                </td>
                                                <td style={{ padding: '0.75rem 1rem', textAlign: 'right', color: 'var(--color-text)', fontSize: 'var(--text-sm)' }}>
                                                    {currencySymbol}{formatCurrency(item.expended)}
                                                </td>
                                                <td style={{ padding: '0.75rem 1rem', textAlign: 'right', fontWeight: 600, color: '#22c55e', fontSize: 'var(--text-sm)' }}>
                                                    {currencySymbol}{formatCurrency(item.available)}
                                                </td>
                                                <td style={{ padding: '0.75rem 1rem', textAlign: 'right' }}>
                                                    {getStatusBadge(item.utilization_percentage)}
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        )
                    ) : (
                        <p style={{ color: 'var(--color-text-muted)', textAlign: 'center', padding: '2rem 0' }}>
                            No utilization data available
                        </p>
                    )}
                </div>

                {/* Alerts & Warnings */}
                <div className="glass-card" style={{ padding: '1.5rem' }}>
                    <h3 style={{ fontSize: 'var(--text-base)', fontWeight: 600, color: 'var(--color-text)', margin: '0 0 1rem 0' }}>
                        Alerts & Warnings
                    </h3>
                    {alerts && alerts.length > 0 ? (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                            {alerts.slice(0, 5).map((alert: any) => (
                                <div
                                    key={alert.id}
                                    style={{
                                        padding: '0.75rem',
                                        borderRadius: '8px',
                                        background: alert.alert_type === 'CRITICAL' ? 'rgba(239,68,68,0.08)' : 'rgba(245,158,11,0.08)',
                                        border: `1px solid ${alert.alert_type === 'CRITICAL' ? 'rgba(239,68,68,0.2)' : 'rgba(245,158,11,0.2)'}`,
                                        display: 'flex',
                                        alignItems: 'flex-start',
                                        gap: '0.5rem',
                                    }}
                                >
                                    {alert.alert_type === 'CRITICAL' ? (
                                        <AlertCircle size={16} style={{ color: '#ef4444', marginTop: '2px', flexShrink: 0 }} />
                                    ) : (
                                        <AlertTriangle size={16} style={{ color: '#f59e0b', marginTop: '2px', flexShrink: 0 }} />
                                    )}
                                    <span style={{
                                        fontSize: 'var(--text-xs)',
                                        color: alert.alert_type === 'CRITICAL' ? '#ef4444' : '#f59e0b',
                                        lineHeight: 1.4,
                                    }}>
                                        {alert.message}
                                    </span>
                                </div>
                            ))}
                            {alerts.length > 5 && (
                                <span style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', textAlign: 'center' }}>
                                    +{alerts.length - 5} more alerts
                                </span>
                            )}
                        </div>
                    ) : (
                        <div style={{
                            padding: '1rem',
                            borderRadius: '8px',
                            background: 'rgba(34,197,94,0.08)',
                            border: '1px solid rgba(34,197,94,0.2)',
                            display: 'flex',
                            alignItems: 'center',
                            gap: '0.5rem',
                        }}>
                            <CheckCircle size={16} style={{ color: '#22c55e' }} />
                            <span style={{ fontSize: 'var(--text-sm)', color: '#22c55e' }}>
                                All budgets within normal range
                            </span>
                        </div>
                    )}
                </div>
            </div>

            {/* Top Spending Accounts */}
            <div className="glass-card" style={{ overflow: 'hidden' }}>
                <div style={{ padding: '1.25rem 1.5rem', borderBottom: '1px solid var(--color-border)' }}>
                    <h3 style={{ fontSize: 'var(--text-base)', fontWeight: 600, color: 'var(--color-text)', margin: 0 }}>
                        Top Spending Accounts
                    </h3>
                </div>
                <div style={{ overflowX: 'auto' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                        <thead>
                            <tr style={{ borderBottom: '1px solid var(--color-border)' }}>
                                <th style={{ padding: '0.875rem 1.5rem', textAlign: 'left', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text)' }}>Account</th>
                                <th style={{ padding: '0.875rem 1.5rem', textAlign: 'right', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text)' }}>Allocated</th>
                                <th style={{ padding: '0.875rem 1.5rem', textAlign: 'right', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text)' }}>Used</th>
                                <th style={{ padding: '0.875rem 1.5rem', textAlign: 'right', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text)' }}>Utilization</th>
                            </tr>
                        </thead>
                        <tbody>
                            {topSpending && topSpending.length > 0 ? (
                                topSpending.map((item: any, index: number) => (
                                    <tr
                                        key={item.id}
                                        style={{
                                            borderBottom: '1px solid var(--color-border)',
                                            animation: `fadeInUp 0.3s ease-out ${index * 0.05}s both`,
                                        }}
                                    >
                                        <td style={{ padding: '0.875rem 1.5rem' }}>
                                            <div style={{ fontWeight: 500, color: 'var(--color-text)', fontSize: 'var(--text-sm)' }}>
                                                {item.account_code}
                                            </div>
                                            <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>
                                                {item.account_name}
                                            </div>
                                        </td>
                                        <td style={{ padding: '0.875rem 1.5rem', textAlign: 'right', color: 'var(--color-text)', fontSize: 'var(--text-sm)' }}>
                                            {currencySymbol}{formatCurrency(item.allocated)}
                                        </td>
                                        <td style={{ padding: '0.875rem 1.5rem', textAlign: 'right', color: 'var(--color-text)', fontSize: 'var(--text-sm)' }}>
                                            {currencySymbol}{formatCurrency(item.used)}
                                        </td>
                                        <td style={{ padding: '0.875rem 1.5rem', textAlign: 'right' }}>
                                            {getStatusBadge(item.utilization_percentage)}
                                        </td>
                                    </tr>
                                ))
                            ) : (
                                <tr>
                                    <td colSpan={4} style={{ padding: '3rem 1.5rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>
                                        No spending data available
                                    </td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    );
};

export default BudgetDashboard;
