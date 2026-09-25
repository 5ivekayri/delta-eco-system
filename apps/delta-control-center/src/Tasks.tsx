import {FormEvent, useCallback, useEffect, useState} from 'react';
import {Plus, Check, Pencil, Trash2} from 'lucide-react';
import {Task, TaskInput, Workspace, getWorkspaces, getTasks, createTask, updateTask, deleteTask} from './api';

export function Tasks() {
  const [rows,setRows]=useState<Task[]>([]);
  const [status,setStatus]=useState('');
  const [workspace,setWorkspace]=useState('');
  const [workspaces,setWorkspaces]=useState<Workspace[]>([]);
  useEffect(()=>{getWorkspaces().then(setWorkspaces).catch(()=>{});},[]);
  const [priority,setPriority]=useState('');
  const [error,setError]=useState('');
  const [loading,setLoading]=useState(true);
  const [editing,setEditing]=useState<Task|null>(null);
  const [form,setForm]=useState(false);
  const [busy,setBusy]=useState(false);
  const refresh=useCallback(async()=>{try{setRows(await getTasks({status,priority,workspace_id:workspace}));setError('');}catch(e){setError((e as Error).message);}finally{setLoading(false);}},[status,priority,workspace]);
  useEffect(()=>{refresh();const id=setInterval(refresh,5000);return()=>clearInterval(id);},[refresh]);
  async function save(event:FormEvent<HTMLFormElement>){
    event.preventDefault();setBusy(true);
    const data=new FormData(event.currentTarget);
    const body:TaskInput={title:String(data.get('title')),description:String(data.get('description')),workspace_id:String(data.get('workspace_id'))||null,priority:data.get('priority') as Task['priority'],due_date:String(data.get('due_date'))||null};
    try{if(editing)await updateTask(editing.id,body);else await createTask(body);setForm(false);await refresh();}catch(e){setError((e as Error).message);}finally{setBusy(false);}
  }
  async function complete(task:Task){setBusy(true);try{await updateTask(task.id,{status:task.status==='done'?'todo':'done'});await refresh();}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
  async function remove(task:Task){if(!confirm(`Удалить задачу «${task.title}»?`))return;setBusy(true);try{await deleteTask(task.id);await refresh();}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
  return <>
    <div className="toolbar"><div className="filters"><label>Пространство<select aria-label="Фильтр пространства" value={workspace} onChange={e=>setWorkspace(e.target.value)}><option value="">Все пространства</option>{workspaces.map(w=><option key={w.id} value={w.id}>{w.name}</option>)}</select></label><label>Статус<select aria-label="Статус" value={status} onChange={e=>setStatus(e.target.value)}><option value="">Все статусы</option><option value="todo">To do</option><option value="in_progress">In progress</option><option value="done">Done</option></select></label><label>Приоритет<select aria-label="Приоритет" value={priority} onChange={e=>setPriority(e.target.value)}><option value="">Все приоритеты</option><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option></select></label></div><button className="primary" onClick={()=>{setEditing(null);setForm(true);}}><Plus size={15}/> Новая задача</button></div>
    {error&&<div role="alert" className="error">{error}</div>}
    {form&&<article className="editor"><h2>{editing?'Редактировать задачу':'Новая задача'}</h2><form onSubmit={save} key={editing?.id||'new'}><label>Название<input name="title" defaultValue={editing?.title} required maxLength={300}/></label><label>Описание<textarea name="description" defaultValue={editing?.description}/></label><label>Пространство задачи<select aria-label="Пространство задачи" name="workspace_id" defaultValue={editing?.workspace_id||''}><option value="">Без пространства</option>{workspaces.map(w=><option key={w.id} value={w.id}>{w.name}</option>)}</select></label><div className="grid"><label>Приоритет задачи<select aria-label="Приоритет задачи" name="priority" defaultValue={editing?.priority||'medium'}><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option></select></label><label>Срок<input name="due_date" type="date" defaultValue={editing?.due_date||''}/></label></div><div className="actions"><button className="primary" disabled={busy}>Сохранить задачу</button><button type="button" onClick={()=>setForm(false)}>Отмена</button></div></form></article>}
    <article>{loading?<p>Загрузка задач…</p>:!rows.length?<div className="empty">Задач пока нет</div>:rows.map(task=><div className="task-row" key={task.id}><button title={task.status==='done'?'Вернуть в работу':'Завершить'} className={task.status==='done'?'check checked':'check'} disabled={busy} onClick={()=>complete(task)}><Check size={14}/></button><div className="task-title"><strong>{task.title}</strong>{task.description&&<p>{task.description}</p>}<small>{task.status} · {task.priority}{task.due_date&&` · ${task.due_date}`}</small></div><select aria-label={`Статус ${task.title}`} value={task.status} disabled={busy} onChange={async e=>{try{await updateTask(task.id,{status:e.target.value as Task['status']});await refresh();}catch(err){setError((err as Error).message);}}}><option value="todo">To do</option><option value="in_progress">In progress</option><option value="done">Done</option></select><button title="Редактировать" onClick={()=>{setEditing(task);setForm(true);}}><Pencil size={14}/></button><button title="Удалить" disabled={busy} onClick={()=>remove(task)}><Trash2 size={14}/></button></div>)}</article>
  </>;
}
