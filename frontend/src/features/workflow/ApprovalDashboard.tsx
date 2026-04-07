import React from 'react';
import Sidebar from '../../components/Sidebar';
import PageHeader from '../../components/PageHeader';
import {
    Inbox,
    Users,
    FileText,
    History,
    CheckCircle,
    ArrowRight,
    Search
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';

const ApprovalDashboard = () => {
    const navigate = useNavigate();

    const sections = [
        {
            title: 'Operations',
            links: [
                { name: 'Workflow Inbox', path: '/workflow/inbox', icon: Inbox, desc: 'Your pending approval requests' },
                { name: 'Approval History', path: '/workflow/instances', icon: History, desc: 'Audit log of completed approvals' },
            ]
        },
        {
            title: 'Configuration',
            links: [
                { name: 'Approval Groups', path: '/workflow/groups', icon: Users, desc: 'Manage reviewer teams and roles' },
                { name: 'Workflow Templates', path: '/workflow/definitions', icon: FileText, desc: 'Design multi-step approval paths' },
            ]
        },
        {
            title: 'Insights',
            links: [
                { name: 'Audit Search', path: '/workflow/instances', icon: Search, desc: 'Deep search across all workflow logs' },
            ]
        }
    ];

    return (
        <div style={{ display: 'flex' }}>
            <Sidebar />
            <main style={{ flex: 1, marginLeft: '260px', padding: '2.5rem' }}>
                <PageHeader
                    title="Approval Command Center"
                    subtitle="Centrally manage and audit organization-wide approval workflows."
                    icon={<CheckCircle size={22} color="white" />}
                />

                <div style={{ display: 'flex', flexDirection: 'column', gap: '2.5rem' }}>
                    {sections.map((section) => (
                        <div key={section.title}>
                            <h2 style={{ fontSize: 'var(--text-lg)', fontWeight: 600, marginBottom: '1.25rem', color: 'var(--color-text)' }}>
                                {section.title}
                            </h2>
                            <div style={{
                                display: 'grid',
                                gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))',
                                gap: '1.5rem'
                            }}>
                                {section.links.map((link) => (
                                    <div
                                        key={link.name}
                                        className="card glass animate-fade"
                                        style={{
                                            cursor: 'pointer',
                                            padding: '1.5rem',
                                            transition: 'var(--transition)',
                                            display: 'flex',
                                            flexDirection: 'column',
                                            gap: '1rem'
                                        }}
                                        onClick={() => navigate(link.path)}
                                        onMouseOver={(e) => {
                                            e.currentTarget.style.transform = 'translateY(-4px)';
                                            e.currentTarget.style.borderColor = '#6366f1';
                                        }}
                                        onMouseOut={(e) => {
                                            e.currentTarget.style.transform = 'translateY(0)';
                                            e.currentTarget.style.borderColor = 'var(--color-border)';
                                        }}
                                    >
                                        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                                            <div style={{
                                                width: '40px',
                                                height: '40px',
                                                borderRadius: '10px',
                                                background: 'rgba(99, 102, 241, 0.1)',
                                                color: '#6366f1',
                                                display: 'flex',
                                                alignItems: 'center',
                                                justifyContent: 'center'
                                            }}>
                                                <link.icon size={20} />
                                            </div>
                                            <div style={{ fontWeight: 600 }}>{link.name}</div>
                                        </div>
                                        <p style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)', lineHeight: '1.5' }}>
                                            {link.desc}
                                        </p>
                                        <div style={{
                                            display: 'flex',
                                            alignItems: 'center',
                                            gap: '0.25rem',
                                            fontSize: 'var(--text-xs)',
                                            fontWeight: 600,
                                            color: '#6366f1',
                                            marginTop: 'auto'
                                        }}>
                                            Enter <ArrowRight size={14} />
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    ))}
                </div>
            </main>
        </div>
    );
};

export default ApprovalDashboard;
