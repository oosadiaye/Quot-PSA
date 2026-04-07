import { useState } from 'react';
import { Coins, TrendingUp, DollarSign, Plus } from 'lucide-react';
import { useCurrencies, useCreateCurrency } from '../hooks/useAccountingEnhancements';
import GlassCard from '../components/shared/GlassCard';
import AnimatedButton from '../components/shared/AnimatedButton';
import Modal from '../components/shared/Modal';
import PageHeader from '../../../components/PageHeader';
import LoadingScreen from '../../../components/common/LoadingScreen';
import logger from '../../../utils/logger';
import '../styles/glassmorphism.css';

export default function CurrencySettings() {
    const { data: currencies, isLoading } = useCurrencies();
    const createCurrency = useCreateCurrency();

    const [showForm, setShowForm] = useState(false);
    const [formData, setFormData] = useState({
        code: '',
        name: '',
        symbol: '',
        exchange_rate: '1.0',
        is_active: true,
    });

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        try {
            await createCurrency.mutateAsync(formData);
            setShowForm(false);
            setFormData({ code: '', name: '', symbol: '', exchange_rate: '1.0', is_active: true });
        } catch (error) {
            logger.error('Failed to create currency:', error);
        }
    };

    const baseCurrency = currencies?.find((c: any) => c.is_base_currency);
    const activeCurrencies = currencies?.filter((c: any) => c.is_active) || [];

    if (isLoading) {
        return <LoadingScreen message="Loading currencies..." />;
    }

    return (
        <div style={{ padding: '32px', maxWidth: '1400px', margin: '0 auto' }}>
            <PageHeader
                title="Currency Management"
                subtitle="Manage exchange rates and multi-currency support"
                icon={<Coins size={22} />}
                backButton={false}
                actions={
                    <AnimatedButton onClick={() => setShowForm(true)} variant="primary">
                        <span style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <Plus size={18} />
                            Add Currency
                        </span>
                    </AnimatedButton>
                }
            />

            {/* Stats Cards */}
            <div className="animate-slide-in" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '20px', marginBottom: '32px' }}>
                <GlassCard hover className="metric-card">
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                        <div>
                            <div className="metric-label">Total Currencies</div>
                            <div className="metric-value">{currencies?.length || 0}</div>
                        </div>
                        <div style={{ padding: '12px', borderRadius: '12px', background: 'rgba(36, 113, 163, 0.1)', color: '#2471a3' }}>
                            <Coins size={24} />
                        </div>
                    </div>
                </GlassCard>

                <GlassCard hover className="metric-card">
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                        <div>
                            <div className="metric-label">Active Currencies</div>
                            <div className="metric-value">{activeCurrencies.length}</div>
                        </div>
                        <div style={{ padding: '12px', borderRadius: '12px', background: 'rgba(16, 185, 129, 0.1)', color: '#10b981' }}>
                            <TrendingUp size={24} />
                        </div>
                    </div>
                </GlassCard>

                <GlassCard hover className="metric-card">
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                        <div>
                            <div className="metric-label">Base Currency</div>
                            <div className="metric-value">{baseCurrency?.code || 'N/A'}</div>
                        </div>
                        <div style={{ padding: '12px', borderRadius: '12px', background: 'rgba(245, 158, 11, 0.1)', color: '#f59e0b' }}>
                            <DollarSign size={24} />
                        </div>
                    </div>
                </GlassCard>
            </div>

            {/* Currency Grid */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '20px' }}>
                {currencies?.map((currency: any, index: number) => (
                    <GlassCard
                        key={currency.id}
                        hover
                        gradient={currency.is_base_currency}
                        className={`stagger-item animate-scale-in`}
                        style={{ animationDelay: `${index * 0.05}s` }}
                    >
                        <div style={{ padding: '24px' }}>
                            {/* Currency Header */}
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '16px' }}>
                                <div>
                                    <div style={{ fontSize: 'var(--text-2xl)', fontWeight: 700, color: 'var(--text-primary)', marginBottom: '4px' }}>
                                        {currency.code}
                                    </div>
                                    <div style={{ fontSize: 'var(--text-base)', color: 'var(--text-secondary)' }}>
                                        {currency.name}
                                    </div>
                                </div>
                                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', alignItems: 'flex-end' }}>
                                    {currency.is_base_currency && (
                                        <span className="badge-glass badge-paid" style={{ fontSize: 'var(--text-xs)' }}>
                                            BASE
                                        </span>
                                    )}
                                    {!currency.is_active && (
                                        <span className="badge-glass badge-void" style={{ fontSize: 'var(--text-xs)' }}>
                                            INACTIVE
                                        </span>
                                    )}
                                </div>
                            </div>

                            {/* Currency Details */}
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', paddingTop: '16px', borderTop: '1px solid var(--border)' }}>
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                    <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)', fontWeight: 500 }}>
                                        Symbol
                                    </span>
                                    <span style={{ fontSize: 'var(--text-lg)', fontWeight: 600, color: 'var(--text-primary)' }}>
                                        {currency.symbol}
                                    </span>
                                </div>
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                    <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)', fontWeight: 500 }}>
                                        Exchange Rate
                                    </span>
                                    <span style={{ fontSize: 'var(--text-base)', fontWeight: 600, color: 'var(--accent)' }}>
                                        {parseFloat(currency.exchange_rate).toFixed(6)}
                                    </span>
                                </div>
                            </div>
                        </div>
                    </GlassCard>
                ))}
            </div>

            {currencies?.length === 0 && (
                <div className="animate-fade-in" style={{ textAlign: 'center', padding: '80px 20px', color: 'var(--text-secondary)' }}>
                    <Coins size={64} style={{ margin: '0 auto 16px', opacity: 0.3 }} />
                    <p style={{ fontSize: 'var(--text-lg)', fontWeight: 500 }}>No currencies configured</p>
                    <p style={{ fontSize: 'var(--text-sm)', marginTop: '8px' }}>Add your first currency to get started</p>
                </div>
            )}

            {/* Add Currency Modal */}
            <Modal isOpen={showForm} onClose={() => setShowForm(false)} title="Add New Currency" size="md">
                <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                        <div>
                            <label style={{ display: 'block', fontSize: 'var(--text-sm)', fontWeight: 500, color: 'var(--text-secondary)', marginBottom: '8px' }}>
                                Currency Code *
                            </label>
                            <input
                                type="text"
                                maxLength={3}
                                value={formData.code}
                                onChange={(e) => setFormData({ ...formData, code: e.target.value.toUpperCase() })}
                                placeholder="USD"
                                required
                                className="glass-input"
                                style={{ width: '100%' }}
                            />
                        </div>
                        <div>
                            <label style={{ display: 'block', fontSize: 'var(--text-sm)', fontWeight: 500, color: 'var(--text-secondary)', marginBottom: '8px' }}>
                                Symbol *
                            </label>
                            <input
                                type="text"
                                maxLength={5}
                                value={formData.symbol}
                                onChange={(e) => setFormData({ ...formData, symbol: e.target.value })}
                                placeholder="$"
                                required
                                className="glass-input"
                                style={{ width: '100%' }}
                            />
                        </div>
                    </div>

                    <div>
                        <label style={{ display: 'block', fontSize: 'var(--text-sm)', fontWeight: 500, color: 'var(--text-secondary)', marginBottom: '8px' }}>
                            Currency Name *
                        </label>
                        <input
                            type="text"
                            value={formData.name}
                            onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                            placeholder="US Dollar"
                            required
                            className="glass-input"
                            style={{ width: '100%' }}
                        />
                    </div>

                    <div>
                        <label style={{ display: 'block', fontSize: 'var(--text-sm)', fontWeight: 500, color: 'var(--text-secondary)', marginBottom: '8px' }}>
                            Exchange Rate to Base Currency *
                        </label>
                        <input
                            type="number"
                            step="0.000001"
                            value={formData.exchange_rate}
                            onChange={(e) => setFormData({ ...formData, exchange_rate: e.target.value })}
                            required
                            className="glass-input"
                            style={{ width: '100%' }}
                        />
                    </div>

                    <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end', marginTop: '8px' }}>
                        <AnimatedButton variant="glass" onClick={() => setShowForm(false)} type="button">
                            Cancel
                        </AnimatedButton>
                        <AnimatedButton variant="primary" type="submit" loading={createCurrency.isPending}>
                            Create Currency
                        </AnimatedButton>
                    </div>
                </form>
            </Modal>
        </div>
    );
}
