import { Alert, Button, Space, Typography } from 'antd';
import { LogoutOutlined, UserSwitchOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { useCallback } from 'react';
import { superadminApi } from '../api/superadmin';

const { Text } = Typography;

/**
 * Returns impersonation state from localStorage.
 * Stored as JSON: { sessionId, originalToken, originalUser, targetUser, targetTenant }
 */
export function getImpersonationState(): {
  sessionId: number;
  originalToken: string;
  originalUser: string;
  targetUser: string;
  targetTenant: string;
} | null {
  try {
    const raw = localStorage.getItem('impersonation');
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function isImpersonating(): boolean {
  return !!localStorage.getItem('impersonation');
}

/**
 * Banner displayed at the top of every page while a superadmin is impersonating a user.
 */
const ImpersonationBanner = () => {
  const navigate = useNavigate();
  const state = getImpersonationState();

  const handleStopImpersonation = useCallback(async () => {
    if (!state) return;

    try {
      await superadminApi.stopImpersonation(state.sessionId);
    } catch {
      // Best-effort – still restore original session
    }

    // Restore original superadmin session
    localStorage.setItem('authToken', state.originalToken);
    localStorage.setItem('user', state.originalUser);
    localStorage.removeItem('impersonation');
    localStorage.removeItem('tenantDomain');
    localStorage.removeItem('tenantInfo');
    localStorage.removeItem('tenantPermissions');

    // Navigate back to superadmin dashboard
    navigate('/superadmin');
    window.location.reload();
  }, [state, navigate]);

  if (!state) return null;

  return (
    <Alert
      banner
      type="warning"
      icon={<UserSwitchOutlined />}
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        zIndex: 9999,
        borderRadius: 0,
        background: 'linear-gradient(90deg, #faad14 0%, #fa8c16 100%)',
        border: 'none',
        padding: '6px 24px',
      }}
      title={
        <Space style={{ width: '100%', justifyContent: 'center' }}>
          <Text strong style={{ color: '#000' }}>
            Impersonating: {state.targetUser} in {state.targetTenant}
          </Text>
          <Button
            size="small"
            type="primary"
            danger
            icon={<LogoutOutlined />}
            onClick={handleStopImpersonation}
          >
            Return to SuperAdmin
          </Button>
        </Space>
      }
    />
  );
};

export default ImpersonationBanner;
