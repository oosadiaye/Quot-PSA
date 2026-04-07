import { useState } from 'react';
import { useServiceMetrics, useServiceDashboard, useGenerateMetrics } from '../hooks/useService';
import Sidebar from '../../../components/Sidebar';
import PageHeader from '../../../components/PageHeader';
import { BarChart3, Ticket, CheckCircle, Clock, DollarSign, Users } from 'lucide-react';
import LoadingScreen from '../../../components/common/LoadingScreen';
import type { ServiceMetric as ServiceMetricType } from '../types';
import type { LucideIcon } from 'lucide-react';

const ServiceMetrics = () => {
    const { data: dashboard, isLoading: isDashboardLoading } = useServiceDashboard();
    const { data: metrics, isLoading: isMetricsLoading } = useServiceMetrics();
    const generateMetrics = useGenerateMetrics();
    const [selectedPeriod, setSelectedPeriod] = useState('Monthly');

    if (isDashboardLoading || isMetricsLoading) {
        return <LoadingScreen message="Loading service metrics..." />;
    }

    const handleGenerate = () => {
        generateMetrics.mutate(selectedPeriod);
    };

    const StatCard = ({ title, value, icon: Icon, color }: { title: string; value: string | number; icon: LucideIcon; color: string }) => (
        <div className="card">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div>
                    <div style={{ fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', marginBottom: '0.5rem' }}>{title}</div>
                    <div style={{ fontSize: 'var(--text-xl)', fontWeight: 700, color: 'var(--color-text)' }}>{value}</div>
                </div>
                <div style={{
                    padding: '0.75rem',
                    borderRadius: '0.5rem',
                    background: `${color}20`,
                    color: color
                }}>
                    <Icon size={24} />
                </div>
            </div>
        </div>
    );

    return (
        <div style={{ display: 'flex' }}>
            <Sidebar />
            <main style={{ flex: 1, marginLeft: '260px', padding: '2.5rem' }}>
                <PageHeader
                    title="Service Metrics"
                    subtitle="Track KPIs and service performance."
                    icon={<BarChart3 size={22} color="white" />}
                    actions={
                        <div style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
                            <select
                                className="input"
                                style={{ width: 'auto' }}
                                value={selectedPeriod}
                                onChange={(e) => setSelectedPeriod(e.target.value)}
                            >
                                <option value="Daily">Daily</option>
                                <option value="Weekly">Weekly</option>
                                <option value="Monthly">Monthly</option>
                                <option value="Quarterly">Quarterly</option>
                                <option value="Yearly">Yearly</option>
                            </select>
                            <button
                                className="btn btn-primary"
                                onClick={handleGenerate}
                                disabled={generateMetrics.isPending}
                            >
                                {generateMetrics.isPending ? 'Generating...' : 'Generate Report'}
                            </button>
                        </div>
                    }
                />

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1.25rem', marginBottom: '2.5rem' }}>
                    <StatCard
                        title="TOTAL TICKETS"
                        value={dashboard?.total_tickets || 0}
                        icon={Ticket}
                        color="var(--color-primary)"
                    />
                    <StatCard
                        title="OPEN TICKETS"
                        value={dashboard?.open_tickets || 0}
                        icon={Clock}
                        color="var(--color-warning)"
                    />
                    <StatCard
                        title="RESOLVED TICKETS"
                        value={dashboard?.resolved_tickets || 0}
                        icon={CheckCircle}
                        color="var(--color-success)"
                    />
                    <StatCard
                        title="TECHNICIANS AVAILABLE"
                        value={dashboard?.technicians_available || 0}
                        icon={Users}
                        color="var(--color-cta)"
                    />
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1.25rem', marginBottom: '2.5rem' }}>
                    <StatCard
                        title="WORK ORDERS"
                        value={dashboard?.total_work_orders || 0}
                        icon={BarChart3}
                        color="var(--color-primary)"
                    />
                    <StatCard
                        title="PENDING"
                        value={dashboard?.pending_work_orders || 0}
                        icon={Clock}
                        color="var(--color-warning)"
                    />
                    <StatCard
                        title="COMPLETED"
                        value={dashboard?.completed_work_orders || 0}
                        icon={CheckCircle}
                        color="var(--color-success)"
                    />
                    <StatCard
                        title="CITIZEN REQUESTS"
                        value={dashboard?.total_citizen_requests || 0}
                        icon={Ticket}
                        color="var(--color-cta)"
                    />
                </div>

                <h2 style={{ fontSize: 'var(--text-lg)', marginBottom: '1.5rem', color: 'var(--color-text)' }}>Historical Metrics</h2>
                <div className="card">
                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                        <thead>
                            <tr style={{ borderBottom: '1px solid var(--color-border)' }}>
                                <th style={{ textAlign: 'left', padding: '1rem', fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>NAME</th>
                                <th style={{ textAlign: 'left', padding: '1rem', fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>PERIOD</th>
                                <th style={{ textAlign: 'right', padding: '1rem', fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>TICKETS</th>
                                <th style={{ textAlign: 'right', padding: '1rem', fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>RESOLVED</th>
                                <th style={{ textAlign: 'right', padding: '1rem', fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>WORK ORDERS</th>
                                <th style={{ textAlign: 'right', padding: '1rem', fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>TOTAL COST</th>
                            </tr>
                        </thead>
                        <tbody>
                            {((metrics?.results || metrics || []) as ServiceMetricType[]).map((m: ServiceMetricType) => (
                                <tr key={m.id} style={{ borderBottom: '1px solid var(--color-border)' }}>
                                    <td style={{ padding: '1rem', fontSize: 'var(--text-sm)' }}>{m.name}</td>
                                    <td style={{ padding: '1rem', fontSize: 'var(--text-sm)' }}>{m.period}</td>
                                    <td style={{ padding: '1rem', textAlign: 'right', fontSize: 'var(--text-sm)' }}>{m.total_tickets}</td>
                                    <td style={{ padding: '1rem', textAlign: 'right', fontSize: 'var(--text-sm)' }}>{m.resolved_tickets}</td>
                                    <td style={{ padding: '1rem', textAlign: 'right', fontSize: 'var(--text-sm)' }}>{m.completed_work_orders}</td>
                                    <td style={{ padding: '1rem', textAlign: 'right', fontSize: 'var(--text-sm)' }}>${Number(m.total_cost).toLocaleString()}</td>
                                </tr>
                            ))}
                            {!((metrics?.results || metrics || []) as ServiceMetricType[]).length && (
                                <tr>
                                    <td colSpan={6} style={{ padding: '2rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>
                                        No metrics generated yet. Click "Generate Report" to create metrics.
                                    </td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>
            </main>
        </div>
    );
};

export default ServiceMetrics;
