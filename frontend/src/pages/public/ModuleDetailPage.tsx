import { useParams, useNavigate } from 'react-router-dom';
import { useModulePricingDetail } from '../../hooks/useModulePricing';
import { usePricingCurrency } from '../../hooks/usePricingCurrency';
import CurrencySwitcher from '../../components/public/CurrencySwitcher';
import {
  ArrowLeft, ArrowRight, Check, Building2,
  BarChart3, Shield, Globe, Users,
  Package, FileText, Wallet, Layers,
  Zap,
} from 'lucide-react';

const MODULE_ICONS: Record<string, React.ReactNode> = {
  accounting: <Wallet size={32} />,
  procurement: <Package size={32} />,
  inventory: <Layers size={32} />,
  hrm: <Users size={32} />,
  budget: <BarChart3 size={32} />,
  dimensions: <Globe size={32} />,
  workflow: <FileText size={32} />,
};

const MODULE_DESCRIPTIONS: Record<string, string> = {
  accounting: 'Full double-entry accounting with Chart of Accounts, General Ledger, Accounts Payable, Accounts Receivable, Fixed Assets, Bank Reconciliation, and real-time financial statements. Government-grade reporting with multi-dimensional tracking.',
  procurement: 'Complete purchase-to-pay cycle including purchase requests, purchase orders, goods received notes (GRN), vendor invoices with 3-way matching, and vendor management. Credit notes, debit notes, and returns supported.',
  inventory: 'Warehouse management with multi-location stock tracking, batch and serial number control, automated reorder alerts, stock movements, and reconciliation. Full integration with procurement.',
  hrm: 'Comprehensive human resource management: employee records, leave management, attendance tracking, payroll processing, recruitment pipeline, onboarding workflows, performance reviews, and training management.',
  budget: 'Budget planning and control with multi-level allocations, variance analysis, and encumbrance tracking. Prevent over-spending with real-time budget checking on procurement and journal entries.',
  dimensions: 'Multi-dimensional accounting for government and enterprise: Fund, Function, Program, Geographic Region, and MDA dimensions. Enable granular reporting and compliance with IPSAS/IFRS standards.',
  workflow: 'Configurable approval workflows with sequential and parallel approval chains, delegation rules, escalation policies, and complete audit trail. Attach to any business document.',
};

