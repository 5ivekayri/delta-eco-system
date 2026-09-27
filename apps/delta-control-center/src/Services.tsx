import {useEffect,useRef,useState} from 'react';
import {Boxes} from 'lucide-react';
import {getServices,Service} from './api';
export function Services(){
  const [rows,setRows]=useState<Service[]>([]),[error,setError]=useState(''),[loading,setLoading]=useState(true);
  const refresh=useRef<()=>void>(()=>{});
  const debug=sessionStorage.getItem('delta-debug')==='true';
  useEffect(()=>{let live=true,busy=false;const load=async()=>{
    if(busy)return;busy=true;setLoading(true);
    try{const data=await getServices();if(live){setRows(data);setError('');}}
    catch(e){if(live)setError((e as Error).message);}finally{busy=false;if(live)setLoading(false);}
  };refresh.current=()=>{void load();};void load();const id=setInterval(load,5000);return()=>{live=false;clearInterval(id);};},[]);
  return <><div className="section-heading"><p>Проверка здоровья каждые 15 секунд · обновление экрана каждые 5 секунд</p><button disabled={loading} onClick={()=>refresh.current()}>Обновить</button></div>
    {error&&<div className="error" role="alert">Данные сервисов могли устареть: {error}</div>}
    {loading&&<p role="status">Загрузка сервисов…</p>}
    {!loading&&!error&&!rows.length&&<article className="empty">Сервисы не настроены</article>}
    <div className="grid">{rows.map(service=><article key={service.service_id}><Boxes size={23}/><span className={'badge '+(service.status==='online'?'success':'')}>{service.status}</span><h2>{service.name}</h2><p>v{service.version||'—'} · {service.available_tools.length} tools</p><small>Последняя проверка: {service.last_health_check?new Date(service.last_health_check).toLocaleString('ru-RU'):'ожидание'}</small>{service.status!=='online'&&<p>Инструменты сервиса сейчас недоступны.</p>}<details><summary>Доступные инструменты</summary>{service.available_tools.map(tool=><p key={tool.name}><strong>{tool.name}</strong><br/>{tool.description}</p>)}</details>{debug&&<p>{service.service_id} · {service.base_url}</p>}</article>)}</div></>;
}
