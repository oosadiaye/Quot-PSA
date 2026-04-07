import { Settings } from 'lucide-react';
import Sidebar from '../../components/Sidebar';
import BackButton from '../../components/BackButton';
import '../accounting/styles/glassmorphism.css';

export default function SettingsLayout({ children }: { children: React.ReactNode }) {

    return (
        <div style={{ display: 'flex' }}>
            <Sidebar />
            <div style={{ flex: 1, marginLeft: '260px', minHeight: '100vh', background: 'var(--color-background)' }}>
                {/* Page header */}
                <div style={{
                    padding: '1.5rem 3rem 1.25rem',
                    borderBottom: '1px solid var(--color-border)',
                    background: 'var(--color-surface)',
                }}>
                    <BackButton />
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', marginBottom: '0.25rem', marginTop: '0.5rem' }}>
                        <Settings size={22} style={{ color: 'var(--color-primary)' }} />
                        <h1 style={{ fontSize: 'var(--text-lg)', fontWeight: 700, color: 'var(--color-text)' }}>
                            Accounting Settings
                        </h1>
                    </div>
                    <p style={{ color: 'var(--color-text-muted)', fontSize: 'var(--text-sm)', margin: 0 }}>
                        Configure accounting preferences, currencies, and chart of accounts structure.
                    </p>
                </div>

                <div style={{ padding: '2.5rem 3rem 3rem' }}>
                    <main>
                        {children}
                    </main>
                </div>
            </div>
        </div>
    );
}
