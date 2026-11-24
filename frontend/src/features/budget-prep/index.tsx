import ModuleCrudPage from '../_base/ModuleCrudPage';
import BudgetHandoff from './BudgetHandoff';
import MtefFramework from './mtef/MtefFramework';
import { moduleConfig } from './config';

export default function BudgetPrepPage() {
  return (
    <ModuleCrudPage
      config={moduleConfig}
      banner={({ activeKey }) => (activeKey === 'mtefProjection' ? null : <BudgetHandoff />)}
      panel={({ openForm }) => <MtefFramework openForm={openForm} />}
    />
  );
}
