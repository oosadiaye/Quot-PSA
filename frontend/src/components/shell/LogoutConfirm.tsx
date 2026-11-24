import { LogOut } from 'lucide-react';

interface LogoutConfirmProps {
  tenantName: string;
  onStay: () => void;
  onConfirm: () => void;
}

/** "Sign out?" dialog, shared by the menu bar and the launcher. */
export default function LogoutConfirm({ tenantName, onStay, onConfirm }: LogoutConfirmProps) {
  return (
    <div className="shell-modal-scrim" role="dialog" aria-modal="true" aria-labelledby="logout-title">
      <div className="shell-modal">
        <div className="shell-modal-icon"><LogOut size={28} /></div>
        <h3 id="logout-title">Sign Out?</h3>
        <p>You are about to sign out of <strong>{tenantName}</strong>. Any unsaved changes will be lost.</p>
        <div className="shell-modal-actions">
          <button type="button" className="shell-btn" onClick={onStay}>Stay</button>
          <button type="button" className="shell-btn shell-btn-danger" onClick={onConfirm}>Sign Out</button>
        </div>
      </div>
    </div>
  );
}
