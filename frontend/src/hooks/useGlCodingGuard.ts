/**
 * GL coding guard — run the advisory description-vs-account check before a
 * posting form submits, and surface an amber warning when a line's GL looks
 * wrong. Non-blocking: on a warning the user may "Post anyway", go back, or —
 * when the form passes `onAdopt` — adopt one of the existing GL accounts the
 * server suggests for the line's description.
 *
 * Usage in a form:
 *   const gl = useGlCodingGuard();
 *   // in the submit handler, instead of calling doSubmit() directly:
 *   gl.guard(
 *     lines.map(l => ({ name: accountName(l), code: accountCode(l), description: l.description })),
 *     doSubmit,
 *     (index, acct) => setLineAccount(index, acct.id),   // optional: enables "Use this account"
 *     (acct) => accountMeta.has(String(acct.id)),        // optional: only offer pickable accounts
 *   );
 *   // render once: <GlCodingWarningModal {...gl.modalProps} />
 */
import { useCallback, useRef, useState } from 'react';
import apiClient from '../api/client';

export interface GlCheckLine {
  name: string;
  code?: string;
  description: string;
}

export interface GlSuggestion {
  id: number;
  code: string;
  name: string;
  account_type: string;
  score: number;
  /** `name` = account name fits the description; `history` = past postings like this used it. */
  source: 'name' | 'history';
}

export interface GlSuspect {
  /** Index of the line in the array passed to `guard` (so the form can recode it). */
  index: number;
  name: string;
  code?: string;
  description: string;
  reason: string;
  suggestions: GlSuggestion[];
}

interface CheckResult {
  index: number;
  name: string;
  code: string;
  description: string;
  verdict: 'ok' | 'suspect';
  reason: string;
  suggestions?: GlSuggestion[];
}

export interface GlCodingModalProps {
  suspects: GlSuspect[] | null;
  /** True when the form can recode a line, i.e. suggestions are actionable. */
  canAdopt: boolean;
  onAdopt: (suspect: GlSuspect, suggestion: GlSuggestion) => void;
  onConfirm: () => void;
  onCancel: () => void;
}

export function useGlCodingGuard() {
  const [suspects, setSuspects] = useState<GlSuspect[] | null>(null);
  const [checking, setChecking] = useState(false);
  const proceedRef = useRef<(() => void) | null>(null);
  const adoptRef = useRef<((index: number, s: GlSuggestion) => void) | null>(null);

  const guard = useCallback(async (
    lines: GlCheckLine[],
    onProceed: () => void,
    onAdopt?: (index: number, suggestion: GlSuggestion) => void,
    /** Hide suggestions the form's account picker can't actually select. */
    canUse?: (suggestion: GlSuggestion) => boolean,
  ) => {
    // Only lines with both a GL name and a description can be judged.
    const clean = lines
      .map((l, i) => ({
        index: i,
        name: (l.name || '').trim(),
        code: (l.code || '').trim(),
        description: (l.description || '').trim(),
      }))
      .filter((l) => l.name && l.description);

    if (clean.length === 0) {
      onProceed();
      return;
    }

    setChecking(true);
    try {
      const { data } = await apiClient.post('/accounting/gl-coding-check/', { lines: clean });
      const bad: GlSuspect[] = ((data?.results as CheckResult[]) || [])
        .filter((r) => r.verdict === 'suspect')
        .map((r) => ({
          index: r.index, name: r.name, code: r.code, description: r.description,
          reason: r.reason,
          suggestions: (r.suggestions || []).filter((g) => !onAdopt || !canUse || canUse(g)),
        }));
      if (bad.length > 0) {
        proceedRef.current = onProceed;
        adoptRef.current = onAdopt ?? null;
        setSuspects(bad);
        return;
      }
      onProceed();
    } catch {
      // Advisory only — a failed check must never block a posting.
      onProceed();
    } finally {
      setChecking(false);
    }
  }, []);

  const onConfirm = useCallback(() => {
    const fn = proceedRef.current;
    proceedRef.current = null;
    adoptRef.current = null;
    setSuspects(null);
    fn?.();
  }, []);

  const onCancel = useCallback(() => {
    proceedRef.current = null;
    adoptRef.current = null;
    setSuspects(null);
  }, []);

  // Adopting recodes the line in the form and drops it from the warning. Once
  // every flagged line is resolved the modal closes WITHOUT submitting, so the
  // operator reviews the recoded lines and posts again (which re-checks them).
  const onAdopt = useCallback((suspect: GlSuspect, suggestion: GlSuggestion) => {
    adoptRef.current?.(suspect.index, suggestion);
    setSuspects((cur) => {
      const left = (cur || []).filter((x) => x.index !== suspect.index);
      if (left.length === 0) {
        proceedRef.current = null;
        adoptRef.current = null;
        return null;
      }
      return left;
    });
  }, []);

  const modalProps: GlCodingModalProps = {
    suspects, canAdopt: adoptRef.current != null, onAdopt, onConfirm, onCancel,
  };
  return { guard, checking, modalProps };
}
