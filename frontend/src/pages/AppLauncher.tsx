import { useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { X } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { useVisibleModules } from '../hooks/useVisibleModules';
import { menusLabel, toTiles } from '../config/modules';
import { MODULE_STORAGE_KEY } from '../components/shell/TopNav';
import LogoutConfirm from '../components/shell/LogoutConfirm';
import AppearanceMenu from '../components/shell/AppearanceMenu';
import '../components/shell/shell.css';

/** "All modules": one tile per module the user may open. Opening a tile goes to that module's first menu. */
export default function AppLauncher() {
  const navigate = useNavigate();
  const { logout } = useAuth();
  const modules = useVisibleModules();
  const [query, setQuery] = useState('');
  const [confirmOut, setConfirmOut] = useState(false);
  const tenantName = (() => {
    try { return JSON.parse(localStorage.getItem('tenantInfo') || 'null')?.name || 'No Organization'; } catch { return 'No Organization'; }
  })();

  const tiles = useMemo(() => {
    const q = query.trim().toLowerCase();
    return toTiles(modules).filter((t) => !q || t.name.toLowerCase().includes(q));
  }, [modules, query]);

  const open = (name: string) => {
    try { window.sessionStorage.setItem(MODULE_STORAGE_KEY, name); } catch { /* private mode */ }
  };
  const canClose = window.history.length > 1;

  return (
    <div className="launcher">
      <div className="launcher-bar">
        {canClose && (
          <button type="button" className="launcher-link" onClick={() => navigate(-1)} aria-label="Close launcher">
            <X size={16} />
          </button>
        )}
        <span className="launcher-tenant">{tenantName}</span>
        <input
          className="launcher-search" type="search" placeholder="Search modules" aria-label="Search modules"
          value={query} onChange={(e) => setQuery(e.target.value)} autoFocus
        />
        <AppearanceMenu buttonClassName="launcher-link" />
        <button type="button" className="launcher-link" onClick={() => setConfirmOut(true)}>Sign out</button>
      </div>
      <div className="launcher-head"><h1>All modules</h1></div>
      {tiles.length === 0 ? (
        <p className="launcher-empty">{query ? `No module matches “${query}”.` : 'No modules are available to you yet.'}</p>
      ) : (
        <nav className="launcher-grid" aria-label="Modules">
          {tiles.map((t) => {
            const first = modules.find((m) => m.name === t.name)?.subItems?.[0]?.path ?? t.path;
            return (
              <Link key={t.name} to={first} className="launcher-tile" onClick={() => open(t.name)}>
                <span className="launcher-icon" style={{ background: t.accent }}><t.icon size={30} color="#fff" /></span>
                <span className="launcher-name">{t.name}</span>
                <span className="launcher-count">{menusLabel(t.menus)}</span>
              </Link>
            );
          })}
        </nav>
      )}
      {confirmOut && (
        <LogoutConfirm tenantName={tenantName} onStay={() => setConfirmOut(false)} onConfirm={() => { logout(); navigate('/login'); }} />
      )}
    </div>
  );
}
