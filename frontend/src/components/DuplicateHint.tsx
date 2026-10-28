/**
 * Inline, as-you-type "this may already exist" hint for master-data create
 * forms. Driven by `useDuplicateLookup`. Non-blocking.
 */
import { AlertTriangle } from 'lucide-react';
import { LEVEL_LABEL, type DupMatch } from '../hooks/useDuplicateCheck';

const AMBER = '#d97706';
const AMBER_BG = '#fffbeb';
const AMBER_BORDER = '#fde68a';

interface Props {
  matches: DupMatch[];
  label?: string;
  max?: number;
  onUseExisting?: (m: DupMatch) => void;
}

export default function DuplicateHint({ matches, label = 'record', max = 3, onUseExisting }: Props) {
  if (!matches || matches.length === 0) return null;
  const shown = matches.slice(0, max);
  return (
    <div
      role="status"
      style={{
        marginTop: 6, background: AMBER_BG, border: `1px solid ${AMBER_BORDER}`,
        borderRadius: 8, padding: '8px 10px', fontSize: 12.5, color: '#92400e',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontWeight: 700 }}>
        <AlertTriangle size={14} color={AMBER} />
        A similar {label.toLowerCase()} already exists — check before creating a new one.
      </div>
      <ul style={{ margin: '6px 0 0', padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 4 }}>
        {shown.map((m) => (
          <li key={m.id} style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <span style={{ color: '#334155' }}>
              <strong>{m.code ? `${m.code} · ` : ''}{m.name}</strong>
              {!m.is_active && <em style={{ color: '#94a3b8' }}> (inactive)</em>}
            </span>
            <span style={{ color: AMBER, fontWeight: 600 }}>
              {LEVEL_LABEL[m.level]}{m.reasons.length ? ` — ${m.reasons.join(', ').toLowerCase()}` : ''}
            </span>
            {onUseExisting && (
              <button
                type="button"
                onClick={() => onUseExisting(m)}
                style={{
                  marginLeft: 'auto', padding: '2px 10px', borderRadius: 6, cursor: 'pointer',
                  border: `1px solid ${AMBER}`, background: '#fff', color: AMBER, fontSize: 12, fontWeight: 600,
                }}
              >
                Use this
              </button>
            )}
          </li>
        ))}
      </ul>
      {matches.length > shown.length && (
        <div style={{ marginTop: 4, color: '#a16207' }}>+{matches.length - shown.length} more</div>
      )}
    </div>
  );
}
