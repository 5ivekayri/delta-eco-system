import {useSyncExternalStore} from 'react';
import {clearRequestLog, getRequestLog, loggingEnabled, setLogging, subscribeRequestLog} from './requestLog';

const providers = {openrouter:'OpenRouter', local:'Локальная LLM', mock:'Тестовый провайдер', bridge_unknown:'Bridge — маршрут не подтверждён'};
export function RequestLog() {
  const enabled = useSyncExternalStore(subscribeRequestLog, loggingEnabled);
  const entries = useSyncExternalStore(subscribeRequestLog, getRequestLog);
  return <div className="request-log">
    <label className="debug-toggle"><input type="checkbox" checked={enabled} onChange={e=>setLogging(e.target.checked)}/>Журнал запросов LLM</label>
    {(enabled || entries.length>0)&&<details open><summary>Запросы: {entries.length} · {enabled?'запись включена':'запись выключена'}</summary>
      <p>Последние 50 текстовых и голосовых запросов в этой вкладке. Без текста сообщений и ключей. Журнал очищается при обновлении страницы.</p>
      <button onClick={clearRequestLog} disabled={!entries.length}>Очистить журнал</button>
      {!entries.length&&<p>Отправьте сообщение, чтобы увидеть провайдера, модель и время ответа.</p>}
      <div className="request-log-entries">{entries.map(entry=><article key={entry.id}>
        <strong>{entry.time} · {entry.kind} · {entry.status?`HTTP ${entry.status}`:'Ошибка сети / отмена'} · {Math.round(entry.duration_ms)} мс</strong>
        {entry.calls===undefined?<p>Данные о LLM недоступны.</p>:!entry.calls.length?<p>Без обращения к LLM — локальная обработка.</p>:entry.calls.map((call,i)=><p key={i}>
          {providers[call.provider] || 'Неизвестный провайдер'} · {call.model || 'модель неизвестна'} · {call.role==='router'?'маршрутизация':'ответ'} · {Math.round(call.duration_ms)} мс · {call.outcome}
          {(call.attempts??0)>1&&` · попыток: ${call.attempts}`}{call.fallback&&' · переход с OpenRouter на локальную LLM'}
        </p>)}
      </article>)}</div>
    </details>}
  </div>;
}
