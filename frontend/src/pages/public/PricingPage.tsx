import { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useModulePricing, type ModulePricingItem } from '../../hooks/useModulePricing';
import { usePublicPlans, type PublicPlan } from '../../hooks/usePublicPlans';
import { usePricingCurrency } from '../../hooks/usePricingCurrency';
import CurrencySwitcher from '../../components/public/CurrencySwitcher';
import {
  Check, ArrowRight, Building2, ChevronRight, Star, Crown, Sparkles,
  BarChart3, Globe, Users,
  Package, FileText, Wallet, Factory, Wrench, ClipboardCheck, Layers,
  TrendingUp,
} from 'lucide-react';

const MODULE_ICONS: Record<string, React.ReactNode> = {
  accounting: <Wallet size={24} />,
  sales: <TrendingUp size={24} />,
  procurement: <Package size={24} />,
  inventory: <Layers size={24} />,
  hrm: <Users size={24} />,
  budget: <BarChart3 size={24} />,
  production: <Factory size={24} />,
  quality: <ClipboardCheck size={24} />,
  service: <Wrench size={24} />,
  dimensions: <Globe size={24} />,
  workflow: <FileText size={24} />,
};

const PLAN_ICONS: Record<string, React.ReactNode> = {
  free: <Sparkles size={28} color="#64748b" />,
  basic: <Package size={28} color="#242a88" />,
  standard: <Star size={28} color="#242a88" />,
  premium: <Crown size={28} color="#242a88" />,
  enterprise: <Building2 size={28} color="#242a88" />,
};

const PLAN_ACCENTS: Record<string, string> = {
  free: '#64748b',
  basic: '#242a88',
  standard: '#2e35a0',
  premium: '#1e1e6e',
  enterprise: '#0f0f3d',
};

