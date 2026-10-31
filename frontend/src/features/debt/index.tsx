import ModuleCrudPage from '../_base/ModuleCrudPage';
import { moduleConfig } from './config';
import DebtPosition from './DebtPosition';

export default function DebtModulePage() {
  return <ModuleCrudPage config={moduleConfig} banner={<DebtPosition />} />;
}
