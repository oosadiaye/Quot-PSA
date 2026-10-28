/**
 * Master-data duplicate lookup — warn before a near-duplicate Vendor / GL
 * account / MDA / … is created, and let the operator adopt the existing record.
 *
 * Two entry points sharing one endpoint (`POST /core/duplicate-check/`):
 *
 *   // 1. As-you-type hint under the name field
 *   const { matches } = useDuplicateLookup('vendor', { name, code, tax_id }, { excludeId: editing?.id });
 *   <DuplicateHint matches={matches} onUseExisting={adopt} />
 *
 *   // 2. Submit-time guard (catches what was never typed into a watched field)
 *   const dup = useDuplicateGuard('vendor');
 *   dup.guard(values, () => doSave(), { excludeId, onUseExisting: adopt });
 *   <DuplicateWarningModal {...dup.modalProps} />
 *
 * Advisory only: a failed lookup never blocks a save.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import apiClient from '../api/client';

export type DupEntity =
  | 'vendor' | 'account' | 'mda' | 'admin_segment'
  | 'vendor_category' | 'asset_category' | 'item'
  | 'ncoa_fund' | 'ncoa_functional' | 'ncoa_programme' | 'ncoa_geographic' | 'tsa_account';

export type DupLevel = 'exact' | 'likely' | 'similar';

export const LEVEL_LABEL: Record<DupLevel, string> = {
  exact: 'Already exists',
  likely: 'Likely duplicate',
  similar: 'Similar',
};

export interface DupMatch {
  id: number;
  code: string;
  name: string;
  is_active: boolean;
  level: DupLevel;
  score: number;
  reasons: string[];
  extra: Record<string, unknown>;
}

export async function fetchDuplicates(
  entity: DupEntity,
  values: Record<string, unknown>,
  excludeId?: number | string | null,
): Promise<{ label: string; matches: DupMatch[] }> {
  try {
    const { data } = await apiClient.post('/core/duplicate-check/', {
      entity,
      values,
      ...(excludeId != null && excludeId !== '' ? { exclude_id: excludeId } : {}),
    });
    return { label: data?.label || '', matches: (data?.matches as DupMatch[]) || [] };
  } catch {
    // Advisory only — never block data entry on a lookup failure.
    return { label: '', matches: [] };
  }
}

const hasAnyValue = (values: Record<string, unknown>) =>
  Object.values(values).some((v) => String(v ?? '').trim() !== '');

/** Debounced as-you-type lookup. */
export function useDuplicateLookup(
  entity: DupEntity,
  values: Record<string, unknown>,
  opts: { excludeId?: number | string | null; enabled?: boolean; debounceMs?: number } = {},
) {
  const { excludeId = null, enabled = true, debounceMs = 450 } = opts;
  const [matches, setMatches] = useState<DupMatch[]>([]);
  const [loading, setLoading] = useState(false);
  const seq = useRef(0);
  const key = JSON.stringify([entity, values, excludeId, enabled]);

  useEffect(() => {
    if (!enabled || !hasAnyValue(values)) {
      setMatches([]);
      setLoading(false);
      return;
    }
    const mine = ++seq.current;
    setLoading(true);
    const t = window.setTimeout(async () => {
      const res = await fetchDuplicates(entity, values, excludeId);
      if (mine === seq.current) {          // ignore out-of-order responses
        setMatches(res.matches);
        setLoading(false);
      }
    }, debounceMs);
    return () => window.clearTimeout(t);
    // `key` captures entity/values/excludeId/enabled by value.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, debounceMs]);

  return { matches, loading };
}

export interface DuplicateModalProps {
  label: string;
  matches: DupMatch[] | null;
  canAdopt: boolean;
  /** True when a matching code means the server will reject a create anyway. */
  blocksCreate: boolean;
  onUseExisting: (m: DupMatch) => void;
  onCreateAnyway: () => void;
  onCancel: () => void;
}

interface GuardOptions {
  excludeId?: number | string | null;
  /** Called when the operator picks "Use this one" for an existing record. */
  onUseExisting?: (m: DupMatch) => void;
}

/** Submit-time guard: check, and if anything matches ask before saving. */
export function useDuplicateGuard(entity: DupEntity) {
  const [state, setState] = useState<{ label: string; matches: DupMatch[] } | null>(null);
  const [checking, setChecking] = useState(false);
  const proceedRef = useRef<(() => void) | null>(null);
  const adoptRef = useRef<((m: DupMatch) => void) | null>(null);

  const guard = useCallback(
    async (values: Record<string, unknown>, onProceed: () => void, opts: GuardOptions = {}) => {
      if (!hasAnyValue(values)) {
        onProceed();
        return;
      }
      setChecking(true);
      try {
        const res = await fetchDuplicates(entity, values, opts.excludeId);
        if (res.matches.length > 0) {
          proceedRef.current = onProceed;
          adoptRef.current = opts.onUseExisting ?? null;
          setState(res);
          return;
        }
        onProceed();
      } finally {
        setChecking(false);
      }
    },
    [entity],
  );

  const close = useCallback(() => {
    proceedRef.current = null;
    adoptRef.current = null;
    setState(null);
  }, []);

  const modalProps: DuplicateModalProps = {
    label: state?.label || '',
    matches: state?.matches ?? null,
    canAdopt: adoptRef.current != null,
    blocksCreate: !!state?.matches.some((m) => m.reasons.includes('Same code')),
    onUseExisting: (m) => {
      const fn = adoptRef.current;
      close();
      fn?.(m);
    },
    onCreateAnyway: () => {
      const fn = proceedRef.current;
      close();
      fn?.();
    },
    onCancel: close,
  };

  return { guard, checking, modalProps };
}
