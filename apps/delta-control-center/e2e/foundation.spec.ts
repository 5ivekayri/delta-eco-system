import {test, expect} from '@playwright/test';

test('shows actual Core health, stores session token and collapses navigation', async ({page}) => {
  await page.goto('/');
  await expect(page.getByRole('heading', {name: 'Your workspace. Connected.'})).toBeVisible();
  await expect(page.getByRole('heading', {name: 'Core is ready'})).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.getByRole('button', {name:'Settings',exact:true}).click();
  await page.getByLabel('Development token').fill('test-only-token-123456');
  await page.getByRole('button', {name:'Сохранить в этой сессии'}).click();
  expect(await page.evaluate(() => sessionStorage.getItem('delta-token'))).toBe('test-only-token-123456');
  await page.getByRole('button', {name:'Свернуть меню'}).click();
  await expect(page.locator('.shell')).toHaveClass('shell collapsed');
  await page.screenshot({path:'test-results/foundation.png',fullPage:true});
});
