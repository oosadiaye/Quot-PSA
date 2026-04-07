import React from 'react';
import { useNavigate } from 'react-router-dom';
import DimensionManager from '../components/DimensionManager';
import AccountingLayout from '../AccountingLayout';
import { useIsDimensionsEnabled } from '../../../hooks/useTenantModules';
import {
    useGeos,
    useCreateGeo,
    useUpdateGeo,
    useDeleteGeo,
    useBulkImportDimension,
} from '../hooks/useDimensions';

const GeoManagement: React.FC = () => {
    const navigate = useNavigate();
    const { isEnabled: dimensionsEnabled, isLoading: modulesLoading } = useIsDimensionsEnabled();
    const { data: geos, isLoading } = useGeos();
    const createMutation = useCreateGeo();
    const updateMutation = useUpdateGeo();
    const deleteMutation = useDeleteGeo();
    const importMutation = useBulkImportDimension('geos');

    if (!dimensionsEnabled && !modulesLoading) {
        return (
            <AccountingLayout>
                <div style={{ padding: '2rem', textAlign: 'center' }}>
                    <h2>Dimensions Module Disabled</h2>
                    <p>The dimensions module is not enabled for this tenant. Please enable it in SuperAdmin to manage Geographic Locations.</p>
                    <button
                        className="btn btn-primary"
                        onClick={() => navigate('/accounting')}
                        style={{ marginTop: '1rem' }}
                    >
                        Back to Accounting
                    </button>
                </div>
            </AccountingLayout>
        );
    }

    return (
        <AccountingLayout>
            <DimensionManager
                title="Geographic Locations"
                dimensionType="geos"
                dimensions={geos}
                isLoading={isLoading}
                onCreate={(data) => createMutation.mutate(data)}
                onUpdate={(id, data) => updateMutation.mutate({ id, data })}
                onDelete={(id) => deleteMutation.mutate(id)}
                onBulkImport={(file) => importMutation.mutateAsync(file)}
                isCreating={createMutation.isPending}
                isUpdating={updateMutation.isPending}
                isImporting={importMutation.isPending}
            />
        </AccountingLayout>
    );
};

export default GeoManagement;
