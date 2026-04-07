import React from 'react';
import { useNavigate } from 'react-router-dom';
import DimensionManager from '../components/DimensionManager';
import AccountingLayout from '../AccountingLayout';
import { useIsDimensionsEnabled } from '../../../hooks/useTenantModules';
import {
    useFunctions,
    useCreateFunction,
    useUpdateFunction,
    useDeleteFunction,
    useBulkImportDimension,
} from '../hooks/useDimensions';

const FunctionManagement: React.FC = () => {
    const navigate = useNavigate();
    const { isEnabled: dimensionsEnabled, isLoading: modulesLoading } = useIsDimensionsEnabled();
    const { data: functions, isLoading } = useFunctions();
    const createMutation = useCreateFunction();
    const updateMutation = useUpdateFunction();
    const deleteMutation = useDeleteFunction();
    const importMutation = useBulkImportDimension('functions');

    if (!dimensionsEnabled && !modulesLoading) {
        return (
            <AccountingLayout>
                <div style={{ padding: '2rem', textAlign: 'center' }}>
                    <h2>Dimensions Module Disabled</h2>
                    <p>The dimensions module is not enabled for this tenant. Please enable it in SuperAdmin to manage Functions.</p>
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
                title="Functions"
                dimensionType="functions"
                dimensions={functions}
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

export default FunctionManagement;
