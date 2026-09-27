import {useEffect,useState} from 'react';
import {getDevices,getServices,getTasks,getWorkspaces} from './api';
import {ActivityFeed} from './ActivityFeed';

type Metric={label:string;value:string|null;error:boolean};
const initial:Metric[]=['Устройства онлайн / всего','Сервисы онлайн / всего','Рабочие пространства','Открытые задачи'].map(label=>({label,value:null,error:false}));
export function Overview({online}:{online:boolean}) {
  const [metrics,setMetrics]=useState(initial);
  const connected=Boolean(sessionStorage.getItem('delta-token'));
  useEffect(()=>{
    if(!connected)return;
    let live=true,busy=false;
    async function refresh(){
      if(busy)return;busy=true;
      const results=await Promise.allSettled([
        getDevices().then(rows=>`${rows.filter(row=>row.status==='online').length} / ${rows.length}`),
        getServices().then(rows=>`${rows.filter(row=>row.status==='online').length} / ${rows.length}`),
        getWorkspaces().then(rows=>String(rows.length)),
        Promise.all([getTasks({status:'todo'}),getTasks({status:'in_progress'})]).then(([todo,progress])=>`${todo.length+progress.length}${todo.length===1000||progress.length===1000?'+':''}`),
      ]);
      if(live)setMetrics(old=>old.map((metric,index)=>{
        const result=results[index];
        return {...metric,value:result.status==='fulfilled'?result.value:metric.value,error:result.status==='rejected'};
      }));
      busy=false;
    }
    void refresh();const timer=setInterval(refresh,5000);
    return()=>{live=false;clearInterval(timer);};
  },[connected]);
  return <><article className="hero"><div className="hero-mark">Δ</div><div><span className="eyebrow">SYSTEM STATUS</span><h2>{online?'Core is ready':'Waiting for Core'}</h2><p>Устройства, сервисы и задачи в одном пространстве.</p></div><span className={online?'badge success':'badge'}>{online?'Online':'Offline'}</span></article>
    {!connected?<article><h2>Подключение к Delta</h2><p>Откройте Settings и сохраните Development token, чтобы увидеть ваши устройства, задачи и события.</p></article>:<><div className="grid overview-metrics">{metrics.map(metric=><article key={metric.label}><h2>{metric.label}</h2><strong>{metric.value??'—'}</strong>{metric.error?<p role="alert">Не удалось обновить{metric.value!==null?' · данные устарели':''}</p>:metric.value===null?<p>Загрузка…</p>:null}</article>)}</div><ActivityFeed compact/></>}
  </>;
}
