import {test, expect} from '@playwright/test';
import {readFileSync} from 'node:fs';

const token=readFileSync(new URL('../../../.env',import.meta.url),'utf8').match(/^DELTA_TOKEN=(.+)$/m)![1];
const headers={Authorization:`Bearer ${token}`};
const fixture={source:'virtual',desk_light:false,temperature:23,brightness:30,motion:true,updated_at:'2026-09-26T12:00:00Z'};

async function openIoT(page:import('@playwright/test').Page) {
  await page.addInitScript(token=>sessionStorage.setItem('delta-token',token),token);
  await page.goto('/');
  await page.getByRole('button',{name:'Virtual IoT',exact:true}).click();
}

test('real IoT switch persists, Assistant shares state, and external changes refresh',async({page,request})=>{
  const originalResponse=await request.get('/core/api/v1/iot/state',{headers});
  expect(originalResponse.ok()).toBeTruthy();
  const original=await originalResponse.json();
  try {
    expect((await request.post('/core/api/v1/iot/light',{headers,data:{enabled:false}})).ok()).toBeTruthy();
    await openIoT(page);
    await expect(page.getByTestId('iot-temperature')).toContainText('23');
    await expect(page.getByTestId('iot-brightness')).toContainText('30');
    await expect(page.getByTestId('iot-motion')).toContainText('Обнаружено');
    await expect(page.getByText('Эмуляция',{exact:true})).toBeVisible();
    const toggle=page.getByRole('switch',{name:'Рабочий свет'});
    await expect(toggle).toHaveAttribute('aria-checked','false');
    await toggle.click();
    await expect(toggle).toHaveAttribute('aria-checked','true');
    await page.reload();
    await page.getByRole('button',{name:'Virtual IoT',exact:true}).click();
    await expect(toggle).toHaveAttribute('aria-checked','true');
    await page.getByRole('button',{name:'Assistant',exact:true}).click();
    await page.getByLabel('Сообщение Assistant').fill('Выключи рабочий свет');
    const reply=page.waitForResponse(r=>r.url().endsWith('/assistant/message'));
    await page.getByRole('button',{name:'Отправить',exact:true}).click();
    const body=await(await reply).json();
    expect(body.route_source).toBe('local');
    expect(body.tool_results[0].data.enabled).toBe(false);
    await page.getByRole('button',{name:'Virtual IoT',exact:true}).click();
    await expect(toggle).toHaveAttribute('aria-checked','false');
    await request.post('/core/api/v1/iot/light',{headers,data:{enabled:true}});
    await expect(toggle).toHaveAttribute('aria-checked','true',{timeout:7000});
  } finally {
    await request.post('/core/api/v1/iot/light',{headers,data:{enabled:original.desk_light}});
  }
});

test('IoT service failure does not display fabricated sensor values',async({page})=>{
  await page.route('**/core/api/v1/iot/state',r=>r.fulfill({status:503,json:{message:'IoT недоступен'}}));
  await openIoT(page);
  await expect(page.getByRole('alert')).toContainText('IoT недоступен');
  await expect(page.getByTestId('iot-temperature')).toHaveCount(0);
  await expect(page.getByRole('switch',{name:'Рабочий свет'})).toHaveCount(0);
});

test('an older poll cannot overwrite an acknowledged light update',async({page})=>{
  let reads=0;
  let release:(()=>void)|undefined;
  const gate=new Promise<void>(resolve=>{release=resolve;});
  await page.route('**/core/api/v1/iot/state',async route=>{
    reads++;
    if(reads===2)await gate;
    await route.fulfill({json:{...fixture,desk_light:reads>2}});
  });
  await page.route('**/core/api/v1/iot/light',r=>r.fulfill({json:{...fixture,desk_light:true}}));
  await openIoT(page);
  const toggle=page.getByRole('switch',{name:'Рабочий свет'});
  await expect(toggle).toHaveAttribute('aria-checked','false');
  await expect.poll(()=>reads,{timeout:7000}).toBe(2);
  await toggle.click();
  await expect(toggle).toHaveAttribute('aria-checked','true');
  const oldReply=page.waitForResponse(r=>r.url().endsWith('/iot/state'));
  release!();
  await oldReply;
  await expect(toggle).toHaveAttribute('aria-checked','true');
});
