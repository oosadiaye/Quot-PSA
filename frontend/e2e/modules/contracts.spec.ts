import { test, expect } from '../fixtures/auth';

test.describe('Contracts module — smoke', () => {
  for (const [name, path] of [
    ['dashboard', '/contracts/dashboard'],
    ['list', '/contracts'],
    ['IPCs', '/contracts/ipcs'],
    ['variations', '/contracts/variations'],
  ] as const) {
    test(`${name} loads`, async ({ authedPage }) => {
      await authedPage.goto(path);
      await expect(authedPage.locator('h1, h2').first()).toBeVisible({ timeout: 15_000 });
    });
  }
});
