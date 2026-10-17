import {useEffect,useRef,useState} from 'react';
export function WorkingIndicator({text='Запрос принят. Обрабатываю…',recording=false,level=0}:{text?:string;recording?:boolean;level?:number}){
  const container=useRef<HTMLDivElement|null>(null);
  useEffect(()=>{container.current?.scrollIntoView({block:'nearest',behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth'});},[]);
  const [seconds,setSeconds]=useState(0);
  useEffect(()=>{const start=Date.now();const timer=setInterval(()=>setSeconds(Math.floor((Date.now()-start)/1000)),1000);return()=>clearInterval(timer);},[]);
  return <div ref={container} className={'working-indicator '+(recording?'listening':'processing')} role="status" aria-live="polite">
    <div className="voice-orb" aria-hidden="true"><span>Δ</span><div className="voice-rings"/></div>
    <div><strong>{recording?text:seconds>=15?'Ответ ещё готовится':text}</strong><p>{recording?'Говорите спокойно. Я слушаю.':seconds>=15?'Ожидаю завершения обработки. Повторно отправлять запрос не нужно.':'Запрос обрабатывается. Ответ появится здесь.'}</p>
    {recording?<div className="voice-wave" aria-hidden="true">{[.4,.7,1,.65,.9,.5,.8].map((factor,i)=><i key={i} style={{transform:`scaleY(${.15+Math.min(1,level*12)*factor})`}}/>)}</div>:<small aria-hidden="true">{seconds} с</small>}</div>
  </div>;
}
