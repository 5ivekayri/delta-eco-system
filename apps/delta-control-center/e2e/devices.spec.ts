import {readFileSync} from 'node:fs';
import {test, expect} from '@playwright/test';

test('lists real persisted devices and opens device details', async ({page}) => {
  const env = readFileSync(new URL('../../../.env', import.meta.url), 'utf8');
  const token = env.match(/^DELTA_TOKEN=(.+)$/m)![1];
  await page.goto('/');
  await page.getByRole('button', {name:'Settings',exact:true}).click();
  await page.getByLabel('Development token').fill(token);
  await page.getByRole('button', {name:'Сохранить в этой сессии'}).click();
  await page.getByRole('button', {name:'Devices',exact:true}).click();
  await page.getByRole('button').filter({has:page.getByRole('heading',{name:'Delta local verification'})}).click();
  await expect(page.getByText('Last heartbeat',{exact:true})).toBeVisible();
  await expect(page.getByRole('button',{name:'Get System Info'})).toBeVisible();
  await expect(page.getByRole('heading',{name:'Recent commands & results'})).toBeVisible();
});
