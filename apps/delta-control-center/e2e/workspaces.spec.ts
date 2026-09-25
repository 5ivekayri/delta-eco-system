import {readFileSync} from 'node:fs';
import {test,expect} from '@playwright/test';

test('workspace CRUD and per-device binding',async({page})=>{
  const token=readFileSync(new URL('../../../.env',import.meta.url),'utf8').match(/^DELTA_TOKEN=(.+)$/m)![1];
  await page.goto('/');await page.evaluate(token=>sessionStorage.setItem('delta-token',token),token);await page.reload();
  await page.getByRole('button',{name:'Workspaces',exact:true}).click();
  await page.getByRole('button',{name:'Новое пространство'}).click();
  const name=`Workspace verification ${Date.now()}`;
  await page.getByLabel('Название пространства').fill(name);
  await page.getByLabel('Описание пространства').fill('Portable project');
  await page.getByRole('button',{name:'Сохранить пространство'}).click();
  await page.getByRole('button').filter({has:page.getByRole('heading',{name,exact:true})}).click();
  const device=await page.locator('select[aria-label="Устройство"] option').filter({hasText:'Delta local verification'}).getAttribute('value');
  await page.getByLabel('Устройство',{exact:true}).selectOption(device!);
  await page.getByLabel('Сайты — по одному адресу на строке').fill('https://example.com');
  await page.getByRole('button',{name:'Сохранить привязку'}).click();
  await expect(page.getByRole('status')).toContainText('Привязка сохранена');
  await expect(page.getByRole('button',{name:'Launch Workspace'})).toBeDisabled();
  page.on('dialog',dialog=>dialog.accept());
  await page.getByRole('button',{name:'Удалить',exact:true}).click();
  await expect(page.getByRole('heading',{name,exact:true})).not.toBeVisible();
});
