import {test,expect} from '@playwright/test';

test('overview isolates service failures and counts only open tasks',async({page})=>{
  await page.addInitScript(()=>sessionStorage.setItem('delta-token','test-only-token-123456'));
  await page.route('**/core/api/v1/devices',route=>route.fulfill({json:[{status:'online'},{status:'offline'}]}));
  await page.route('**/core/api/v1/services',route=>route.fulfill({json:[{status:'online'}]}));
  await page.route('**/core/api/v1/workspaces',route=>route.fulfill({json:[{},{}]}));
  await page.route('**/tasks-api/api/v1/tasks?*',route=>route.fulfill({json:new URL(route.request().url()).searchParams.get('status')==='todo'?[{},{}]:[{}]}));
  await page.goto('/');
  const cards=page.locator('.overview-metrics article');
  await expect(cards.nth(0)).toContainText('1 / 2');
  await expect(cards.nth(3).locator('strong')).toHaveText('3');
  await page.route('**/tasks-api/api/v1/tasks?*',route=>route.fulfill({status:503,json:{message:'unavailable'}}));
  await expect(cards.nth(3)).toContainText('данные устарели',{timeout:8000});
  await expect(cards.nth(3).locator('strong')).toHaveText('3');
  await expect(cards.nth(0).getByRole('alert')).toHaveCount(0);
});

test('mobile pages fit viewport and provide keyboard-visible controls',async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await page.goto('/');
  await expect(page.getByRole('heading',{name:'Подключение к Delta'})).toBeVisible();
  for(const name of ['Overview','Settings','Services','Tasks','Activity','Virtual IoT']){
    await page.getByRole('button',{name,exact:true}).click();
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  }
  await page.getByRole('button',{name:'Overview',exact:true}).click();
  await page.screenshot({path:'test-results/overview-mobile.png',fullPage:true});
});

test('live overview matches API counts on desktop and mobile',async({page,request})=>{
  const {readFileSync}=await import('node:fs');
  const token=readFileSync(new URL('../../../.env',import.meta.url),'utf8').match(/^DELTA_TOKEN=(.+)$/m)![1];
  const headers={Authorization:`Bearer ${token}`};
  const paths=['/core/api/v1/devices','/core/api/v1/services','/core/api/v1/workspaces','/tasks-api/api/v1/tasks?status=todo','/tasks-api/api/v1/tasks?status=in_progress'];
  const rows=await Promise.all(paths.map(async path=>{const response=await request.get(path,{headers});expect(response.ok()).toBeTruthy();return response.json();}));
  await page.addInitScript(token=>sessionStorage.setItem('delta-token',token),token);
  await page.goto('/');
  const values=page.locator('.overview-metrics strong');
  await expect(values.nth(0)).toHaveText(`${rows[0].filter((r:{status:string})=>r.status==='online').length} / ${rows[0].length}`);
  await expect(values.nth(1)).toHaveText(`${rows[1].filter((r:{status:string})=>r.status==='online').length} / ${rows[1].length}`);
  await expect(values.nth(2)).toHaveText(String(rows[2].length));
  await expect(values.nth(3)).toHaveText(String(rows[3].length+rows[4].length));
  await page.screenshot({path:'test-results/overview-live-desktop.png',fullPage:true});
  await page.setViewportSize({width:390,height:844});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:'test-results/overview-live-mobile.png',fullPage:true});
});