const PricingPage = () => {
  const navigate = useNavigate();
  const { data: modules = [], isLoading: modulesLoading } = useModulePricing();
  const { data: plans = [], isLoading: plansLoading } = usePublicPlans();
  const {
    currencies, selectedCode, setCurrency, formatPrice,
    detectedCountry,
  } = usePricingCurrency();
  const [billing, setBilling] = useState<'monthly' | 'yearly'>('monthly');
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [mode, setMode] = useState<'plans' | 'custom'>('plans');

  const toggle = (name: string) => {
    setSelected(prev => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  };

  const total = useMemo(() => {
    return modules
      .filter(m => selected.has(m.module_name))
      .reduce((sum, m) => sum + Number(billing === 'monthly' ? m.price_monthly : m.price_yearly), 0);
  }, [modules, selected, billing]);

  const isLoading = modulesLoading || plansLoading;

  // Filter plans by billing cycle, fall back to showing all if none match
  const filteredPlans = useMemo(() => {
    const matched = plans.filter(p => p.billing_cycle === billing);
    return matched.length > 0 ? matched : plans;
  }, [plans, billing]);

  return (
    <div style={{ fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, sans-serif", color: '#191c1e', background: '#f8f9fb', minHeight: '100vh' }}>
      {/* ── Nav ───────────────────────────────────────────── */}
      <nav style={{
        position: 'sticky', top: 0, zIndex: 100,
        background: 'rgba(255,255,255,0.85)', backdropFilter: 'blur(16px)', WebkitBackdropFilter: 'blur(16px)',
        padding: '16px 0', boxShadow: '0 1px 0 rgba(25,28,30,0.06)',
      }}>
        <div style={{ maxWidth: 1200, margin: '0 auto', padding: '0 24px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer' }} onClick={() => navigate('/')}>
            <div style={{
              width: 36, height: 36, borderRadius: 10,
              background: 'linear-gradient(135deg, #242a88, #2e35a0)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              <Building2 size={20} color="#fff" />
            </div>
            <span style={{ fontFamily: "'Manrope', sans-serif", fontSize: '1.25rem', fontWeight: 700 }}>DTSG ERP</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            <CurrencySwitcher
              currencies={currencies}
              selectedCode={selectedCode}
              onChange={setCurrency}
              detectedCountry={detectedCountry}
            />
            <button onClick={() => navigate('/')} style={{ background: 'none', border: 'none', color: '#4a5568', fontSize: '0.875rem', fontWeight: 500, cursor: 'pointer', fontFamily: 'inherit' }}>Home</button>
            <button
              onClick={() => navigate('/login')}
              style={{
                padding: '10px 24px', borderRadius: 8, border: 'none', cursor: 'pointer',
                background: 'linear-gradient(135deg, #242a88, #2e35a0)', color: '#fff',
                fontWeight: 600, fontSize: '0.875rem', fontFamily: 'inherit',
                boxShadow: '0 2px 8px rgba(36,42,136,0.25)',
              }}
            >
              Sign In
            </button>
          </div>
        </div>
      </nav>

      {/* ── Header ────────────────────────────────────────── */}
      <section style={{ padding: '80px 0 40px', textAlign: 'center' }}>
        <div style={{ maxWidth: 1200, margin: '0 auto', padding: '0 24px' }}>
          <h1 style={{
            fontFamily: "'Manrope', sans-serif", fontSize: 'clamp(2rem, 4vw, 2.5rem)',
            fontWeight: 700, color: '#191c1e', margin: '0 0 16px', letterSpacing: '-0.03em',
          }}>
            Choose how you want to get started
          </h1>
          <p style={{ fontSize: '1.05rem', color: '#4a5568', maxWidth: 600, margin: '0 auto 32px' }}>
            Subscribe to a ready-made plan or build your own by selecting individual modules.
          </p>

          {/* Mode toggle + Billing toggle */}
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 16 }}>
            {/* Plan / Custom toggle */}
            <div style={{ display: 'inline-flex', borderRadius: 10, background: '#edeef0', padding: 4 }}>
              <button
                onClick={() => setMode('plans')}
                style={{
                  padding: '10px 28px', borderRadius: 8, border: 'none', cursor: 'pointer',
                  background: mode === 'plans' ? '#ffffff' : 'transparent',
                  color: mode === 'plans' ? '#191c1e' : '#4a5568',
                  fontWeight: 600, fontSize: '0.85rem', fontFamily: 'inherit',
                  boxShadow: mode === 'plans' ? '0 1px 3px rgba(0,0,0,0.08)' : 'none',
                  transition: 'all 150ms ease',
                }}
              >
                Ready-Made Plans
              </button>
              <button
                onClick={() => setMode('custom')}
                style={{
                  padding: '10px 28px', borderRadius: 8, border: 'none', cursor: 'pointer',
                  background: mode === 'custom' ? '#ffffff' : 'transparent',
                  color: mode === 'custom' ? '#191c1e' : '#4a5568',
                  fontWeight: 600, fontSize: '0.85rem', fontFamily: 'inherit',
                  boxShadow: mode === 'custom' ? '0 1px 3px rgba(0,0,0,0.08)' : 'none',
                  transition: 'all 150ms ease',
                }}
              >
                Build Your Own
              </button>
            </div>

            {/* Billing toggle */}
            <div style={{ display: 'inline-flex', borderRadius: 8, background: '#edeef0', padding: 4 }}>
              <button
                onClick={() => setBilling('monthly')}
                style={{
                  padding: '8px 20px', borderRadius: 6, border: 'none', cursor: 'pointer',
                  background: billing === 'monthly' ? '#ffffff' : 'transparent',
                  color: billing === 'monthly' ? '#191c1e' : '#4a5568',
                  fontWeight: 600, fontSize: '0.8rem', fontFamily: 'inherit',
                  boxShadow: billing === 'monthly' ? '0 1px 3px rgba(0,0,0,0.08)' : 'none',
                  transition: 'all 150ms ease',
                }}
              >
                Monthly
              </button>
              <button
                onClick={() => setBilling('yearly')}
                style={{
                  padding: '8px 20px', borderRadius: 6, border: 'none', cursor: 'pointer',
                  background: billing === 'yearly' ? '#ffffff' : 'transparent',
                  color: billing === 'yearly' ? '#191c1e' : '#4a5568',
                  fontWeight: 600, fontSize: '0.8rem', fontFamily: 'inherit',
                  boxShadow: billing === 'yearly' ? '0 1px 3px rgba(0,0,0,0.08)' : 'none',
                  transition: 'all 150ms ease',
                }}
              >
                Yearly <span style={{ color: '#242a88', fontSize: '0.7rem', marginLeft: 4 }}>Save 20%</span>
              </button>
            </div>
          </div>
        </div>
      </section>

      {/* ── Content ───────────────────────────────────────── */}
      <section style={{ paddingBottom: 120 }}>
        <div style={{ maxWidth: 1200, margin: '0 auto', padding: '0 24px' }}>
          {isLoading ? (
            <div style={{ textAlign: 'center', padding: 80, color: '#94a3b8' }}>Loading pricing...</div>
          ) : mode === 'plans' ? (
            /* ═══════════════════ PLANS VIEW ═══════════════════ */
            <>
              {filteredPlans.length === 0 ? (
                <div style={{ textAlign: 'center', padding: 80, background: '#ffffff', borderRadius: 12 }}>
                  <Package size={48} color="#94a3b8" style={{ marginBottom: 16 }} />
                  <h3 style={{ fontFamily: "'Manrope', sans-serif", fontSize: '1.25rem', fontWeight: 600, margin: '0 0 8px' }}>
                    No plans available yet
                  </h3>
                  <p style={{ color: '#4a5568', fontSize: '0.9rem', margin: '0 0 24px' }}>
                    Plans will appear here once configured by the administrator.
                  </p>
                  <button
                    onClick={() => setMode('custom')}
                    style={{
                      padding: '12px 28px', borderRadius: 8, border: '2px solid #242a88', cursor: 'pointer',
                      background: 'transparent', color: '#242a88',
                      fontWeight: 600, fontSize: '0.875rem', fontFamily: 'inherit',
                    }}
                  >
                    Build Your Own Instead
                  </button>
                </div>
              ) : (
                <div style={{
                  display: 'grid',
                  gridTemplateColumns: `repeat(${Math.min(filteredPlans.length, 4)}, 1fr)`,
                  gap: 24,
                  maxWidth: filteredPlans.length <= 3 ? 960 : 1200,
                  margin: '0 auto',
                }}>
                  {filteredPlans.map((plan) => {
                    const accent = PLAN_ACCENTS[plan.plan_type] || '#242a88';
                    const isFeatured = plan.is_featured;
                    const price = Number(plan.price);
                    const includedFeatures = (plan.features || []).filter(f => f.included);

                    return (
                      <div
                        key={plan.id}
                        style={{
                          background: isFeatured
                            ? `linear-gradient(180deg, ${accent} 0%, ${accent}ee 100%)`
                            : '#ffffff',
                          color: isFeatured ? '#ffffff' : '#191c1e',
                          borderRadius: 16,
                          padding: '32px 28px',
                          position: 'relative',
                          display: 'flex', flexDirection: 'column',
                          outline: isFeatured ? 'none' : '1px solid #edeef0',
                          transition: 'transform 200ms ease, box-shadow 200ms ease',
                        }}
                        onMouseEnter={(e) => {
                          e.currentTarget.style.transform = 'translateY(-4px)';
                          e.currentTarget.style.boxShadow = isFeatured
                            ? '0 20px 60px rgba(36,42,136,0.3)'
                            : '0 12px 40px rgba(25,28,30,0.08)';
                        }}
                        onMouseLeave={(e) => {
                          e.currentTarget.style.transform = 'translateY(0)';
                          e.currentTarget.style.boxShadow = 'none';
                        }}
                      >
                        {isFeatured && (
                          <div style={{
                            position: 'absolute', top: -12, left: '50%', transform: 'translateX(-50%)',
                            padding: '4px 16px', borderRadius: 100,
                            background: '#fff', color: accent,
                            fontSize: '0.65rem', fontWeight: 700, textTransform: 'uppercase',
                            letterSpacing: '0.5px', boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
                          }}>
                            Most Popular
                          </div>
                        )}

                        <div style={{ marginBottom: 20 }}>
                          {PLAN_ICONS[plan.plan_type] || <Package size={28} />}
                        </div>

                        <h3 style={{
                          fontFamily: "'Manrope', sans-serif", fontSize: '1.15rem',
                          fontWeight: 700, margin: '0 0 6px',
                        }}>
                          {plan.name}
                        </h3>
                        <p style={{
                          fontSize: '0.8rem', margin: '0 0 20px', lineHeight: 1.5,
                          color: isFeatured ? 'rgba(255,255,255,0.75)' : '#4a5568',
                          minHeight: 40,
                        }}>
                          {plan.description || `${plan.allowed_modules.length} modules included`}
                        </p>

                        {/* Price */}
                        <div style={{ display: 'flex', alignItems: 'baseline', gap: 4, marginBottom: 24 }}>
                          {price === 0 ? (
                            <span style={{ fontFamily: "'Manrope', sans-serif", fontSize: '2rem', fontWeight: 700 }}>Free</span>
                          ) : (
                            <>
                              <span style={{ fontFamily: "'Manrope', sans-serif", fontSize: '2rem', fontWeight: 700 }}>
                                {formatPrice(price)}
                              </span>
                              <span style={{
                                fontSize: '0.75rem',
                                color: isFeatured ? 'rgba(255,255,255,0.6)' : '#94a3b8',
                              }}>
                                /{plan.billing_cycle === 'yearly' ? 'yr' : 'mo'}
                              </span>
                            </>
                          )}
                        </div>

                        {/* CTA */}
                        <button
                          onClick={() => {
                            const params = new URLSearchParams();
                            params.set('plan_id', String(plan.id));
                            params.set('plan_type', plan.plan_type);
                            params.set('billing', plan.billing_cycle);
                            if (plan.allowed_modules.length > 0) {
                              params.set('modules', plan.allowed_modules.join(','));
                            }
                            navigate(`/register?${params.toString()}`);
                          }}
                          style={{
                            width: '100%', padding: '12px 0', borderRadius: 8, border: 'none',
                            cursor: 'pointer', fontFamily: 'inherit',
                            fontWeight: 600, fontSize: '0.875rem',
                            background: isFeatured ? '#fff' : `linear-gradient(135deg, ${accent}, ${accent}dd)`,
                            color: isFeatured ? accent : '#fff',
                            boxShadow: isFeatured ? 'none' : `0 4px 14px ${accent}40`,
                            marginBottom: 24,
                          }}
                        >
                          {price === 0 ? 'Start Free' : 'Start Free Trial'}
                        </button>

                        {/* Included modules */}
                        <div style={{ fontSize: '0.7rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: 12, color: isFeatured ? 'rgba(255,255,255,0.5)' : '#94a3b8' }}>
                          {plan.allowed_modules.length} modules included
                        </div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, flex: 1 }}>
                          {plan.module_names.map((name, i) => (
                            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                              <Check size={14} color={isFeatured ? 'rgba(255,255,255,0.8)' : accent} style={{ flexShrink: 0 }} />
                              <span style={{ fontSize: '0.8rem', color: isFeatured ? 'rgba(255,255,255,0.85)' : '#4a5568' }}>{name}</span>
                            </div>
                          ))}
                        </div>

                        {/* Plan limits */}
                        <div style={{
                          marginTop: 20, paddingTop: 16,
                          borderTop: `1px solid ${isFeatured ? 'rgba(255,255,255,0.15)' : '#edeef0'}`,
                          display: 'flex', flexDirection: 'column', gap: 6,
                        }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem' }}>
                            <span style={{ color: isFeatured ? 'rgba(255,255,255,0.6)' : '#94a3b8' }}>Users</span>
                            <span style={{ fontWeight: 600 }}>Up to {plan.max_users}</span>
                          </div>
                          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem' }}>
                            <span style={{ color: isFeatured ? 'rgba(255,255,255,0.6)' : '#94a3b8' }}>Storage</span>
                            <span style={{ fontWeight: 600 }}>{plan.max_storage_gb} GB</span>
                          </div>
                          {plan.trial_days > 0 && (
                            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem' }}>
                              <span style={{ color: isFeatured ? 'rgba(255,255,255,0.6)' : '#94a3b8' }}>Free trial</span>
                              <span style={{ fontWeight: 600 }}>{plan.trial_days} days</span>
                            </div>
                          )}
                        </div>

                        {/* Included features */}
                        {includedFeatures.length > 0 && (
                          <div style={{ marginTop: 16, display: 'flex', flexDirection: 'column', gap: 6 }}>
                            {includedFeatures.slice(0, 5).map((feat, i) => (
                              <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                <Check size={12} color={isFeatured ? 'rgba(255,255,255,0.6)' : '#94a3b8'} style={{ flexShrink: 0 }} />
                                <span style={{ fontSize: '0.7rem', color: isFeatured ? 'rgba(255,255,255,0.7)' : '#94a3b8' }}>
                                  {feat.name}{feat.limit ? ` (${feat.limit})` : ''}
                                </span>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}

              {/* Link to custom mode */}
              <div style={{ textAlign: 'center', marginTop: 48, padding: '32px 24px', background: '#fff', borderRadius: 12 }}>
                <p style={{ fontSize: '1rem', color: '#191c1e', fontWeight: 600, margin: '0 0 8px' }}>
                  Need a different combination?
                </p>
                <p style={{ fontSize: '0.875rem', color: '#4a5568', margin: '0 0 20px' }}>
                  Build a custom plan by picking exactly the modules you need.
                </p>
                <button
                  onClick={() => setMode('custom')}
                  style={{
                    padding: '12px 28px', borderRadius: 8, border: '2px solid #242a88', cursor: 'pointer',
                    background: 'transparent', color: '#242a88',
                    fontWeight: 600, fontSize: '0.875rem', fontFamily: 'inherit',
                    display: 'inline-flex', alignItems: 'center', gap: 8,
                  }}
                >
                  Build Your Own <ArrowRight size={16} />
                </button>
              </div>
            </>
          ) : (
            /* ═══════════════════ CUSTOM / MODULE VIEW ═══════════════════ */
            <>
              {modules.length === 0 ? (
                <div style={{ textAlign: 'center', padding: 80, background: '#ffffff', borderRadius: 12 }}>
                  <Package size={48} color="#94a3b8" style={{ marginBottom: 16 }} />
                  <h3 style={{ fontFamily: "'Manrope', sans-serif", fontSize: '1.25rem', fontWeight: 600, margin: '0 0 8px' }}>
                    No modules available yet
                  </h3>
                  <p style={{ color: '#4a5568', fontSize: '0.9rem' }}>
                    Module pricing will appear here once configured by the administrator.
                  </p>
                </div>
              ) : (
                <>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 24 }}>
                    {modules.map((mod) => {
                      const isSelected = selected.has(mod.module_name);
                      const price = billing === 'monthly' ? mod.price_monthly : mod.price_yearly;
                      return (
                        <div
                          key={mod.module_name}
                          style={{
                            background: '#ffffff', borderRadius: 12, padding: 28, position: 'relative',
                            outline: isSelected ? '2px solid #242a88' : '2px solid transparent',
                            transition: 'all 200ms ease', cursor: 'pointer',
                          }}
                          onClick={() => toggle(mod.module_name)}
                          onMouseEnter={(e) => {
                            if (!isSelected) e.currentTarget.style.boxShadow = '0 8px 30px rgba(25,28,30,0.06)';
                          }}
                          onMouseLeave={(e) => {
                            e.currentTarget.style.boxShadow = 'none';
                          }}
                        >
                          {/* Selection checkbox */}
                          <div style={{
                            position: 'absolute', top: 16, right: 16,
                            width: 24, height: 24, borderRadius: 6,
                            background: isSelected ? '#242a88' : '#edeef0',
                            display: 'flex', alignItems: 'center', justifyContent: 'center',
                            transition: 'all 150ms ease',
                          }}>
                            {isSelected && <Check size={14} color="#fff" strokeWidth={3} />}
                          </div>

                          {mod.is_popular && (
                            <div style={{
                              display: 'inline-flex', padding: '3px 10px', borderRadius: 100,
                              background: 'rgba(36,42,136,0.06)', color: '#242a88',
                              fontSize: '0.65rem', fontWeight: 600, textTransform: 'uppercase',
                              letterSpacing: '0.5px', marginBottom: 12,
                            }}>
                              Popular
                            </div>
                          )}

                          <div style={{
                            width: 44, height: 44, borderRadius: 10,
                            background: isSelected ? 'rgba(36,42,136,0.08)' : '#f8f9fb',
                            color: '#242a88', display: 'flex', alignItems: 'center', justifyContent: 'center',
                            marginBottom: 16, transition: 'all 150ms ease',
                          }}>
                            {MODULE_ICONS[mod.module_name] || <Package size={24} />}
                          </div>

                          <h3 style={{ fontFamily: "'Manrope', sans-serif", fontSize: '1rem', fontWeight: 600, margin: '0 0 4px' }}>
                            {mod.title}
                          </h3>
                          <p style={{ fontSize: '0.8rem', color: '#4a5568', margin: '0 0 16px', lineHeight: 1.5, minHeight: 36 }}>
                            {mod.tagline || mod.description?.slice(0, 100)}
                          </p>

                          <div style={{ display: 'flex', alignItems: 'baseline', gap: 4, marginBottom: 16 }}>
                            <span style={{ fontFamily: "'Manrope', sans-serif", fontSize: '1.5rem', fontWeight: 700, color: '#191c1e' }}>
                              {formatPrice(price)}
                            </span>
                            <span style={{ fontSize: '0.75rem', color: '#94a3b8' }}>/{billing === 'monthly' ? 'mo' : 'yr'}</span>
                          </div>

                          {mod.features && mod.features.length > 0 && (
                            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                              {mod.features.slice(0, 4).map((feat, i) => (
                                <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
                                  <Check size={14} color="#242a88" style={{ marginTop: 2, flexShrink: 0 }} />
                                  <span style={{ fontSize: '0.8rem', color: '#4a5568' }}>{feat}</span>
                                </div>
                              ))}
                              {mod.features.length > 4 && (
                                <span
                                  onClick={(e) => { e.stopPropagation(); navigate(`/pricing/${mod.module_name}`); }}
                                  style={{ fontSize: '0.75rem', color: '#242a88', fontWeight: 500, cursor: 'pointer' }}
                                >
                                  +{mod.features.length - 4} more features <ChevronRight size={12} style={{ verticalAlign: 'middle' }} />
                                </span>
                              )}
                            </div>
                          )}

                          <div style={{ marginTop: 16 }}>
                            <span
                              onClick={(e) => { e.stopPropagation(); navigate(`/pricing/${mod.module_name}`); }}
                              style={{ fontSize: '0.8rem', color: '#242a88', fontWeight: 500, cursor: 'pointer' }}
                            >
                              Learn more <ChevronRight size={14} style={{ verticalAlign: 'middle' }} />
                            </span>
                          </div>
                        </div>
                      );
                    })}
                  </div>

                  {/* ── Floating Summary Tray ────────────────────── */}
                  {selected.size > 0 && (
                    <div style={{
                      position: 'fixed', bottom: 24, left: '50%', transform: 'translateX(-50%)',
                      zIndex: 100, background: 'rgba(255,255,255,0.92)',
                      backdropFilter: 'blur(16px)', WebkitBackdropFilter: 'blur(16px)',
                      borderRadius: 16, padding: '16px 28px',
                      boxShadow: '0 12px 40px rgba(25,28,30,0.12), 0 2px 8px rgba(25,28,30,0.06)',
                      display: 'flex', alignItems: 'center', gap: 24,
                      maxWidth: 600, width: 'calc(100% - 48px)',
                    }}>
                      <div style={{ flex: 1 }}>
                        <div style={{ fontSize: '0.75rem', color: '#4a5568', fontWeight: 500, marginBottom: 2 }}>
                          {selected.size} module{selected.size !== 1 ? 's' : ''} selected
                        </div>
                        <div style={{ display: 'flex', alignItems: 'baseline', gap: 4 }}>
                          <span style={{ fontFamily: "'Manrope', sans-serif", fontSize: '1.5rem', fontWeight: 700, color: '#191c1e' }}>
                            {formatPrice(total)}
                          </span>
                          <span style={{ fontSize: '0.75rem', color: '#94a3b8' }}>/{billing === 'monthly' ? 'mo' : 'yr'}</span>
                        </div>
                      </div>
                      <button
                        onClick={() => {
                          const params = new URLSearchParams();
                          params.set('modules', Array.from(selected).join(','));
                          params.set('billing', billing);
                          navigate(`/register?${params.toString()}`);
                        }}
                        style={{
                          padding: '12px 28px', borderRadius: 8, border: 'none', cursor: 'pointer',
                          background: 'linear-gradient(135deg, #242a88, #2e35a0)', color: '#fff',
                          fontWeight: 600, fontSize: '0.875rem', fontFamily: 'inherit',
                          boxShadow: '0 4px 14px rgba(36,42,136,0.3)',
                          display: 'flex', alignItems: 'center', gap: 8, whiteSpace: 'nowrap',
                        }}
                      >
                        Get Started <ArrowRight size={16} />
                      </button>
                    </div>
                  )}
                </>
              )}

              {/* Link back to plans */}
              {filteredPlans.length > 0 && (
                <div style={{ textAlign: 'center', marginTop: 48, padding: '32px 24px', background: '#fff', borderRadius: 12 }}>
                  <p style={{ fontSize: '1rem', color: '#191c1e', fontWeight: 600, margin: '0 0 8px' }}>
                    Prefer a pre-configured plan?
                  </p>
                  <p style={{ fontSize: '0.875rem', color: '#4a5568', margin: '0 0 20px' }}>
                    Check our ready-made plans with bundled modules and better pricing.
                  </p>
                  <button
                    onClick={() => setMode('plans')}
                    style={{
                      padding: '12px 28px', borderRadius: 8, border: '2px solid #242a88', cursor: 'pointer',
                      background: 'transparent', color: '#242a88',
                      fontWeight: 600, fontSize: '0.875rem', fontFamily: 'inherit',
                      display: 'inline-flex', alignItems: 'center', gap: 8,
                    }}
                  >
                    View Plans <ArrowRight size={16} />
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      </section>
    </div>
  );
};

export default PricingPage;
