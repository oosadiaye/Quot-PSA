import ModuleCrudPage from '../_base/ModuleCrudPage';
import { moduleConfig } from './config';

export default function DebtModulePage() {
  return <ModuleCrudPage config={moduleConfig} />;
}