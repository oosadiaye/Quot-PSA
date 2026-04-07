import { useNavigate } from 'react-router-dom';
import { useModulePricing } from '../../hooks/useModulePricing';
import {
  BarChart3, Shield, Globe, Zap, ArrowRight, Check, Building2, Users,
  Package, FileText, Wallet, Factory, Wrench, ClipboardCheck, Layers,
  TrendingUp, ChevronRight,
} from 'lucide-react';

const MODULE_ICONS: Record<string, React.ReactNode> = {
  accounting: <Wallet size={28} />,
  sales: <TrendingUp size={28} />,
  procurement: <Package size={28} />,
  inventory: <Layers size={28} />,
  hrm: <Users size={28} />,
  budget: <BarChart3 size={28} />,
  production: <Factory size={28} />,
  quality: <ClipboardCheck size={28} />,
  service: <Wrench size={28} />,
  dimensions: <Globe size={28} />,
  workflow: <FileText size={28} />,
};

/* Fallback modules when no pricing data exists in the DB yet */
const defaultModules = [
  { module_name: 'accounting', title: 'Accounting', tagline: 'Chart of Accounts, Journals, AP/AR, Fixed Assets', is_popular: true, price_monthly: '', description: '' },
  { module_name: 'procurement', title: 'Procurement', tagline: 'Purchase Requests, Orders, Vendors, GRN', is_popular: false, price_monthly: '', description: '' },
  { module_name: 'inventory', title: 'Inventory', tagline: 'Items, Stock, Warehouses, Batch Tracking', is_popular: false, price_monthly: '', description: '' },
  { module_name: 'sales', title: 'Sales', tagline: 'CRM, Quotations, Sales Orders, Delivery', is_popular: true, price_monthly: '', description: '' },
  { module_name: 'hrm', title: 'Human Resources', tagline: 'Employees, Leave, Payroll, Performance', is_popular: false, price_monthly: '', description: '' },
  { module_name: 'budget', title: 'Budget Management', tagline: 'Allocations, Variance Analysis', is_popular: false, price_monthly: '', description: '' },
  { module_name: 'production', title: 'Production', tagline: 'BOM, Work Orders, Manufacturing', is_popular: false, price_monthly: '', description: '' },
  { module_name: 'quality', title: 'Quality', tagline: 'Inspections, NCR, Complaints', is_popular: false, price_monthly: '', description: '' },
  { module_name: 'service', title: 'Service', tagline: 'Tickets, Maintenance, SLA Tracking', is_popular: false, price_monthly: '', description: '' },
  { module_name: 'workflow', title: 'Workflow', tagline: 'Approval Templates & Workflows', is_popular: false, price_monthly: '', description: '' },
  { module_name: 'dimensions', title: 'Dimensions', tagline: 'Fund, Function, Program, Geo, MDA', is_popular: false, price_monthly: '', description: '' },
];

