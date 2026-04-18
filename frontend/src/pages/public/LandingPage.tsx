import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useModulePricing } from '../../hooks/useModulePricing';
import {
    BarChart3, Shield, Zap, ArrowRight, Building2, Users,
    Package, FileText, Wallet, Layers, Landmark, Scale,
    Banknote, ClipboardCheck, ShieldCheck, FileBarChart2, MapPin,
    Receipt, Gavel, CheckCircle2, ChevronRight, BookOpen,
    Menu, X,
} from 'lucide-react';
import { useIsMobile } from '../../design';

// ─────────────────────────────────────────────────────────────────
// Nigerian Public-Sector ERP — landing page.
// Target audience: State Ministries of Finance, Offices of the
// Accountant-General, Local Government Councils, Parastatals, MDAs.
// Positioning anchored to regulatory alignment, not feature counts.
// ─────────────────────────────────────────────────────────────────

const NAVY = '#1a237e';
const NAVY_DARK = '#0f1759';
const NIGERIA_GREEN = '#008751';
const INK = '#0b1320';
const MUTED = '#4a5568';
const SURFACE = '#f6f8fb';

type Module = {
    module_name: string;
    title: string;
    tagline: string;
    is_popular: boolean;
    price_monthly?: string;
    description?: string;
};

const MODULE_ICONS: Record<string, React.ReactNode> = {
    budget: <Gavel size={26} />,
    accounting: <Wallet size={26} />,
    treasury: <Landmark size={26} />,
    procurement: <Package size={26} />,
    ncoa: <Layers size={26} />,
    ipsas: <FileBarChart2 size={26} />,
    statutory: <Receipt size={26} />,
    hrm: <Users size={26} />,
    inventory: <ClipboardCheck size={26} />,
    workflow: <FileText size={26} />,
};

/* Fallback modules when no pricing data exists in the DB yet.
 * Tailored to Nigerian public-sector IFMIS scope. */
const defaultModules: Module[] = [
    {
        module_name: 'budget',
        title: 'Budget & Appropriation',
        tagline: 'Appropriation Act, Supplementary, Virements, Warrants',
        is_popular: true,
    },
    {
        module_name: 'accounting',
        title: 'GL & Accounting (IPSAS)',
        tagline: 'Accrual GL, Journals, AP/AR, Fixed Assets, Period Close',
        is_popular: true,
    },
    {
        module_name: 'treasury',
        title: 'Treasury (TSA)',
        tagline: 'Cash position, FAAC allocations, Bank reconciliation',
        is_popular: false,
    },
    {
        module_name: 'ncoa',
        title: 'NCoA Classification',
        tagline: 'Administrative, Economic, Functional, Programme, Fund, Geo',
        is_popular: false,
    },
    {
        module_name: 'procurement',
        title: 'Procurement',
        tagline: 'PR → PO → GRN → Invoice · 3-way matching · Commitment accounting',
        is_popular: false,
    },
    {
        module_name: 'statutory',
        title: 'Statutory Reporting',
        tagline: 'FIRS WHT / VAT XML · PENCOM pension schedule · OAGF bulletin',
        is_popular: false,
    },
    {
        module_name: 'ipsas',
        title: 'IPSAS Financial Statements',
        tagline: 'SoFP, SoFPerf, Cash Flow, Budget-vs-Actual, Notes',
        is_popular: true,
    },
    {
        module_name: 'hrm',
        title: 'HR & Nigerian Payroll',
        tagline: 'PAYE, Pension (8%/10%), NHF, leave, career history',
        is_popular: false,
    },
    {
        module_name: 'inventory',
        title: 'Government Stores',
        tagline: 'Store ledger, requisitions, batch tracking per MDA',
        is_popular: false,
    },
    {
        module_name: 'workflow',
        title: 'Approval Workflow',
        tagline: 'Multi-level SOD · Dual-control overrides · Audit-ready trail',
        is_popular: false,
    },
];

