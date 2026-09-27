import {FormEvent,useEffect,useRef,useState} from 'react';
import {LatencyDetails} from './LatencyDetails';
import {VoicePlayback} from './VoicePlayback';
import {VoiceInput} from './VoiceInput';
import {MarkdownMessage} from './MarkdownMessage';
import {ArrowUp,MessageSquare} from 'lucide-react';
import {AssistantResponse,Device,Interaction,VoiceTimings,getDevices,getHistory,sendMessage} from './api';

export function Assistant(){
  const [history,setHistory]=useState<Interaction[]>([]);const [devices,setDevices]=useState<Device[]>([]);
  const [deviceId,setDeviceId]=useState(sessionStorage.getItem('delta-device')||'');
  const [spokenResponse,setSpokenResponse]=useState<AssistantResponse>();
  const [voiceBusy,setVoiceBusy]=useState(false);
  const [errorTimings,setErrorTimings]=useState<VoiceTimings>();
  const [transcript,setTranscript]=useState('');
  const [message,setMessage]=useState('');const [busy,setBusy]=useState(false);const [error,setError]=useState('');
  const bottom=useRef<HTMLDivElement>(null);const debug=sessionStorage.getItem('delta-debug')==='true';
  useEffect(()=>{getHistory().then(setHistory).catch(e=>setError(e.message));getDevices().then(setDevices).catch(()=>{});},[]);
  useEffect(()=>{bottom.current?.scrollIntoView({behavior:'smooth',block:'nearest'});},[history]);
  async function submit(event:FormEvent){event.preventDefault();if(!message.trim()||busy||voiceBusy)return;setSpokenResponse(undefined);setBusy(true);setError('');const userMessage=message;
    try{const response=await sendMessage(userMessage,deviceId);setHistory(h=>[...h,{...response,user_message:userMessage,created_at:new Date().toISOString()}]);setMessage('');}
    catch(e){setError((e as Error).message);}finally{setBusy(false);}}
  return <div className="assistant"><div className="assistant-context"><label>Текущий компьютер<select aria-label="Текущий компьютер" value={deviceId} onChange={e=>{setDeviceId(e.target.value);sessionStorage.setItem('delta-device',e.target.value);}}><option value="">Выберите для команд «на этом компьютере»</option>{devices.map(d=><option value={d.id} key={d.id}>{d.display_name} · {d.status}</option>)}</select></label></div>
    <div className="messages">{!history.length&&<div className="chat-empty"><span className="symbol">Δ</span><h2>Что сделаем сегодня?</h2><p>Ваши устройства, проекты и задачи — в одном разговоре.</p><div className="suggestions">{['Покажи устройства','Покажи задачи','Добавь задачу протестировать API','Открой Dark Weather'].map(text=><button key={text} onClick={()=>setMessage(text)}>{text}</button>)}</div></div>}{history.map(item=><div className="exchange" key={item.id}><div className="user-message"><span>YOU</span><p>{item.user_message}</p></div><div className="assistant-message"><span>Δ DELTA</span><MarkdownMessage text={item.assistant_text}/>{debug&&!item.timings&&item.route_source&&<p className="route-source">{item.route_source==='local' ? 'Local route' : 'LLM route'} · {item.local_router_ms?.toFixed(2)} ms · confidence {Math.round((item.confidence??0)*100)}%</p>}{debug&&item.timings&&<LatencyDetails timings={item.timings}/>}{debug&&item.tool_calls.length>0&&<details><summary>Tool execution details</summary><pre>{JSON.stringify({calls:item.tool_calls,results:item.tool_results},null,2)}</pre></details>}</div></div>)}<div ref={bottom}/></div>
    {transcript&&<div className="voice-transcript"><strong>Распознано</strong><p>{transcript}</p></div>}
    <VoiceInput disabled={busy} deviceId={deviceId} onBusy={value=>{setVoiceBusy(value);if(value)setSpokenResponse(undefined);}}
      onError={(text,recognized,timings)=>{setError(text);setErrorTimings(timings);if(recognized){setTranscript(recognized);setMessage(recognized);}}}
      onResult={response=>{setSpokenResponse(response);setError('');setErrorTimings(undefined);setTranscript(response.transcript||'');setHistory(h=>[...h,{...response,user_message:response.transcript||'',created_at:new Date().toISOString()}]);}}/>
    <VoicePlayback response={spokenResponse}/>
    {debug&&errorTimings&&<LatencyDetails timings={errorTimings}/>}
    {error&&<div className="error" role="alert">{error}</div>}{busy&&<p role="status" className="thinking">Обработка запроса…</p>}
    <form className="composer" onSubmit={submit}><MessageSquare size={19}/><input aria-label="Сообщение Assistant" value={message} onChange={e=>setMessage(e.target.value)} placeholder="Что нужно сделать?" maxLength={10000} disabled={busy}/><button className="primary" aria-label="Отправить" disabled={busy||voiceBusy||!message.trim()}><ArrowUp size={19}/></button></form><p className="composer-note">Действия выполняются через подключённые устройства и сервисы.</p>
  </div>;
}
