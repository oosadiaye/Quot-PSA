import ModuleCrudPage from '../_base/ModuleCrudPage';
import AdvanceActions from './AdvanceActions';
import { moduleConfig } from './config';

export default function StaffAdvancesPage() {
  return <ModuleCrudPage config={moduleConfig} banner={({ activeKey }) => <AdvanceActions tab={activeKey} />} />;
}