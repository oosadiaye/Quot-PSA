import { Settings } from 'lucide-react';
import Sidebar from '../../../components/Sidebar';
import PageHeader from '../../../components/PageHeader';
import '../styles/glassmorphism.css';

export default function BudgetLayout({ children }: { children: React.ReactNode }) {
    return (
        <div style={{ display: 'flex' }}>
            <Sidebar />
            <main style={{ flex: 1, marginLeft: '260px', padding: '2.5rem' }}>
                <PageHeader
                    title="Budget Management"
                    subtitle="Monitor budgets, manage allocations, and analyze variance across fiscal periods."
                    icon={<Settings size={22} />}
                    backButton={false}
                />
                {children}
            </main>
        </div>
    );
}
