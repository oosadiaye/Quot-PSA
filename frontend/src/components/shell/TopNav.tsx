import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { ChevronDown, Grid3x3, LogOut, User } from 'lucide-react';
import { Dropdown } from 'antd';
import type { MenuProps } from 'antd';
import { useAuth } from '../../context/AuthContext';
import { useVisibleModules } from '../../hooks/useVisibleModules';
import { activeModule, currentSub, fitCount } from '../../config/modules';
import ThemeSwitcher from '../ThemeSwitcher';
import NotificationBell from '../NotificationBell';
import OrganizationSwitcher from '../OrganizationSwitcher';
import LogoutConfirm from './LogoutConfirm';
import AppearanceMenu from './AppearanceMenu';
import './shell.css';

/** Remembers the module the user opened, for a page two modules both list. */
export const MODULE_STORAGE_KEY = 'quotpse.nav.module.v1';
const MENU_GAP = 2;
const MORE_WIDTH = 84;

const readTenant = (): { name?: string } | null => {
  try {
    const raw = localStorage.getItem('tenantInfo');
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
};

const initials = (name: string): string =>
  name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]?.toUpperCase()).join('') || 'U';

export default function TopNav() {
  const navigate = useNavigate();
  const { pathname, search } = useLocation();
  const { mdaIsolationMode, logout } = useAuth();
  const modules = useVisibleModules();
  const tenantName = readTenant()?.name || 'No Organization';

  // Read on every render: it changes as the user moves between modules, and the read is cheap.
  let preferred: string | null = null;
  try { preferred = window.sessionStorage.getItem(MODULE_STORAGE_KEY); } catch { /* private mode */ }
  const module = useMemo(() => activeModule(modules, pathname, search, preferred), [modules, pathname, search, preferred]);

  useEffect(() => {
    if (!module) return;
    try { window.sessionStorage.setItem(MODULE_STORAGE_KEY, module.name); } catch { /* private mode */ }
  }, [module]);

  // A single-page module has one menu: itself.
  const menus = useMemo(
    () => module?.subItems ?? (module ? [{ name: module.name, path: module.path, icon: module.icon }] : []),
    [module],
  );
  const current = module ? currentSub(menus, pathname, search) : null;

  // How many menus fit: measured on a hidden copy of the whole row, so a wider font or a longer name is accounted for.
  const barRef = useRef<HTMLDivElement>(null);
  const measureRef = useRef<HTMLDivElement>(null);
  const [shown, setShown] = useState(menus.length);
  const recompute = useCallback(() => {
    const bar = barRef.current;
    const probe = measureRef.current;
    if (!bar || !probe) return;
    const widths = Array.from(probe.children).map((c) => (c as HTMLElement).offsetWidth);
    setShown(fitCount(widths, bar.clientWidth, MORE_WIDTH, MENU_GAP));
  }, []);
  useLayoutEffect(() => {
    recompute();
    const bar = barRef.current;
    if (!bar || typeof ResizeObserver === 'undefined') return undefined;
    const ro = new ResizeObserver(recompute);
    ro.observe(bar);
    return () => ro.disconnect();
  }, [recompute, menus]);

  const inline = menus.slice(0, shown);
  const overflow = menus.slice(shown);
  // "More" is open for the page it was opened on, so going to another page closes it without an effect.
  const here = `${pathname}${search}`;
  const [openFor, setOpenFor] = useState<string | null>(null);
  const moreOpen = openFor === here;
  const setMoreOpen = (open: boolean) => setOpenFor(open ? here : null);
  const moreRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!moreOpen) return undefined;
    const onDown = (e: MouseEvent) => { if (!moreRef.current?.contains(e.target as Node)) setOpenFor(null); };
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpenFor(null); };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => { document.removeEventListener('mousedown', onDown); document.removeEventListener('keydown', onKey); };
  }, [moreOpen]);

  const [confirmOut, setConfirmOut] = useState(false);
  const userItems: MenuProps['items'] = [
    { key: 'account', label: 'My Account', icon: <User size={14} />, onClick: () => navigate('/account') },
    { type: 'divider' },
    { key: 'logout', label: 'Sign Out', icon: <LogOut size={14} />, danger: true, onClick: () => setConfirmOut(true) },
  ];

  const link = (m: { name: string; path: string; icon: React.ComponentType<{ size?: number }> }, measure = false) => (
    <Link
      key={m.name}
      to={m.path}
      className={`topnav-link${current?.name === m.name ? ' is-active' : ''}`}
      aria-current={current?.name === m.name ? 'page' : undefined}
      tabIndex={measure ? -1 : undefined}
    >
      {m.name}
    </Link>
  );

  return (
    <>
      <header className="topnav">
        <Link to="/apps" className="topnav-apps" aria-label="All modules" title="All modules"><Grid3x3 size={20} /></Link>
        <span className="topnav-module">{module?.name ?? 'Quot PSA'}</span>

        <nav className="topnav-menus" ref={barRef} aria-label={module ? `${module.name} menus` : 'Menus'}>
          {inline.map((m) => link(m))}
          {overflow.length > 0 && (
            <div className="topnav-more" ref={moreRef}>
              <button
                type="button"
                className={`topnav-link${overflow.some((m) => m.name === current?.name) ? ' is-active' : ''}`}
                aria-haspopup="menu" aria-expanded={moreOpen}
                onClick={() => setMoreOpen(!moreOpen)}
              >
                More <ChevronDown size={14} />
              </button>
              {moreOpen && <div className="topnav-more-panel" role="menu">{overflow.map((m) => link(m))}</div>}
            </div>
          )}
        </nav>
        {/* Hidden copy of every menu, only to read their widths. */}
        <div className="topnav-menus is-measure" ref={measureRef} aria-hidden="true">{menus.map((m) => link(m, true))}</div>

        <div className="topnav-systray">
          {mdaIsolationMode === 'SEPARATED' && <OrganizationSwitcher />}
          <span className="topnav-tenant" title={tenantName}>{tenantName}</span>
          <ThemeSwitcher iconOnly />
          <AppearanceMenu />
          <NotificationBell />
          <Dropdown menu={{ items: userItems }} trigger={['click']} placement="bottomRight" arrow>
            <button type="button" className="topnav-avatar" aria-label="Account menu">{initials(tenantName)}</button>
          </Dropdown>
        </div>
      </header>
      {confirmOut && (
        <LogoutConfirm
          tenantName={tenantName}
          onStay={() => setConfirmOut(false)}
          onConfirm={() => { logout(); navigate('/login'); }}
        />
      )}
    </>
  );
}
