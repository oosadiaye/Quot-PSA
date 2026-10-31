import ModuleCrudPage from '../_base/ModuleCrudPage';
import BudgetHandoff from './BudgetHandoff';
import { moduleConfig } from './config';

export default function BudgetPrepPage() {
  return <ModuleCrudPage config={moduleConfig} banner={<BudgetHandoff />} />;
}
