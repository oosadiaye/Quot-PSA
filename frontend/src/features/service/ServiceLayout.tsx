import React from 'react';
import Sidebar from '../../components/Sidebar';

const ServiceLayout: React.FC<{ children: React.ReactNode }> = ({ children }) => {
    return (
        <div style={{ display: 'flex' }}>
            <Sidebar />
            <main style={{ flex: 1, marginLeft: '260px', padding: '2.5rem' }}>
                {children}
            </main>
        </div>
    );
};

export default ServiceLayout;
