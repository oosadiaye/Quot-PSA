import type { ReactNode } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { LayoutDashboard, Wallet, CalendarDays, UserCircle, FolderLock, LogOut } from 'lucide-react';

interface PortalLayoutProps {
  children: ReactNode;
}

const NAV_ITEMS = [
  { to: '/portal', label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/portal/payslips', label: 'Payslips', icon: Wallet, end: false },
  { to: '/portal/leave', label: 'Leave', icon: CalendarDays, end: false },
  { to: '/portal/documents', label: 'My Documents', icon: FolderLock, end: false },
  { to: '/portal/profile', label: 'My Profile', icon: UserCircle, end: false },
] as const;

export default function PortalLayout({ children }: PortalLayoutProps) {
  const navigate = useNavigate();

  const handleLogout = () => {
    localStorage.removeItem('authToken');
    localStorage.removeItem('user');
    navigate('/login');
  };

  return (
    <div style={{ display: 'flex', minHeight: '100vh', background: '#f5f7fb' }}>
      <aside
        style={{
          width: 240,
          background: 'linear-gradient(180deg, #1a1f66 0%, #242a88 100%)',
          color: '#ffffff',
          position: 'fixed',
          top: 0,
          bottom: 0,
          left: 0,
          display: 'flex',
          flexDirection: 'column',
          zIndex: 20,
        }}
      >
        <div style={{ padding: '22px 20px', borderBottom: '1px solid rgba(255,255,255,0.08)' }}>
          <div style={{ fontSize: 13, fontWeight: 600, opacity: 0.65, textTransform: 'uppercase', letterSpacing: 1 }}>
            Employee Portal
          </div>
          <div style={{ fontSize: 17, fontWeight: 700, marginTop: 4 }}>Self-Service</div>
        </div>
        <nav style={{ flex: 1, padding: '12px 10px' }}>
          {NAV_ITEMS.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              style={({ isActive }) => ({
                display: 'flex',
                alignItems: 'center',
                gap: 12,
                padding: '10px 14px',
                borderRadius: 8,
                marginBottom: 4,
                color: isActive ? '#ffffff' : 'rgba(255,255,255,0.72)',
                background: isActive ? 'rgba(255,255,255,0.14)' : 'transparent',
                textDecoration: 'none',
                fontSize: 14,
                fontWeight: isActive ? 600 : 500,
                transition: 'all 0.15s',
              })}
            >
              <Icon size={17} />
              {label}
            </NavLink>
          ))}
        </nav>
        <button
          onClick={handleLogout}
          style={{
            margin: 16,
            padding: '10px 14px',
            background: 'rgba(239, 68, 68, 0.12)',
            border: '1px solid rgba(239, 68, 68, 0.35)',
            color: '#fca5a5',
            borderRadius: 8,
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            fontSize: 13,
            fontWeight: 500,
          }}
        >
          <LogOut size={15} />
          Sign out
        </button>
      </aside>
      <main style={{ flex: 1, marginLeft: 240, padding: '28px 36px', maxWidth: 1400 }}>
        {children}
      </main>
    </div>
  );
}
