import {test,expect} from '@playwright/test';
import {readFileSync} from 'node:fs';
const token=readFileSync(new URL('../../../.env',import.meta.url),'utf8').match(/^DELTA_TOKEN=(.+)$/m)![1];
test('activity reads persisted events, filters and hides debug details',async({page})=>{
  await page.addInitScript(token=>sessionStorage.setItem('delta-token',token),token);
  await page.goto('/');
  await page.getByRole('button',{name:'Activity',exact:true}).click();
  await expect(page.getByRole('heading',{name:'Журнал событий'})).toBeVisible();
  await expect(page.locator('.activity-feed article').first()).toBeVisible();
  await expect(page.getByText('Данные события',{exact:true})).toHaveCount(0);
  await page.getByLabel('Тип события').selectOption('IOT_ACTION');
  await expect(page.locator('.activity-feed article').first()).toContainText('IOT_ACTION');
  await page.getByRole('button',{name:'Settings',exact:true}).click();
  await page.getByLabel('Developer mode').check();
  await page.getByRole('button',{name:'Activity',exact:true}).click();
  await expect(page.getByText('Данные события',{exact:true}).first()).toBeVisible();
});
test('services show real health and tool availability',async({page})=>{
  await page.addInitScript(token=>sessionStorage.setItem('delta-token',token),token);
  await page.goto('/');await page.getByRole('button',{name:'Services',exact:true}).click();
  await expect(page.locator('.grid article').first()).toContainText('online');
  await expect(page.getByRole('button',{name:'Обновить',exact:true})).toBeEnabled();
});
