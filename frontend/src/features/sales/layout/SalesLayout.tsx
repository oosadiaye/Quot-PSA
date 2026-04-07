import type { ReactNode } from 'react';
import Sidebar from '../../../components/Sidebar';
import PageHeader from '../../../components/PageHeader';
import { TrendingUp } from 'lucide-react';

interface SalesLayoutProps {
    children: ReactNode;
    title: string;
    description: string;
    icon?: ReactNode;
    actions?: ReactNode;
}

const SalesLayout = ({ children, title, description, icon, actions }: SalesLayoutProps) => {
    return (
        <div style={{ display: 'flex' }}>
            <Sidebar />
            <main style={{ flex: 1, minWidth: 0, marginLeft: '260px', padding: '2.5rem' }}>
                <PageHeader
                    title={title}
                    subtitle={description}
                    icon={icon || <TrendingUp size={22} color="white" />}
                    actions={actions}
                />
                {children}
            </main>
        </div>
    );
};

export default SalesLayout;
