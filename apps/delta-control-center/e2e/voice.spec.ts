import {test, expect} from '@playwright/test';

test.use({launchOptions:{args:['--use-fake-device-for-media-stream','--use-fake-ui-for-media-stream']},permissions:['microphone']});

async function setup(page: import('@playwright/test').Page, maxSeconds = 60) {
  await page.route('**/core/api/v1/assistant/voice/config', route => route.fulfill({json:{provider:'whisper',max_seconds:maxSeconds,max_bytes:10485760}}));
  await page.route('**/core/api/v1/assistant/history', route => route.fulfill({json:[]}));
  await page.route('**/core/api/v1/devices', route => route.fulfill({json:[]}));
  await page.addInitScript(() => {
    const media = navigator.mediaDevices;
    const get = media.getUserMedia.bind(media);
    const tracked = window as typeof window & {voiceStreams:MediaStream[]};
    tracked.voiceStreams = [];
    media.getUserMedia = async constraints => {
      const stream = await get(constraints);
      tracked.voiceStreams.push(stream);
      return stream;
    };
  });
  await page.goto('/');
  await page.getByRole('button',{name:'Assistant',exact:true}).click();
}

async function tracksStopped(page: import('@playwright/test').Page) {
  await expect.poll(() => page.evaluate(() => {
    const streams = (window as typeof window & {voiceStreams:MediaStream[]}).voiceStreams;
    return streams.length > 0 && streams.every(stream => stream.getTracks().every(track => track.readyState==='ended'));
  })).toBe(true);
}

test('records audio, submits once, displays transcript and releases microphone', async ({page}) => {
  let requests = 0;
  await page.route('**/core/api/v1/assistant/voice', async route => {
    requests++;
    expect(route.request().headers()['content-type']).toContain('multipart/form-data');
    expect(route.request().postDataBuffer()!.length).toBeGreaterThan(100);
    await route.fulfill({json:{id:'voice-1',transcript:'покажи устройства',assistant_text:'Устройства найдены.',tool_calls:[],tool_results:[],audio_available:false}});
  });
  await setup(page);
  await page.getByRole('button',{name:'Записать голосовое сообщение',exact:true}).click();
  await expect(page.getByRole('button',{name:'Остановить и отправить запись',exact:true})).toContainText(/Запись [1-9]\d* с/);
  await page.getByRole('button',{name:'Остановить и отправить запись',exact:true}).click();
  await expect(page.locator('.voice-transcript')).toContainText('покажи устройства');
  await expect(page.locator('.assistant-message')).toContainText('Устройства найдены.');
  expect(requests).toBe(1);
  await tracksStopped(page);
});

