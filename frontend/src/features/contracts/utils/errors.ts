/**
 * Translate backend service-error envelope into toast-friendly strings.
 *
 * The contracts API uses `translate_service_errors()` on the server which
 * wraps domain exceptions in `{code, message, context}`. The API layer
 * returns them as HTTP 400/409 with body `{detail: {code, message, context}}`
 * or sometimes `{code, message, context}` at the top level.
 *
 * This helper is UI-side polish: it takes an axios error and returns a
 * human-readable message, preferring the structured code-specific
 * message when available.
 */
import type { AxiosError } from 'axios';

export interface ServiceErrorEnvelope {
  code: string;
  message: string;
  context?: Record<string, unknown>;
}

const CODE_HINTS: Record<string, string> = {
  CONTRACT_CEILING_BREACH: 'This action would exceed the contract ceiling.',
  IPC_DUPLICATE_HASH: 'An IPC with identical line items already exists.',
  VARIATION_TIER_REQUIRED: 'Variation exceeds tier threshold — needs higher approval.',
  RETENTION_RELEASE_BLOCKED: 'Retention cannot be released yet.',
  MOBILIZATION_RECOVERY_SHORT: 'Mobilization advance not fully recovered.',
  IPC_STATE_INVALID: 'IPC is not in a state that allows this action.',
  CONTRACT_NOT_ACTIVE: 'Contract is not active.',
};

export function extractServiceError(err: unknown): ServiceErrorEnvelope | null {
  const ax = err as AxiosError<any>;
  const body = ax?.response?.data;
  if (!body) return null;

  // Shape 1: {detail: {code, message, context}}
  if (body.detail && typeof body.detail === 'object' && 'code' in body.detail) {
    return body.detail as ServiceErrorEnvelope;
  }
  // Shape 2: top-level envelope
  if (typeof body === 'object' && 'code' in body && 'message' in body) {
    return body as ServiceErrorEnvelope;
  }
  return null;
}

/**
 * Stringify DRF field-level error bodies, e.g.
 *   { signed_date: ["Required for activation."],
 *     contract_start_date: ["Required for activation."] }
 * into "signed_date: Required for activation. · contract_start_date: ...".
 * Returns null if the body doesn't look like a field-error envelope.
 */
function formatFieldErrors(body: unknown): string | null {
  if (!body || typeof body !== 'object' || Array.isArray(body)) return null;
  const entries = Object.entries(body as Record<string, unknown>);
  if (!entries.length) return null;
  const parts: string[] = [];
  for (const [field, raw] of entries) {
    const msg = Array.isArray(raw)
      ? raw.map(String).join(' ')
      : typeof raw === 'string'
      ? raw
      : JSON.stringify(raw);
    parts.push(`${field}: ${msg}`);
  }
  return parts.join(' · ');
}

export function formatServiceError(err: unknown, fallback = 'Request failed'): string {
  const env = extractServiceError(err);
  if (env) {
    const hint = CODE_HINTS[env.code];
    return hint ? `${env.message} — ${hint}` : env.message;
  }

  const ax = err as AxiosError<any>;
  const body = ax?.response?.data;

  // Shape 3: DRF field-errors ({field: ["msg", ...], ...}) — very common
  // for Django ValidationError({...}) raised inside a service method.
  const fieldMsg = formatFieldErrors(body);
  if (fieldMsg) return fieldMsg;

  // Shape 4: {detail: "string"}
  if (typeof body?.detail === 'string') return body.detail;

  return ax?.message || fallback;
}
