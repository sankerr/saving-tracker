import { test, expect } from '@playwright/test';

test('home redirects unauthenticated users; smoke title on login', async ({
  page,
}) => {
  await page.goto('/');
  await expect(page.locator('html')).toHaveAttribute('lang', 'he');
  await expect(page.locator('html')).toHaveAttribute('dir', 'rtl');
  await expect(page.getByRole('heading', { name: 'התחברות' })).toBeVisible();
});