const LandingPage = () => {
  const navigate = useNavigate();
  const { data: rawModules = [] } = useModulePricing();
  const modules = Array.isArray(rawModules) ? rawModules : [];

  return (
    <div style={{ fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, sans-serif", color: '#191c1e', background: '#f8f9fb' }}>
      {/* ── Glassmorphic Navigation ────────────────────────── */}
      <nav style={{
        position: 'fixed', top: 0, left: 0, right: 0, zIndex: 100,
        background: 'rgba(255,255,255,0.85)', backdropFilter: 'blur(16px)', WebkitBackdropFilter: 'blur(16px)',
        padding: '16px 0',
        boxShadow: '0 1px 0 rgba(25,28,30,0.06)',
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
            <span style={{ fontFamily: "'Manrope', sans-serif", fontSize: '1.25rem', fontWeight: 700, color: '#191c1e' }}>
              DTSG ERP
            </span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 32 }}>
            <a href="#features" style={{ color: '#4a5568', textDecoration: 'none', fontSize: '0.875rem', fontWeight: 500 }}>Features</a>
            <a href="#modules" style={{ color: '#4a5568', textDecoration: 'none', fontSize: '0.875rem', fontWeight: 500 }}>Modules</a>
            <button
              onClick={() => navigate('/pricing')}
              style={{
                background: 'none', border: 'none', color: '#4a5568', fontSize: '0.875rem',
                fontWeight: 500, cursor: 'pointer', fontFamily: 'inherit',
              }}
            >
              Pricing
            </button>
            <button
              onClick={() => navigate('/login')}
              style={{
                padding: '10px 24px', borderRadius: 8, border: 'none', cursor: 'pointer',
                background: 'linear-gradient(135deg, #242a88, #2e35a0)', color: '#fff',
                fontWeight: 600, fontSize: '0.875rem', fontFamily: 'inherit',
                boxShadow: '0 2px 8px rgba(36,42,136,0.25)',
                transition: 'all 200ms ease',
              }}
            >
              Sign In
            </button>
          </div>
        </div>
      </nav>

      {/* ── Hero Section ───────────────────────────────────── */}
      <section style={{
        paddingTop: 160, paddingBottom: 120,
        background: 'linear-gradient(180deg, #ffffff 0%, #f8f9fb 100%)',
        position: 'relative', overflow: 'hidden',
      }}>
        {/* Decorative gradient orbs */}
        <div style={{
          position: 'absolute', top: -100, right: -100, width: 500, height: 500,
          borderRadius: '50%', background: 'radial-gradient(circle, rgba(36,42,136,0.06) 0%, transparent 70%)',
        }} />
        <div style={{
          position: 'absolute', bottom: -60, left: -80, width: 400, height: 400,
          borderRadius: '50%', background: 'radial-gradient(circle, rgba(0,75,89,0.04) 0%, transparent 70%)',
        }} />

        <div style={{ maxWidth: 1200, margin: '0 auto', padding: '0 24px', position: 'relative' }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 64, alignItems: 'center' }}>
            <div>
              <div style={{
                display: 'inline-flex', alignItems: 'center', gap: 8, padding: '6px 16px',
                borderRadius: 100, background: 'rgba(36,42,136,0.06)', marginBottom: 24,
              }}>
                <Zap size={14} color="#242a88" />
                <span style={{ fontSize: '0.75rem', fontWeight: 600, color: '#242a88', letterSpacing: '0.5px', textTransform: 'uppercase' }}>
                  Enterprise-grade ERP
                </span>
              </div>

              <h1 style={{
                fontFamily: "'Manrope', sans-serif", fontSize: 'clamp(2.5rem, 5vw, 3.5rem)',
                fontWeight: 700, lineHeight: 1.1, color: '#191c1e', margin: '0 0 24px',
                letterSpacing: '-0.03em',
              }}>
                Build your organization
                <br />
                <span style={{ color: '#242a88' }}>module by module</span>
              </h1>

              <p style={{
                fontSize: '1.125rem', lineHeight: 1.7, color: '#4a5568', maxWidth: 560,
                margin: '0 0 40px',
              }}>
                Select only the modules you need. Scale as you grow. One platform for accounting,
                procurement, HR, inventory, and more &mdash; with per-module pricing that puts you in control.
              </p>

              <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
                <button
                  onClick={() => navigate('/register')}
                  style={{
                    padding: '14px 32px', borderRadius: 8, border: 'none', cursor: 'pointer',
                    background: 'linear-gradient(135deg, #242a88, #2e35a0)', color: '#fff',
                    fontWeight: 600, fontSize: '1rem', fontFamily: 'inherit',
                    boxShadow: '0 4px 14px rgba(36,42,136,0.3)',
                    display: 'flex', alignItems: 'center', gap: 8,
                    transition: 'all 200ms ease',
                  }}
                >
                  Start Free Trial <ArrowRight size={18} />
                </button>
                <button
                  onClick={() => navigate('/pricing')}
                  style={{
                    padding: '14px 32px', borderRadius: 8, border: '1.5px solid #242a88',
                    background: 'transparent', color: '#242a88', cursor: 'pointer',
                    fontWeight: 600, fontSize: '1rem', fontFamily: 'inherit',
                    transition: 'all 200ms ease',
                  }}
                >
                  View Pricing
                </button>
              </div>
            </div>

            {/* Hero Image */}
            <div style={{ position: 'relative' }}>
              <img
                src="https://images.unsplash.com/photo-1460925895917-afdab827c52f?w=600&h=450&fit=crop&q=80"
                alt="Business analytics dashboard"
                style={{
                  width: '100%', borderRadius: 16,
                  boxShadow: '0 20px 60px rgba(36,42,136,0.15)',
                  objectFit: 'cover',
                }}
              />
              {/* Floating stats card */}
              <div style={{
                position: 'absolute', bottom: -24, left: -24, background: '#ffffff',
                borderRadius: 12, padding: '16px 20px',
                boxShadow: '0 8px 30px rgba(25,28,30,0.12)',
                display: 'flex', alignItems: 'center', gap: 12,
              }}>
                <div style={{
                  width: 40, height: 40, borderRadius: 10,
                  background: 'rgba(36,42,136,0.08)', color: '#242a88',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                }}>
                  <TrendingUp size={20} />
                </div>
                <div>
                  <div style={{ fontSize: '0.7rem', color: '#94a3b8', fontWeight: 500 }}>Efficiency gain</div>
                  <div style={{ fontSize: '1.25rem', fontWeight: 700, color: '#191c1e' }}>+42%</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── Trust Bar ──────────────────────────────────────── */}
      <section style={{ background: '#ffffff', padding: '48px 0' }}>
        <div style={{ maxWidth: 1200, margin: '0 auto', padding: '0 24px' }}>
          <div style={{ display: 'flex', justifyContent: 'center', gap: 64, flexWrap: 'wrap', alignItems: 'center' }}>
            {[
              { icon: <Shield size={20} color="#242a88" />, text: 'SOC 2 Compliant' },
              { icon: <Globe size={20} color="#242a88" />, text: 'Multi-tenant Architecture' },
              { icon: <Zap size={20} color="#242a88" />, text: 'Real-time Analytics' },
              { icon: <Users size={20} color="#242a88" />, text: 'Role-based Access' },
            ].map((item, i) => (
              <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                {item.icon}
                <span style={{ fontSize: '0.875rem', fontWeight: 500, color: '#4a5568' }}>{item.text}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Features Section ───────────────────────────────── */}
      <section id="features" style={{ padding: '100px 0', background: '#f8f9fb' }}>
        <div style={{ maxWidth: 1200, margin: '0 auto', padding: '0 24px' }}>
          <div style={{ textAlign: 'center', marginBottom: 72 }}>
            <h2 style={{
              fontFamily: "'Manrope', sans-serif", fontSize: '1.75rem', fontWeight: 600,
              color: '#191c1e', margin: '0 0 16px',
            }}>
              Why organizations choose DTSG
            </h2>
            <p style={{ fontSize: '1rem', color: '#4a5568', maxWidth: 560, margin: '0 auto' }}>
              An enterprise resource platform designed for modern teams that demand flexibility without compromise.
            </p>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 32 }}>
            {[
              {
                icon: <Layers size={24} />,
                title: 'Modular by Design',
                desc: 'Pick the exact modules your organization needs. No bloated bundles — pay only for what you use.',
              },
              {
                icon: <Shield size={24} />,
                title: 'Enterprise Security',
                desc: 'Multi-tenant isolation, role-based access control, audit logging, and 256-bit encryption at rest.',
              },
              {
                icon: <BarChart3 size={24} />,
                title: 'Real-time Financials',
                desc: 'GL posting, trial balance, P&L, and balance sheet — all generated in real-time from your journal entries.',
              },
              {
                icon: <Globe size={24} />,
                title: 'Multi-dimensional Accounting',
                desc: 'Track by Fund, Function, Program, Geo, and MDA simultaneously for complete government-grade reporting.',
              },
              {
                icon: <Zap size={24} />,
                title: 'Instant Provisioning',
                desc: 'Sign up and your tenant is ready in seconds. No waiting for setup calls or manual configuration.',
              },
              {
                icon: <TrendingUp size={24} />,
                title: 'Scale Without Limits',
                desc: 'Add modules, users, and storage as your organization grows. Upgrade or downgrade anytime.',
              },
            ].map((feature, i) => (
              <div key={i} style={{
                background: '#ffffff', borderRadius: 12, padding: 32,
                transition: 'all 200ms ease',
              }}>
                <div style={{
                  width: 48, height: 48, borderRadius: 10,
                  background: 'rgba(36,42,136,0.06)', color: '#242a88',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  marginBottom: 20,
                }}>
                  {feature.icon}
                </div>
                <h3 style={{ fontFamily: "'Manrope', sans-serif", fontSize: '1rem', fontWeight: 600, margin: '0 0 8px' }}>
                  {feature.title}
                </h3>
                <p style={{ fontSize: '0.875rem', lineHeight: 1.6, color: '#4a5568', margin: 0 }}>
                  {feature.desc}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Modules Showcase ───────────────────────────────── */}
      <section id="modules" style={{ padding: '100px 0', background: '#ffffff' }}>
        <div style={{ maxWidth: 1200, margin: '0 auto', padding: '0 24px' }}>
          <div style={{ textAlign: 'center', marginBottom: 72 }}>
            <h2 style={{
              fontFamily: "'Manrope', sans-serif", fontSize: '1.75rem', fontWeight: 600,
              color: '#191c1e', margin: '0 0 16px',
            }}>
              {modules.length > 0 ? `${modules.length} modules, one platform` : 'Comprehensive ERP modules'}
            </h2>
            <p style={{ fontSize: '1rem', color: '#4a5568', maxWidth: 560, margin: '0 auto' }}>
              Each module works independently or integrates seamlessly with the rest.
              Select what you need today — add more as you grow.
            </p>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 24 }}>
            {(modules.length > 0 ? modules : defaultModules).map((mod, i) => (
              <div
                key={mod.module_name || i}
                onClick={() => navigate(`/pricing/${mod.module_name}`)}
                style={{
                  background: '#f8f9fb', borderRadius: 12, padding: 28,
                  cursor: 'pointer', transition: 'all 200ms ease',
                  position: 'relative',
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.background = '#ffffff';
                  e.currentTarget.style.boxShadow = '0 8px 30px rgba(25,28,30,0.06)';
                  e.currentTarget.style.transform = 'translateY(-2px)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = '#f8f9fb';
                  e.currentTarget.style.boxShadow = 'none';
                  e.currentTarget.style.transform = 'translateY(0)';
                }}
              >
                {mod.is_popular && (
                  <div style={{
                    position: 'absolute', top: 12, right: 12, padding: '3px 10px',
                    borderRadius: 100, background: 'rgba(36,42,136,0.08)', color: '#242a88',
                    fontSize: '0.65rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px',
                  }}>
                    Popular
                  </div>
                )}
                <div style={{
                  width: 48, height: 48, borderRadius: 10,
                  background: 'rgba(36,42,136,0.06)', color: '#242a88',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  marginBottom: 16,
                }}>
                  {MODULE_ICONS[mod.module_name] || <Package size={28} />}
                </div>
                <h3 style={{ fontFamily: "'Manrope', sans-serif", fontSize: '1rem', fontWeight: 600, margin: '0 0 6px' }}>
                  {mod.title}
                </h3>
                <p style={{ fontSize: '0.8rem', lineHeight: 1.5, color: '#4a5568', margin: '0 0 16px', minHeight: 40 }}>
                  {mod.tagline || mod.description?.slice(0, 80)}
                </p>
                {mod.price_monthly && Number(mod.price_monthly) > 0 ? (
                  <div style={{ display: 'flex', alignItems: 'baseline', gap: 4 }}>
                    <span style={{ fontFamily: "'Manrope', sans-serif", fontSize: '1.25rem', fontWeight: 700, color: '#191c1e' }}>
                      ${mod.price_monthly}
                    </span>
                    <span style={{ fontSize: '0.75rem', color: '#94a3b8' }}>/mo</span>
                  </div>
                ) : (
                  <span style={{ fontSize: '0.8rem', color: '#242a88', fontWeight: 600 }}>Learn more <ChevronRight size={14} style={{ verticalAlign: 'middle' }} /></span>
                )}
              </div>
            ))}
          </div>

          <div style={{ textAlign: 'center', marginTop: 48 }}>
            <button
              onClick={() => navigate('/pricing')}
              style={{
                padding: '14px 32px', borderRadius: 8, border: 'none', cursor: 'pointer',
                background: 'linear-gradient(135deg, #242a88, #2e35a0)', color: '#fff',
                fontWeight: 600, fontSize: '1rem', fontFamily: 'inherit',
                boxShadow: '0 4px 14px rgba(36,42,136,0.3)',
                display: 'inline-flex', alignItems: 'center', gap: 8,
              }}
            >
              View All Pricing <ArrowRight size={18} />
            </button>
          </div>
        </div>
      </section>

      {/* ── CTA Section ────────────────────────────────────── */}
      <section style={{
        padding: '100px 0',
        background: 'linear-gradient(135deg, #242a88 0%, #2e35a0 100%)',
        position: 'relative', overflow: 'hidden',
      }}>
        <div style={{
          position: 'absolute', top: -100, right: -50, width: 400, height: 400,
          borderRadius: '50%', background: 'rgba(255,255,255,0.04)',
        }} />
        <div style={{ maxWidth: 1200, margin: '0 auto', padding: '0 24px', position: 'relative' }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 64, alignItems: 'center' }}>
            <div>
              <h2 style={{
                fontFamily: "'Manrope', sans-serif", fontSize: 'clamp(1.5rem, 3vw, 2rem)',
                fontWeight: 700, color: '#ffffff', margin: '0 0 16px',
              }}>
                Ready to modernize your operations?
              </h2>
              <p style={{ fontSize: '1rem', color: 'rgba(255,255,255,0.8)', margin: '0 0 40px', lineHeight: 1.7 }}>
                Start with a free trial. No credit card required. Your dedicated ERP environment
                is provisioned instantly.
              </p>
              <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
                <button
                  onClick={() => navigate('/register')}
                  style={{
                    padding: '14px 32px', borderRadius: 8, border: 'none', cursor: 'pointer',
                    background: '#ffffff', color: '#242a88',
                    fontWeight: 600, fontSize: '1rem', fontFamily: 'inherit',
                    boxShadow: '0 4px 14px rgba(0,0,0,0.15)',
                    display: 'flex', alignItems: 'center', gap: 8,
                  }}
                >
                  Get Started Free <ArrowRight size={18} />
                </button>
                <button
                  onClick={() => navigate('/login')}
                  style={{
                    padding: '14px 32px', borderRadius: 8, border: '1.5px solid rgba(255,255,255,0.4)',
                    background: 'transparent', color: '#ffffff', cursor: 'pointer',
                    fontWeight: 600, fontSize: '1rem', fontFamily: 'inherit',
                  }}
                >
                  Sign In
                </button>
              </div>
            </div>
            <div>
              <img
                src="https://images.unsplash.com/photo-1553877522-43269d4ea984?w=560&h=400&fit=crop&q=80"
                alt="Team collaborating in modern office"
                style={{
                  width: '100%', borderRadius: 16,
                  boxShadow: '0 20px 60px rgba(0,0,0,0.3)',
                  objectFit: 'cover',
                }}
              />
            </div>
          </div>
        </div>
      </section>

      {/* ── Footer ─────────────────────────────────────────── */}
      <footer style={{ background: '#191c1e', padding: '64px 0 32px', color: 'rgba(255,255,255,0.6)' }}>
        <div style={{ maxWidth: 1200, margin: '0 auto', padding: '0 24px' }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 48, marginBottom: 48 }}>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
                <div style={{
                  width: 32, height: 32, borderRadius: 8,
                  background: 'linear-gradient(135deg, #242a88, #2e35a0)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                }}>
                  <Building2 size={16} color="#fff" />
                </div>
                <span style={{ fontFamily: "'Manrope', sans-serif", fontSize: '1rem', fontWeight: 700, color: '#fff' }}>
                  DTSG ERP
                </span>
              </div>
              <p style={{ fontSize: '0.8rem', lineHeight: 1.7 }}>
                Enterprise Resource Planning built for modern organizations.
              </p>
            </div>
            <div>
              <h4 style={{ color: '#fff', fontSize: '0.8rem', fontWeight: 600, marginBottom: 16, textTransform: 'uppercase', letterSpacing: '0.5px' }}>Product</h4>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                <a href="#features" style={{ color: 'inherit', textDecoration: 'none', fontSize: '0.8rem' }}>Features</a>
                <a href="#modules" style={{ color: 'inherit', textDecoration: 'none', fontSize: '0.8rem' }}>Modules</a>
                <a onClick={() => navigate('/pricing')} style={{ color: 'inherit', textDecoration: 'none', fontSize: '0.8rem', cursor: 'pointer' }}>Pricing</a>
              </div>
            </div>
            <div>
              <h4 style={{ color: '#fff', fontSize: '0.8rem', fontWeight: 600, marginBottom: 16, textTransform: 'uppercase', letterSpacing: '0.5px' }}>Company</h4>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                <span style={{ fontSize: '0.8rem' }}>About</span>
                <span style={{ fontSize: '0.8rem' }}>Contact</span>
                <span style={{ fontSize: '0.8rem' }}>Careers</span>
              </div>
            </div>
            <div>
              <h4 style={{ color: '#fff', fontSize: '0.8rem', fontWeight: 600, marginBottom: 16, textTransform: 'uppercase', letterSpacing: '0.5px' }}>Legal</h4>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                <span style={{ fontSize: '0.8rem' }}>Privacy Policy</span>
                <span style={{ fontSize: '0.8rem' }}>Terms of Service</span>
              </div>
            </div>
          </div>
          <div style={{ borderTop: '1px solid rgba(255,255,255,0.08)', paddingTop: 24, textAlign: 'center' }}>
            <p style={{ fontSize: '0.75rem' }}>&copy; {new Date().getFullYear()} DTSG ERP. All rights reserved.</p>
          </div>
        </div>
      </footer>
    </div>
  );
};

export default LandingPage;
