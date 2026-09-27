import {useEffect, useRef, useState} from 'react';
import {Square, Volume2} from 'lucide-react';
import {AssistantResponse} from './api';

type PlaybackState = 'idle'|'speaking'|'blocked'|'error';

export function VoicePlayback({response}: {response?:AssistantResponse}) {
  const audio = useRef<HTMLAudioElement | null>(null);
  const generation = useRef(0);
  const [state,setState] = useState<PlaybackState>('idle');
  const [ready,setReady] = useState(false);

  async function play() {
    const current = audio.current;
    const attempt = generation.current;
    if (!current) return;
    current.currentTime = 0;
    try {
      await current.play();
      if (attempt === generation.current) setState('speaking');
    } catch (error) {
      if (attempt === generation.current) setState((error as Error).name === 'NotAllowedError' ? 'blocked' : 'error');
    }
  }
  function stop() {
    generation.current++;
    audio.current?.pause();
    if (audio.current) audio.current.currentTime = 0;
    setState('idle');
  }
  useEffect(() => {
    generation.current++;
    setState('idle'); setReady(false);
    if (!response?.audio_available || !response.audio_base64) return;
    let url: string | undefined;
    let current: HTMLAudioElement | undefined;
    try {
      const data = Uint8Array.from(atob(response.audio_base64), char => char.charCodeAt(0));
      url = URL.createObjectURL(new Blob([data],{type:'audio/wav'}));
      current = new Audio(url);
      audio.current = current;
      current.onended = () => {if (current === audio.current) setState('idle');};
      current.onerror = () => {if (current === audio.current) setState('error');};
      setReady(true);
      // Browsers may require a new gesture after a long STT request; retain a play button.
      void play();
    } catch {setState('error');}
    return () => {
      generation.current++;
      if (current) {
        current.onended = current.onerror = null;
        current.pause(); current.removeAttribute('src'); current.load();
      }
      audio.current = null;
      if (url) URL.revokeObjectURL(url);
    };
  }, [response]);

  if (!response) return null;
  if (response.tts_error) return <p className="voice-playback" role="status">{response.tts_message || 'Озвучивание недоступно. Текст ответа сохранён.'}</p>;
  if (!response.audio_available) return null;
  return <div className="voice-playback">
    {ready&&<button type="button" onClick={()=>state==='speaking' ? stop() : void play()} aria-label={state==='speaking' ? 'Остановить озвучивание' : 'Прослушать ответ'}>
      {state==='speaking' ? <Square size={18}/> : <Volume2 size={18}/>}
      {state==='speaking' ? 'Остановить' : 'Прослушать ответ'}
    </button>}
    <span role="status">{state==='speaking' ? 'Озвучивание ответа…' : state==='blocked' ? 'Нажмите «Прослушать ответ», чтобы включить звук.' :
      state==='error' ? 'Не удалось воспроизвести звук. Текст ответа сохранён.' : 'Можно повторно прослушать ответ.'}
      {response.tts_provider==='mock'&&' Тестовый режим озвучивания: без речи.'}</span>
  </div>;
}
