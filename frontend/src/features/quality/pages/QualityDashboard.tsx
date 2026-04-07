import { useState } from 'react';
import { Search, AlertTriangle, CheckCircle, XCircle, Gauge, BadgeCheck, Shield } from 'lucide-react';
import PageHeader from '../../../components/PageHeader';
import { useQualityInspections, useNonConformances, useCustomerComplaints, useDueOverdueCalibrations, useSupplierQuality } from '../hooks/useQuality';
import QualityLayout from '../QualityLayout';
import LoadingScreen from '../../../components/common/LoadingScreen';

export default function QualityDashboard() {
    const { data: inspections, isLoading: loadingInspections } = useQualityInspections({});
    const { data: ncrs, isLoading: loadingNCRs } = useNonConformances({});
    const { data: complaints, isLoading: loadingComplaints } = useCustomerComplaints({});
    const { data: dueCalibrations } = useDueOverdueCalibrations();
    const { data: supplierQual } = useSupplierQuality({});

    const inspectionsList = inspections?.results || inspections || [];
    const ncrsList = ncrs?.results || ncrs || [];
    const complaintsList = complaints?.results || complaints || [];
    const calibrationsList = dueCalibrations?.results || dueCalibrations || [];
    const supplierList = supplierQual?.results || supplierQual || [];

    const pendingInspections = inspectionsList.filter((i: any) => i.status === 'Pending').length;
    const passedInspections = inspectionsList.filter((i: any) => i.status === 'Passed').length;
    const failedInspections = inspectionsList.filter((i: any) => i.status === 'Failed').length;
    const openNCRs = ncrsList.filter((n: any) => n.status === 'Open').length;
    const openComplaints = complaintsList.filter((c: any) => c.status === 'Received').length;
    const overdueCalibrations = calibrationsList.filter((c: any) => c.status === 'Overdue').length;

    if (loadingInspections || loadingNCRs || loadingComplaints) {
        return <LoadingScreen message="Loading quality data..." />;
    }

    const stats = [
        { label: 'Pending Inspections', value: pendingInspections, color: '#fbbf24', icon: Search },
        { label: 'Passed', value: passedInspections, color: '#22c55e', icon: CheckCircle },
        { label: 'Failed', value: failedInspections, color: '#ef4444', icon: XCircle },
        { label: 'Open NCRs', value: openNCRs, color: '#f97316', icon: AlertTriangle },
        { label: 'Open Complaints', value: openComplaints, color: '#8b5cf6', icon: AlertTriangle },
        { label: 'Overdue Calibrations', value: overdueCalibrations, color: '#ef4444', icon: Gauge },
    ];

    const avgSupplierScore = supplierList.length > 0 
        ? (supplierList.reduce((acc: number, s: any) => acc + parseFloat(s.overall_score || 0), 0) / supplierList.length).toFixed(1)
        : 0;

    return (
        <QualityLayout>
            <div style={{ padding: '1.5rem' }}>
                <PageHeader
                    title="Quality Dashboard"
                    subtitle="Overview of quality metrics and compliance"
                    icon={<Shield size={22} color="white" />}
                    backButton={false}
                />

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '1rem', marginBottom: '2rem' }}>
                    {stats.map((stat) => (
                        <div key={stat.label} style={{
                            background: 'var(--color-surface)',
                            borderRadius: '12px',
                            border: '1px solid var(--color-border)',
                            padding: '1.25rem',
                        }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.5rem' }}>
                                <div style={{ padding: '0.5rem', background: `${stat.color}15`, borderRadius: '8px' }}>
                                    <stat.icon size={20} style={{ color: stat.color }} />
                                </div>
                                <span style={{ color: 'var(--color-text-muted)', fontSize: 'var(--text-sm)' }}>{stat.label}</span>
                            </div>
                            <p style={{ fontSize: 'var(--text-xl)', fontWeight: 700, margin: 0, color: 'var(--color-text)' }}>
                                {stat.value}
                            </p>
                        </div>
                    ))}
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '1rem' }}>
                    <div style={{
                        background: 'var(--color-surface)',
                        borderRadius: '12px',
                        border: '1px solid var(--color-border)',
                        padding: '1.25rem',
                    }}>
                        <h3 style={{ fontSize: 'var(--text-base)', fontWeight: 600, margin: '0 0 1rem 0', color: 'var(--color-text)' }}>
                            Inspection Summary
                        </h3>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                            {['Pending', 'In Progress', 'Passed', 'Failed'].map((status) => {
                                const count = inspectionsList.filter((i: any) => i.status === status).length;
                                const total = inspectionsList.length || 1;
                                const pct = ((count / total) * 100).toFixed(0);
                                return (
                                    <div key={status} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                        <span style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)' }}>{status}</span>
                                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                            <div style={{ width: '100px', height: '6px', background: 'var(--color-border)', borderRadius: '3px', overflow: 'hidden' }}>
                                                <div style={{ width: `${pct}%`, height: '100%', background: status === 'Passed' ? '#22c55e' : status === 'Failed' ? '#ef4444' : '#fbbf24', borderRadius: '3px' }} />
                                            </div>
                                            <span style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)', minWidth: '30px', textAlign: 'right' }}>{count}</span>
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                    </div>

                    <div style={{
                        background: 'var(--color-surface)',
                        borderRadius: '12px',
                        border: '1px solid var(--color-border)',
                        padding: '1.25rem',
                    }}>
                        <h3 style={{ fontSize: 'var(--text-base)', fontWeight: 600, margin: '0 0 1rem 0', color: 'var(--color-text)' }}>
                            NCR Summary
                        </h3>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                            {['Open', 'Under Investigation', 'Corrective Action', 'Closed'].map((status) => {
                                const count = ncrsList.filter((n: any) => n.status === status).length;
                                return (
                                    <div key={status} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                        <span style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)' }}>{status}</span>
                                        <span style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)' }}>{count}</span>
                                    </div>
                                );
                            })}
                        </div>
                    </div>

                    <div style={{
                        background: 'var(--color-surface)',
                        borderRadius: '12px',
                        border: '1px solid var(--color-border)',
                        padding: '1.25rem',
                    }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1rem' }}>
                            <BadgeCheck size={20} style={{ color: '#22c55e' }} />
                            <h3 style={{ fontSize: 'var(--text-base)', fontWeight: 600, margin: 0, color: 'var(--color-text)' }}>
                                Supplier Quality
                            </h3>
                        </div>
                        <div style={{ textAlign: 'center', padding: '1rem 0' }}>
                            <p style={{ fontSize: 'var(--text-2xl)', fontWeight: 700, margin: 0, color: Number(avgSupplierScore) >= 70 ? '#22c55e' : Number(avgSupplierScore) >= 50 ? '#fbbf24' : '#ef4444' }}>
                                {avgSupplierScore}%
                            </p>
                            <p style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)', margin: '0.25rem 0 0' }}>
                                Average Quality Score
                            </p>
                        </div>
                        <div style={{ marginTop: '1rem', paddingTop: '1rem', borderTop: '1px solid var(--color-border)' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                <span style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)' }}>Suppliers Evaluated</span>
                                <span style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--color-text)' }}>{supplierList.length}</span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </QualityLayout>
    );
}
