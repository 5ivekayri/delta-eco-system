import {useEffect,useRef,useState} from 'react';
import {Square,Volume2} from 'lucide-react';
import {AssistantResponse,synthesizeSpeech} from './api';
type PlaybackState='idle'|'speaking'|'blocked'|'error'|'loading';
export function VoicePlayback({response}:{response?:AssistantResponse}){
  const audio=useRef<HTMLAudioElement|null>(null),url=useRef<string|undefined>(undefined);
  const generation=useRef(0),controller=useRef<AbortController|undefined>(undefined);
  const [state,setState]=useState<PlaybackState>('idle');
  const [ready,setReady]=useState(false);
  function clearAudio(){const current=audio.current;audio.current=null;
    if(current){current.onended=current.onerror=null;current.pause();current.removeAttribute('src');current.load();}
    if(url.current)URL.revokeObjectURL(url.current);url.current=undefined;}
  function createAudio(base64:string){clearAudio();
    const data=Uint8Array.from(atob(base64),char=>char.charCodeAt(0));
    url.current=URL.createObjectURL(new Blob([data],{type:'audio/wav'}));
    const current=new Audio(url.current);audio.current=current;
    current.onended=()=>{if(current===audio.current)setState('idle');};
    current.onerror=()=>{if(current===audio.current)setState('error');};}
  async function play(){
    const attempt=++generation.current;controller.current?.abort();audio.current?.pause();
    try{if(!audio.current){
      if(!response?.assistant_text)throw new Error('No text');
      setState('loading');controller.current=new AbortController();
      const result=await synthesizeSpeech(response.assistant_text,controller.current.signal);
      if(attempt!==generation.current)return;createAudio(result.audio_base64);
    }
    const current=audio.current!;current.currentTime=0;await current.play();
    if(attempt===generation.current)setState('speaking');
    }catch(error){if(attempt===generation.current)setState((error as Error).name==='NotAllowedError'?'blocked':'error');}
  }
  function stop(){generation.current++;controller.current?.abort();
    audio.current?.pause();if(audio.current)audio.current.currentTime=0;setState('idle');}
  useEffect(()=>{
    generation.current++;setState('idle');setReady(false);
    if(!response)return;
    try{if(response.audio_available&&response.audio_base64)createAudio(response.audio_base64);
      // Old API responses may omit audio; synthesis still never executes an action.
      if(response.tts_mode==='system'||audio.current){setReady(true);void play();}
    }catch{setState('error');}
    return()=>{generation.current++;controller.current?.abort();clearAudio();};
  },[response]);
  if(!response)return null;
  if(response.tts_error&&response.tts_mode!=='system')return <p className="voice-playback" role="status">{response.tts_message||'Озвучивание недоступно. Текст ответа сохранён.'}</p>;
  if(!ready)return null;
  return <div className="voice-playback"><button type="button" onClick={()=>state==='speaking'||state==='loading'?stop():void play()} aria-label={state==='speaking'||state==='loading'?'Остановить озвучивание':'Прослушать ответ'}>
    {state==='speaking'||state==='loading'?<Square size={18}/>:<Volume2 size={18}/>}{state==='speaking'?'Остановить':state==='loading'?'Остановить озвучивание':'Прослушать ответ'}
    </button><span role="status">{state==='speaking'?'Озвучивание ответа…':state==='loading'?'Подготавливаю звук…':state==='blocked'?'Нажмите «Прослушать ответ», чтобы включить звук.':state==='error'?'Не удалось воспроизвести звук. Текст ответа сохранён.':'Можно повторно прослушать ответ.'}
    {response.tts_fallback_reason&&' Используется резервный Piper.'}{response.tts_provider==='mock'&&' Тестовый режим озвучивания: без речи.'}</span></div>;
}
