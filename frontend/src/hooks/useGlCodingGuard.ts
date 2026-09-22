/**
 * GL coding guard — run the advisory description-vs-account check before a
 * posting form submits, and surface an amber warning when a line's GL looks
 * wrong. Non-blocking: on a warning the user may "Post anyway".
 *
 * Usage in a form:
 *   const gl = useGlCodingGuard();
 *   // in the submit handler, instead of calling doSubmit() directly:
 *   gl.guard(lines.map(l => ({ name: accountName(l), code: accountCode(l), description: l.description })), doSubmit);
 *   // render once: <GlCodingWarningModal {...gl.modalProps} />
 */
import { useCallback, useRef, useState } from 'react';
import apiClient from '../api/client';

export interface GlCheckLine {
  name: string;
  code?: string;
  description: string;
}

export interface GlSuspect {
  name: string;
  code?: string;
  description: string;
  reason: string;
}

interface CheckResult {
  index: number;
  name: string;
  code: string;
  description: string;
  verdict: 'ok' | 'suspect';
  reason: string;
}

export interface GlCodingModalProps {
  suspects: GlSuspect[] | null;
  onConfirm: () => void;
  onCancel: () => void;
}

export function useGlCodingGuard() {
  const [suspects, setSuspects] = useState<GlSuspect[] | null>(null);
  const [checking, setChecking] = useState(false);
  const proceedRef = useRef<(() => void) | null>(null);

  const guard = useCallback(async (lines: GlCheckLine[], onProceed: () => void) => {
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
        .map((r) => ({ name: r.name, code: r.code, description: r.description, reason: r.reason }));
      if (bad.length > 0) {
        proceedRef.current = onProceed;
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
    setSuspects(null);
    fn?.();
  }, []);

  const onCancel = useCallback(() => {
    proceedRef.current = null;
    setSuspects(null);
  }, []);

  const modalProps: GlCodingModalProps = { suspects, onConfirm, onCancel };
  return { guard, checking, modalProps };
}
