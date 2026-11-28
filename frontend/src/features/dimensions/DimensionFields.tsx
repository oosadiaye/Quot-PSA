import { Select } from 'antd';
import type { FormDimension, Tags } from './api';

interface Props {
  dimensions: FormDimension[];
  value: Tags;
  onChange: (next: Tags) => void;
  /** 'inline': compact stack for a table cell (the placeholder names each one); 'row': labelled, side by side, wrapping;
   *  'stacked': labelled, one under another. */
  layout?: 'inline' | 'row' | 'stacked';
  /** Prefix for test ids, so several sets on one page stay distinguishable. */
  idPrefix?: string;
  disabled?: boolean;
}

/** The values of a dimension that can be picked now: a child only offers the children of the parent already chosen. */
export function optionsFor(dimension: FormDimension, value: Tags) {
  const parentValue = dimension.parent_type ? value[dimension.parent_type] : undefined;
  return dimension.values
    .filter((v) => !parentValue || !v.parent || v.parent === parentValue)
    .map((v) => ({ value: v.code, label: `${v.code} — ${v.name}` }));
}

/** Drops chosen values that no longer fit under their parent after the parent changed. */
export function withoutOrphans(dimensions: FormDimension[], next: Tags): Tags {
  const cleaned: Tags = { ...next };
  for (const d of dimensions) {
    const chosen = cleaned[d.code];
    if (!chosen || !d.parent_type || !cleaned[d.parent_type]) continue;
    const v = d.values.find((x) => x.code === chosen);
    if (v?.parent && v.parent !== cleaned[d.parent_type]) delete cleaned[d.code];
  }
  return cleaned;
}

export default function DimensionFields({ dimensions, value, onChange, layout = 'stacked', idPrefix = 'dim', disabled }: Props) {
  if (!dimensions.length) return null;
  return (
    <div style={{ display: 'flex', flexDirection: layout === 'row' ? 'row' : 'column', flexWrap: 'wrap', gap: layout === 'inline' ? 4 : 12 }}>
      {dimensions.map((d) => (
        <label key={d.code} style={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 150 }}>
          {/* In a table cell the placeholder names the dimension; stacked forms show a label above it. */}
          {layout !== 'inline' && (
            <span style={{ fontSize: 'var(--text-xs, 12px)', fontWeight: 600, color: 'var(--color-text-muted, #666)' }}>
              {d.name}{d.required ? ' *' : ''}
            </span>
          )}
          <Select
            data-testid={`${idPrefix}-${d.code}`}
            aria-label={d.name}
            size="small"
            allowClear={!d.required}
            showSearch
            optionFilterProp="label"
            placeholder={`${d.name}${d.required ? ' *' : ''}`}
            disabled={disabled}
            value={value[d.code] || undefined}
            options={optionsFor(d, value)}
            onChange={(v?: string) => {
              const next = { ...value };
              if (v) next[d.code] = v; else delete next[d.code];
              onChange(withoutOrphans(dimensions, next));
            }}
          />
        </label>
      ))}
    </div>
  );
}
