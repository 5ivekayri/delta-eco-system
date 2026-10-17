import {test,expect,Page} from '@playwright/test';
test.use({launchOptions:{args:['--use-fake-device-for-media-stream','--use-fake-ui-for-media-stream']},permissions:['microphone']});
async function setup(page:Page,{silence=false,failSpeech=false,maxSeconds=60}={}){
  await page.addInitScript(({silence,failSpeech})=>{
    const w=window as any;w.speechTest={spoken:[],cancels:0,plays:0,tracks:[]};
    const local={name:'Милена тест',voiceURI:'local-ru',lang:'ru-RU',localService:true,default:true};
    const remote={name:'Cloud voice',voiceURI:'cloud-ru',lang:'ru-RU',localService:false,default:false};
    const engine=Object.assign(new EventTarget(),{getVoices:()=>[local,remote],cancel:()=>{w.speechTest.cancels++;},speak:(u:any)=>{w.speechTest.spoken.push(u.text);setTimeout(()=>{if(failSpeech&&u.text==='Устройства найдены.')u.onerror?.();else u.onstart?.();},0);}});
    Object.defineProperty(window,'speechSynthesis',{value:engine});
    w.SpeechSynthesisUtterance=class {voice:any;lang='';onerror:any;onend:any;onstart:any;constructor(public text:string){}};
    w.Audio=class {currentTime=0;onended:any;onerror:any;async play(){w.speechTest.plays++;}pause(){}removeAttribute(){}load(){}};
    let began=0;
    AnalyserNode.prototype.getFloatTimeDomainData=function(buffer){if(!began)began=performance.now();buffer.fill(!silence&&performance.now()-began<650?.08:0);};
    const get=navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
    navigator.mediaDevices.getUserMedia=async constraints=>{const stream=await get(constraints);w.speechTest.tracks.push(...stream.getTracks());return stream;};
  },{silence,failSpeech});
  await page.route('**/core/api/v1/assistant/history',route=>route.fulfill({json:[]}));
  await page.route('**/core/api/v1/devices',route=>route.fulfill({json:[]}));
  await page.route('**/core/api/v1/assistant/voice/config',route=>route.fulfill({json:{provider:'whisper',max_seconds:maxSeconds,max_bytes:10485760,neural_ready:true,voices:[{id:'piper',name:'Irina · Piper',kind:'fast'},{id:'serena',name:'Serena · Qwen3-TTS',kind:'neural'}]}}));
  await page.goto('/');await page.getByRole('button',{name:'Assistant',exact:true}).click();
}
const reply={id:'experience-1',transcript:'покажи устройства',assistant_text:'Устройства найдены.',tool_calls:[],tool_results:[],audio_available:true,audio_base64:'UklGRg==',tts_mode:'piper',tts_provider:'qwen'};

test('speech pause submits once, acknowledges immediately, then plays server audio',async({page})=>{
  let requests=0;let release!:()=>void;
  const gate=new Promise<void>(resolve=>{release=resolve;});
  await page.route('**/core/api/v1/assistant/voice',async route=>{requests++;expect(route.request().postDataBuffer()!.toString()).toContain('auto');await gate;await route.fulfill({json:reply});});
  await setup(page);
  await page.getByRole('button',{name:'Записать голосовое сообщение',exact:true}).click();
  await expect(page.locator('.working-indicator.listening')).toBeVisible({timeout:15000});
  await expect(page.locator('.working-indicator.processing')).toContainText('Секунду, обрабатываю',{timeout:7000});
  await expect.poll(()=>requests).toBe(1);
  expect(await page.evaluate(()=>(window as any).speechTest.spoken)).toEqual([]);
  expect(await page.evaluate(()=>(window as any).speechTest.tracks.every((t:MediaStreamTrack)=>t.readyState==='ended'))).toBe(true);
  await page.screenshot({path:'test-results/voice-processing.png',fullPage:true});
  release();await expect(page.locator('.voice-playback')).toContainText('Озвучивание ответа');
  await page.getByRole('button',{name:'Остановить озвучивание',exact:true}).click();
  await page.getByRole('button',{name:'Прослушать ответ',exact:true}).click();
  expect(requests).toBe(1);
});

test('silence is discarded instead of becoming an assistant request',async({page})=>{
  let requests=0;await page.route('**/core/api/v1/assistant/voice',route=>{requests++;return route.abort();});
  await setup(page,{silence:true});await page.getByRole('button',{name:'Записать голосовое сообщение',exact:true}).click();
  await expect(page.getByRole('alert')).toContainText('Речь не обнаружена',{timeout:14000});expect(requests).toBe(0);
  expect(await page.evaluate(()=>(window as any).speechTest.tracks.every((t:MediaStreamTrack)=>t.readyState==='ended'))).toBe(true);
});