const LandingPage = () => {
    const navigate = useNavigate();
    const isMobile = useIsMobile();
    const [mobileNavOpen, setMobileNavOpen] = useState(false);
    const { data: rawModules = [] } = useModulePricing();
    const modulesFromDb = Array.isArray(rawModules) ? (rawModules as Module[]) : [];
    const modules: Module[] = modulesFromDb.length > 0 ? modulesFromDb : defaultModules;

    const goTo = (path: string) => { setMobileNavOpen(false); navigate(path); };
    const scrollTo = (sel: string) => {
        setMobileNavOpen(false);
        setTimeout(() => document.querySelector(sel)?.scrollIntoView({ behavior: 'smooth' }), 80);
    };

    return (
        <div style={{ fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, sans-serif", color: INK, background: SURFACE }}>
            {/* ── Glassmorphic Navigation ──────────────────────── */}
            <nav style={{
                position: 'fixed', top: 0, left: 0, right: 0, zIndex: 100,
                background: 'rgba(255,255,255,0.9)', backdropFilter: 'blur(18px)', WebkitBackdropFilter: 'blur(18px)',
                padding: '14px 0',
                boxShadow: '0 1px 0 rgba(15,23,89,0.08)',
            }}>
                <div style={{ maxWidth: 1240, margin: '0 auto', padding: '0 28px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 12, cursor: 'pointer' }} onClick={() => navigate('/')}>
                        <div style={{
                            width: 40, height: 40, borderRadius: 10,
                            background: `linear-gradient(135deg, ${NAVY}, ${NAVY_DARK})`,
                            display: 'flex', alignItems: 'center', justifyContent: 'center',
                            boxShadow: `0 2px 8px ${NAVY}33`,
                        }}>
                            <Building2 size={22} color="#fff" />
                        </div>
                        <div style={{ lineHeight: 1 }}>
                            <div style={{ fontFamily: "'Manrope', sans-serif", fontSize: '1.25rem', fontWeight: 800, color: INK }}>
                                Quot PSE
                            </div>
                            <div style={{ fontSize: '0.65rem', color: NIGERIA_GREEN, fontWeight: 700, letterSpacing: '0.6px', textTransform: 'uppercase', marginTop: 2 }}>
                                Nigeria Public-Sector IFMIS
                            </div>
                        </div>
                    </div>
                    {/* Desktop nav */}
                    <div style={{ display: isMobile ? 'none' : 'flex', alignItems: 'center', gap: 32 }}>
                        <a href="#compliance" style={{ color: MUTED, textDecoration: 'none', fontSize: '0.875rem', fontWeight: 500 }}>Compliance</a>
                        <a href="#modules" style={{ color: MUTED, textDecoration: 'none', fontSize: '0.875rem', fontWeight: 500 }}>Modules</a>
                        <a href="#who" style={{ color: MUTED, textDecoration: 'none', fontSize: '0.875rem', fontWeight: 500 }}>Who it's for</a>
                        <button
                            onClick={() => navigate('/pricing')}
                            style={{
                                background: 'none', border: 'none', color: MUTED, fontSize: '0.875rem',
                                fontWeight: 500, cursor: 'pointer', fontFamily: 'inherit',
                            }}
                        >
                            Pricing
                        </button>
                        <button
                            onClick={() => navigate('/login')}
                            style={{
                                padding: '10px 22px', borderRadius: 8, border: 'none', cursor: 'pointer',
                                background: `linear-gradient(135deg, ${NAVY}, ${NAVY_DARK})`, color: '#fff',
                                fontWeight: 600, fontSize: '0.875rem', fontFamily: 'inherit',
                                boxShadow: `0 2px 8px ${NAVY}33`,
                            }}
                        >
                            Sign In
                        </button>
                    </div>

                    {/* Mobile hamburger */}
                    {isMobile && (
                        <button
                            onClick={() => setMobileNavOpen(v => !v)}
                            aria-label={mobileNavOpen ? 'Close menu' : 'Open menu'}
                            style={{
                                background: 'transparent', border: 'none', cursor: 'pointer',
                                width: 44, height: 44, borderRadius: 8, color: NAVY,
                                display: 'flex', alignItems: 'center', justifyContent: 'center',
                            }}
                        >
                            {mobileNavOpen ? <X size={22} /> : <Menu size={22} />}
                        </button>
                    )}
                </div>

                {/* Mobile dropdown panel */}
                {isMobile && mobileNavOpen && (
                    <div style={{
                        background: '#fff', borderTop: `1px solid ${NAVY}14`,
                        padding: '12px 28px 20px',
                        display: 'flex', flexDirection: 'column', gap: 4,
                    }}>
                        {[
                            { label: 'Compliance', action: () => scrollTo('#compliance') },
                            { label: 'Modules', action: () => scrollTo('#modules') },
                            { label: "Who it's for", action: () => scrollTo('#who') },
                            { label: 'Pricing', action: () => goTo('/pricing') },
                        ].map(item => (
                            <button
                                key={item.label}
                                onClick={item.action}
                                style={{
                                    textAlign: 'left', background: 'transparent', border: 'none',
                                    color: INK, fontSize: 15, fontWeight: 500, fontFamily: 'inherit',
                                    padding: '12px 4px', cursor: 'pointer',
                                    borderBottom: `1px solid ${NAVY}10`,
                                }}
                            >
                                {item.label}
                            </button>
                        ))}
                        <button
                            onClick={() => goTo('/login')}
                            style={{
                                marginTop: 12, padding: '14px 22px', borderRadius: 8, border: 'none',
                                background: `linear-gradient(135deg, ${NAVY}, ${NAVY_DARK})`, color: '#fff',
                                fontWeight: 700, fontSize: 15, cursor: 'pointer', fontFamily: 'inherit',
                                boxShadow: `0 2px 8px ${NAVY}33`,
                            }}
                        >
                            Sign In
                        </button>
                    </div>
                )}
            </nav>

            {/* ── Hero Section ─────────────────────────────────── */}
            <section style={{
                paddingTop: 160, paddingBottom: 110,
                background: 'linear-gradient(180deg, #ffffff 0%, #f6f8fb 100%)',
                position: 'relative', overflow: 'hidden',
            }}>
                {/* Decorative gradient orbs */}
                <div style={{
                    position: 'absolute', top: -120, right: -120, width: 540, height: 540,
                    borderRadius: '50%', background: `radial-gradient(circle, ${NAVY}10 0%, transparent 70%)`,
                }} />
                <div style={{
                    position: 'absolute', bottom: -80, left: -100, width: 420, height: 420,
                    borderRadius: '50%', background: `radial-gradient(circle, ${NIGERIA_GREEN}0f 0%, transparent 70%)`,
                }} />

                <div style={{ maxWidth: 1240, margin: '0 auto', padding: '0 28px', position: 'relative' }}>
                    <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1.1fr 1fr', gap: isMobile ? 36 : 64, alignItems: 'center' }}>
                        <div>
                            <div style={{
                                display: 'inline-flex', alignItems: 'center', gap: 10, padding: '7px 16px',
                                borderRadius: 100, background: `${NIGERIA_GREEN}10`, marginBottom: 28,
                                border: `1px solid ${NIGERIA_GREEN}33`,
                            }}>
                                <span style={{ width: 8, height: 8, borderRadius: '50%', background: NIGERIA_GREEN, boxShadow: `0 0 0 3px ${NIGERIA_GREEN}22` }} />
                                <span style={{ fontSize: '0.75rem', fontWeight: 700, color: NIGERIA_GREEN, letterSpacing: '0.4px', textTransform: 'uppercase' }}>
                                    Built for Nigerian State &amp; Local Government
                                </span>
                            </div>

                            <h1 style={{
                                fontFamily: "'Manrope', sans-serif", fontSize: 'clamp(2.6rem, 5vw, 3.8rem)',
                                fontWeight: 800, lineHeight: 1.05, color: INK, margin: '0 0 24px',
                                letterSpacing: '-0.035em',
                            }}>
                                The modern IFMIS for
                                <br />
                                <span style={{
                                    background: `linear-gradient(90deg, ${NAVY} 0%, ${NIGERIA_GREEN} 100%)`,
                                    WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent',
                                    backgroundClip: 'text',
                                }}>
                                    States, LGAs &amp; Parastatals
                                </span>
                            </h1>

                            <p style={{
                                fontSize: '1.15rem', lineHeight: 1.7, color: MUTED, maxWidth: 620,
                                margin: '0 0 36px',
                            }}>
                                Run your State's entire fiscal cycle &mdash; Appropriation Act to audited
                                IPSAS statements &mdash; on a single platform that speaks <strong style={{ color: INK }}>NCoA</strong>,
                                <strong style={{ color: INK }}> TSA</strong>, <strong style={{ color: INK }}>FAAC</strong>,
                                <strong style={{ color: INK }}> FIRS</strong> and <strong style={{ color: INK }}>PENCOM</strong> natively.
                            </p>

                            <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', marginBottom: 40 }}>
                                <button
                                    onClick={() => navigate('/register')}
                                    style={{
                                        padding: '14px 30px', borderRadius: 8, border: 'none', cursor: 'pointer',
                                        background: `linear-gradient(135deg, ${NAVY}, ${NAVY_DARK})`, color: '#fff',
                                        fontWeight: 600, fontSize: '1rem', fontFamily: 'inherit',
                                        boxShadow: `0 6px 16px ${NAVY}3d`,
                                        display: 'flex', alignItems: 'center', gap: 8,
                                    }}
                                >
                                    Request a Demo <ArrowRight size={18} />
                                </button>
                                <button
                                    onClick={() => navigate('/pricing')}
                                    style={{
                                        padding: '14px 30px', borderRadius: 8, border: `1.5px solid ${NAVY}`,
                                        background: 'transparent', color: NAVY, cursor: 'pointer',
                                        fontWeight: 600, fontSize: '1rem', fontFamily: 'inherit',
                                    }}
                                >
                                    View Modules &amp; Pricing
                                </button>
                            </div>

                            {/* Stat strip */}
                            <div style={{
                                display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 24,
                                paddingTop: 28, borderTop: '1px solid rgba(15,23,89,0.08)',
                            }}>
                                {[
                                    { v: '5', l: 'IPSAS Financial Statements' },
                                    { v: '6', l: 'NCoA Classification Segments' },
                                    { v: '3-way', l: 'Procurement Matching' },
                                ].map((s, i) => (
                                    <div key={i}>
                                        <div style={{ fontFamily: "'Manrope', sans-serif", fontSize: '1.6rem', fontWeight: 800, color: INK, letterSpacing: '-0.02em' }}>
                                            {s.v}
                                        </div>
                                        <div style={{ fontSize: '0.75rem', color: MUTED, fontWeight: 500, marginTop: 2 }}>
                                            {s.l}
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>

                        {/* Hero visual — product preview mock */}
                        <div style={{ position: 'relative' }}>
                            <div style={{
                                background: '#fff', borderRadius: 16, padding: 18,
                                boxShadow: `0 24px 60px ${NAVY}22`,
                                border: `1px solid ${NAVY}10`,
                            }}>
                                <div style={{ display: 'flex', gap: 6, marginBottom: 14 }}>
                                    <span style={{ width: 10, height: 10, borderRadius: '50%', background: '#ff5f57' }} />
                                    <span style={{ width: 10, height: 10, borderRadius: '50%', background: '#ffbd2e' }} />
                                    <span style={{ width: 10, height: 10, borderRadius: '50%', background: '#28ca41' }} />
                                    <span style={{ marginLeft: 14, fontSize: '0.7rem', color: MUTED, fontFamily: "'JetBrains Mono', monospace" }}>
                                        accountant-general.delta.gov.ng/dashboard
                                    </span>
                                </div>

                                {/* Preview cards */}
                                <div style={{ padding: 16, background: SURFACE, borderRadius: 10 }}>
                                    <div style={{ fontSize: '0.7rem', color: MUTED, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.6px', marginBottom: 10 }}>
                                        Government Financial Dashboard
                                    </div>
                                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 14 }}>
                                        {[
                                            { label: 'TSA Cash Position', value: '₦17.84B', tone: NAVY },
                                            { label: 'YTD Revenue', value: '₦212.8M', tone: NIGERIA_GREEN },
                                        ].map((c, i) => (
                                            <div key={i} style={{
                                                background: '#fff', padding: 12, borderRadius: 8,
                                                borderLeft: `3px solid ${c.tone}`,
                                            }}>
                                                <div style={{ fontSize: '0.65rem', color: MUTED, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                                                    {c.label}
                                                </div>
                                                <div style={{ fontSize: '1.15rem', fontWeight: 700, color: INK, marginTop: 2 }}>
                                                    {c.value}
                                                </div>
                                            </div>
                                        ))}
                                    </div>

                                    {/* Budget bars */}
                                    <div style={{ background: '#fff', padding: 12, borderRadius: 8 }}>
                                        <div style={{ fontSize: '0.7rem', color: INK, fontWeight: 600, marginBottom: 8 }}>
                                            Budget Execution by MDA
                                        </div>
                                        {[
                                            { mda: 'Min. of Education', pct: 68, tone: NIGERIA_GREEN },
                                            { mda: 'Min. of Health', pct: 54, tone: NAVY },
                                            { mda: 'Min. of Works', pct: 43, tone: '#c47f17' },
                                            { mda: 'Min. of Agric', pct: 31, tone: MUTED },
                                        ].map((b, i) => (
                                            <div key={i} style={{ marginBottom: i === 3 ? 0 : 8 }}>
                                                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.7rem', color: MUTED, marginBottom: 3 }}>
                                                    <span>{b.mda}</span>
                                                    <span style={{ fontWeight: 600, color: INK }}>{b.pct}%</span>
                                                </div>
                                                <div style={{ height: 5, background: '#eef1f6', borderRadius: 3, overflow: 'hidden' }}>
                                                    <div style={{ height: '100%', width: `${b.pct}%`, background: b.tone, borderRadius: 3 }} />
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            </div>

                            {/* Floating compliance badge */}
                            <div style={{
                                position: 'absolute', bottom: -20, right: -20, background: '#ffffff',
                                borderRadius: 12, padding: '12px 16px',
                                boxShadow: '0 10px 30px rgba(15,23,89,0.15)',
                                display: 'flex', alignItems: 'center', gap: 10,
                                border: `1px solid ${NIGERIA_GREEN}22`,
                            }}>
                                <div style={{
                                    width: 36, height: 36, borderRadius: 8,
                                    background: `${NIGERIA_GREEN}14`, color: NIGERIA_GREEN,
                                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                                }}>
                                    <ShieldCheck size={18} />
                                </div>
                                <div>
                                    <div style={{ fontSize: '0.65rem', color: MUTED, fontWeight: 500 }}>IPSAS Accrual</div>
                                    <div style={{ fontSize: '0.85rem', fontWeight: 700, color: INK }}>Audit-Ready</div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </section>

            {/* ── Compliance Bar ────────────────────────────────── */}
            <section id="compliance" style={{ background: '#ffffff', padding: '44px 0', borderTop: `1px solid ${NAVY}0f`, borderBottom: `1px solid ${NAVY}0f` }}>
                <div style={{ maxWidth: 1240, margin: '0 auto', padding: '0 28px' }}>
                    <div style={{ textAlign: 'center', marginBottom: 28 }}>
                        <span style={{ fontSize: '0.7rem', fontWeight: 700, color: MUTED, letterSpacing: '1.5px', textTransform: 'uppercase' }}>
                            Regulatory alignment — out of the box
                        </span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'center', gap: 40, flexWrap: 'wrap', alignItems: 'center' }}>
                        {[
                            { label: 'IPSAS Accrual', sub: 'IFRS-aligned public sector', icon: <Scale size={18} /> },
                            { label: 'NCoA 6-Segment', sub: 'Federal Chart of Accounts', icon: <Layers size={18} /> },
                            { label: 'TSA Compliant', sub: 'Treasury Single Account', icon: <Landmark size={18} /> },
                            { label: 'FAAC Ready', sub: 'Statutory / VAT / Derivation', icon: <Banknote size={18} /> },
                            { label: 'FIRS XML', sub: 'WHT & VAT schedules', icon: <Receipt size={18} /> },
                            { label: 'PENCOM XML', sub: 'Pension remittance', icon: <ShieldCheck size={18} /> },
                        ].map((item, i) => (
                            <div key={i} style={{
                                display: 'flex', alignItems: 'center', gap: 10, padding: '10px 16px',
                                borderRadius: 10, background: SURFACE,
                                border: `1px solid ${NAVY}0f`,
                            }}>
                                <div style={{ color: NAVY, display: 'flex' }}>{item.icon}</div>
                                <div>
                                    <div style={{ fontSize: '0.85rem', fontWeight: 700, color: INK, lineHeight: 1.15 }}>{item.label}</div>
                                    <div style={{ fontSize: '0.7rem', color: MUTED, marginTop: 1 }}>{item.sub}</div>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            </section>

            {/* ── Public-Sector Feature Grid ────────────────────── */}
            <section style={{ padding: '96px 0', background: SURFACE }}>
                <div style={{ maxWidth: 1240, margin: '0 auto', padding: '0 28px' }}>
                    <div style={{ textAlign: 'center', marginBottom: 64, maxWidth: 760, marginLeft: 'auto', marginRight: 'auto' }}>
                        <div style={{
                            display: 'inline-block', padding: '5px 14px', borderRadius: 100,
                            background: `${NAVY}10`, color: NAVY,
                            fontSize: '0.7rem', fontWeight: 700, letterSpacing: '0.5px', textTransform: 'uppercase',
                            marginBottom: 16,
                        }}>
                            Purpose-built for Nigeria
                        </div>
                        <h2 style={{
                            fontFamily: "'Manrope', sans-serif", fontSize: 'clamp(1.75rem, 3vw, 2.3rem)', fontWeight: 700,
                            color: INK, margin: '0 0 18px', letterSpacing: '-0.02em',
                        }}>
                            Every feature the OAGF checklist asks for
                        </h2>
                        <p style={{ fontSize: '1rem', color: MUTED, margin: 0, lineHeight: 1.6 }}>
                            Not a generic ERP with a government skin &mdash; every module was designed
                            from first principles around the 1999 Constitution, the PFM Act, IPSAS,
                            and the Federal Treasury Circulars.
                        </p>
                    </div>

                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 20 }}>
                        {[
                            {
                                icon: <Gavel size={22} />,
                                title: 'Appropriation Act enforcement',
                                desc: 'Original, Supplementary, Virement workflows route through the State House of Assembly with full law-reference tracking and a hard ceiling on over-commitment.',
                                tone: NIGERIA_GREEN,
                            },
                            {
                                icon: <Layers size={22} />,
                                title: 'NCoA six-segment coding',
                                desc: 'Administrative · Economic · Functional · Programme · Fund · Geographic. Every journal line is coded to the full 52-digit NCoA composite.',
                                tone: NAVY,
                            },
                            {
                                icon: <Landmark size={22} />,
                                title: 'TSA & sub-account discipline',
                                desc: 'Main TSA, Revenue, Holding, and Sub-accounts tracked in real time. FAAC statutory, VAT and derivation inflows tagged at receipt.',
                                tone: NIGERIA_GREEN,
                            },
                            {
                                icon: <FileBarChart2 size={22} />,
                                title: 'IPSAS monthly management pack',
                                desc: 'Statement of Financial Position, Performance, Cash Flow, Changes in Net Assets, and Notes — generated live from the GL with prior-year comparatives.',
                                tone: NAVY,
                            },
                            {
                                icon: <ClipboardCheck size={22} />,
                                title: '3-way matching procurement',
                                desc: 'PR → PO → GRN → Invoice with commitment accounting. POs reduce the Appropriation ceiling instantly; verified invoices release the commitment to actual expenditure.',
                                tone: NIGERIA_GREEN,
                            },
                            {
                                icon: <Receipt size={22} />,
                                title: 'FIRS & PENCOM native exports',
                                desc: 'Monthly WHT and VAT returns, and PENCOM pension schedules generated as XSD-validated XML ready for portal upload — no spreadsheet gymnastics.',
                                tone: NAVY,
                            },
                            {
                                icon: <Users size={22} />,
                                title: 'Nigerian payroll out of the box',
                                desc: 'PAYE (progressive bands), Pension 8%/10%, NHF, NSITF, ITF deductions computed per statute. Social benefit batch pay for pensioners and widows.',
                                tone: NIGERIA_GREEN,
                            },
                            {
                                icon: <ShieldCheck size={22} />,
                                title: 'Segregation of Duties + Dual Control',
                                desc: 'Initiator ≠ approver is enforced at the database level. Dual-control overrides require two Accountant-General signatures and write to an immutable audit log.',
                                tone: NAVY,
                            },
                            {
                                icon: <BookOpen size={22} />,
                                title: 'Full audit trail & Data Quality',
                                desc: 'Every posting, override and setting change is append-only logged. Data Quality dashboard flags missing NCoA codes, unbalanced journals, and closed-period breaches.',
                                tone: NIGERIA_GREEN,
                            },
                        ].map((feature, i) => (
                            <div key={i} style={{
                                background: '#ffffff', borderRadius: 14, padding: 28,
                                border: `1px solid ${NAVY}0a`,
                                transition: 'all 200ms ease',
                            }}
                                onMouseEnter={e => {
                                    e.currentTarget.style.boxShadow = `0 12px 32px ${NAVY}18`;
                                    e.currentTarget.style.transform = 'translateY(-2px)';
                                }}
                                onMouseLeave={e => {
                                    e.currentTarget.style.boxShadow = 'none';
                                    e.currentTarget.style.transform = 'translateY(0)';
                                }}>
                                <div style={{
                                    width: 44, height: 44, borderRadius: 10,
                                    background: `${feature.tone}14`, color: feature.tone,
                                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                                    marginBottom: 18,
                                }}>
                                    {feature.icon}
                                </div>
                                <h3 style={{ fontFamily: "'Manrope', sans-serif", fontSize: '1.05rem', fontWeight: 700, margin: '0 0 10px', color: INK }}>
                                    {feature.title}
                                </h3>
                                <p style={{ fontSize: '0.88rem', lineHeight: 1.65, color: MUTED, margin: 0 }}>
                                    {feature.desc}
                                </p>
                            </div>
                        ))}
                    </div>
                </div>
            </section>

            {/* ── Who It's For ──────────────────────────────────── */}
            <section id="who" style={{ padding: '96px 0', background: '#ffffff' }}>
                <div style={{ maxWidth: 1240, margin: '0 auto', padding: '0 28px' }}>
                    <div style={{ textAlign: 'center', marginBottom: 64, maxWidth: 720, marginLeft: 'auto', marginRight: 'auto' }}>
                        <h2 style={{
                            fontFamily: "'Manrope', sans-serif", fontSize: 'clamp(1.75rem, 3vw, 2.3rem)', fontWeight: 700,
                            color: INK, margin: '0 0 18px', letterSpacing: '-0.02em',
                        }}>
                            Who runs on Quot PSE
                        </h2>
                        <p style={{ fontSize: '1rem', color: MUTED, margin: 0, lineHeight: 1.6 }}>
                            Every tier of public-sector finance &mdash; from the Governor's Office
                            of the Accountant-General down to a Local Government Chairman &mdash; gets
                            the same battle-tested controls and IPSAS-compliant books.
                        </p>
                    </div>

                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 24 }}>
                        {[
                            {
                                icon: <Building2 size={28} />,
                                title: 'State Ministries of Finance',
                                desc: 'Commissioners and their teams running the annual budget cycle, cash plans, and revenue profiles across all MDAs.',
                                bullets: ['Budget cycle management', 'Revenue profile tracking', 'MDA oversight'],
                            },
                            {
                                icon: <Landmark size={28} />,
                                title: 'Offices of the Accountant-General',
                                desc: 'The apex stewards of State finances — closing periods, signing statements, and filing statutory returns.',
                                bullets: ['Period close & sign-off', 'IPSAS filing', 'Override audit'],
                            },
                            {
                                icon: <MapPin size={28} />,
                                title: 'Local Government Councils',
                                desc: 'All 774 Councils can plug in with their own NCoA segment, warrant limits, and LG-specific reporting packs.',
                                bullets: ['Council-scoped books', 'LG-funded projects', 'IGR tracking'],
                            },
                            {
                                icon: <Package size={28} />,
                                title: 'Parastatals & Agencies',
                                desc: 'SOEs, tertiary institutions, hospitals, and boards operate as independent tenants consolidating up to the State.',
                                bullets: ['Independent tenant schema', 'Sub-vention workflow', 'Consolidation ready'],
                            },
                        ].map((persona, i) => (
                            <div key={i} style={{
                                background: SURFACE, borderRadius: 14, padding: 28,
                                border: `1px solid ${NAVY}0a`,
                            }}>
                                <div style={{
                                    width: 56, height: 56, borderRadius: 14,
                                    background: `linear-gradient(135deg, ${NAVY}, ${NAVY_DARK})`,
                                    color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center',
                                    marginBottom: 20, boxShadow: `0 6px 16px ${NAVY}33`,
                                }}>
                                    {persona.icon}
                                </div>
                                <h3 style={{ fontFamily: "'Manrope', sans-serif", fontSize: '1.1rem', fontWeight: 700, margin: '0 0 12px', color: INK }}>
                                    {persona.title}
                                </h3>
                                <p style={{ fontSize: '0.88rem', lineHeight: 1.65, color: MUTED, margin: '0 0 18px' }}>
                                    {persona.desc}
                                </p>
                                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                                    {persona.bullets.map((b, j) => (
                                        <div key={j} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                            <CheckCircle2 size={14} color={NIGERIA_GREEN} />
                                            <span style={{ fontSize: '0.82rem', color: INK, fontWeight: 500 }}>{b}</span>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            </section>

            {/* ── Modules Showcase ─────────────────────────────── */}
            <section id="modules" style={{ padding: '96px 0', background: SURFACE }}>
                <div style={{ maxWidth: 1240, margin: '0 auto', padding: '0 28px' }}>
                    <div style={{ textAlign: 'center', marginBottom: 64 }}>
                        <h2 style={{
                            fontFamily: "'Manrope', sans-serif", fontSize: 'clamp(1.75rem, 3vw, 2.3rem)', fontWeight: 700,
                            color: INK, margin: '0 0 18px', letterSpacing: '-0.02em',
                        }}>
                            {modulesFromDb.length > 0 ? `${modulesFromDb.length} modules, one fiscal backbone` : 'Ten public-sector modules, one fiscal backbone'}
                        </h2>
                        <p style={{ fontSize: '1rem', color: MUTED, maxWidth: 640, margin: '0 auto', lineHeight: 1.6 }}>
                            Each module stands alone &mdash; but they share one General Ledger, one
                            NCoA, and one audit trail. Switch on what you need; the rest sleeps until
                            you're ready.
                        </p>
                    </div>

                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 20 }}>
                        {modules.map((mod, i) => (
                            <div
                                key={mod.module_name || i}
                                onClick={() => navigate(`/pricing/${mod.module_name}`)}
                                style={{
                                    background: '#fff', borderRadius: 14, padding: 26,
                                    cursor: 'pointer', transition: 'all 200ms ease',
                                    position: 'relative',
                                    border: `1px solid ${NAVY}0c`,
                                }}
                                onMouseEnter={(e) => {
                                    e.currentTarget.style.boxShadow = `0 12px 32px ${NAVY}20`;
                                    e.currentTarget.style.transform = 'translateY(-3px)';
                                    e.currentTarget.style.borderColor = `${NAVY}22`;
                                }}
                                onMouseLeave={(e) => {
                                    e.currentTarget.style.boxShadow = 'none';
                                    e.currentTarget.style.transform = 'translateY(0)';
                                    e.currentTarget.style.borderColor = `${NAVY}0c`;
                                }}
                            >
                                {mod.is_popular && (
                                    <div style={{
                                        position: 'absolute', top: 14, right: 14, padding: '3px 10px',
                                        borderRadius: 100, background: `${NIGERIA_GREEN}14`, color: NIGERIA_GREEN,
                                        fontSize: '0.62rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.6px',
                                    }}>
                                        Core
                                    </div>
                                )}
                                <div style={{
                                    width: 48, height: 48, borderRadius: 11,
                                    background: `${NAVY}10`, color: NAVY,
                                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                                    marginBottom: 16,
                                }}>
                                    {MODULE_ICONS[mod.module_name] || <Package size={26} />}
                                </div>
                                <h3 style={{ fontFamily: "'Manrope', sans-serif", fontSize: '1rem', fontWeight: 700, margin: '0 0 8px', color: INK }}>
                                    {mod.title}
                                </h3>
                                <p style={{ fontSize: '0.8rem', lineHeight: 1.55, color: MUTED, margin: '0 0 18px', minHeight: 40 }}>
                                    {mod.tagline || mod.description?.slice(0, 80)}
                                </p>
                                {mod.price_monthly && Number(mod.price_monthly) > 0 ? (
                                    <div style={{ display: 'flex', alignItems: 'baseline', gap: 4 }}>
                                        <span style={{ fontFamily: "'Manrope', sans-serif", fontSize: '1.25rem', fontWeight: 700, color: INK }}>
                                            ₦{Number(mod.price_monthly).toLocaleString()}
                                        </span>
                                        <span style={{ fontSize: '0.75rem', color: MUTED }}>/mo</span>
                                    </div>
                                ) : (
                                    <span style={{ fontSize: '0.8rem', color: NAVY, fontWeight: 600 }}>
                                        Learn more <ChevronRight size={14} style={{ verticalAlign: 'middle' }} />
                                    </span>
                                )}
                            </div>
                        ))}
                    </div>

                    <div style={{ textAlign: 'center', marginTop: 48 }}>
                        <button
                            onClick={() => navigate('/pricing')}
                            style={{
                                padding: '14px 32px', borderRadius: 8, border: 'none', cursor: 'pointer',
                                background: `linear-gradient(135deg, ${NAVY}, ${NAVY_DARK})`, color: '#fff',
                                fontWeight: 600, fontSize: '1rem', fontFamily: 'inherit',
                                boxShadow: `0 6px 16px ${NAVY}3d`,
                                display: 'inline-flex', alignItems: 'center', gap: 8,
                            }}
                        >
                            View Full Module Catalogue <ArrowRight size={18} />
                        </button>
                    </div>
                </div>
            </section>

            {/* ── Outcomes / Stats Band ─────────────────────────── */}
            <section style={{ padding: '80px 0', background: '#ffffff' }}>
                <div style={{ maxWidth: 1240, margin: '0 auto', padding: '0 28px' }}>
                    <div style={{
                        display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
                        gap: 0, padding: '40px 28px',
                        background: `linear-gradient(135deg, ${SURFACE} 0%, #eef1f6 100%)`,
                        borderRadius: 16, border: `1px solid ${NAVY}0a`,
                    }}>
                        {[
                            { value: '774', label: 'LGAs addressable', icon: <MapPin size={22} /> },
                            { value: '36+1', label: 'States + FCT supported', icon: <Shield size={22} /> },
                            { value: '9', label: 'IPSAS reports shipped', icon: <FileBarChart2 size={22} /> },
                            { value: 'Zero', label: 'Excel VLOOKUPs required', icon: <Zap size={22} /> },
                        ].map((s, i) => (
                            <div key={i} style={{
                                padding: '20px 24px',
                                borderLeft: i === 0 ? 'none' : `1px solid ${NAVY}14`,
                                textAlign: 'center',
                            }}>
                                <div style={{ color: NIGERIA_GREEN, display: 'inline-flex', marginBottom: 10 }}>
                                    {s.icon}
                                </div>
                                <div style={{ fontFamily: "'Manrope', sans-serif", fontSize: '2rem', fontWeight: 800, color: INK, letterSpacing: '-0.02em', lineHeight: 1 }}>
                                    {s.value}
                                </div>
                                <div style={{ fontSize: '0.8rem', color: MUTED, fontWeight: 500, marginTop: 8 }}>
                                    {s.label}
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            </section>

            {/* ── Final CTA ─────────────────────────────────────── */}
            <section style={{
                padding: '100px 0',
                background: `linear-gradient(135deg, ${NAVY} 0%, ${NAVY_DARK} 55%, #0a1240 100%)`,
                position: 'relative', overflow: 'hidden',
            }}>
                <div style={{
                    position: 'absolute', top: -120, right: -60, width: 440, height: 440,
                    borderRadius: '50%', background: 'rgba(255,255,255,0.04)',
                }} />
                <div style={{
                    position: 'absolute', bottom: -100, left: -50, width: 360, height: 360,
                    borderRadius: '50%', background: `${NIGERIA_GREEN}18`,
                }} />
                <div style={{ maxWidth: 1240, margin: '0 auto', padding: '0 28px', position: 'relative' }}>
                    <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : '1.1fr 1fr', gap: isMobile ? 36 : 64, alignItems: 'center' }}>
                        <div>
                            <div style={{
                                display: 'inline-flex', alignItems: 'center', gap: 8, padding: '5px 14px',
                                borderRadius: 100, background: 'rgba(255,255,255,0.12)', marginBottom: 20,
                            }}>
                                <span style={{ width: 6, height: 6, borderRadius: '50%', background: NIGERIA_GREEN }} />
                                <span style={{ fontSize: '0.7rem', fontWeight: 700, color: '#fff', letterSpacing: '0.6px', textTransform: 'uppercase' }}>
                                    Onboard in days, not quarters
                                </span>
                            </div>
                            <h2 style={{
                                fontFamily: "'Manrope', sans-serif", fontSize: 'clamp(1.8rem, 3.4vw, 2.4rem)',
                                fontWeight: 800, color: '#ffffff', margin: '0 0 18px',
                                letterSpacing: '-0.02em', lineHeight: 1.15,
                            }}>
                                Bring your State's books into the IPSAS era
                            </h2>
                            <p style={{ fontSize: '1rem', color: 'rgba(255,255,255,0.82)', margin: '0 0 36px', lineHeight: 1.7 }}>
                                We'll stand up your tenant, migrate your NCoA, seed opening balances
                                and train your team. Your Accountant-General posts the first journal
                                on day one.
                            </p>
                            <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap' }}>
                                <button
                                    onClick={() => navigate('/register')}
                                    style={{
                                        padding: '14px 30px', borderRadius: 8, border: 'none', cursor: 'pointer',
                                        background: '#ffffff', color: NAVY,
                                        fontWeight: 700, fontSize: '1rem', fontFamily: 'inherit',
                                        boxShadow: '0 6px 16px rgba(0,0,0,0.2)',
                                        display: 'flex', alignItems: 'center', gap: 8,
                                    }}
                                >
                                    Book an Executive Demo <ArrowRight size={18} />
                                </button>
                                <button
                                    onClick={() => navigate('/login')}
                                    style={{
                                        padding: '14px 30px', borderRadius: 8,
                                        border: '1.5px solid rgba(255,255,255,0.45)',
                                        background: 'transparent', color: '#ffffff', cursor: 'pointer',
                                        fontWeight: 600, fontSize: '1rem', fontFamily: 'inherit',
                                    }}
                                >
                                    Sign in
                                </button>
                            </div>
                        </div>
                        <div style={{
                            background: 'rgba(255,255,255,0.06)', borderRadius: 16, padding: 28,
                            border: '1px solid rgba(255,255,255,0.1)',
                            backdropFilter: 'blur(10px)', WebkitBackdropFilter: 'blur(10px)',
                        }}>
                            <div style={{ fontSize: '0.75rem', color: 'rgba(255,255,255,0.65)', fontWeight: 700, letterSpacing: '0.8px', textTransform: 'uppercase', marginBottom: 16 }}>
                                Onboarding in 4 steps
                            </div>
                            {[
                                { step: '01', title: 'Tenant provisioning', body: 'Dedicated schema, domain and Accountant-General user live in under an hour.' },
                                { step: '02', title: 'NCoA & opening balances', body: 'Your State\'s NCoA segments seeded; audited opening balances migrated.' },
                                { step: '03', title: 'Workflow & SOD setup', body: 'Approval levels mapped to your Civil Service grades with dual-control rules.' },
                                { step: '04', title: 'Go-live training', body: 'Budget, Accounting, Procurement teams trained; first IPSAS pack filed in-app.' },
                            ].map((s, i) => (
                                <div key={i} style={{
                                    display: 'flex', alignItems: 'flex-start', gap: 14,
                                    padding: '14px 0',
                                    borderTop: i === 0 ? 'none' : '1px solid rgba(255,255,255,0.08)',
                                }}>
                                    <div style={{
                                        fontFamily: "'Manrope', sans-serif", fontSize: '0.95rem', fontWeight: 800,
                                        color: NIGERIA_GREEN, minWidth: 32,
                                    }}>
                                        {s.step}
                                    </div>
                                    <div>
                                        <div style={{ fontSize: '0.9rem', fontWeight: 600, color: '#fff', marginBottom: 2 }}>
                                            {s.title}
                                        </div>
                                        <div style={{ fontSize: '0.78rem', color: 'rgba(255,255,255,0.7)', lineHeight: 1.55 }}>
                                            {s.body}
                                        </div>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            </section>

            {/* ── Footer ────────────────────────────────────────── */}
            <footer style={{ background: INK, padding: '64px 0 32px', color: 'rgba(255,255,255,0.6)' }}>
                <div style={{ maxWidth: 1240, margin: '0 auto', padding: '0 28px' }}>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 48, marginBottom: 48 }}>
                        <div>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
                                <div style={{
                                    width: 34, height: 34, borderRadius: 8,
                                    background: `linear-gradient(135deg, ${NAVY}, ${NAVY_DARK})`,
                                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                                }}>
                                    <Building2 size={17} color="#fff" />
                                </div>
                                <div style={{ lineHeight: 1 }}>
                                    <div style={{ fontFamily: "'Manrope', sans-serif", fontSize: '1rem', fontWeight: 800, color: '#fff' }}>
                                        Quot PSE
                                    </div>
                                    <div style={{ fontSize: '0.6rem', color: NIGERIA_GREEN, fontWeight: 700, letterSpacing: '0.5px', textTransform: 'uppercase', marginTop: 2 }}>
                                        Public-Sector IFMIS
                                    </div>
                                </div>
                            </div>
                            <p style={{ fontSize: '0.8rem', lineHeight: 1.7, margin: 0 }}>
                                IPSAS-compliant, NCoA-native fiscal management for Nigeria's 36 States, the FCT,
                                and all 774 Local Government Councils.
                            </p>
                        </div>
                        <div>
                            <h4 style={{ color: '#fff', fontSize: '0.8rem', fontWeight: 700, marginBottom: 16, textTransform: 'uppercase', letterSpacing: '0.5px' }}>Platform</h4>
                            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                                <a href="#modules" style={{ color: 'inherit', textDecoration: 'none', fontSize: '0.8rem' }}>Modules</a>
                                <a href="#compliance" style={{ color: 'inherit', textDecoration: 'none', fontSize: '0.8rem' }}>Compliance</a>
                                <a href="#who" style={{ color: 'inherit', textDecoration: 'none', fontSize: '0.8rem' }}>Who it's for</a>
                                <a onClick={() => navigate('/pricing')} style={{ color: 'inherit', textDecoration: 'none', fontSize: '0.8rem', cursor: 'pointer' }}>Pricing</a>
                            </div>
                        </div>
                        <div>
                            <h4 style={{ color: '#fff', fontSize: '0.8rem', fontWeight: 700, marginBottom: 16, textTransform: 'uppercase', letterSpacing: '0.5px' }}>Resources</h4>
                            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                                <span style={{ fontSize: '0.8rem' }}>IPSAS Adoption Guide</span>
                                <span style={{ fontSize: '0.8rem' }}>NCoA Coding Handbook</span>
                                <span style={{ fontSize: '0.8rem' }}>Onboarding Runbook</span>
                            </div>
                        </div>
                        <div>
                            <h4 style={{ color: '#fff', fontSize: '0.8rem', fontWeight: 700, marginBottom: 16, textTransform: 'uppercase', letterSpacing: '0.5px' }}>Legal</h4>
                            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                                <span style={{ fontSize: '0.8rem' }}>Privacy Policy</span>
                                <span style={{ fontSize: '0.8rem' }}>Terms of Service</span>
                                <span style={{ fontSize: '0.8rem' }}>Data Residency (NG)</span>
                            </div>
                        </div>
                    </div>
                    <div style={{ borderTop: '1px solid rgba(255,255,255,0.08)', paddingTop: 24, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
                        <p style={{ fontSize: '0.75rem', margin: 0 }}>&copy; {new Date().getFullYear()} Quot PSE. All rights reserved.</p>
                        <p style={{ fontSize: '0.72rem', margin: 0, color: 'rgba(255,255,255,0.45)' }}>
                            Aligned with IPSAS · NCoA · PFM Act · Pension Reform Act 2014 · FIRSCA 2007
                        </p>
                    </div>
                </div>
            </footer>
        </div>
    );
};

export default LandingPage;
