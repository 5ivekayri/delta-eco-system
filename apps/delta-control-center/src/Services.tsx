import {useEffect,useState} from 'react';
import {Boxes} from 'lucide-react';
import {getServices,Service} from './api';
export function Services(){
  const [rows,setRows]=useState<Service[]>([]);const [error,setError]=useState('');
  useEffect(()=>{let live=true;const refresh=()=>getServices().then(data=>{if(live){setRows(data);setError('');}}).catch(e=>{if(live)setError(e.message);});refresh();const id=setInterval(refresh,5000);return()=>{live=false;clearInterval(id);};},[]);
  return <>{error&&<div className="error" role="alert">{error}</div>}<div className="grid">{rows.map(service=><article key={service.service_id}><Boxes size={23}/><span className={'badge '+(service.status==='online'?'success':'')}>{service.status}</span><h2>{service.name}</h2><p>v{service.version||'—'} · {service.available_tools.length} tools</p><p>{service.base_url}</p><small>Last check: {service.last_health_check?new Date(service.last_health_check).toLocaleTimeString():'ожидание'}</small><details><summary>Available tools</summary>{service.available_tools.map(tool=><p key={tool.name}><strong>{tool.name}</strong><br/>{tool.description}</p>)}</details></article>)}</div></>;
}
