import React from 'react';
import Sidebar from '../../components/Sidebar';

const AccountingLayout: React.FC<{ children: React.ReactNode }> = ({ children }) => {
    return (
        <div style={{ display: 'flex' }}>
            <Sidebar />
            <main style={{ flex: 1, marginLeft: '260px', paddingTop: '64px', paddingLeft: '2.5rem', paddingRight: '2.5rem', paddingBottom: '2.5rem' }}>
                {children}
            </main>
        </div>
    );
};

export default AccountingLayout;
