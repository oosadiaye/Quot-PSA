/**
 * Write `e2e/.auth/storage.json` from a token you already hold.
 *
 * `global-setup.ts` obtains one by logging in, which is right for CI. On a
 * developer machine the seeded e2e account often does not exist, so this
 * takes the token directly instead:
 *
 *   node scripts/seed-e2e-auth.mjs <token> [tenantDomain] [tenantName]
 *
 * Mint a token with:
 *   python manage.py shell -c "from rest_framework.authtoken.models import Token; \
 *     from django.contrib.auth import get_user_model; \
 *     print(Token.objects.get_or_create(user=get_user_model().objects.filter(is_superuser=True).first())[0].key)"
 *
 * `tenantInfo.role` must be present: `AuthContext.hasRole` returns false
 * when it is missing — before it checks `is_superuser` — so every
 * role-guarded route renders "Access Denied" without it.
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const [token, tenantDomain = 'delta.quotpse.ng', tenantName = 'Delta State Government'] =
    process.argv.slice(2);

if (!token) {
    console.error('usage: node scripts/seed-e2e-auth.mjs <token> [tenantDomain] [tenantName]');
    process.exit(1);
}

const origin = process.env.E2E_BASE_URL ?? 'http://127.0.0.1:5173';

const user = {
    id: 1, username: 'admin', email: 'admin@quotpse.ng',
    first_name: '', last_name: '', is_superuser: true,
    groups: [], permissions: [],
};
const tenantInfo = { id: 6, name: tenantName, domain: tenantDomain, role: 'admin' };

const entries = {
    authToken: token,
    user: JSON.stringify(user),
    tenantDomain,
    tenantInfo: JSON.stringify(tenantInfo),
    tenantPermissions: JSON.stringify(['__all__']),
    activeTenant: tenantName,
};

const state = {
    cookies: [],
    origins: [{
        origin,
        localStorage: Object.entries(entries).map(([name, value]) => ({ name, value })),
    }],
};

const out = path.resolve(__dirname, '../e2e/.auth/storage.json');
fs.mkdirSync(path.dirname(out), { recursive: true });
fs.writeFileSync(out, JSON.stringify(state, null, 2), 'utf8');
console.log(`wrote ${out} for origin ${origin}`);
