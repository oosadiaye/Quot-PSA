import {
    useProductionQualityInspection, useCreateQualityInspectionFromProduction,
} from '../../hooks/useProduction';
import { Shield } from 'lucide-react';

interface Props {
    orderId: number;
    order: any;
}

const QualityTab = ({ orderId, order }: Props) => {
    const { data: inspection } = useProductionQualityInspection(orderId);
    const createInspection = useCreateQualityInspectionFromProduction();

    const requiresQI = order.bom_requires_quality_inspection;

    const handleCreate = async () => {
        await createInspection.mutateAsync({ id: orderId });
    };

    if (!requiresQI) {
        return (
            <div style={{ textAlign: 'center', padding: '48px 0', color: 'var(--color-text-muted)' }}>
                <div style={{ marginBottom: '12px' }}><Shield size={48} strokeWidth={1} /></div>
                <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '6px' }}>Quality Inspection Not Required</h3>
                <p style={{ fontSize: '13px' }}>This product does not require quality inspection. You can enable it in the BOM settings.</p>
            </div>
        );
    }

    if (!inspection) {
        return (
            <div style={{ textAlign: 'center', padding: '48px 0', color: 'var(--color-text-muted)' }}>
                <div style={{ marginBottom: '12px' }}><Shield size={48} strokeWidth={1} /></div>
                <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '6px' }}>No Quality Inspection</h3>
                <p style={{ fontSize: '13px', marginBottom: '16px' }}>Create a quality inspection to verify production output before completion</p>
                <button onClick={handleCreate} disabled={createInspection.isPending} style={{
                    padding: '9px 20px', borderRadius: '8px', fontSize: '13px', fontWeight: 600,
                    border: 'none', cursor: 'pointer', fontFamily: 'inherit',
                    background: 'linear-gradient(135deg, #0f1240, #191e6a)', color: 'white',
                    boxShadow: '0 4px 12px rgba(15,18,64,0.3)',
                }}>
                    {createInspection.isPending ? 'Creating...' : '+ Create Quality Inspection'}
                </button>
            </div>
        );
    }

    const statusColor = inspection.status === 'Pass' ? '#10b981' : inspection.status === 'Fail' ? '#ef4444' : '#f59e0b';

    return (
        <div>
            <div style={{
                background: 'var(--color-surface, #fff)', border: '1px solid var(--color-border)',
                borderRadius: '12px', padding: '20px', marginBottom: '16px',
            }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
                    <h3 style={{ fontSize: '14px', fontWeight: 700 }}>Quality Inspection: {inspection.inspection_number || `#${inspection.id}`}</h3>
                    <span style={{
                        padding: '5px 14px', borderRadius: '20px', fontSize: '11px', fontWeight: 700,
                        textTransform: 'uppercase', letterSpacing: '0.5px',
                        background: `${statusColor}1a`, color: statusColor,
                    }}>{inspection.status}</span>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '16px', fontSize: '13px' }}>
                    <div>
                        <div style={{ fontSize: '11px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px', color: 'var(--color-text-muted)', marginBottom: '4px' }}>Type</div>
                        <div style={{ fontWeight: 600 }}>{inspection.inspection_type || 'In-Process'}</div>
                    </div>
                    <div>
                        <div style={{ fontSize: '11px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px', color: 'var(--color-text-muted)', marginBottom: '4px' }}>Date</div>
                        <div style={{ fontWeight: 600 }}>{inspection.inspection_date || '\u2014'}</div>
                    </div>
                    <div>
                        <div style={{ fontSize: '11px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px', color: 'var(--color-text-muted)', marginBottom: '4px' }}>Inspector</div>
                        <div style={{ fontWeight: 600 }}>{inspection.inspector_name || '\u2014'}</div>
                    </div>
                </div>

                {inspection.notes && (
                    <div style={{ marginTop: '12px', padding: '10px 14px', borderRadius: '8px', background: 'var(--color-surface-hover, #f8fafc)', fontSize: '13px', color: 'var(--color-text-secondary)' }}>
                        {inspection.notes}
                    </div>
                )}

                <div style={{ marginTop: '16px', paddingTop: '12px', borderTop: '1px solid var(--color-border)', fontSize: '12px', color: 'var(--color-text-muted)' }}>
                    To edit inspection details, manage this inspection in the <strong>Quality</strong> module.
                </div>
            </div>
        </div>
    );
};

export default QualityTab;
