/**
 * Mocked-API harness for `playwright.mock.config.ts`.
 *
 * `bootMock(page, handlers)` does two things before the SPA boots:
 *   1. seeds a signed-in superuser session (the SPA reads it from sessionStorage);
 *   2. answers every `/api/v1/**` request from `handlers`, falling back to an
 *      empty list for GET and `{}` for writes, and records each call so a spec
 *      can assert what the UI sent.
 */
import type { Page, Route } from '@playwright/test';

export const API = process.env.E2E_MOCK_API ?? 'http://127.0.0.1:8099';

export interface Call {
  method: string;
  path: string;            // path under /api/v1, e.g. /core/duplicate-check/
  query: URLSearchParams;
  // Arbitrary JSON sent by the app; specs assert on it with optional chaining.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  body: any;
}
export interface Reply { status?: number; body: unknown }
export type Handler = (c: Call) => Reply | undefined;

const USER = {
  id: 1, username: 'e2e', email: 'e2e@example.com',
  first_name: 'E2E', last_name: 'Tester', is_superuser: true, is_staff: true,
};
const TENANT = { id: 1, name: 'E2E Tenant', domain: 'e2e.local', role: 'admin' };

export const emptyList = { count: 0, next: null, previous: null, results: [] };

export async function bootMock(page: Page, handlers: Handler[] = []) {
  const calls: Call[] = [];

  await page.addInitScript(({ user, tenant }) => {
    const set = (k: string, v: string) => { if (sessionStorage.getItem(k) === null) sessionStorage.setItem(k, v); };
    set('authToken', 'e2e-token');
    set('user', JSON.stringify(user));
    set('tenantDomain', tenant.domain);
    set('tenantInfo', JSON.stringify(tenant));
    set('tenantPermissions', JSON.stringify(['__all__']));
    set('activeTenant', tenant.name);
  }, { user: USER, tenant: TENANT });

  await page.route(`${API}/**`, async (route: Route) => {
    const req = route.request();
    const origin = req.headers()['origin'] ?? '*';
    const cors = {
      'access-control-allow-origin': origin,
      'access-control-allow-credentials': 'true',
      'access-control-allow-headers': req.headers()['access-control-request-headers'] ?? '*',
      'access-control-allow-methods': 'GET,POST,PUT,PATCH,DELETE,OPTIONS',
    };
    if (req.method() === 'OPTIONS') {
      return route.fulfill({ status: 204, headers: cors });
    }

    const url = new URL(req.url());
    const path = url.pathname.replace(/^\/api\/v1/, '');
    let body: Call['body'] = null;
    try { body = req.postDataJSON(); } catch { body = req.postData(); }
    const call: Call = { method: req.method(), path, query: url.searchParams, body };
    calls.push(call);

    let reply: Reply | undefined;
    for (const h of handlers) { reply = h(call); if (reply) break; }
    if (!reply) {
      if (path === '/core/users/me/') reply = { body: USER };
      else if (req.method() === 'GET') reply = { body: emptyList };
      else reply = { body: {} };
    }
    return route.fulfill({
      status: reply.status ?? 200,
      headers: { ...cors, 'content-type': 'application/json' },
      body: JSON.stringify(reply.body),
    });
  });

  return {
    calls,
    /** Calls matching a method + path (exact). */
    find: (method: string, path: string) => calls.filter((c) => c.method === method && c.path === path),
  };
}

/** Handler: answer `POST /core/duplicate-check/` with `matches` when the entity matches. */
export const duplicateCheck = (entity: string, matches: unknown[], label = 'Record'): Handler => (c) =>
  c.method === 'POST' && c.path === '/core/duplicate-check/' && c.body?.entity === entity
    ? { body: { entity, label, matches } }
    : undefined;

export const dupMatch = (over: Record<string, unknown> = {}) => ({
  id: 7, code: 'X-007', name: 'Existing Record', is_active: true,
  level: 'likely', score: 0.97, reasons: ['Almost the same name'], extra: {}, ...over,
});
