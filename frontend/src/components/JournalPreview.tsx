import type { CSSProperties, ReactNode } from 'react';
import { AlertTriangle } from 'lucide-react';

/**
 * A compact DR/CR ledger preview for confirmation dialogs — shows the journal
 * a destructive/posting action will write, so the user can eyeball that debits
 * equal credits before confirming. Optional neutral `info` line and an amber
 * `note` callout sit under the ledger.
 */
export interface JournalPreviewLine {
  drcr: 'DR' | 'CR';
  account: string;
  amount: string;     // pre-formatted currency string
  indent?: boolean;   // credits are indented, T-account style
}

interface JournalPreviewProps {
  intro?: string;
  lines: JournalPreviewLine[];
  info?: ReactNode;   // neutral secondary line(s)
  note?: ReactNode;   // amber "cannot be undone / requires…" callout
  maxWidth?: number;
}

export default function JournalPreview({
  intro, lines, info, note, maxWidth = 320,
}: JournalPreviewProps) {
  return (
    <div style={{ maxWidth }}>
      {intro && <div style={introStyle}>{intro}</div>}
      <div style={cardStyle}>
        {lines.map((l, i) => (
          <div key={i} style={i === 0 ? rowStyle : { ...rowStyle, borderTop: '1px dashed #e2e8f0' }}>
            <span style={pillStyle}>{l.drcr}</span>
            <span style={l.indent ? { ...acctStyle, paddingLeft: 12 } : acctStyle}>{l.account}</span>
            <span style={amtStyle}>{l.amount}</span>
          </div>
        ))}
      </div>
      {info && <div style={infoStyle}>{info}</div>}
      {note && (
        <div style={noteStyle}>
          <AlertTriangle size={13} style={{ flexShrink: 0, marginTop: 1 }} />
          <span>{note}</span>
        </div>
      )}
    </div>
  );
}

const introStyle: CSSProperties = { fontSize: 12, color: '#64748b', marginBottom: 8 };
const cardStyle: CSSProperties = {
  border: '1px solid #e2e8f0', borderRadius: 10, overflow: 'hidden', background: '#f8fafc',
};
const rowStyle: CSSProperties = {
  display: 'flex', alignItems: 'center', gap: 8, padding: '7px 10px', fontSize: 12.5,
};
const pillStyle: CSSProperties = {
  fontFamily: 'monospace', fontWeight: 700, fontSize: 10.5,
  color: '#4338ca', background: '#eef2ff',
  borderRadius: 5, padding: '1px 6px', minWidth: 24, textAlign: 'center',
};
const acctStyle: CSSProperties = { color: '#334155', flex: 1, minWidth: 0 };
const amtStyle: CSSProperties = {
  fontFamily: 'monospace', fontWeight: 700, color: '#0f172a', whiteSpace: 'nowrap',
};
const infoStyle: CSSProperties = { marginTop: 8, fontSize: 11.5, color: '#64748b', lineHeight: 1.45 };
const noteStyle: CSSProperties = {
  marginTop: 10, display: 'flex', gap: 6, alignItems: 'flex-start',
  background: '#fffbeb', border: '1px solid #fde68a', borderRadius: 8,
  padding: '7px 10px', fontSize: 11.5, color: '#92400e', lineHeight: 1.45,
};