test('cancel and navigating away release the microphone without submitting', async ({page}) => {
  let requests = 0;
  await page.route('**/core/api/v1/assistant/voice', route => {requests++;return route.abort();});
  await setup(page);
  await page.getByRole('button',{name:'Записать голосовое сообщение',exact:true}).click();
  await page.getByRole('button',{name:'Отменить запись',exact:true}).click();
  await tracksStopped(page);
  await page.getByRole('button',{name:'Записать голосовое сообщение',exact:true}).click();
  await expect(page.getByRole('button',{name:'Отменить запись',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Overview',exact:true}).click();
  await tracksStopped(page);
  expect(requests).toBe(0);
});

test('microphone denial leaves text chat usable', async ({page}) => {
  await setup(page);
  await page.evaluate(() => {navigator.mediaDevices.getUserMedia = async () => {throw new DOMException('denied','NotAllowedError');};});
  await page.route('**/core/api/v1/assistant/message', route => route.fulfill({json:{id:'text-1',assistant_text:'Текст работает.',tool_calls:[],tool_results:[]}}));
  await page.getByRole('button',{name:'Записать голосовое сообщение',exact:true}).click();
  await expect(page.getByRole('alert')).toContainText('Доступ к микрофону запрещён');
  await page.getByLabel('Сообщение Assistant').fill('покажи устройства');
  await page.getByRole('button',{name:'Отправить',exact:true}).click();
  await expect(page.locator('.assistant-message')).toContainText('Текст работает.');
});

test('auto stop preserves transcript on model failure and enables text editing', async ({page}) => {
  await page.route('**/core/api/v1/assistant/voice', route => route.fulfill({status:503,json:{message:'Модель недоступна',transcript:'покажи задачи'}}));
  await setup(page, 1);
  await page.getByRole('button',{name:'Записать голосовое сообщение',exact:true}).click();
  await expect(page.getByRole('alert')).toContainText('Модель недоступна');
  await expect(page.getByLabel('Сообщение Assistant')).toHaveValue('покажи задачи');
  await expect(page.getByRole('button',{name:'Отправить',exact:true})).toBeEnabled();
  await tracksStopped(page);
});

test('developer mode displays upload and all latency stages after recording ends', async ({page}) => {
  await setup(page, 1);
  await page.evaluate(() => sessionStorage.setItem('delta-debug','true'));
  await page.getByRole('button',{name:'Overview',exact:true}).click();
  await page.getByRole('button',{name:'Assistant',exact:true}).click();
  await page.route('**/core/api/v1/assistant/voice', route => route.fulfill({json:{
    id:'latency-1',transcript:'покажи устройства',assistant_text:'Готово',tool_calls:[],tool_results:[],
    timings:{upload_ms:2,stt_ms:30,router_ms:40,tool_ms:5,response_generation_ms:0.1,tts_ms:0,
      server_total_ms:80,router_calls:1,response_generation_calls:0,execution_path:'fast',tts_status:'not_configured'},
  }}));
  await page.getByRole('button',{name:'Записать голосовое сообщение',exact:true}).click();
  await page.locator('.voice-latency summary').click();
  const details = page.locator('.voice-latency');
  for (const label of ['Audio upload','STT ms','Router ms','Tool ms','Response generation ms','TTS ms','Total ms']) {
    await expect(details.getByText(label,{exact:true})).toBeVisible();
  }
  await expect(details).toContainText('0 LLM calls');
  await expect(details).toContainText('Not configured');
  await expect(details.locator('dd').filter({hasText:'after recording ends'})).not.toContainText('—');
  await page.getByRole('button',{name:'Settings',exact:true}).click();
  await page.getByLabel('Developer mode').uncheck();
  await page.getByRole('button',{name:'Assistant',exact:true}).click();
  await expect(page.locator('.voice-latency')).toHaveCount(0);
});

for (const source of ['local','llm'] as const) {
  test(`developer voice telemetry identifies ${source} route`, async ({page}) => {
    await setup(page, 1);
    await page.evaluate(() => sessionStorage.setItem('delta-debug','true'));
    await page.getByRole('button',{name:'Overview',exact:true}).click();
    await page.getByRole('button',{name:'Assistant',exact:true}).click();
    await page.route('**/core/api/v1/assistant/voice', route => route.fulfill({json:{
      id:'route-'+source,transcript:'покажи устройства',assistant_text:'Готово',tool_calls:[],tool_results:[],
      timings:{route_source:source,local_router_ms:.2,confidence:source==='local' ? .99 : .2,
        upload_ms:2,stt_ms:30,router_ms:source==='local' ? 0 : 40,tool_ms:5,response_generation_ms:0.1,tts_ms:0,
        server_total_ms:80,router_calls:source==='local' ? 0 : 1,response_generation_calls:0,execution_path:'fast',tts_status:'not_configured'},
    }}));
    await page.getByRole('button',{name:'Записать голосовое сообщение',exact:true}).click();
    await page.locator('.voice-latency summary').click();
    await expect(page.locator('.voice-latency')).toContainText(source==='local' ? 'Local route' : 'LLM route');
    await expect(page.locator('.voice-latency')).toContainText(source==='local' ? 'confidence 99%' : 'confidence 20%');
  });
}

async function observePlayback(page:import('@playwright/test').Page, blockFirst:boolean) {
  await page.addInitScript(blockFirst => {
    const state = {players:[] as any[],revoked:0};
    (window as any).playbackTest = state;
    const revoke = URL.revokeObjectURL.bind(URL);
    URL.revokeObjectURL = url => {state.revoked++;revoke(url);};
    (window as any).Audio = class {
      currentTime=0; onended: (()=>void)|null=null; onerror:(()=>void)|null=null;
      plays=0; pauses=0;
      constructor(public src:string) {state.players.push(this);}
      async play() {this.plays++;if(blockFirst&&this.plays===1)throw new DOMException('gesture required','NotAllowedError');}
      pause() {this.pauses++;}
      removeAttribute() {}
      load() {}
    };
  }, blockFirst);
}

const spokenResponse = {
  id:'spoken-1',transcript:'покажи устройства',assistant_text:'Устройства найдены.',tool_calls:[],tool_results:[],
  audio_available:true,audio_mime:'audio/wav',audio_base64:'UklGRg==',tts_provider:'piper',
};

test('blocked autoplay can replay and stop without repeating tools; navigation releases audio',async({page})=>{
  await observePlayback(page,true);
  let calls=0;
  await page.route('**/core/api/v1/assistant/voice',route=>{calls++;return route.fulfill({json:spokenResponse});});
  await setup(page,1);
  await page.getByRole('button',{name:'Записать голосовое сообщение',exact:true}).click();
  await expect(page.locator('.voice-playback')).toContainText('чтобы включить звук');
  await expect(page.locator('.assistant-message')).toContainText('Устройства найдены.');
  await page.getByRole('button',{name:'Прослушать ответ',exact:true}).click();
  await expect(page.locator('.voice-playback')).toContainText('Озвучивание ответа');
  await page.getByRole('button',{name:'Остановить озвучивание',exact:true}).click();
  await page.getByRole('button',{name:'Прослушать ответ',exact:true}).click();
  await page.evaluate(()=>{(window as any).playbackTest.players[0].onended();});
  await expect(page.getByRole('button',{name:'Прослушать ответ',exact:true})).toBeVisible();
  expect(calls).toBe(1);
  await page.getByRole('button',{name:'Overview',exact:true}).click();
  const cleanup=await page.evaluate(()=>({pauses:(window as any).playbackTest.players[0].pauses,revoked:(window as any).playbackTest.revoked}));
  expect(cleanup.pauses).toBeGreaterThanOrEqual(2);
  expect(cleanup.revoked).toBe(1);
});

test('starting a new recording stops spoken audio',async({page})=>{
  await observePlayback(page,false);
  await page.route('**/core/api/v1/assistant/voice',route=>route.fulfill({json:spokenResponse}));
  await setup(page,1);
  await page.getByRole('button',{name:'Записать голосовое сообщение',exact:true}).click();
  await expect(page.getByRole('button',{name:'Остановить озвучивание',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'Записать голосовое сообщение',exact:true}).click();
  await page.getByRole('button',{name:'Отменить запись',exact:true}).click();
  await expect(page.locator('.voice-playback')).toHaveCount(0);
  expect(await page.evaluate(()=>(window as any).playbackTest.players[0].pauses)).toBeGreaterThan(0);
});

test('synthesis failure keeps text and reports speech unavailable',async({page})=>{
  await page.route('**/core/api/v1/assistant/voice',route=>route.fulfill({json:{...spokenResponse,
    audio_available:false,audio_base64:undefined,tts_error:'TTS_UNAVAILABLE',tts_message:'Озвучивание недоступно. Текст ответа сохранён.'}}));
  await setup(page,1);
  await page.getByRole('button',{name:'Записать голосовое сообщение',exact:true}).click();
  await expect(page.locator('.voice-playback')).toContainText('Озвучивание недоступно');
  await expect(page.locator('.assistant-message')).toContainText('Устройства найдены.');
  await expect(page.getByLabel('Сообщение Assistant')).toBeEnabled();
  await expect(page.getByRole('button',{name:'Прослушать ответ',exact:true})).toHaveCount(0);
});
