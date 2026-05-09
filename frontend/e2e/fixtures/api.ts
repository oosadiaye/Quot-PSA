import { APIRequestContext, request } from '@playwright/test';
import * as fs from 'node:fs';
import * as path from 'node:path';
import { fileURLToPath } from 'node:url';

export const API_BASE = process.env.E2E_API_URL ?? 'http://localhost:8000';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const SESSION_PATH = path.resolve(__dirname, '../.auth/session.json');

interface Session { token: string; tenantDomain: string | null }

function readSession(): Session {
  if (!fs.existsSync(SESSION_PATH)) {
    throw new Error(
      `Session not found at ${SESSION_PATH}. Did globalSetup run?`,
    );
  }
  return JSON.parse(fs.readFileSync(SESSION_PATH, 'utf8'));
}

export async function apiContext(): Promise<APIRequestContext> {
  const { token, tenantDomain } = readSession();
  const headers: Record<string, string> = { Authorization: `Token ${token}` };
  if (tenantDomain) headers['X-Tenant-Domain'] = tenantDomain;
  return request.newContext({
    baseURL: API_BASE,
    extraHTTPHeaders: headers,
  });
}

export interface AppropriationSnapshot {
  id: number;
  approved_amount: number;
  cached_total_committed: number | string | null;
  total_committed_live: number | string | null;
  available_balance: number | string;
}

async function getWithThrottleRetry(
  ctx: APIRequestContext,
  url: string,
  attempts = 3,
): Promise<ReturnType<APIRequestContext['get']> extends Promise<infer R> ? R : never> {
  let lastRes: any;
  for (let i = 0; i < attempts; i++) {
    lastRes = await ctx.get(url);
    if (lastRes.status() !== 429) return lastRes;
    // DRF throttle responses include `Retry-After` (seconds). Respect it
    // but cap the wait to keep tests bounded.
    const retryAfter = Number(lastRes.headers()['retry-after'] ?? 5);
    const waitMs = Math.min(retryAfter * 1000, 8_000);
    await new Promise((r) => setTimeout(r, waitMs));
  }
  return lastRes;
}

export async function fetchAppropriation(id: number): Promise<AppropriationSnapshot> {
  const ctx = await apiContext();
  const res = await getWithThrottleRetry(ctx, `/api/v1/budget/appropriations/${id}/`);
  if (!res.ok()) {
    throw new Error(`Appropriation fetch failed: ${res.status()} ${await res.text()}`);
  }
  return await res.json();
}
