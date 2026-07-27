import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test, expect, type Page } from '@playwright/test';

const portfolio = JSON.parse(
  readFileSync(
    path.join(path.dirname(fileURLToPath(import.meta.url)), 'fixtures/portfolio.json'),
    'utf8',
  ),
);

function nav(page: Page, target: string) {
  return page.locator(`.section-nav .nav-pill[data-target="${target}"]`);
}

async function login(page: Page) {
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
  await page.route('**/api/chat', async (route) => {
    if (route.request().method() === 'POST') {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ ok: true, reply: 'תשובת בדיקה' }),
      });
      return;
    }
    await route.fallback();
  });
  await page.route('**/api/settings', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ ok: true }),
    });
  });
  await page.route('**/api/export', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ ok: true, exported: true }),
    });
  });
  await page.route('**/api/funds/search**', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        ok: true,
        results: [{ fund_id: 999, fund_name: 'קרן בדיקה', data_source: 'gemelnet' }],
      }),
    });
  });

  await page.goto('/login');
  await page.locator('input[type="email"]').fill('user@example.com');
  await page.locator('input[type="password"]').fill('secret');
  await page.getByRole('button', { name: 'התחברות' }).click();
  await expect(page).toHaveURL('/');
}

test('section nav reaches retirement and settings', async ({ page }) => {
  await login(page);
  await nav(page, 'retirement-simulator-card').click();
  await expect(page.locator('#retirement-simulator-card')).toBeVisible();
  await expect(page.locator('#retirement-simulator-card')).toContainText('תאריך לידה');

  await nav(page, 'settings-card').click();
  await expect(page.locator('#settings-card')).toBeVisible();
  await expect(page.locator('#settings-card')).toContainText('ייצוא JSON');
  await expect(page.locator('#settings-card')).toContainText('ייבוא JSON');
  await expect(page.locator('#settings-card')).toContainText('שינוי סיסמה');
  await expect(page.locator('#settings-card')).toContainText('מחיקת החשבון');
});

test('retirement simulator computes paths', async ({ page }) => {
  await login(page);
  await nav(page, 'retirement-simulator-card').click();
  const card = page.locator('#retirement-simulator-card');
  await card.locator('input[type="date"]').fill('1985-06-15');
  await card
    .locator('label')
    .filter({ hasText: 'יתרת מקיפה' })
    .locator('input')
    .fill('5000000');
  await card
    .locator('label')
    .filter({ hasText: 'יעד פנסיה' })
    .locator('input[type="number"]')
    .fill('20000');
  await expect(card).toContainText('מסלול 1');
  await expect(card).toContainText('פנסיה חודשית');
  await expect(card).toContainText('מקדם');
});

test('holdings detail expands for fund, rsu, espp', async ({ page }) => {
  await login(page);

  await nav(page, 'funds-card').click();
  await page.locator('#funds-card .holding-row__head').first().click();
  await expect(page.locator('#funds-card .holding-row__detail')).toBeVisible();

  await nav(page, 'rsu-card').click();
  await page.locator('#rsu-card .holding-row__head').first().click();
  await expect(page.locator('#rsu-card .holding-row__detail')).toBeVisible();

  await nav(page, 'espp-card').click();
  await page.locator('#espp-card .holding-row__head').first().click();
  await expect(page.locator('#espp-card .holding-row__detail')).toBeVisible();
});

test('AI chat send is mocked', async ({ page }) => {
  await login(page);
  await page.getByRole('button', { name: /צ׳אט AI|AI/ }).first().click();
  await page.locator('.chat-composer textarea').fill('מה המצב?');
  await page.locator('.chat-composer').getByRole('button').click();
  await expect(page.locator('.chat-msg--assistant')).toContainText('תשובת בדיקה');
});

test('fund add posts to API', async ({ page }) => {
  await login(page);
  let posted = false;
  await page.route('**/api/fund-holdings', async (route) => {
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
  await nav(page, 'funds-card').click();
  await page.locator('#funds-card').getByRole('button', { name: /הוספת קופ/ }).click();
  await page.locator('#funds-card input').first().fill('בדיקה');
  await page.locator('#funds-card .search-results button').first().click();
  const inputs = page.locator('#funds-card .add-panel input');
  await inputs.nth(1).fill('כינוי');
  await inputs.nth(2).fill('1000');
  await inputs.nth(3).fill('202501');
  await page.locator('#funds-card').getByRole('button', { name: /שמירת|שמירה/ }).click();
  await expect.poll(() => posted).toBe(true);
});

test('settings export triggers download request', async ({ page }) => {
  await login(page);
  let exported = false;
  await page.route('**/api/export', async (route) => {
    exported = true;
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ ok: true }),
    });
  });
  await nav(page, 'settings-card').click();
  await page.locator('#settings-card').getByRole('button', { name: 'ייצוא JSON' }).click();
  await expect.poll(() => exported).toBe(true);
});
