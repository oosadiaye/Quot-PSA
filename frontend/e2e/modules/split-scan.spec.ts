/**
 * Split & Duplicate Scan — the advisory procurement report.
 *
 * What is worth asserting here is not that a table renders. It is that
 * the page tells the truth about its own limits:
 *
 *   · it says plainly that it blocks nothing, because a reviewer who
 *     believes it enforces something will stop checking;
 *   · it distinguishes "no findings" from "descriptions not assessed" —
 *     collapsing those would let an AI outage read as a clean scan,
 *     which is the most dangerous wrong answer this page could give.
 *
 * The scan is run against whatever data the environment holds, so the
 * assertions are about shape and honesty rather than specific findings.
 */
import { test, expect } from '@playwright/test';

const ROUTE = '/procurement/split-scan';

/**
 * Playwright's `storageState` restores **localStorage only**; it has no
 * concept of sessionStorage. `api/client.ts` reads the auth token from
 * sessionStorage, so a restored session boots looking logged in — the
 * `user` object is there — and then every request goes out with no
 * Authorization header, earning a 401 and a "session expired" banner.
 *
 * Mirroring the auth keys across at init time is the fix. It runs before
 * any page script on every navigation, by which point storageState has
 * already populated localStorage.
 */
test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
        for (const key of ['authToken', 'user', 'tenantDomain', 'tenantInfo',
            'tenantPermissions', 'activeTenant']) {
            const value = localStorage.getItem(key);
            if (value !== null) sessionStorage.setItem(key, value);
        }
    });
});

test.describe('Split & Duplicate Scan', () => {
    test('states that it is advisory and enforces nothing', async ({ page }) => {
        await page.goto(ROUTE);
        await expect(page.getByRole('heading', { name: /Split & Duplicate Scan/i })).toBeVisible();
        // The disclaimer is load-bearing, not decoration.
        await expect(page.getByText(/Advisory only/i)).toBeVisible();
        await expect(page.getByText(/blocks, cancels or amends/i)).toBeVisible();
    });

    test('runs a scan and reports how many orders it looked at', async ({ page }) => {
        await page.goto(ROUTE);

        const response = page.waitForResponse(
            (r) => r.url().includes('/procurement/split-scan/') && r.request().method() === 'POST',
            { timeout: 60_000 },
        );
        await page.getByRole('button', { name: /Run scan/i }).click();
        const res = await response;
        expect(res.status()).toBe(200);

        const body = await res.json();
        expect(body).toHaveProperty('split_clusters');
        expect(body).toHaveProperty('duplicate_candidates');
        expect(body).toHaveProperty('ai_judging');
        expect(Array.isArray(body.split_clusters)).toBe(true);

        await expect(page.getByText(/orders? examined/i)).toBeVisible();
    });

    test('an AI outage never reads as a clean scan', async ({ page }) => {
        await page.goto(ROUTE);

        const response = page.waitForResponse(
            (r) => r.url().includes('/procurement/split-scan/') && r.request().method() === 'POST',
            { timeout: 60_000 },
        );
        await page.getByRole('button', { name: /Run scan/i }).click();
        const body = await (await response).json();

        // The arithmetic runs regardless of AI. When judging is off the page
        // must say so, rather than presenting an unjudged list as assessed.
        if (body.ai_judging === false) {
            await expect(page.getByText(/not assessed/i).first()).toBeVisible();
        }

        // Empty results are stated explicitly, never as a blank panel a
        // reader could mistake for a finding they missed.
        if (body.split_clusters.length === 0) {
            await expect(page.getByTestId('no-clusters')).toBeVisible();
        } else {
            await expect(page.getByTestId('cluster-table')).toBeVisible();
        }
        if (body.duplicate_candidates.length === 0) {
            await expect(page.getByTestId('no-duplicates')).toBeVisible();
        } else {
            await expect(page.getByTestId('duplicate-table')).toBeVisible();
        }
    });

    test('an invalid range is refused rather than silently widened', async ({ page }) => {
        await page.goto(ROUTE);
        await page.locator('#since').fill('2030-01-01');
        await page.locator('#until').fill('2020-01-01');

        const response = page.waitForResponse(
            (r) => r.url().includes('/procurement/split-scan/') && r.request().method() === 'POST',
            { timeout: 60_000 },
        );
        await page.getByRole('button', { name: /Run scan/i }).click();
        expect((await response).status()).toBe(400);
        await expect(page.getByText(/since must not be after until/i)).toBeVisible();
    });
});
