import { test, expect } from '../fixtures/auth';

test.describe('HRM — smoke', () => {
  for (const [name, path] of [
    ['dashboard', '/hrm/dashboard'],
    ['employees', '/hrm/employees'],
    ['departments', '/hrm/departments'],
    ['payroll', '/hrm/payroll'],
    ['attendance', '/hrm/attendance'],
  ] as const) {
    test(`${name} loads (or shows module-disabled state)`, async ({ authedPage }) => {
      await authedPage.goto(path);
      // Either the page renders (heading visible) OR the tenant has the
      // module disabled (legitimate RBAC outcome). Both are acceptable.
      const heading = authedPage.locator('h1, h2').first();
      const disabled = authedPage.getByText(/Module Disabled|Access Restricted/i).first();
      await expect(heading.or(disabled)).toBeVisible({ timeout: 15_000 });
    });
  }
});
