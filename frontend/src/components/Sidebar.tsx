import { useState, useEffect, useLayoutEffect, useRef } from 'react';
import { useNavigate, useLocation, Link } from 'react-router-dom';
import {
    LogOut,
    ChevronRight,
    ChevronDown,
    User,
} from 'lucide-react';
import { Menu, X } from 'lucide-react';
import { usePermissions } from '../hooks/usePermissions';
import { menuItems, isNavItemVisible, type MenuItem } from '../config/navigation';
import { useTenantModules } from '../hooks/useTenantModules';
import { useBranding } from '../context/BrandingContext';
import { useAuth } from '../context/AuthContext';
import ThemeSwitcher from './ThemeSwitcher';
import { useIsMobile } from '../design';
import OrganizationSwitcher from './OrganizationSwitcher';
import NotificationBell from './NotificationBell';
import { Dropdown } from 'antd';
import type { MenuProps } from 'antd';
import BackButton from './BackButton';

const Sidebar = () => {
    const navigate = useNavigate();
    const location = useLocation();
    const { branding } = useBranding();
    const { mdaIsolationMode, logout } = useAuth();
    const showMdaSwitcher = mdaIsolationMode === 'SEPARATED';
    const tenantInfo = (() => {
        try {
            const raw = localStorage.getItem('tenantInfo');
            return raw ? JSON.parse(raw) : null;
        } catch { return null; }
    })();
    const activeTenant = tenantInfo?.name || 'No Organization';
    const { data: user, isLoading: permLoading } = usePermissions();
    const { data: tenantModules, isLoading: modulesLoading } = useTenantModules();
    // Persist expanded menus in localStorage. The Sidebar is rendered
    // by every page layout separately (~96 call-sites), which means it
    // unmounts/remounts on EVERY route change — a plain useState would
    // reset to [] each time and the user would lose their manually-
    // expanded menu groups after each click. localStorage survives
    // remount AND full page reload, so the sidebar stays open on the
    // group the user was working in until they explicitly collapse it.
    const EXPANDED_MENUS_STORAGE_KEY = 'quotpse.sidebar.expandedMenus.v1';
    const [expandedMenus, setExpandedMenus] = useState<string[]>(() => {
        try {
            const raw = window.localStorage.getItem(EXPANDED_MENUS_STORAGE_KEY);
            if (!raw) return [];
            const parsed = JSON.parse(raw);
            return Array.isArray(parsed) ? parsed.filter((x) => typeof x === 'string') : [];
        } catch {
            return [];
        }
    });
    // Write back on every change.
    useEffect(() => {
        try {
            window.localStorage.setItem(
                EXPANDED_MENUS_STORAGE_KEY,
                JSON.stringify(expandedMenus),
            );
        } catch { /* storage quota / private mode — ignore */ }
    }, [expandedMenus]);

    const [showLogoutConfirm, setShowLogoutConfirm] = useState(false);

    // ── Active-item scroll-into-view ───────────────────────────────────
    // Ref attached to the currently active sidebar row. On every path
    // change we scroll it into view so the user always sees where they
    // are in the nav tree without manually scrolling. ``block: 'nearest'``
    // means we don't scroll if it's already visible — avoids gratuitous
    // movement when the active item didn't change.
    const activeRowRef = useRef<HTMLElement | null>(null);
    useLayoutEffect(() => {
        if (activeRowRef.current) {
            activeRowRef.current.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
        }
    }, [location.pathname, location.search]);

    // ── Responsive drawer state (Phase 1 of responsive rollout)
    const isMobile = useIsMobile();
    const [drawerOpen, setDrawerOpen] = useState(false);

    // Close drawer on route change
    useEffect(() => {
        if (isMobile) setDrawerOpen(false);
    }, [location.pathname, isMobile]);

    // Close drawer on Escape
    useEffect(() => {
        if (!drawerOpen) return;
        const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setDrawerOpen(false); };
        window.addEventListener('keydown', onKey);
        return () => window.removeEventListener('keydown', onKey);
    }, [drawerOpen]);

    // Lock body scroll when drawer is open on mobile
    useEffect(() => {
        if (isMobile && drawerOpen) {
            const prev = document.body.style.overflow;
            document.body.style.overflow = 'hidden';
            return () => { document.body.style.overflow = prev; };
        }
    }, [isMobile, drawerOpen]);

    useEffect(() => {
        const activeParent = menuItems.find(
            (item) =>
                item.subItems?.some((sub) => isActive(sub.path)) ||
                location.pathname === item.path ||
                location.pathname.startsWith(item.path)
        );
        if (activeParent?.subItems && !expandedMenus.includes(activeParent.name)) {
            setExpandedMenus((prev) =>
                prev.includes(activeParent.name) ? prev : [...prev, activeParent.name]
            );
        }
    }, [location.pathname, location.search]);

    const toggleMenu = (menuName: string) => {
        setExpandedMenus((prev) =>
            prev.includes(menuName) ? prev.filter((m) => m !== menuName) : [...prev, menuName]
        );
    };

    // The same rule the Ask AI finder uses, so the two can never disagree about what a user may open.
    const filteredItems = menuItems.filter((item) => isNavItemVisible(
        item,
        { user, loading: permLoading },
        { enabledModules: tenantModules?.enabled_modules, loading: modulesLoading },
    ));

    const handleLogout = () => {
        logout();
        navigate('/login');
    };

    // Account / sign-out live in a top-right user dropdown (not the sidebar).
    const userMenuItems: MenuProps['items'] = [
        { key: 'account', label: 'My Account', icon: <User size={14} />,
          onClick: () => navigate('/account') },
        { type: 'divider' },
        { key: 'logout', label: 'Sign Out', icon: <LogOut size={14} />, danger: true,
          onClick: () => setShowLogoutConfirm(true) },
    ];
    const userMenu = (
        <Dropdown menu={{ items: userMenuItems }} trigger={['click']} placement="bottomRight" arrow>
            <button type="button" aria-label="Account menu" style={userMenuBtnStyle}>
                <User size={18} />
            </button>
        </Dropdown>
    );

    const handleSwitchTenant = () => {
        localStorage.removeItem('tenantDomain');
        localStorage.removeItem('tenantInfo');
        localStorage.removeItem('tenantPermissions');
        navigate('/login');
    };

    const isActive = (path: string) => {
        // For paths with a query string (e.g. /accounting/ar?tab=payments),
        // compare both pathname and search so the highlight works correctly.
        if (path.includes('?')) {
            const [p, q] = path.split('?');
            return location.pathname === p && location.search === `?${q}`;
        }
        return location.pathname === path;
    };
    const isParentActive = (item: MenuItem) => {
        if (item.subItems) {
            return item.subItems.some((sub) => isActive(sub.path)) || location.pathname.startsWith(item.path);
        }
        return isActive(item.path);
    };

    return (
        <>
        {/* Mobile hamburger + top bar — only on mobile */}
        {isMobile && (
            <div style={{
                position: 'fixed', top: 0, left: 0, right: 0, height: '56px',
                background: 'var(--sidebar-bg)', borderBottom: '1px solid var(--sidebar-border)',
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                padding: '0 12px', gap: '12px', zIndex: 30,
                boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
                paddingTop: 'env(safe-area-inset-top, 0)',
            }}>
                <button
                    onClick={() => setDrawerOpen(true)}
                    aria-label="Open navigation"
                    className="tap-target"
                    style={{ background: 'transparent', border: 'none', cursor: 'pointer', borderRadius: 8, color: '#1a237e' }}
                >
                    <Menu size={22} />
                </button>
                <div style={{ flex: 1, fontFamily: "'Manrope',sans-serif", fontWeight: 700, fontSize: 15, color: 'var(--color-text)', textAlign: 'center', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {branding.name || 'Quot PSA'}
                </div>
                <ThemeSwitcher iconOnly />
                {userMenu}
                <NotificationBell />
            </div>
        )}

        {/* Top Header Bar — only visible when MDA separation is active, desktop only */}
        {showMdaSwitcher && !isMobile && (
            <div style={{
                position: 'fixed', top: 0, left: '260px', right: 0, height: '48px',
                background: 'var(--sidebar-bg)', borderBottom: '1px solid var(--sidebar-border)',
                display: 'flex', alignItems: 'center', justifyContent: 'flex-end',
                padding: '0 24px', gap: '16px', zIndex: 15,
                boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
            }}>
                <OrganizationSwitcher />
                <ThemeSwitcher iconOnly />
                {userMenu}
                <NotificationBell />
            </div>
        )}

        {/* Theme switcher + account — pinned top-right on desktop when no MDA
            header bar is present, so the controls are always in the same spot. */}
        {!showMdaSwitcher && !isMobile && (
            <div style={{ position: 'fixed', top: 12, right: 16, zIndex: 15, display: 'flex', alignItems: 'center', gap: 12 }}>
                <ThemeSwitcher iconOnly />
                {userMenu}
            </div>
        )}

        {/* Mobile drawer scrim */}
        {isMobile && drawerOpen && (
            <div
                onClick={() => setDrawerOpen(false)}
                style={{
                    position: 'fixed', inset: 0, background: 'rgba(15,23,89,0.45)',
                    zIndex: 25, animation: 'fade-in 180ms ease',
                }}
            />
        )}

        <div style={{
            width: '260px',
            height: '100vh',
            // Theme-driven surface: white + slate in light, navy + light text
            // in dark (via --sidebar-* tokens). Active item is a solid indigo
            // pill (#2926d9) in both themes.
            background: 'var(--sidebar-bg)',
            color: 'var(--sidebar-text)',
            display: 'flex', flexDirection: 'column',
            position: 'fixed', left: 0, top: 0,
            overflowY: 'auto',
            borderRight: '1px solid var(--sidebar-border)',
            zIndex: isMobile ? 28 : 20,
            transform: isMobile ? (drawerOpen ? 'translateX(0)' : 'translateX(-100%)') : 'none',
            transition: isMobile ? 'transform 240ms cubic-bezier(0.16, 1, 0.3, 1)' : 'none',
            boxShadow: isMobile && drawerOpen ? '0 0 40px rgba(15,23,42,0.18)' : 'none',
        }}>
            {/* Close button — mobile drawer only */}
            {isMobile && (
                <button
                    onClick={() => setDrawerOpen(false)}
                    aria-label="Close navigation"
                    className="tap-target"
                    style={{
                        position: 'absolute', top: 8, right: 8,
                        background: 'var(--sidebar-hover)', border: 'none', cursor: 'pointer',
                        color: 'var(--sidebar-text)', borderRadius: 8, zIndex: 2,
                    }}
                >
                    <X size={20} />
                </button>
            )}
            {/* Header */}
            <div style={{
                padding: '20px 20px 16px',
                borderBottom: '1px solid var(--sidebar-border)',
            }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '12px' }}>
                    <div style={{
                        width: '36px', height: '36px', borderRadius: '10px',
                        // Light tint of the new accent so the placeholder
                        // logo block reads as part of the same palette
                        // when ``branding.logo`` is unset.
                        background: 'var(--sidebar-hover)',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        flexShrink: 0, overflow: 'hidden',
                    }}>
                        {branding.logo ? (
                            <img src={branding.logo} alt={branding.name} style={{ width: '100%', height: '100%', objectFit: 'contain' }} />
                        ) : (
                            <svg viewBox="0 0 40 40" fill="none" width="20" height="20">
                                {/* Inverted from white-on-navy to indigo-on-light. */}
                                <rect x="4" y="8" width="14" height="14" rx="3" fill="#2926d9"/>
                                <rect x="22" y="8" width="14" height="14" rx="3" fill="rgba(41,38,217,0.7)"/>
                                <rect x="4" y="26" width="14" height="6" rx="3" fill="rgba(41,38,217,0.5)"/>
                                <rect x="22" y="26" width="14" height="6" rx="3" fill="rgba(41,38,217,0.3)"/>
                            </svg>
                        )}
                    </div>
                    <div>
                        <div style={{ fontSize: '16px', fontWeight: 700, color: 'var(--color-text)', letterSpacing: '-0.3px' }}>
                            {branding.name}
                        </div>
                        <div style={{ fontSize: '11px', color: 'var(--color-text-muted)', fontWeight: 500 }}>
                            Enterprise Platform
                        </div>
                    </div>
                </div>
            </div>

            {/* Back button */}
            <div style={{ padding: '8px 12px 4px' }}>
                <BackButton variant="compact" />
            </div>

            {/* Navigation */}
            <nav style={{ flex: 1, padding: '4px 12px', display: 'flex', flexDirection: 'column', gap: '1px' }}>
                {filteredItems.map((item) => {
                    // Light-theme palette anchored on indigo #2926d9.
                    // Active state is now a SOLID full-width pill (matches
                    // the SuperAdmin reference): the accent fills the
                    // background and text/icon flip to white. Hover is a
                    // gentle slate wash so it reads as "interactive" without
                    // competing with the active selection.
                    const ACCENT = '#2926d9';
                    // Slightly darker on press would be nice for tactile
                    // feedback, but a single shade keeps the active pill
                    // visually stable while users navigate.
                    const ACTIVE_BG  = ACCENT;
                    const ACTIVE_FG  = '#ffffff';
                    const HOVER_BG   = 'var(--sidebar-hover)';
                    const HOVER_FG   = 'var(--sidebar-text-active)';
                    // Inactive sidebar text was previously slate-600 / slate-400
                    // which read as washed-out grey ("ash") against the white
                    // background. Bumped to near-black (slate-900) for the
                    // primary text and slate-700 for the icon/chevron so the
                    // visual rhythm of label > icon survives while every label
                    // now meets AAA contrast against the white sidebar.
                    // Active state (white on blue) and hover state untouched.
                    const INACTIVE_FG       = 'var(--sidebar-text)';
                    const INACTIVE_ICON     = 'var(--sidebar-text)';
                    const INACTIVE_LABEL_FG = 'var(--sidebar-text)';
                    const INACTIVE_CHEVRON  = 'var(--sidebar-text)';

                    const parentActive = isParentActive(item);

                    // Shared row styling for both the parent <Link> (when the
                    // item has no subItems and is a real destination) and the
                    // parent <div> toggler (when the item groups subItems).
                    // Built as a function so the two code paths stay in sync.
                    const parentRowStyle: React.CSSProperties = {
                        position: 'relative',
                        display: 'flex', alignItems: 'center', gap: '10px',
                        padding: '8px 12px', borderRadius: '8px',
                        cursor: 'pointer', transition: 'background 0.15s, color 0.15s',
                        background: parentActive ? ACTIVE_BG : 'transparent',
                        color: parentActive ? ACTIVE_FG : INACTIVE_FG,
                        // Link inherits <a> defaults; strip them out.
                        textDecoration: 'none',
                        // The previous design used an inset 3px strip; the
                        // SuperAdmin reference uses a fully filled pill
                        // instead — strip removed.
                    };
                    const parentRowHoverIn = (e: React.MouseEvent<HTMLElement>) => {
                        if (!parentActive) {
                            (e.currentTarget as HTMLElement).style.background = HOVER_BG;
                            (e.currentTarget as HTMLElement).style.color = HOVER_FG;
                        }
                    };
                    const parentRowHoverOut = (e: React.MouseEvent<HTMLElement>) => {
                        if (!parentActive) {
                            (e.currentTarget as HTMLElement).style.background = 'transparent';
                            (e.currentTarget as HTMLElement).style.color = INACTIVE_FG;
                        }
                    };
                    // Only the parent without subItems gets the
                    // active-ref (so scroll-into-view targets a leaf
                    // page). Parents with subItems delegate the ref to
                    // their active child below.
                    const parentRefProp = (parentActive && !item.subItems)
                        ? { ref: activeRowRef as React.RefObject<HTMLAnchorElement & HTMLDivElement> }
                        : {};
                    const parentInner = (
                        <>
                            <item.icon size={18} style={{
                                // Icon/label/chevron all flip to white when
                                // the parent is active so the entire pill
                                // reads as a single solid block.
                                color: parentActive ? ACTIVE_FG : INACTIVE_ICON,
                                flexShrink: 0
                            }} />
                            <span style={{
                                flex: 1, fontSize: '13.5px',
                                fontWeight: parentActive ? 700 : 500,
                                color: parentActive ? ACTIVE_FG : INACTIVE_LABEL_FG,
                            }}>
                                {item.name}
                            </span>
                            {item.subItems ? (
                                expandedMenus.includes(item.name) ?
                                    <ChevronDown size={14} style={{ color: parentActive ? ACTIVE_FG : INACTIVE_CHEVRON }} /> :
                                    <ChevronRight size={14} style={{ color: parentActive ? ACTIVE_FG : INACTIVE_CHEVRON }} />
                            ) : null}
                        </>
                    );

                    return (
                        <div key={item.name}>
                            {item.subItems ? (
                                // Has a submenu — row is a toggler, not a link.
                                // (Most common case and there's no natural
                                // destination when subItems exist.)
                                <div
                                    role="button"
                                    tabIndex={0}
                                    onClick={() => toggleMenu(item.name)}
                                    onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') toggleMenu(item.name); }}
                                    style={parentRowStyle}
                                    onMouseOver={parentRowHoverIn}
                                    onMouseOut={parentRowHoverOut}
                                >
                                    {parentInner}
                                </div>
                            ) : (
                                // Leaf item — render as a real <Link> so
                                // right-click / middle-click / Ctrl+click
                                // open in a new tab and hover shows the URL
                                // in the status bar. Navigation via left-click
                                // still goes through React Router (no full
                                // page reload) because Link handles that.
                                <Link
                                    {...parentRefProp}
                                    to={item.path}
                                    style={parentRowStyle}
                                    onMouseOver={parentRowHoverIn}
                                    onMouseOut={parentRowHoverOut}
                                >
                                    {parentInner}
                                </Link>
                            )}

                            {item.subItems && expandedMenus.includes(item.name) && (
                                <div style={{
                                    marginLeft: '12px',
                                    borderLeft: '1.5px solid #e2e8f0',
                                    marginTop: '2px', marginBottom: '4px',
                                }}>
                                    {item.subItems.map((subItem) => {
                                        const subActive = isActive(subItem.path);
                                        return (
                                            <Link
                                                ref={subActive ? (activeRowRef as React.RefObject<HTMLAnchorElement>) : undefined}
                                                key={subItem.name}
                                                to={subItem.path}
                                                style={{
                                                    position: 'relative',
                                                    display: 'flex', alignItems: 'center', gap: '8px',
                                                    padding: '6px 12px 6px 16px',
                                                    // Sub-items use the same fully-rounded pill so
                                                    // the active state matches the parent visually
                                                    // (a half-rounded sub-pill would have looked
                                                    // mismatched against a fully-rounded parent
                                                    // pill on the same theme).
                                                    borderRadius: '6px',
                                                    cursor: 'pointer', transition: 'background 0.15s, color 0.15s',
                                                    background: subActive ? ACTIVE_BG : 'transparent',
                                                    marginLeft: '4px',
                                                    textDecoration: 'none',
                                                }}
                                                onMouseOver={(e) => {
                                                    if (!subActive) {
                                                        e.currentTarget.style.background = HOVER_BG;
                                                    }
                                                }}
                                                onMouseOut={(e) => {
                                                    if (!subActive) {
                                                        e.currentTarget.style.background = 'transparent';
                                                    }
                                                }}
                                            >
                                                <subItem.icon size={14} style={{
                                                    color: subActive ? ACTIVE_FG : INACTIVE_ICON,
                                                    flexShrink: 0
                                                }} />
                                                <span style={{
                                                    fontSize: '12.5px',
                                                    fontWeight: subActive ? 700 : 500,
                                                    color: subActive ? ACTIVE_FG : INACTIVE_FG,
                                                }}>
                                                    {subItem.name}
                                                </span>
                                            </Link>
                                        );
                                    })}
                                </div>
                            )}
                        </div>
                    );
                })}
            </nav>

            {/* Account + Sign Out moved to the top-right user dropdown. */}

            {/* ── Logout confirmation overlay ─────────────────────── */}
            {showLogoutConfirm && (
                <div style={{
                    position: 'fixed', inset: 0,
                    background: 'rgba(15, 23, 42, 0.55)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    zIndex: 9999,
                    backdropFilter: 'blur(2px)',
                }}>
                    <div style={{
                        background: 'var(--color-surface)', borderRadius: '20px',
                        padding: '36px 32px', maxWidth: '380px', width: '90%',
                        boxShadow: '0 24px 64px rgba(0,0,0,0.25)',
                        border: '1px solid var(--color-border)',
                        textAlign: 'center',
                    }}>
                        <div style={{
                            width: '60px', height: '60px', borderRadius: '50%',
                            background: '#fef2f2',
                            display: 'flex', alignItems: 'center', justifyContent: 'center',
                            margin: '0 auto 20px',
                        }}>
                            <LogOut size={28} style={{ color: '#ef4444' }} />
                        </div>

                        <h3 style={{ fontSize: '20px', fontWeight: 700, color: 'var(--color-text)', marginBottom: '8px' }}>
                            Sign Out?
                        </h3>
                        <p style={{ fontSize: '14px', color: 'var(--color-text-muted)', lineHeight: 1.6, marginBottom: '28px' }}>
                            You are about to sign out of <strong>{activeTenant}</strong>.
                            Any unsaved changes will be lost.
                        </p>

                        <div style={{ display: 'flex', gap: '12px' }}>
                            <button
                                onClick={() => setShowLogoutConfirm(false)}
                                style={{
                                    flex: 1, padding: '12px',
                                    background: 'var(--color-surface-hover)', border: '1.5px solid var(--color-border)',
                                    borderRadius: '10px', fontSize: '14px', fontWeight: 600,
                                    color: 'var(--color-text-secondary)', cursor: 'pointer', fontFamily: 'inherit',
                                    transition: 'all 0.15s',
                                }}
                            >
                                Stay
                            </button>
                            <button
                                onClick={handleLogout}
                                style={{
                                    flex: 1, padding: '12px',
                                    background: 'linear-gradient(135deg, #ef4444, #dc2626)',
                                    border: 'none', borderRadius: '10px',
                                    fontSize: '14px', fontWeight: 600,
                                    color: 'white', cursor: 'pointer', fontFamily: 'inherit',
                                    boxShadow: '0 4px 12px rgba(239,68,68,0.35)',
                                    transition: 'all 0.15s',
                                }}
                                onMouseOver={(e) => e.currentTarget.style.opacity = '0.9'}
                                onMouseOut={(e) => e.currentTarget.style.opacity = '1'}
                            >
                                Sign Out
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
        </>
    );
};

const userMenuBtnStyle: React.CSSProperties = {
    display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
    width: 34, height: 34, borderRadius: '50%',
    background: 'var(--color-surface)',
    border: '1px solid var(--color-border)',
    color: 'var(--color-primary)',
    cursor: 'pointer',
    transition: 'background 140ms ease',
};

export default Sidebar;
