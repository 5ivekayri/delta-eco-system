import {useEffect,useRef,useState} from 'react';
import {getVoiceConfig,synthesizeSpeech,VoiceConfig} from './api';
import {preferenceKey} from './speech';
export function SpeechSettings({disabled=false}:{disabled?:boolean}){
  const audio=useRef<HTMLAudioElement|null>(null),url=useRef<string|null>(null),abort=useRef<AbortController|null>(null);
  const [config,setConfig]=useState<VoiceConfig>(),[previewing,setPreviewing]=useState(false),[error,setError]=useState('');
  const [value,setValue]=useState(()=>{const v=localStorage.getItem(preferenceKey)||'auto';return ['auto','piper','serena','vivian','ryan','aiden'].includes(v)?v:'auto';});
  const [auto,setAuto]=useState(()=>localStorage.getItem('delta-auto-stop')!=='false');
  const [pause,setPause]=useState(()=>localStorage.getItem('delta-silence-ms')||'1800');
  function stop(){abort.current?.abort();if(audio.current){audio.current.onended=audio.current.onerror=null;audio.current.pause();audio.current=null;}if(url.current)URL.revokeObjectURL(url.current);url.current=null;}
  useEffect(()=>{let live=true;getVoiceConfig().then(c=>{if(live)setConfig(c);}).catch(e=>{if(live)setError(e.message);});return()=>{live=false;stop();};},[]);
  return <article className="speech-settings"><h2>Голос ассистента</h2>
    <p>Озвучивание выполняется локально на сервере. Qwen3-TTS — нейроголоса с поддержкой русского; Piper — быстрый резерв.</p>
    {config&&!config.neural_ready&&<p role="status">Нейросинтез пока недоступен на сервере. Автоматический режим использует Piper.</p>}
    <label>Голос ответа<select disabled={disabled} value={value} onChange={e=>{stop();setPreviewing(false);setError('');localStorage.setItem(preferenceKey,e.target.value);setValue(e.target.value);}}>
      <option value="auto">Авто — нейроголос, при перегрузке Piper</option>
      {(config?.voices||[{id:'piper',name:'Irina · Piper',kind:'fast'}]).map(v=><option key={v.id} value={v.id} disabled={v.kind==='neural'&&!config?.neural_ready}>{v.name}{v.kind==='fast'?' — быстрый':''}</option>)}
    </select></label>
    <button disabled={disabled||!config} onClick={async()=>{
      if(previewing){stop();setPreviewing(false);return;}
      stop();setError('');setPreviewing(true);const request=new AbortController();abort.current=request;
      try{const result=await synthesizeSpeech('Привет! Я Дельта. Готова помочь. Чем займёмся сегодня?',request.signal,value,true);
        if(request.signal.aborted)return;
        url.current=URL.createObjectURL(new Blob([Uint8Array.from(atob(result.audio_base64),c=>c.charCodeAt(0))],{type:'audio/wav'}));
        const player=new Audio(url.current);audio.current=player;player.onended=()=>setPreviewing(false);player.onerror=()=>{setError('Не удалось воспроизвести пример.');setPreviewing(false);};await player.play();
      }catch(e){if(!request.signal.aborted){setError((e as Error).message);setPreviewing(false);}}
    }}>{previewing?'Остановить пример':'Прослушать голос'}</button>
    {previewing&&<p role="status">Готовлю пример голоса… На CPU нейросинтез может занять больше времени.</p>}
    {error&&<p role="alert">{error}</p>}
    <p>В режиме ответа занятая или недоступная нейромодель автоматически уступает Piper. Пример выбранного голоса не подменяется другим голосом. Настройки сохраняются в этом браузере.</p>
    <h2>Запись речи</h2><label className="debug-toggle"><input type="checkbox" checked={auto} disabled={disabled} onChange={e=>{setAuto(e.target.checked);localStorage.setItem('delta-auto-stop',String(e.target.checked));}}/>Отправлять после паузы в речи</label>
    <label>Длина паузы<select disabled={disabled||!auto} value={pause} onChange={e=>{setPause(e.target.value);localStorage.setItem('delta-silence-ms',e.target.value);}}><option value="1200">1,2 секунды</option><option value="1800">1,8 секунды</option><option value="2500">2,5 секунды</option></select></label>
  </article>;
}
