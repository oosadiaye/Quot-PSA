import ModuleCrudPage from '../_base/ModuleCrudPage';
import RevenueActions from './RevenueActions';
import { moduleConfig } from './config';

export default function RevenueAdminPage() {
  return <ModuleCrudPage config={moduleConfig} banner={({ activeKey }) => <RevenueActions tab={activeKey} />} />;
}