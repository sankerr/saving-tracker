import { test, expect } from '@playwright/test';

test('home redirects to login when unauthenticated', async ({ page }) => {
  await page.goto('/');
  await expect(page).toHaveURL(/\/login/);
  await expect(page.getByRole('heading', { name: 'התחברות' })).toBeVisible();
});

test('login then logout', async ({ page }) => {
  await page.route('**/api/login', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ ok: true, token: 'test-token' }),
    });
  });

  await page.goto('/login');
  await page.getByLabel(/.*/).first(); // warm
  await page.locator('input[type="email"]').fill('user@example.com');
  await page.locator('input[type="password"]').fill('secret');
  await page.getByRole('button', { name: 'התחברות' }).click();

  await expect(page).toHaveURL('/');
  await expect(page.getByRole('navigation')).toBeVisible();

  await page.getByRole('button', { name: 'התנתקות' }).click();
  await expect(page).toHaveURL(/\/login/);
});
