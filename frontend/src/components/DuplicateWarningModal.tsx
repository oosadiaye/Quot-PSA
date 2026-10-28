/**
 * Amber, non-blocking prompt shown on save when the master record being created
 * looks like one that already exists. Driven by `useDuplicateGuard`.
 * "Use existing" adopts a record, "Create anyway" saves, "Go back" cancels.
 */
import { AlertTriangle, X } from 'lucide-react';
import { LEVEL_LABEL, type DuplicateModalProps } from '../hooks/useDuplicateCheck';

const AMBER = '#d97706';
const AMBER_BG = '#fffbeb';
const AMBER_BORDER = '#fde68a';

export default function DuplicateWarningModal({
  label, matches, canAdopt, blocksCreate, onUseExisting, onCreateAnyway, onCancel,
}: DuplicateModalProps) {
  if (!matches || matches.length === 0) return null;
  const noun = (label || 'record').toLowerCase();
  const hasExact = matches.some((m) => m.level === 'exact');

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
        aria-label={`Possible duplicate ${noun}`}
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
              {hasExact ? `This ${noun} already exists` : `A similar ${noun} already exists`}
            </h3>
            <p style={{ margin: '3px 0 0', fontSize: 13, color: '#64748b' }}>
              {canAdopt
                ? 'Use the existing record to avoid duplicates, or create a new one if this really is different.'
                : 'Check the existing record(s) below before creating a new one.'}
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
          {matches.map((m) => (
            <div
              key={m.id}
              style={{
                background: AMBER_BG, border: `1px solid ${AMBER_BORDER}`, borderRadius: 10,
                padding: '10px 12px', display: 'flex', alignItems: 'center', gap: 10,
              }}
            >
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 13, color: '#92400e', fontWeight: 700 }}>
                  {m.code ? `${m.code} · ` : ''}{m.name}
                  {!m.is_active && <em style={{ color: '#94a3b8', fontWeight: 400 }}> (inactive)</em>}
                </div>
                <div style={{ fontSize: 12, color: AMBER, marginTop: 2, fontWeight: 600 }}>
                  {LEVEL_LABEL[m.level]}{m.reasons.length ? ` — ${m.reasons.join(', ').toLowerCase()}` : ''}
                </div>
              </div>
              {canAdopt && (
                <button
                  onClick={() => onUseExisting(m)}
                  style={{
                    flexShrink: 0, padding: '7px 12px', borderRadius: 8, border: 'none',
                    background: AMBER, color: '#fff', fontSize: 12.5, fontWeight: 700, cursor: 'pointer',
                  }}
                >
                  Use this one
                </button>
              )}
            </div>
          ))}
        </div>

        <div style={{
          display: 'flex', justifyContent: 'flex-end', gap: 10,
          padding: '14px 20px', borderTop: '1px solid #f1f5f9',
        }}>
          {!blocksCreate && (
            <button
              onClick={onCreateAnyway}
              style={{
                padding: '9px 16px', borderRadius: 9, border: '1px solid #e2e8f0',
                background: '#fff', color: '#475569', fontSize: 13, fontWeight: 600, cursor: 'pointer',
              }}
            >
              Create anyway
            </button>
          )}
          <button
            onClick={onCancel}
            style={{
              padding: '9px 18px', borderRadius: 9, border: 'none',
              background: blocksCreate || !canAdopt ? AMBER : '#e2e8f0',
              color: blocksCreate || !canAdopt ? '#fff' : '#475569',
              fontSize: 13, fontWeight: 700, cursor: 'pointer',
            }}
          >
            Go back
          </button>
        </div>
      </div>
    </div>
  );
}
