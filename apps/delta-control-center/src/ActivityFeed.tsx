import {useEffect,useRef,useState} from 'react';
import {ActivityEvent,request} from './api';
interface Page {items:ActivityEvent[];next_cursor:Record<string,string>|null}
export function ActivityFeed({compact=false}:{compact?:boolean}) {
  const [rows,setRows]=useState<ActivityEvent[]>([]),[cursor,setCursor]=useState<Page['next_cursor']>(null);
  const [filter,setFilter]=useState(''),[error,setError]=useState(''),[loading,setLoading]=useState(true);
  const refresh=useRef<()=>void>(()=>{});
  const older=useRef<()=>void>(()=>{});
  const debug=sessionStorage.getItem('delta-debug')==='true';
  useEffect(()=>{
    let live=true,busy=false;let next:Page['next_cursor']=null;let history=false;
    setRows([]);setCursor(null);setLoading(true);
    async function load(more=false){
      if(busy||!live)return;
      busy=true;setLoading(true);
      try {
        const params=new URLSearchParams({limit:compact?'5':'30',...(filter?{event_type:filter}:{}),...(more&&next?next:{})});
        const page=await request<Page>('/core/api/v1/activity?'+params);
        if(live){setRows(old=>more?[...old,...page.items.filter(item=>!old.some(row=>row.id===item.id))]:page.items);next=page.next_cursor;setCursor(next);setError('');history=more;}
      }catch(e){if(live)setError((e as Error).message);}finally{busy=false;if(live)setLoading(false);}
    }
    refresh.current=()=>{void load();};older.current=()=>{if(next)void load(true);};
    void load();const timer=setInterval(()=>{if(!history)void load();},5000);
    return()=>{live=false;clearInterval(timer);};
  },[compact,filter]);
  return <div className="activity-feed"><div className="section-heading"><h2>{compact?'Recent activity':'Журнал событий'}</h2><button disabled={loading} onClick={()=>refresh.current()}>Обновить</button></div>
    {!compact&&<label>Тип события<select aria-label="Тип события" value={filter} onChange={e=>setFilter(e.target.value)}><option value="">Все, кроме heartbeat</option>{['DEVICE_CONNECTED','DEVICE_OFFLINE','VOICE_REQUEST','STT_COMPLETED','ASSISTANT_REQUEST','TOOL_SELECTED','TOOL_COMPLETED','TASK_CREATED','TASK_UPDATED','WORKSPACE_LAUNCHED','COMMAND_SENT','COMMAND_COMPLETED','SERVICE_ONLINE','SERVICE_OFFLINE','IOT_ACTION','HEARTBEAT'].map(type=><option key={type}>{type}</option>)}</select></label>}
    {error&&<p className="error" role="alert">Не удалось обновить события: {error}. Показаны последние полученные данные.</p>}
    {loading&&<p role="status">Загрузка событий…</p>}
    {!loading&&!error&&!rows.length&&<article className="empty">Событий пока нет</article>}
    {rows.map(row=><article key={row.id}><small>{new Date(row.created_at).toLocaleString('ru-RU')} · {row.event_type}</small><p>{row.message}</p>{debug&&<details><summary>Данные события</summary><pre>{JSON.stringify(row.details,null,2)}</pre></details>}</article>)}
    {!compact&&cursor&&<button disabled={loading} onClick={()=>older.current()}>Загрузить более ранние</button>}
    {!compact&&<small>Обновление каждые 5 секунд. При просмотре истории нажмите «Обновить», чтобы вернуться к новым событиям.</small>}
  </div>;
}
