import ModuleCrudPage from '../_base/ModuleCrudPage';
import WarrantPlanning from './WarrantPlanning';
import { moduleConfig } from './config';

export default function CashPlanningPage() {
  return <ModuleCrudPage config={moduleConfig} banner={<WarrantPlanning />} />;
}
