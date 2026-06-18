import { test, expect } from '../fixtures/auth';

/**
 * Snapshots E2E — happy-path spec
 *
 * Route:  /settings/backups  → TenantSnapshotsPage (tenant-admin view)
 *
 * The test runs under the default E2E user (admin@example.com) which is
 * expected to have the `admin` role on the first tenant, giving access to
 * the ProtectedRoute that guards /settings/backups.
 *
 * Delete is a soft delete (Task 16): the backend transitions the row to
 * status=EXPIRED and returns 204.  After query invalidation the row remains
 * visible in the table with an "Expired" status pill.
 */
test.describe('Snapshots E2E', () => {
  const LABEL = `e2e-snapshot-${Date.now()}`;

  test('tenant admin can create, view, and delete a snapshot', async ({ authedPage }) => {
    const page = authedPage;

    // ── Navigate ────────────────────────────────────────────────────────────
    await page.goto('/settings/backups');
    await expect(page.locator('h1, h2').first()).toContainText(/Snapshot/i, {
      timeout: 15_000,
    });

    // ── Create ──────────────────────────────────────────────────────────────
    // The tenant-admin view locks the schema field; only the label is editable.
    await page.fill('#snapshot-label', LABEL);
    await page.click('button[type="submit"]:has-text("Create snapshot")');

    // The new row appears once the API request completes and the query is
    // refetched.  In-flight jobs poll every 5 s; allow up to 60 s total.
    const newRow = page.locator('table tbody tr').filter({ hasText: LABEL });
    await expect(newRow).toBeVisible({ timeout: 60_000 });

    // ── View detail drawer ───────────────────────────────────────────────────
    await newRow.locator('button[title="View details"]').click();
    await expect(page.locator('h2')).toContainText(/Snapshot #/i, {
      timeout: 10_000,
    });
    await page.click('button[aria-label="Close"]');

    // Drawer should be gone.
    await expect(page.locator('h2:has-text("Snapshot #")')).toHaveCount(0, {
      timeout: 5_000,
    });

    // ── Delete ───────────────────────────────────────────────────────────────
    // window.confirm is used in SnapshotsTable; register handler before click.
    page.once('dialog', (dialog) => dialog.accept());
    await newRow.locator('button[title="Delete"]').click();

    // Soft delete — the row stays in the list but its status pill becomes
    // "Expired" (backend: status=EXPIRED, artifact_path='', returns 204).
    await expect(
      page
        .locator('table tbody tr')
        .filter({ hasText: LABEL })
        .filter({ hasText: /expired/i }),
    ).toBeVisible({ timeout: 15_000 });
  });
});
