import { useSkills } from '../hooks/useHrm';
import Sidebar from '../../../components/Sidebar';
import PageHeader from '../../../components/PageHeader';
import LoadingScreen from '../../../components/common/LoadingScreen';
import { Award, User } from 'lucide-react';

const SkillList = () => {
    const { data: skillsData, isLoading } = useSkills();

    const skills = skillsData?.results || skillsData || [];

    if (isLoading) return <LoadingScreen message="Loading skills..." />;

    return (
        <div style={{ display: 'flex' }}>
            <Sidebar />
            <main style={{ flex: 1, marginLeft: '260px', padding: '2.5rem' }}>
                <PageHeader
                    title="Skills"
                    subtitle="View employee skills and competencies"
                    icon={<Award size={22} color="white" />}
                />

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(250px, 1fr))', gap: '1rem' }}>
                    {skills.length === 0 ? (
                        <div className="card" style={{ textAlign: 'center', padding: '3rem', gridColumn: '1 / -1' }}><Award size={48} style={{ color: 'var(--color-text-muted)', marginBottom: '1rem' }} /><p>No skills found</p></div>
                    ) : (
                        skills.map((skill: any) => (
                            <div key={skill.id} className="card" style={{ padding: '1.25rem' }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                                    <div style={{ width: '40px', height: '40px', borderRadius: '8px', background: 'rgba(245, 158, 11, 0.1)', color: '#f59e0b', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><Award size={20} /></div>
                                    <div style={{ flex: 1 }}>
                                        <div style={{ fontWeight: 600 }}>{skill.name}</div>
                                        {skill.category && <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)' }}>{skill.category}</div>}
                                    </div>
                                </div>
                                {skill.employee_count !== undefined && (
                                    <div style={{ marginTop: '0.75rem', paddingTop: '0.75rem', borderTop: '1px solid var(--color-border)', fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)', display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                                        <User size={14} /> {skill.employee_count} employees
                                    </div>
                                )}
                            </div>
                        ))
                    )}
                </div>
            </main>
        </div>
    );
};

export default SkillList;
