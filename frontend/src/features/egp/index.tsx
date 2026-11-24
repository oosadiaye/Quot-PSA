import ModuleCrudPage from '../_base/ModuleCrudPage';
import BidOpeningPanel from './BidOpeningPanel';
import { moduleConfig } from './config';

export default function EGPPage() {
  return (
    <ModuleCrudPage
      config={moduleConfig}
      banner={({ activeKey }) => (activeKey === 'tenderNotice' ? <BidOpeningPanel /> : null)}
    />
  );
}
