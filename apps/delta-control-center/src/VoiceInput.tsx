import {useEffect, useRef, useState} from 'react';
import {Mic, Square, X} from 'lucide-react';
import {ApiError, AssistantResponse, getVoiceConfig, sendVoice, VoiceConfig, VoiceTimings} from './api';

type Props = {
  disabled: boolean;
  deviceId: string;
  onResult: (response: AssistantResponse) => void;
  onError: (message: string, transcript?: string, timings?: VoiceTimings) => void;
  onBusy: (busy: boolean) => void;
};

export function VoiceInput({disabled, deviceId, onResult, onError, onBusy}: Props) {
  const [state, setState] = useState<'idle'|'permission'|'recording'|'processing'>('idle');
  const [seconds, setSeconds] = useState(0);
  const [config, setConfig] = useState<VoiceConfig | null>(null);
  const recorder = useRef<MediaRecorder | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const controller = useRef<AbortController | null>(null);
  const generation = useRef(0);
  const cancelled = useRef(false);
  const recordingEndedAt = useRef<number | null>(null);
  const callbacks = useRef({onResult, onError, onBusy});
  callbacks.current = {onResult, onError, onBusy};

  function release() {
    if (timer.current) clearInterval(timer.current);
    timer.current = null;
    stream.current?.getTracks().forEach(track => track.stop());
    stream.current = null;
  }
  useEffect(() => {
    let live = true;
    getVoiceConfig().then(value => {if (live) setConfig(value);}).catch(() => {});
    return () => {
      live = false;
      generation.current++;
      cancelled.current = true;
      if (recorder.current?.state === 'recording') recorder.current.stop();
      release();
      controller.current?.abort();
      callbacks.current.onBusy(false);
    };
  }, []);

  function stop(cancel = false) {
    cancelled.current = cancel;
    if (cancel) generation.current++;
    if (recorder.current?.state === 'recording') {
      recordingEndedAt.current = performance.now();
      recorder.current.stop();
    }
    release();
    if (cancel) {setState('idle'); callbacks.current.onBusy(false);}
  }

  async function start() {
    if (disabled || state !== 'idle') return;
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
      onError('Микрофон недоступен. Откройте Delta через localhost или HTTPS; текстовый чат доступен.');
      return;
    }
    const attempt = ++generation.current;
    cancelled.current = false;
    recordingEndedAt.current = null;
    setState('permission'); onBusy(true); onError('');
    try {
      // Obtain the limits/provider before opening a microphone permission prompt.
      const options = config || await getVoiceConfig();
      if (attempt !== generation.current) return;
      setConfig(options);
      const media = await navigator.mediaDevices.getUserMedia({audio:true});
      if (attempt !== generation.current) {media.getTracks().forEach(track => track.stop()); return;}
      stream.current = media;
      const mimeType = ['audio/webm;codecs=opus','audio/ogg;codecs=opus','audio/mp4'].find(type => MediaRecorder.isTypeSupported(type));
      const current = new MediaRecorder(media, mimeType ? {mimeType} : undefined);
      recorder.current = current;
      const chunks: Blob[] = [];
      let bytes = 0;
      current.ondataavailable = event => {
        if (attempt !== generation.current || !event.data.size || cancelled.current) return;
        bytes += event.data.size;
        if (bytes > options.max_bytes) {
          stop(true);
          callbacks.current.onError('Запись слишком большая. Попробуйте более короткое сообщение.');
          return;
        }
        chunks.push(event.data);
      };
      current.onerror = () => {
        if (attempt !== generation.current) return;
        stop(true);
        callbacks.current.onError('Не удалось записать звук. Проверьте микрофон и попробуйте снова.');
      };
      current.onstop = async () => {
        if (cancelled.current || attempt !== generation.current) return;
        release();
        const audio = new Blob(chunks, {type:current.mimeType || chunks[0]?.type || 'audio/webm'});
        if (!audio.size) {
          setState('idle'); callbacks.current.onBusy(false);
          callbacks.current.onError('Запись пустая. Попробуйте ещё раз.'); return;
        }
        setState('processing');
        controller.current = new AbortController();
        try {
          const result = await sendVoice(audio, deviceId, controller.current.signal, recordingEndedAt.current ?? performance.now());
          if (attempt === generation.current) callbacks.current.onResult(result);
        } catch (error) {
          if (attempt === generation.current) callbacks.current.onError((error as Error).message, (error as ApiError).transcript, (error as ApiError).timings);
        } finally {
          if (attempt === generation.current) {setState('idle'); callbacks.current.onBusy(false);}
        }
      };
      current.start(250);
      setSeconds(0); setState('recording');
      const began = Date.now();
      timer.current = setInterval(() => {
        const elapsed = Math.floor((Date.now()-began)/1000);
        setSeconds(elapsed);
        if (elapsed >= options.max_seconds) stop();
      }, 250);
    } catch (error) {
      release();
      if (attempt !== generation.current) return;
      setState('idle'); onBusy(false);
      const denied = (error as Error).name === 'NotAllowedError';
      onError(denied ? 'Доступ к микрофону запрещён. Разрешите его в настройках браузера или напишите сообщение.' :
        'Не удалось включить микрофон: '+(error as Error).message);
    }
  }

  return <div className="voice-input">
    <button type="button" className={state==='recording' ? 'voice-recording' : ''}
      aria-label={state==='recording' ? 'Остановить и отправить запись' : 'Записать голосовое сообщение'}
      disabled={state==='permission'||state==='processing'||(disabled&&state==='idle')}
      onClick={() => state==='recording' ? stop() : void start()}>
      {state==='recording' ? <Square size={18}/> : <Mic size={18}/>}
      {state==='recording' ? `Запись ${seconds} с` : 'Голос'}
    </button>
    {state==='recording'&&<button type="button" aria-label="Отменить запись" onClick={()=>stop(true)}><X size={16}/></button>}
    <span role="status">{state==='permission' ? 'Ожидание доступа к микрофону…' :
      state==='processing' ? 'Распознавание и обработка сообщения…' :
      state==='recording' ? `Остановите запись, чтобы отправить. Лимит ${config?.max_seconds} с.` :
      config?.provider==='mock' ? 'Тестовый режим: вместо речи используется заданная тестовая фраза.' : 'Нажмите, чтобы записать сообщение.'}</span>
  </div>;
}