const ModuleDetailPage = () => {
  const { moduleName } = useParams<{ moduleName: string }>();
  const navigate = useNavigate();
  const { data: mod, isLoading, isError } = useModulePricingDetail(moduleName || '');
  const { currencies, selectedCode, setCurrency, formatPrice, detectedCountry } = usePricingCurrency();

  if (isLoading) {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: "'Inter', sans-serif", background: '#f8f9fb' }}>
        <div style={{ textAlign: 'center', color: '#94a3b8' }}>
          <div style={{ width: 40, height: 40, border: '3px solid #edeef0', borderTop: '3px solid #242a88', borderRadius: '50%', animation: 'spin 1s linear infinite', margin: '0 auto 16px' }} />
          Loading module details...
        </div>
      </div>
    );
  }

  const title = mod?.title || moduleName?.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase()) || 'Module';
  const description = mod?.description || MODULE_DESCRIPTIONS[moduleName || ''] || '';
  const features = mod?.features || [];
  const highlights = mod?.highlights || [];

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
            <span style={{ fontFamily: "'Manrope', sans-serif", fontSize: '1.25rem', fontWeight: 700 }}>QUOT ERP</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            <CurrencySwitcher
              currencies={currencies}
              selectedCode={selectedCode}
              onChange={setCurrency}
              detectedCountry={detectedCountry}
            />
            <button onClick={() => navigate('/pricing')} style={{ background: 'none', border: 'none', color: '#4a5568', fontSize: '0.875rem', fontWeight: 500, cursor: 'pointer', fontFamily: 'inherit' }}>All Modules</button>
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

      {/* ── Breadcrumb ────────────────────────────────────── */}
      <div style={{ maxWidth: 1200, margin: '0 auto', padding: '24px 24px 0' }}>
        <button
          onClick={() => navigate('/pricing')}
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 6, background: 'none', border: 'none',
            color: '#242a88', fontSize: '0.8rem', fontWeight: 500, cursor: 'pointer', fontFamily: 'inherit',
          }}
        >
          <ArrowLeft size={14} /> Back to all modules
        </button>
      </div>

      {/* ── Hero ──────────────────────────────────────────── */}
      <section style={{ padding: '48px 0 80px' }}>
        <div style={{ maxWidth: 1200, margin: '0 auto', padding: '0 24px' }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 380px', gap: 64, alignItems: 'start' }}>
            {/* Left — Details */}
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 24 }}>
                <div style={{
                  width: 56, height: 56, borderRadius: 14,
                  background: 'rgba(36,42,136,0.06)', color: '#242a88',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                }}>
                  {MODULE_ICONS[moduleName || ''] || <Package size={32} />}
                </div>
                <div>
                  {mod?.is_popular && (
                    <div style={{
                      display: 'inline-flex', padding: '2px 8px', borderRadius: 100,
                      background: 'rgba(36,42,136,0.06)', color: '#242a88',
                      fontSize: '0.6rem', fontWeight: 600, textTransform: 'uppercase',
                      letterSpacing: '0.5px', marginBottom: 4,
                    }}>
                      Popular
                    </div>
                  )}
                  <h1 style={{
                    fontFamily: "'Manrope', sans-serif", fontSize: '2rem', fontWeight: 700,
                    color: '#191c1e', margin: 0, letterSpacing: '-0.02em',
                  }}>
                    {title}
                  </h1>
                </div>
              </div>

              {mod?.tagline && (
                <p style={{ fontSize: '1.05rem', color: '#4a5568', margin: '0 0 24px', fontWeight: 500 }}>
                  {mod.tagline}
                </p>
              )}

              <p style={{ fontSize: '0.95rem', lineHeight: 1.8, color: '#4a5568', margin: '0 0 40px', maxWidth: 640 }}>
                {description}
              </p>

              {/* Highlights */}
              {highlights.length > 0 && (
                <div style={{ marginBottom: 40 }}>
                  <h3 style={{ fontFamily: "'Manrope', sans-serif", fontSize: '1rem', fontWeight: 600, margin: '0 0 16px' }}>
                    Key Benefits
                  </h3>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 12 }}>
                    {highlights.map((h, i) => (
                      <div key={i} style={{
                        display: 'flex', alignItems: 'flex-start', gap: 12, padding: 16,
                        background: '#ffffff', borderRadius: 10,
                      }}>
                        <div style={{
                          width: 28, height: 28, borderRadius: 7, flexShrink: 0,
                          background: 'rgba(36,42,136,0.06)', color: '#242a88',
                          display: 'flex', alignItems: 'center', justifyContent: 'center',
                        }}>
                          <Zap size={14} />
                        </div>
                        <span style={{ fontSize: '0.85rem', color: '#191c1e', lineHeight: 1.5 }}>{h}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Features */}
              {features.length > 0 && (
                <div>
                  <h3 style={{ fontFamily: "'Manrope', sans-serif", fontSize: '1rem', fontWeight: 600, margin: '0 0 16px' }}>
                    Included Features
                  </h3>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: 10 }}>
                    {features.map((f, i) => (
                      <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
                        <Check size={16} color="#242a88" style={{ marginTop: 2, flexShrink: 0 }} />
                        <span style={{ fontSize: '0.85rem', color: '#4a5568', lineHeight: 1.5 }}>{f}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Fallback when no data from API */}
              {!mod && !isError && (
                <div style={{
                  padding: 32, background: '#ffffff', borderRadius: 12, textAlign: 'center',
                }}>
                  <Shield size={32} color="#94a3b8" style={{ marginBottom: 12 }} />
                  <p style={{ color: '#4a5568', fontSize: '0.9rem', margin: 0 }}>
                    Detailed pricing and features for this module will be available once configured by the administrator.
                  </p>
                </div>
              )}
            </div>

            {/* Right — Pricing Card (sticky) */}
            <div style={{ position: 'sticky', top: 100 }}>
              <div style={{
                background: '#ffffff', borderRadius: 16, padding: 32,
                boxShadow: '0 4px 20px rgba(25,28,30,0.06)',
              }}>
                {mod ? (
                  <>
                    <div style={{ marginBottom: 24 }}>
                      <div style={{ fontSize: '0.75rem', color: '#94a3b8', fontWeight: 500, textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: 8 }}>
                        Monthly
                      </div>
                      <div style={{ display: 'flex', alignItems: 'baseline', gap: 4 }}>
                        <span style={{ fontFamily: "'Manrope', sans-serif", fontSize: '2.5rem', fontWeight: 700, color: '#191c1e' }}>
                          {formatPrice(mod.price_monthly)}
                        </span>
                        <span style={{ fontSize: '0.875rem', color: '#94a3b8' }}>/month</span>
                      </div>
                    </div>

                    {Number(mod.price_yearly) > 0 && (
                      <div style={{
                        padding: '12px 16px', borderRadius: 8, background: 'rgba(36,42,136,0.04)',
                        marginBottom: 24,
                      }}>
                        <div style={{ fontSize: '0.8rem', color: '#4a5568' }}>
                          Yearly: <strong style={{ color: '#191c1e' }}>{formatPrice(mod.price_yearly)}/yr</strong>
                          <span style={{ color: '#242a88', marginLeft: 8, fontWeight: 600 }}>Save 20%</span>
                        </div>
                      </div>
                    )}

                    <button
                      onClick={() => navigate(`/register?modules=${moduleName}&billing=monthly`)}
                      style={{
                        width: '100%', padding: '14px 0', borderRadius: 8, border: 'none', cursor: 'pointer',
                        background: 'linear-gradient(135deg, #242a88, #2e35a0)', color: '#fff',
                        fontWeight: 600, fontSize: '1rem', fontFamily: 'inherit',
                        boxShadow: '0 4px 14px rgba(36,42,136,0.3)',
                        display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
                        marginBottom: 12,
                      }}
                    >
                      Start Free Trial <ArrowRight size={16} />
                    </button>
                    <button
                      onClick={() => navigate('/pricing')}
                      style={{
                        width: '100%', padding: '12px 0', borderRadius: 8,
                        border: '1.5px solid #edeef0', background: 'transparent', color: '#191c1e',
                        cursor: 'pointer', fontWeight: 500, fontSize: '0.875rem', fontFamily: 'inherit',
                      }}
                    >
                      Compare all modules
                    </button>
                  </>
                ) : (
                  <>
                    <div style={{ textAlign: 'center', padding: '24px 0' }}>
                      <p style={{ color: '#4a5568', fontSize: '0.9rem', margin: '0 0 20px' }}>
                        Pricing not yet configured
                      </p>
                      <button
                        onClick={() => navigate('/register')}
                        style={{
                          width: '100%', padding: '14px 0', borderRadius: 8, border: 'none', cursor: 'pointer',
                          background: 'linear-gradient(135deg, #242a88, #2e35a0)', color: '#fff',
                          fontWeight: 600, fontSize: '1rem', fontFamily: 'inherit',
                          boxShadow: '0 4px 14px rgba(36,42,136,0.3)',
                          display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
                        }}
                      >
                        Start Free Trial <ArrowRight size={16} />
                      </button>
                    </div>
                  </>
                )}

                <div style={{ marginTop: 24, display: 'flex', flexDirection: 'column', gap: 10 }}>
                  {['No credit card required', '14-day free trial', 'Cancel anytime'].map((t, i) => (
                    <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <Check size={14} color="#242a88" />
                      <span style={{ fontSize: '0.8rem', color: '#4a5568' }}>{t}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
};

export default ModuleDetailPage;
