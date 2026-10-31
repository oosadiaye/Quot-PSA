import ModuleCrudPage from '../_base/ModuleCrudPage';
import PayrollFunding from './PayrollFunding';
import { moduleConfig } from './config';

export default function PersonnelBudgetPage() {
  return <ModuleCrudPage config={moduleConfig} banner={<PayrollFunding />} />;
}
