import ModuleCrudPage from '../_base/ModuleCrudPage';
import { moduleConfig } from './config';
import DebtPosition from './DebtPosition';

export default function DebtModulePage() {
  return (
    <>
      <DebtPosition />
      <ModuleCrudPage config={moduleConfig} />
    </>
  );
}