test('server overload fallback plays without repeating the command',async({page})=>{
  let commands=0;
  await page.route('**/core/api/v1/assistant/voice',route=>{commands++;return route.fulfill({json:{...reply,tts_provider:'piper',tts_fallback_reason:'TTS_BUSY'}});});
  await setup(page,{maxSeconds:1});await page.getByRole('button',{name:'Записать голосовое сообщение',exact:true}).click();
  await expect(page.locator('.voice-playback')).toContainText('резервный Piper');
  await page.getByRole('button',{name:'Остановить озвучивание',exact:true}).click();await page.getByRole('button',{name:'Прослушать ответ',exact:true}).click();
  expect(commands).toBe(1);
});

test('server voice settings live on a separate page and persist',async({page})=>{
  let synthesis=0;
  await page.route('**/core/api/v1/assistant/voice/synthesize',route=>{synthesis++;expect(route.request().postDataJSON()).toMatchObject({voice_id:'serena',preview:true});return route.fulfill({json:{audio_base64:'UklGRg==',tts_provider:'qwen'}});});
  await setup(page);
  await expect(page.getByLabel('Голос ответа')).toHaveCount(0);
  await page.getByRole('button',{name:'Настройки ассистента',exact:true}).click();
  await expect(page.getByLabel('Голос ответа').locator('option')).toHaveCount(3);
  await page.getByLabel('Голос ответа').selectOption('serena');
  await page.getByRole('button',{name:'Прослушать голос'}).click();
  await expect.poll(()=>synthesis).toBe(1);
  await page.getByLabel('Длина паузы').selectOption('2500');
  await page.reload();await page.getByRole('button',{name:'Настройки ассистента',exact:true}).click();
  await expect(page.getByLabel('Голос ответа')).toHaveValue('serena');await expect(page.getByLabel('Длина паузы')).toHaveValue('2500');
  await page.getByLabel('Голос ответа').selectOption('piper');
  expect(await page.evaluate(()=>localStorage.getItem('delta-voice'))).toBe('piper');
  await page.screenshot({path:'test-results/assistant-settings.png',fullPage:true});
});

test('typed message receives immediate visible acknowledgment',async({page})=>{
  let release!:()=>void;const gate=new Promise<void>(resolve=>{release=resolve;});
  await page.route('**/core/api/v1/assistant/message',async route=>{await gate;await route.fulfill({json:reply});});
  await setup(page);await page.getByLabel('Сообщение Assistant').fill('Покажи устройства');await page.getByRole('button',{name:'Отправить',exact:true}).click();
  await expect(page.locator('.pending-message')).toContainText('Покажи устройства');
  await expect(page.locator('.working-indicator')).toContainText('Запрос принят');
  await page.setViewportSize({width:390,height:844});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.screenshot({path:'test-results/voice-mobile.png',fullPage:true});
  release();await expect(page.locator('.assistant-message')).toContainText('Устройства найдены.');
});

test('Piper preview uses synthesis only and manual mode never auto-submits',async({page})=>{
  let synthesis=0,commands=0;
  await page.route('**/core/api/v1/assistant/voice/synthesize',route=>{synthesis++;return route.fulfill({json:{audio_base64:'UklGRg==',tts_provider:'piper'}});});
  await page.route('**/core/api/v1/assistant/voice',route=>{commands++;return route.fulfill({json:reply});});
  await setup(page);await page.getByRole('button',{name:'Настройки ассистента',exact:true}).click();
  await page.getByLabel('Голос ответа').selectOption('piper');await page.getByRole('button',{name:'Прослушать голос',exact:true}).click();
  await expect.poll(()=>synthesis).toBe(1);await page.getByRole('button',{name:'Остановить пример',exact:true}).click();
  await page.getByLabel('Отправлять после паузы в речи').uncheck();
  await page.getByRole('button',{name:'Assistant',exact:true}).click();
  await page.getByRole('button',{name:'Записать голосовое сообщение',exact:true}).click();
  await expect(page.getByRole('button',{name:'Остановить и отправить запись',exact:true})).toContainText(/Запись [3-9] с/,{timeout:10000});
  expect(commands).toBe(0);await page.getByRole('button',{name:'Отменить запись',exact:true}).click();expect(commands).toBe(0);
});
