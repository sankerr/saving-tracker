import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test, expect } from '@playwright/test';

const portfolio = JSON.parse(
  readFileSync(
    path.join(path.dirname(fileURLToPath(import.meta.url)), 'fixtures/portfolio.json'),
    'utf8',
  ),
);

async function login(page: import('@playwright/test').Page) {
  await page.route('**/api/login', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ ok: true, token: 'test-token' }),
    });
  });
  await page.route('**/api/data**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(portfolio),
    });
  });
  await page.route('**/api/insights**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ ok: true, text: 'תובנה לדוגמה' }),
    });
  });
  await page.route('**/api/sync**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ ok: true }),
    });
  });
  await page.route('**/api/chat/status', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ ok: true, enabled: true }),
    });
  });

  await page.goto('/login');
  await page.locator('input[type="email"]').fill('user@example.com');
  await page.locator('input[type="password"]').fill('secret');
  await page.getByRole('button', { name: 'התחברות' }).click();
  await expect(page).toHaveURL('/');
}

test('dashboard loads totals and section nav', async ({ page }) => {
  await login(page);
  await expect(page.getByTestId('dash-total')).toContainText(/105|100/);
  await expect(page.getByTestId('ai-insight')).toContainText('תובנה');
  await page.getByRole('button', { name: 'קופות' }).click();
  await expect(page.locator('#funds-card')).toBeVisible();
  await expect(page.getByTestId('funds-card-count')).toHaveText('1');
});

test('cash add uses mocked API', async ({ page }) => {
  await login(page);
  let posted = false;
  await page.route('**/api/cash', async (route) => {
    if (route.request().method() === 'POST') {
      posted = true;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ok: true }),
      });
      return;
    }
    await route.fallback();
  });

  await page.getByRole('button', { name: 'מזומן ולא מושקע' }).click();
  await page.locator('#cash-card').getByRole('button', { name: '+ הוספת מזומן' }).click();
  await page.locator('#cash-card input').nth(0).fill('פיקדון');
  await page.locator('#cash-card input').nth(1).fill('1000');
  await page.locator('#cash-card').getByRole('button', { name: 'שמירה' }).click();
  await expect.poll(() => posted).toBe(true);
});
