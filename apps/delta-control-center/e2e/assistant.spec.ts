import {readFileSync} from 'node:fs';
import {test,expect} from '@playwright/test';

test('Mock Assistant creates a real task through the registry',async({page,request})=>{
  const token=readFileSync(new URL('../../../.env',import.meta.url),'utf8').match(/^DELTA_TOKEN=(.+)$/m)![1];
  await page.goto('/');await page.evaluate(token=>sessionStorage.setItem('delta-token',token),token);await page.reload();
  await page.getByRole('button',{name:'Assistant',exact:true}).click();
  const title=`Assistant verification ${Date.now()}`;
  await page.getByLabel('Сообщение Assistant').fill('Добавь задачу '+title);
  await page.getByRole('button',{name:'Отправить',exact:true}).click();
  await expect(page.locator('.assistant-message').last()).toContainText('Задача добавлена: '+title);
  await page.getByRole('button',{name:'Tasks',exact:true}).click();
  const row=page.locator('.task-row').filter({hasText:title});await expect(row).toBeVisible();
  page.on('dialog',d=>d.accept());await row.getByTitle('Удалить',{exact:true}).click();await expect(row).not.toBeVisible();
});
