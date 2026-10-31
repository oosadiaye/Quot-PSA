/**
 * ReferenceField: pick the record a field points at by searching for it, instead of typing its database ID.
 * Shows the chosen record by name. When the target cannot be resolved it degrades to a plain ID box, with a note.
 */
import React from 'react';
import { useQuery } from '@tanstack/react-query';
import apiClient from '../../api/client';
import SearchableSelect from '../../components/SearchableSelect';
import { describeRecord, resolveReferencePath } from './referenceRegistry';
import type { EntityField } from './types';

interface ReferenceFieldProps {
  field: EntityField;
  value: unknown;
  onChange: (value: number | '') => void;
  id: string;
  invalid?: boolean;
}

interface Option {
  value: string;
  label: string;
  sublabel?: string;
}

const MAX_RESULTS = 25;
const asList = (data: any): Record<string, any>[] => (Array.isArray(data) ? data : data?.results ?? []);
const toOption = (row: Record<string, any>): Option => ({ value: String(row.id), label: describeRecord(row), sublabel: `ID ${row.id}` });

export const ReferenceField: React.FC<ReferenceFieldProps> = ({ field, value, onChange, id, invalid }) => {
  const reference = field.reference!;
  const target = useQuery({
    queryKey: ['reference-path', reference.module, reference.entity],
    queryFn: () => resolveReferencePath(reference),
    staleTime: Infinity,
  });
  const path = target.data ?? null;
  const selectedId = value === '' || value === null || value === undefined ? '' : String(value);

  const selected = useQuery({
    queryKey: ['reference-record', path, selectedId],
    queryFn: async () => toOption((await apiClient.get(`${path}${selectedId}/`)).data),
    enabled: !!path && !!selectedId,
    staleTime: 60_000,
    retry: false,
  });

  if (target.isLoading) {
    return <div id={id} className="ef-input" aria-busy="true" style={{ color: 'var(--color-text-subtle)' }}>Loading…</div>;
  }

  if (!path) {
    // Unknown target: keep the form usable by asking for the ID, and say so rather than looking broken.
    return (
      <>
        <input
          id={id}
          className="ef-input num"
          type="number"
          inputMode="numeric"
          aria-invalid={invalid || undefined}
          value={selectedId}
          placeholder="Record ID"
          onChange={(e) => onChange(e.target.value === '' ? '' : Number(e.target.value))}
        />
        <p className="ef-hint">Enter the ID of the linked record.</p>
      </>
    );
  }

  const search = async (query: string): Promise<Option[]> => {
    const data = (await apiClient.get(path, { params: { search: query, page_size: MAX_RESULTS } })).data;
    return asList(data).slice(0, MAX_RESULTS).map(toOption);
  };

  // The chosen record must be in `options` so its name shows before the person types anything.
  const options: Option[] = selected.data ? [selected.data] : selectedId ? [{ value: selectedId, label: `Record ${selectedId}` }] : [];

  return (
    <div id={id} className="ef-ref" aria-invalid={invalid || undefined}>
      <SearchableSelect
        options={options}
        value={selectedId}
        onChange={(v) => onChange(v === '' ? '' : Number(v))}
        onSearch={search}
        placeholder={`Search ${field.label.toLowerCase()}…`}
      />
    </div>
  );
};

export default ReferenceField;
