import {useEffect, useState} from 'react';
import {ArrowLeft, Monitor, RefreshCw} from 'lucide-react';
import {Device, getDevice, getDevices, sendCommand, CommandResult} from './api';

export function Devices() {
  const [devices,setDevices] = useState<Device[]>([]);
  const [selected,setSelected] = useState<string|null>(null);
  const [detail,setDetail] = useState<Device|null>(null);
  const [loading,setLoading] = useState(true);
  const [error,setError] = useState('');
  const [busy,setBusy] = useState(false);
  const [result,setResult] = useState<CommandResult|null>(null);
  useEffect(() => {
    let live=true;
    const refresh=async()=>{
      try {
        const rows=await getDevices();
        const data=selected?await getDevice(selected):null;
        if(live){setDevices(rows);setDetail(data);setError('');}
      }catch(e){if(live)setError((e as Error).message);}
      finally{if(live)setLoading(false);}
    };
    refresh();const interval=setInterval(refresh,3000);
    return()=>{live=false;clearInterval(interval);};
  },[selected]);
  async function command(action: string,payload={}) {
    if(!selected)return;
    setBusy(true);setError('');setResult(null);
    try{setResult(await sendCommand(selected,action,payload));setDetail(await getDevice(selected));}
    catch(e){setError((e as Error).message);}finally{setBusy(false);}
  }
  return <>
    {error&&<div className="error" role="alert">{error}</div>}
    {selected&&<button onClick={()=>{setSelected(null);setDetail(null);setResult(null);}}><ArrowLeft size={14}/> Все устройства</button>}
    {loading?<article className="empty">Загрузка устройств…</article>:selected&&detail?<>
      <article className="device-detail"><div className="section-heading"><h2>{detail.display_name}</h2><span className={'badge '+(detail.status==='online'?'success':'')}>{detail.status}</span></div>
        <dl>{[['Hostname',detail.hostname],['OS',detail.os],['Architecture',detail.architecture],['Username',detail.username],['Agent',detail.agent_version],['Last heartbeat',new Date(detail.last_seen).toLocaleString()],['Capabilities',detail.capabilities.join(', ')]].map(([k,v])=><div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}</dl>
        <div className="actions"><button disabled={busy||detail.status!=='online'} onClick={()=>command('system_info')}>Get System Info</button><button disabled={busy||detail.status!=='online'} onClick={()=>command('open_url',{url:'https://example.com'})}>Open Example URL</button></div>
        {busy&&<p><RefreshCw size={14}/> Ожидание Agent…</p>}
        {result&&<div role="status" className={result.success?'result':'error'}><p>{result.message}</p>{result.data&&<pre>{JSON.stringify(result.data,null,2)}</pre>}</div>}
      </article><h2>Recent commands & results</h2><article>{detail.recent_commands?.length?detail.recent_commands.map(event=><div className="event" key={event.id}><span>{new Date(event.created_at).toLocaleTimeString()}</span><div><strong>{event.event_type}</strong><p>{event.message}</p></div></div>):<p>Команд пока нет</p>}</article>
    </>:<div className="grid">{devices.map(device=><button className="device-card" key={device.id} onClick={()=>{setSelected(device.id);setLoading(true);}}><Monitor size={25}/><span className={'badge '+(device.status==='online'?'success':'')}>{device.status}</span><h2>{device.display_name}</h2><p>{device.os} · {device.architecture}</p><small>Last seen {new Date(device.last_seen).toLocaleString()}</small><div className="capabilities">{device.capabilities.map(c=><span key={c}>{c}</span>)}</div></button>)}{!devices.length&&<article className="empty"><Monitor size={28}/><h2>Устройства ещё не подключены</h2><p>Запустите Delta Agent на компьютере. Инструкция — в README проекта.</p></article>}</div>}
  </>;
}
