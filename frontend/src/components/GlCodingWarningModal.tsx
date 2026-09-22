/**
 * Amber, non-blocking warning shown before a posting commits when one or more
 * lines' descriptions don't look like they belong to the selected GL account.
 * Driven by `useGlCodingGuard`. "Post anyway" acknowledges and continues;
 * "Go back & fix" cancels so the operator can correct the coding.
 */
import { AlertTriangle, X } from 'lucide-react';
import type { GlCodingModalProps } from '../hooks/useGlCodingGuard';

const AMBER = '#d97706';
const AMBER_BG = '#fffbeb';
const AMBER_BORDER = '#fde68a';

export default function GlCodingWarningModal({ suspects, onConfirm, onCancel }: GlCodingModalProps) {
  if (!suspects || suspects.length === 0) return null;

  return (
    <div
      role="presentation"
      onClick={onCancel}
      style={{
        position: 'fixed', inset: 0, zIndex: 10000,
        background: 'rgba(0,0,0,0.45)', backdropFilter: 'blur(3px)',
        display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '1.5rem',
      }}
    >
      <div
        role="alertdialog"
        aria-modal="true"
        aria-label="Check GL coding"
        onClick={(e) => e.stopPropagation()}
        style={{
          background: '#fff', borderRadius: 16, width: 'min(560px, 96vw)',
          maxHeight: '86vh', display: 'flex', flexDirection: 'column',
          boxShadow: '0 24px 70px rgba(0,0,0,0.28)', overflow: 'hidden',
          borderTop: `4px solid ${AMBER}`,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12, padding: '18px 20px 12px' }}>
          <div style={{
            flexShrink: 0, width: 38, height: 38, borderRadius: 10,
            background: AMBER_BG, border: `1px solid ${AMBER_BORDER}`,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <AlertTriangle size={20} color={AMBER} />
          </div>
          <div style={{ flex: 1 }}>
            <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700, color: '#1e293b' }}>
              Check the GL account{suspects.length > 1 ? 's' : ''}
            </h3>
            <p style={{ margin: '3px 0 0', fontSize: 13, color: '#64748b' }}>
              {suspects.length === 1
                ? 'This line’s description doesn’t look like it belongs to the selected GL account. Make sure the coding is right.'
                : `${suspects.length} lines have a description that doesn’t look like it belongs to the selected GL account. Make sure the coding is right.`}
            </p>
          </div>
          <button
            onClick={onCancel}
            aria-label="Close"
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#94a3b8', padding: 4 }}
          >
            <X size={18} />
          </button>
        </div>

        <div style={{ overflow: 'auto', padding: '4px 20px 8px', display: 'flex', flexDirection: 'column', gap: 8 }}>
          {suspects.map((s, i) => (
            <div
              key={i}
              style={{
                background: AMBER_BG, border: `1px solid ${AMBER_BORDER}`,
                borderRadius: 10, padding: '10px 12px',
              }}
            >
              <div style={{ fontSize: 13, color: '#334155' }}>
                <span style={{ color: '#92400e', fontWeight: 700 }}>
                  {s.code ? `${s.code} · ` : ''}{s.name}
                </span>
              </div>
              <div style={{ fontSize: 13, color: '#475569', marginTop: 2 }}>
                Description: <em>“{s.description}”</em>
              </div>
              {s.reason && (
                <div style={{ fontSize: 12, color: AMBER, marginTop: 4, fontWeight: 600 }}>
                  {s.reason}
                </div>
              )}
            </div>
          ))}
        </div>

        <div style={{
          display: 'flex', justifyContent: 'flex-end', gap: 10,
          padding: '14px 20px', borderTop: '1px solid #f1f5f9',
        }}>
          <button
            onClick={onConfirm}
            style={{
              padding: '9px 16px', borderRadius: 9, border: '1px solid #e2e8f0',
              background: '#fff', color: '#475569', fontSize: 13, fontWeight: 600, cursor: 'pointer',
            }}
          >
            Post anyway
          </button>
          <button
            onClick={onCancel}
            style={{
              padding: '9px 18px', borderRadius: 9, border: 'none',
              background: AMBER, color: '#fff', fontSize: 13, fontWeight: 700, cursor: 'pointer',
            }}
          >
            Go back &amp; fix
          </button>
        </div>
      </div>
    </div>
  );
}
