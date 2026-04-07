import Sidebar from '../../../components/Sidebar';
import PageHeader from '../../../components/PageHeader';
import { Plus, ArrowRight, Trash2, Sprout, X, Loader2, FileText } from 'lucide-react';
import { useState } from 'react';
import {
    useApprovalTemplates,
    useCreateApprovalTemplate,
    useDeleteApprovalTemplate,
    useApprovalGroups,
    useContentTypes,
    useSeedDefaultTemplates,
} from '../hooks/useWorkflow';

interface StepInput {
    group: string;
    sequence: number;
}

interface SeedResult {
    success: boolean;
    created_groups: number;
    skipped_groups: number;
    created_templates: number;
    skipped_templates: number;
    total_groups: number;
    total_templates: number;
}

const ApprovalTemplates = () => {
    const { data: templates, isLoading } = useApprovalTemplates();
    const { data: contentTypes } = useContentTypes();
    const { data: groupsData } = useApprovalGroups();
    const createTemplate = useCreateApprovalTemplate();
    const deleteTemplate = useDeleteApprovalTemplate();
    const seedDefaults = useSeedDefaultTemplates();

    const groups = groupsData?.results || groupsData || [];

    const [showForm, setShowForm] = useState(false);
    const [seedResult, setSeedResult] = useState<SeedResult | null>(null);
    const [form, setForm] = useState({
        name: '',
        description: '',
        content_type: '',
        approval_type: 'Sequential',
    });
    const [steps, setSteps] = useState<StepInput[]>([{ group: '', sequence: 1 }]);

    const addStep = () => {
        setSteps([...steps, { group: '', sequence: steps.length + 1 }]);
    };

    const removeStep = (idx: number) => {
        const updated = steps.filter((_, i) => i !== idx).map((s, i) => ({ ...s, sequence: i + 1 }));
        setSteps(updated.length ? updated : [{ group: '', sequence: 1 }]);
    };

    const updateStep = (idx: number, groupId: string) => {
        const updated = [...steps];
        updated[idx] = { ...updated[idx], group: groupId };
        setSteps(updated);
    };

    const resetForm = () => {
        setForm({ name: '', description: '', content_type: '', approval_type: 'Sequential' });
        setSteps([{ group: '', sequence: 1 }]);
        setShowForm(false);
    };

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        const validSteps = steps.filter(s => s.group);
        createTemplate.mutate(
            { ...form, steps: validSteps },
            { onSuccess: () => resetForm() },
        );
    };

    const handleSeed = () => {
        seedDefaults.mutate(undefined, {
            onSuccess: (data: SeedResult) => setSeedResult(data),
        });
    };

    const templateList = templates?.results || templates || [];

    return (
        <div style={{ display: 'flex' }}>
            <Sidebar />
            <main style={{ flex: 1, marginLeft: '260px', padding: '2.5rem' }}>
                <PageHeader
                    title="Approval Templates"
                    subtitle="Define approval workflows for different document types."
                    icon={<FileText size={22} color="white" />}
                    actions={
                        <div style={{ display: 'flex', gap: '0.75rem' }}>
                            <button
                                className="btn btn-outline"
                                onClick={handleSeed}
                                disabled={seedDefaults.isPending}
                                style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', borderColor: '#10b981', color: '#10b981' }}
                            >
                                {seedDefaults.isPending ? <Loader2 size={16} className="animate-spin" /> : <Sprout size={16} />}
                                Seed Defaults
                            </button>
                            <button className="btn btn-primary" onClick={() => setShowForm(!showForm)} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                <Plus size={18} /> New Template
                            </button>
                        </div>
                    }
                />

                {/* Seed result message */}
                {seedResult && (
                    <div className="card" style={{
                        marginBottom: '1.5rem',
                        padding: '1rem 1.25rem',
                        background: seedResult.created_templates > 0 ? 'rgba(16, 185, 129, 0.08)' : 'rgba(245, 158, 11, 0.08)',
                        border: `1px solid ${seedResult.created_templates > 0 ? '#10b981' : '#f59e0b'}`,
                    }}>
                        <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600, marginBottom: '0.5rem' }}>
                            {seedResult.created_templates > 0 ? 'Default Templates Created' : 'All Defaults Already Exist'}
                        </div>
                        <div style={{ display: 'flex', gap: '2rem', fontSize: 'var(--text-sm)', flexWrap: 'wrap' }}>
                            <div><span style={{ color: 'var(--color-text-muted)' }}>Groups Created: </span><strong style={{ color: '#10b981' }}>{seedResult.created_groups}</strong></div>
                            <div><span style={{ color: 'var(--color-text-muted)' }}>Groups Skipped: </span><strong style={{ color: '#f59e0b' }}>{seedResult.skipped_groups}</strong></div>
                            <div><span style={{ color: 'var(--color-text-muted)' }}>Templates Created: </span><strong style={{ color: '#10b981' }}>{seedResult.created_templates}</strong></div>
                            <div><span style={{ color: 'var(--color-text-muted)' }}>Templates Skipped: </span><strong style={{ color: '#f59e0b' }}>{seedResult.skipped_templates}</strong></div>
                        </div>
                    </div>
                )}

                {/* Create Form */}
                {showForm && (
                    <div className="card" style={{ marginBottom: '2rem', padding: '1.5rem' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem' }}>
                            <h3 style={{ margin: 0 }}>Create Approval Template</h3>
                            <button onClick={resetForm} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-text-muted)' }}>
                                <X size={18} />
                            </button>
                        </div>
                        <form onSubmit={handleSubmit}>
                            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '1rem', marginBottom: '1.25rem' }}>
                                <div>
                                    <label style={{ display: 'block', fontSize: 'var(--text-xs)', fontWeight: 600, marginBottom: '0.35rem', color: 'var(--color-text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                                        Template Name
                                    </label>
                                    <input
                                        className="input"
                                        placeholder="e.g. Purchase Order Approval"
                                        value={form.name}
                                        onChange={e => setForm({ ...form, name: e.target.value })}
                                        required
                                    />
                                </div>
                                <div>
                                    <label style={{ display: 'block', fontSize: 'var(--text-xs)', fontWeight: 600, marginBottom: '0.35rem', color: 'var(--color-text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                                        Description
                                    </label>
                                    <input
                                        className="input"
                                        placeholder="Brief description"
                                        value={form.description}
                                        onChange={e => setForm({ ...form, description: e.target.value })}
                                    />
                                </div>
                                <div>
                                    <label style={{ display: 'block', fontSize: 'var(--text-xs)', fontWeight: 600, marginBottom: '0.35rem', color: 'var(--color-text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                                        Document Type
                                    </label>
                                    <select
                                        className="input"
                                        value={form.content_type}
                                        onChange={e => setForm({ ...form, content_type: e.target.value })}
                                        required
                                    >
                                        <option value="">Select Document Type</option>
                                        {(contentTypes || []).map((ct: any) => (
                                            <option key={ct.id} value={ct.model}>{ct.label}</option>
                                        ))}
                                    </select>
                                </div>
                                <div>
                                    <label style={{ display: 'block', fontSize: 'var(--text-xs)', fontWeight: 600, marginBottom: '0.35rem', color: 'var(--color-text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                                        Approval Type
                                    </label>
                                    <select
                                        className="input"
                                        value={form.approval_type}
                                        onChange={e => setForm({ ...form, approval_type: e.target.value })}
                                    >
                                        <option value="Sequential">Sequential (One after another)</option>
                                        <option value="Parallel">Parallel (All at once)</option>
                                        <option value="Any">Any (One approval enough)</option>
                                    </select>
                                </div>
                            </div>

                            {/* Steps Builder */}
                            <div style={{ marginBottom: '1.25rem' }}>
                                <label style={{ display: 'block', fontSize: 'var(--text-xs)', fontWeight: 600, marginBottom: '0.5rem', color: 'var(--color-text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                                    Approval Steps
                                </label>
                                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                                    {steps.map((step, idx) => (
                                        <div key={idx} style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                                            <span style={{
                                                width: '28px', height: '28px', borderRadius: '50%',
                                                background: 'var(--color-primary)', color: 'white',
                                                display: 'flex', alignItems: 'center', justifyContent: 'center',
                                                fontSize: 'var(--text-xs)', fontWeight: 700, flexShrink: 0,
                                            }}>
                                                {step.sequence}
                                            </span>
                                            <select
                                                className="input"
                                                value={step.group}
                                                onChange={e => updateStep(idx, e.target.value)}
                                                style={{ flex: 1 }}
                                                required
                                            >
                                                <option value="">Select Approval Group</option>
                                                {groups.map((g: any) => (
                                                    <option key={g.id} value={g.id}>{g.name}</option>
                                                ))}
                                            </select>
                                            {steps.length > 1 && (
                                                <button
                                                    type="button"
                                                    onClick={() => removeStep(idx)}
                                                    style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--color-error)', padding: '0.25rem' }}
                                                >
                                                    <X size={16} />
                                                </button>
                                            )}
                                        </div>
                                    ))}
                                </div>
                                <button
                                    type="button"
                                    onClick={addStep}
                                    style={{
                                        marginTop: '0.5rem', background: 'none', border: '1px dashed var(--color-border)',
                                        borderRadius: '8px', padding: '0.5rem 1rem', cursor: 'pointer',
                                        color: 'var(--color-primary)', fontSize: 'var(--text-sm)', fontWeight: 600,
                                        display: 'flex', alignItems: 'center', gap: '0.35rem',
                                    }}
                                >
                                    <Plus size={14} /> Add Step
                                </button>
                            </div>

                            <button type="submit" className="btn btn-primary" disabled={createTemplate.isPending}>
                                {createTemplate.isPending ? 'Creating...' : 'Create Template'}
                            </button>
                        </form>
                    </div>
                )}

                {/* Loading */}
                {isLoading && (
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '200px' }}>
                        <Loader2 size={28} className="animate-spin" style={{ color: 'var(--color-primary)' }} />
                    </div>
                )}

                {/* Template Grid */}
                {!isLoading && (
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(400px, 1fr))', gap: '1.5rem' }}>
                        {templateList.map((template: any) => (
                            <div key={template.id} className="card" style={{ padding: '1.5rem' }}>
                                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1rem' }}>
                                    <div>
                                        <h3 style={{ marginBottom: '0.25rem' }}>{template.name}</h3>
                                        <span style={{
                                            fontSize: 'var(--text-xs)', padding: '0.15rem 0.5rem',
                                            background: 'var(--color-primary)', color: 'white',
                                            borderRadius: '0.25rem', textTransform: 'capitalize',
                                        }}>
                                            {template.content_type_name}
                                        </span>
                                    </div>
                                    <button
                                        className="btn btn-outline"
                                        style={{ color: 'var(--color-error)', padding: '0.35rem' }}
                                        onClick={() => deleteTemplate.mutate(template.id)}
                                    >
                                        <Trash2 size={16} />
                                    </button>
                                </div>
                                <p style={{ fontSize: 'var(--text-sm)', color: 'var(--color-text-muted)', marginBottom: '0.75rem' }}>
                                    {template.description || 'No description'}
                                </p>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: 'var(--text-sm)', marginBottom: '0.75rem' }}>
                                    <span style={{ color: 'var(--color-text-muted)' }}>Approval Type:</span>
                                    <span style={{
                                        fontWeight: 600, fontSize: 'var(--text-xs)', padding: '0.15rem 0.5rem',
                                        borderRadius: '0.25rem',
                                        background: template.approval_type === 'Sequential' ? 'rgba(59,130,246,0.1)' :
                                            template.approval_type === 'Parallel' ? 'rgba(245,158,11,0.1)' : 'rgba(16,185,129,0.1)',
                                        color: template.approval_type === 'Sequential' ? '#2471a3' :
                                            template.approval_type === 'Parallel' ? '#f59e0b' : '#10b981',
                                    }}>
                                        {template.approval_type}
                                    </span>
                                </div>

                                {/* Steps display */}
                                {template.steps && template.steps.length > 0 && (
                                    <div style={{ paddingTop: '0.75rem', borderTop: '1px solid var(--color-border)' }}>
                                        <div style={{ fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', marginBottom: '0.5rem', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                                            APPROVAL STEPS ({template.steps.length})
                                        </div>
                                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.25rem', flexWrap: 'wrap' }}>
                                            {template.steps.map((step: any, i: number) => (
                                                <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                                                    <span style={{
                                                        display: 'inline-flex', alignItems: 'center', gap: '0.35rem',
                                                        padding: '0.3rem 0.6rem', borderRadius: '999px',
                                                        background: 'rgba(59,130,246,0.08)', fontSize: 'var(--text-xs)', fontWeight: 500,
                                                    }}>
                                                        <span style={{
                                                            width: '18px', height: '18px', borderRadius: '50%',
                                                            background: 'var(--color-primary)', color: 'white',
                                                            display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                                                            fontSize: 'var(--text-xs)', fontWeight: 700,
                                                        }}>
                                                            {step.sequence}
                                                        </span>
                                                        {step.group_name || `Group ${step.group}`}
                                                    </span>
                                                    {i < template.steps.length - 1 && (
                                                        <ArrowRight size={12} style={{ color: 'var(--color-text-muted)' }} />
                                                    )}
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                )}
                                {(!template.steps || template.steps.length === 0) && (
                                    <div style={{ paddingTop: '0.75rem', borderTop: '1px solid var(--color-border)', fontSize: 'var(--text-xs)', color: 'var(--color-text-muted)', fontStyle: 'italic' }}>
                                        No approval steps configured
                                    </div>
                                )}
                            </div>
                        ))}
                    </div>
                )}

                {!isLoading && templateList.length === 0 && (
                    <div style={{
                        textAlign: 'center', padding: '3rem', color: 'var(--color-text-muted)',
                        border: '2px dashed var(--color-border)', borderRadius: '12px',
                    }}>
                        <p style={{ fontSize: 'var(--text-base)', marginBottom: '0.5rem' }}>No approval templates yet</p>
                        <p style={{ fontSize: 'var(--text-sm)' }}>
                            Click <strong>Seed Defaults</strong> to create standard templates, or <strong>New Template</strong> to create a custom one.
                        </p>
                    </div>
                )}
            </main>
        </div>
    );
};

export default ApprovalTemplates;
