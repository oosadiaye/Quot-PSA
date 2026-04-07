import { useState } from 'react';
import { Search, TrendingUp, Star, Clock, Package, AlertTriangle } from 'lucide-react';
import { useVendors, useVendorPerformanceReport } from './hooks/useProcurement';
import AccountingLayout from '../accounting/AccountingLayout';
import LoadingScreen from '../../components/common/LoadingScreen';
import { useCurrency } from '../../context/CurrencyContext';
import '../accounting/styles/glassmorphism.css';

export default function VendorPerformance() {
    const [searchTerm, setSearchTerm] = useState('');
    const { formatCurrency } = useCurrency();
    
    const { data: vendors, isLoading } = useVendors({ is_active: true });
    const { data: perfReport } = useVendorPerformanceReport();

    const vendorsList = vendors?.results || vendors || [];
    
    const filteredVendors = Array.isArray(vendorsList) ? vendorsList.filter((v: any) =>
        v.name?.toLowerCase().includes(searchTerm.toLowerCase()) ||
        v.code?.toLowerCase().includes(searchTerm.toLowerCase())
    ) : [];

    const getRatingColor = (rating: number) => {
        if (rating >= 80) return '#22c55e';
        if (rating >= 60) return '#fbbf24';
        if (rating >= 40) return '#f97316';
        return '#ef4444';
    };

    const getRatingLabel = (rating: number) => {
        if (rating >= 80) return 'Excellent';
        if (rating >= 60) return 'Good';
        if (rating >= 40) return 'Fair';
        return 'Poor';
    };

    if (isLoading) return <LoadingScreen message="Loading vendor performance..." />;

    return (
        <AccountingLayout>
            <div style={{ padding: '1.5rem' }}>
                <div style={{ marginBottom: '1.5rem' }}>
                    <h1 style={{ fontSize: 'var(--text-xl)', fontWeight: 700, color: 'var(--color-text)', margin: 0 }}>
                        Vendor Performance
                    </h1>
                    <p style={{ color: 'var(--color-text-muted)', margin: '0.25rem 0 0 0', fontSize: 'var(--text-sm)' }}>
                        Track and analyze vendor performance metrics
                    </p>
                </div>

                <div style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
                    gap: '1rem',
                    marginBottom: '1.5rem',
                }}>
                    <div style={{
                        background: 'var(--color-surface)',
                        borderRadius: '12px',
                        border: '1px solid var(--color-border)',
                        padding: '1.25rem',
                    }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.5rem' }}>
                            <div style={{ padding: '0.5rem', background: 'rgba(36, 113, 163, 0.1)', borderRadius: '8px' }}>
                                <Package size={20} style={{ color: '#2471a3' }} />
                            </div>
                            <span style={{ color: 'var(--color-text-muted)', fontSize: 'var(--text-sm)' }}>Total Vendors</span>
                        </div>
                        <p style={{ fontSize: 'var(--text-xl)', fontWeight: 700, margin: 0, color: 'var(--color-text)' }}>
                            {vendors?.length || 0}
                        </p>
                    </div>
                    
                    <div style={{
                        background: 'var(--color-surface)',
                        borderRadius: '12px',
                        border: '1px solid var(--color-border)',
                        padding: '1.25rem',
                    }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.5rem' }}>
                            <div style={{ padding: '0.5rem', background: 'rgba(34, 197, 94, 0.1)', borderRadius: '8px' }}>
                                <TrendingUp size={20} style={{ color: '#22c55e' }} />
                            </div>
                            <span style={{ color: 'var(--color-text-muted)', fontSize: 'var(--text-sm)' }}>Avg. On-Time Delivery</span>
                        </div>
                        <p style={{ fontSize: 'var(--text-xl)', fontWeight: 700, margin: 0, color: 'var(--color-text)' }}>
                            {perfReport?.length ?
                                (perfReport.reduce((acc: number, v: any) => acc + (Number(v.on_time_delivery_rate) || 0), 0) / perfReport.length).toFixed(1)
                            : 0}%
                        </p>
                    </div>
                    
                    <div style={{
                        background: 'var(--color-surface)',
                        borderRadius: '12px',
                        border: '1px solid var(--color-border)',
                        padding: '1.25rem',
                    }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.5rem' }}>
                            <div style={{ padding: '0.5rem', background: 'rgba(251, 191, 36, 0.1)', borderRadius: '8px' }}>
                                <Star size={20} style={{ color: '#fbbf24' }} />
                            </div>
                            <span style={{ color: 'var(--color-text-muted)', fontSize: 'var(--text-sm)' }}>Avg. Quality Score</span>
                        </div>
                        <p style={{ fontSize: 'var(--text-xl)', fontWeight: 700, margin: 0, color: 'var(--color-text)' }}>
                            {perfReport?.length ?
                                (perfReport.reduce((acc: number, v: any) => acc + (Number(v.quality_score) || 0), 0) / perfReport.length).toFixed(1)
                            : 0}%
                        </p>
                    </div>
                </div>

                <div style={{ marginBottom: '1.5rem', position: 'relative', maxWidth: '400px' }}>
                    <Search size={18} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: 'var(--color-text-muted)' }} />
                    <input
                        type="text"
                        placeholder="Search vendors..."
                        value={searchTerm}
                        onChange={(e) => setSearchTerm(e.target.value)}
                        style={{
                            width: '100%',
                            padding: '0.625rem 0.75rem 0.625rem 2.5rem',
                            border: '1px solid var(--color-border)',
                            borderRadius: '8px',
                            background: 'var(--color-surface)',
                            color: 'var(--color-text)',
                            fontSize: 'var(--text-sm)',
                        }}
                    />
                </div>

                <div style={{
                    background: 'var(--color-surface)',
                    borderRadius: '12px',
                    border: '1px solid var(--color-border)',
                    overflow: 'hidden',
                }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                        <thead>
                            <tr style={{ borderBottom: '1px solid var(--color-border)' }}>
                                <th style={{ padding: '0.75rem 1rem', textAlign: 'left', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Vendor</th>
                                <th style={{ padding: '0.75rem 1rem', textAlign: 'center', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Orders</th>
                                <th style={{ padding: '0.75rem 1rem', textAlign: 'center', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>On-Time %</th>
                                <th style={{ padding: '0.75rem 1rem', textAlign: 'center', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Quality</th>
                                <th style={{ padding: '0.75rem 1rem', textAlign: 'right', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Total Value</th>
                                <th style={{ padding: '0.75rem 1rem', textAlign: 'center', fontSize: 'var(--text-xs)', fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>Rating</th>
                            </tr>
                        </thead>
                        <tbody>
                            {filteredVendors.length === 0 ? (
                                <tr>
                                    <td colSpan={6} style={{ padding: '3rem', textAlign: 'center', color: 'var(--color-text-muted)' }}>
                                        <TrendingUp size={48} style={{ margin: '0 auto 1rem', opacity: 0.5 }} />
                                        <p>No vendors found</p>
                                    </td>
                                </tr>
                            ) : (
                                filteredVendors.map((vendor: any) => (
                                    <tr key={vendor.id} style={{ borderBottom: '1px solid var(--color-border)' }}>
                                        <td style={{ padding: '0.75rem 1rem' }}>
                                            <div>
                                                <p style={{ fontWeight: 600, margin: 0 }}>{vendor.name}</p>
                                                <p style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', margin: '0.25rem 0 0 0' }}>{vendor.code}</p>
                                            </div>
                                        </td>
                                        <td style={{ padding: '0.75rem 1rem', textAlign: 'center' }}>{vendor.total_orders || 0}</td>
                                        <td style={{ padding: '0.75rem 1rem', textAlign: 'center' }}>
                                            <span style={{
                                                color: Number(vendor.on_time_delivery_rate) >= 80 ? '#22c55e' : Number(vendor.on_time_delivery_rate) >= 50 ? '#fbbf24' : '#ef4444',
                                                fontWeight: 600,
                                            }}>
                                                {(Number(vendor.on_time_delivery_rate) || 0).toFixed(1)}%
                                            </span>
                                        </td>
                                        <td style={{ padding: '0.75rem 1rem', textAlign: 'center' }}>
                                            <span style={{
                                                color: (Number(vendor.quality_score) || 0) >= 80 ? '#22c55e' : (Number(vendor.quality_score) || 0) >= 50 ? '#fbbf24' : '#ef4444',
                                                fontWeight: 600,
                                            }}>
                                                {(Number(vendor.quality_score) || 0).toFixed(1)}%
                                            </span>
                                        </td>
                                        <td style={{ padding: '0.75rem 1rem', textAlign: 'right', fontFamily: 'monospace' }}>
                                            {formatCurrency(parseFloat(vendor.total_purchase_value || 0))}
                                        </td>
                                        <td style={{ padding: '0.75rem 1rem', textAlign: 'center' }}>
                                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.5rem' }}>
                                                <div style={{
                                                    width: '40px',
                                                    height: '40px',
                                                    borderRadius: '50%',
                                                    background: `${getRatingColor(Number(vendor.performance_rating) || 0)}20`,
                                                    display: 'flex',
                                                    alignItems: 'center',
                                                    justifyContent: 'center',
                                                    fontWeight: 700,
                                                    fontSize: 'var(--text-sm)',
                                                    color: getRatingColor(Number(vendor.performance_rating) || 0),
                                                }}>
                                                    {(Number(vendor.performance_rating) || 0).toFixed(0)}
                                                </div>
                                            </div>
                                        </td>
                                    </tr>
                                ))
                            )}
                        </tbody>
                    </table>
                </div>
            </div>
        </AccountingLayout>
    );
}
