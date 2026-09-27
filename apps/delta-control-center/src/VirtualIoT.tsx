import {useEffect, useRef, useState} from 'react';
import {Lightbulb, Thermometer, Sun, Activity, RefreshCw} from 'lucide-react';
import {getIoTState, setIoTLight, IoTState} from './api';

export function VirtualIoT() {
  const [state,setState] = useState<IoTState>();
  const [loading,setLoading] = useState(true);
  const [busy,setBusy] = useState(false);
  const [error,setError] = useState('');
  const live = useRef(false);
  const pendingWrite = useRef(false);
  const pendingRead = useRef(false);
  const generation = useRef(0);

  async function refresh() {
    if(pendingWrite.current || pendingRead.current) return;
    pendingRead.current = true;
    const attempt = ++generation.current;
    try {
      const data = await getIoTState();
      if(live.current && attempt===generation.current){setState(data);setError('');}
    } catch(e) {
      if(live.current && attempt===generation.current) setError((e as Error).message);
    } finally {
      pendingRead.current = false;
      if(live.current && attempt===generation.current) setLoading(false);
    }
  }
  useEffect(()=>{
    live.current=true;
    void refresh();
    const timer=setInterval(()=>void refresh(),3000);
    return ()=>{live.current=false;generation.current++;pendingRead.current=false;clearInterval(timer);};
  },[]);

  async function changeLight() {
    if(!state || pendingWrite.current || error) return;
    const enabled = !state.desk_light;
    const attempt = ++generation.current;
    pendingWrite.current=true;setBusy(true);
    try {
      const updated=await setIoTLight(enabled);
      if(live.current && attempt===generation.current){setState(updated);setError('');}
    } catch(e) {
      if(live.current && attempt===generation.current)setError((e as Error).message);
    } finally {
      pendingWrite.current=false;
      if(live.current){setBusy(false);setLoading(false);}
    }
  }
  return <div className="iot-panel">
    <div className="section-heading"><div><h2>Рабочее место</h2><p>Виртуальные датчики и рабочий свет. Физические устройства не подключены.</p></div>
      <button onClick={()=>void refresh()} disabled={busy} aria-label="Обновить IoT"><RefreshCw size={16}/> Обновить</button></div>
    {error&&<div className="error" role="alert">{error}{state&&' Показаны последние полученные значения.'}</div>}
    {loading&&!state?<article role="status">Загрузка IoT…</article>:!state?<article className="empty">Нет данных IoT. Проверьте подключение и обновите страницу.</article>:<>
      <div className="grid iot-grid">
        <article><Lightbulb size={24}/><span className="badge">Эмуляция</span><h2>Рабочий свет</h2>
          <p role="status">{busy?'Сохранение…':state.desk_light?'Включён':'Выключен'}</p>
          <button type="button" role="switch" aria-label="Рабочий свет" aria-checked={state.desk_light} disabled={busy||!!error}
            className={state.desk_light?'primary':''} onClick={()=>void changeLight()}>{state.desk_light?'Выключить':'Включить'}</button>
        </article>
        <article><Thermometer size={24}/><h2>Температура</h2><p className="iot-value" data-testid="iot-temperature">{state.temperature.toLocaleString('ru-RU')} °C</p><small>Виртуальный датчик температуры</small></article>
        <article><Sun size={24}/><h2>Освещённость</h2><p className="iot-value" data-testid="iot-brightness">{state.brightness} %</p><small>Виртуальный датчик освещённости</small></article>
        <article><Activity size={24}/><h2>Движение</h2><p className="iot-value" data-testid="iot-motion">{state.motion?'Обнаружено':'Нет движения'}</p><small>Виртуальный датчик движения</small></article>
      </div>
      <p className="composer-note">Состояние сохранено: {new Date(state.updated_at).toLocaleString('ru-RU')}. Значения обновляются каждые 3 секунды.</p>
      <p>Можно сказать Assistant: «Включи рабочий свет», «Выключи свет» или «Какая температура?».</p>
    </>}
  </div>;
}
