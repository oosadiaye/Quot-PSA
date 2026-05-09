import { chromium, request, FullConfig } from '@playwright/test';
import * as fs from 'node:fs';
import * as path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const STORAGE_PATH = path.resolve(__dirname, '../.auth/storage.json');
const SESSION_PATH = path.resolve(__dirname, '../.auth/session.json');

/**
 * Single API login + direct localStorage injection. Bypasses the
 * browser-side form to avoid triggering DRF throttling on the
 * `/api/v1/core/auth/login/` and `/select-tenant/` endpoints.
 *
 * Writes:
 *   .auth/session.json    — { token, tenantDomain }   (read by api.ts)
 *   .auth/storage.json    — Playwright storageState   (read by playwright.config use.storageState)
 */
export default async function globalSetup(_config: FullConfig): Promise<void> {
  const apiBase = process.env.E2E_API_URL ?? 'http://localhost:8000';
  const baseURL = process.env.E2E_BASE_URL ?? 'http://localhost:5173';
  const username = process.env.E2E_USER ?? 'admin@example.com';
  const password = process.env.E2E_PASSWORD ?? 'Admin@1234';

  fs.mkdirSync(path.dirname(STORAGE_PATH), { recursive: true });

  // 1. API login — single call.
  const apiCtx = await request.newContext({ baseURL: apiBase });
  const apiRes = await apiCtx.post('/api/v1/core/auth/login/', {
    data: { username, password },
  });
  if (!apiRes.ok()) {
    throw new Error(`globalSetup API login failed: ${apiRes.status()} ${await apiRes.text()}`);
  }
  const apiJson = await apiRes.json();
  const token: string = apiJson.token ?? apiJson.access ?? apiJson.access_token;
  const user = apiJson.user;
  const tenants: Array<{ id: number; name: string; domain: string; role?: string }> =
    apiJson.tenants ?? [];
  const tenant = tenants[0];
  const tenantDomain = process.env.E2E_TENANT_DOMAIN || tenant?.domain || null;
  fs.writeFileSync(SESSION_PATH, JSON.stringify({ token, tenantDomain }), 'utf8');

  // 2. Select tenant — also single call. If throttled, fall back to using
  //    the tenant + permissions from /my/ (cached on the user object).
  let permissions: string[] = [];
  if (tenant) {
    const selRes = await apiCtx.post('/api/v1/core/auth/select-tenant/', {
      data: { tenant_id: tenant.id },
      headers: { Authorization: `Token ${token}` },
    });
    if (selRes.ok()) {
      const selJson = await selRes.json();
      permissions = selJson.permissions ?? [];
    }
  }
  await apiCtx.dispose();

  // 3. Pre-seed auth into both localStorage and sessionStorage on a blank
  //    page rooted at the SPA origin. No form submission, no throttle hit.
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ baseURL });
  const page = await ctx.newPage();
  await page.goto(`${baseURL}/`);
  await page.evaluate(
    ({ token, user, tenant, permissions }) => {
      const setBoth = (k: string, v: string) => {
        localStorage.setItem(k, v);
        sessionStorage.setItem(k, v);
      };
      setBoth('authToken', token);
      setBoth('user', JSON.stringify(user));
      if (tenant) {
        setBoth('tenantDomain', tenant.domain);
        setBoth('tenantInfo', JSON.stringify(tenant));
        setBoth('tenantPermissions', JSON.stringify(permissions));
        setBoth('activeTenant', tenant.name || tenant.domain);
      }
    },
    { token, user, tenant, permissions },
  );
  await ctx.storageState({ path: STORAGE_PATH });
  await browser.close();
}
