import { useState } from 'react';
import { Camera } from 'lucide-react';
import type { CreateSnapshotPayload } from '@/types/snapshots';

interface Props {
  defaultSchema?: string;
  canEditSchema?: boolean;
  onSubmit: (payload: CreateSnapshotPayload) => void;
  isSubmitting?: boolean;
}

export function CreateSnapshotForm({
  defaultSchema = '',
  canEditSchema = true,
  onSubmit,
  isSubmitting = false,
}: Props) {
  const [schemaName, setSchemaName] = useState(defaultSchema);
  const [label, setLabel] = useState('');

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!schemaName.trim()) return;
    onSubmit({
      schema_name: schemaName.trim(),
      label: label.trim() || undefined,
    });
    setLabel('');
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="flex flex-wrap items-end gap-3 p-4 bg-gray-50 border-b border-gray-200"
    >
      {canEditSchema && (
        <div>
          <label
            className="block text-xs font-medium text-gray-700 mb-1"
            htmlFor="schema-name"
          >
            Schema name
          </label>
          <input
            id="schema-name"
            type="text"
            value={schemaName}
            onChange={(e) => setSchemaName(e.target.value)}
            placeholder="e.g. delta_state"
            className="px-3 py-2 text-sm border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
            required
          />
        </div>
      )}
      <div className="flex-1 min-w-[200px]">
        <label
          className="block text-xs font-medium text-gray-700 mb-1"
          htmlFor="snapshot-label"
        >
          Label (optional)
        </label>
        <input
          id="snapshot-label"
          type="text"
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          placeholder="e.g. pre FY26 budget import"
          maxLength={120}
          className="w-full px-3 py-2 text-sm border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
      </div>
      <button
        type="submit"
        disabled={isSubmitting || !schemaName.trim()}
        className="inline-flex items-center gap-1 px-3 py-2 text-sm font-medium text-white bg-blue-600 rounded hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
      >
        <Camera className="h-4 w-4" />
        {isSubmitting ? 'Creating…' : 'Create snapshot'}
      </button>
    </form>
  );
}
