import {useEffect,useRef,useState} from 'react';
import {Upload,Download,FileText,Sparkles,Save,Plus,FolderOpen,PanelLeftClose,X,BookOpen,Pencil,History,Check,Search,Copy} from 'lucide-react';
import {request} from './api';
import {MarkdownMessage} from './MarkdownMessage';
import {WordEditor} from './WordEditor';
import {hasChanges,type WordDocument,type RichChanges} from './wordModel';
import './documents.css';

type Row={id:string;name:string;revision:number;updated_at:string};
type Proposal={base_revision:number;edits:{block_id:string;old_text:string;text:string}[];append:string[]};
const base='/core/api/v1/documents';
export function Documents({onDirty}:{onDirty?:(dirty:boolean)=>void}){
 const [rows,setRows]=useState<Row[]>([]),[doc,setDoc]=useState<WordDocument|null>(null),[changes,setChanges]=useState<RichChanges|null>(null);
 const [editing,setEditing]=useState(false),[library,setLibrary]=useState(true),[assistant,setAssistant]=useState(false),[versions,setVersions]=useState(false);
 const [filter,setFilter]=useState(''),[newName,setNewName]=useState(''),[nameAction,setNameAction]=useState<'create'|'rename'|'copy'|null>(null);
 const [selected,setSelected]=useState<string[]>([]),[instruction,setInstruction]=useState(''),[proposal,setProposal]=useState<Proposal|null>(null),[answer,setAnswer]=useState('');
 const [busy,setBusy]=useState(''),[error,setError]=useState(''),[notice,setNotice]=useState('');
 const nameLauncher=useRef<HTMLElement|null>(null);
 const uploadInput=useRef<HTMLInputElement>(null),saveAction=useRef<()=>void>(()=>{});
 const dirty=changes!==null&&hasChanges(changes),current=doc?.view_revision===doc?.revision;
 useEffect(()=>{onDirty?.(dirty);return()=>onDirty?.(false);},[dirty,onDirty]);
 useEffect(()=>{const warn=(e:BeforeUnloadEvent)=>{if(dirty){e.preventDefault();e.returnValue='';}};const shortcut=(e:KeyboardEvent)=>{if(e.defaultPrevented)return;if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='s'){e.preventDefault();saveAction.current();}};window.addEventListener('beforeunload',warn);window.addEventListener('keydown',shortcut);return()=>{window.removeEventListener('beforeunload',warn);window.removeEventListener('keydown',shortcut);};},[dirty]);
 useEffect(()=>{request<Row[]>(base).then(setRows).catch(e=>setError(e.message));},[]);
 function accept(d:WordDocument,edit=false){setDoc(d);setChanges(null);setSelected([]);setProposal(null);setAnswer('');setVersions(false);setEditing(edit);}
 async function refresh(){setRows(await request<Row[]>(base));}
 async function load(id:string,revision?:number){if(dirty&&!confirm('Изменения ещё не сохранены. Открыть другой документ и отказаться от правок?'))return;setBusy('Открываем документ…');setError('');setNotice('');try{accept(await request<WordDocument>(base+'/'+id+(revision?'?revision='+revision:'')));}catch(e){setError((e as Error).message);}finally{setBusy('');}}
 async function upload(file:File){
  if(!file.name.toLowerCase().endsWith('.docx')||file.size>10*1024*1024){setError('Откройте файл Word в формате .docx, не больше 10 МБ.');return;}
  if(dirty&&!confirm('Открыть загружаемый документ без сохранения текущих правок?'))return;
  setBusy('Загружаем документ…');setError('');setNotice('');
  try{const form=new FormData();form.append('file',file);const row=await request<Row>(base,{method:'POST',body:form});accept(await request<WordDocument>(base+'/'+row.id));await refresh();setNotice('Документ открыт. Оригинал сохранён в истории версий.');}catch(e){setError((e as Error).message);}finally{setBusy('');}
 }
 function openName(action:'create'|'rename'|'copy'){nameLauncher.current=document.activeElement as HTMLElement;setNewName(action==='create'?'':action==='rename'?doc!.name.replace(/\.docx$/i,''):doc!.name.replace(/\.docx$/i,'').slice(0,210)+' — копия'+(!current?' (версия '+doc!.view_revision+')':''));setError('');setNameAction(action);}
 function closeName(){setNameAction(null);requestAnimationFrame(()=>nameLauncher.current?.focus());}
 async function submitName(){
  if(busy)return;
  const title=newName.trim(),stem=title.replace(/\.docx$/i,'');
  if((title&&!stem.replace(/[ .]/g,''))||/[\\/\x00-\x1f\x7f]/.test(title)){setError('Введите название без слешей и управляющих символов.');return;}
  if(nameAction==='create'){await create();return;}
  if(!doc||!newName.trim()||(nameAction==='copy'&&dirty))return;
  const action=nameAction;setBusy(action==='rename'?'Переименовываем…':'Создаём копию…');setError('');setNotice('');
  try{
   if(action==='rename'){const row=await request<Row>(base+'/'+doc.id,{method:'PATCH',body:JSON.stringify({name:newName.trim(),base_name:doc.name})});setDoc(d=>d?{...d,name:row.name,updated_at:row.updated_at}:d);setRows(rows=>rows.map(r=>r.id===row.id?row:r));setNotice('Название изменено.');}
   else {const copy=await request<WordDocument>(base+'/'+doc.id+'/copy',{method:'POST',body:JSON.stringify({name:newName.trim(),revision:doc.view_revision})});accept(copy,true);setRows(rows=>[copy,...rows]);setFilter('');setNotice('Копия создана. Можно редактировать — исходный документ сохранён.');}
   closeName();await refresh();
  }catch(e){setError((e as Error).message);}finally{setBusy('');}
 }
 async function create(){if(dirty&&!confirm('Создать документ без сохранения текущих правок?'))return;setBusy('Создаём документ…');setError('');try{accept(await request<WordDocument>(base+'/blank',{method:'POST',body:JSON.stringify({name:newName.trim()||'Новый документ'})}),true);closeName();setFilter('');setNewName('');await refresh();setNotice('Можно начинать писать.');}catch(e){setError((e as Error).message);}finally{setBusy('');}}
 async function save(proposed?:Proposal){
  if(!doc||busy||(!proposed&&!dirty))return;setBusy('Сохраняем…');setError('');setNotice('');
  try{const saved=await request<WordDocument>(base+'/'+doc.id+(proposed?'':'/content'),{method:'PUT',body:JSON.stringify(proposed??changes)});accept(saved,editing);setNotice('Все изменения сохранены.');await refresh();}catch(e){setError((e as Error).message);}finally{setBusy('');}
 }
 saveAction.current=()=>{if(!nameAction)void save();};
 async function ai(edit:boolean){if(!doc)return;setBusy(edit?'Готовим предложения…':'Читаем документ…');setError('');setProposal(null);setAnswer('');try{const result=await request<Proposal&{answer:string}>(base+'/'+doc.id+(edit?'/propose':'/ask'),{method:'POST',body:JSON.stringify({revision:doc.revision,instruction,block_ids:selected})});if(edit)setProposal(result);else setAnswer(result.answer);}catch(e){setError((e as Error).message);}finally{setBusy('');}}
 return <div className="word-workspace">
  <input ref={uploadInput} className="word-file-input" aria-label="Загрузить DOCX" type="file" accept=".docx" disabled={!!busy} onChange={e=>{const file=e.target.files?.[0];e.target.value='';if(file)void upload(file);}}/>
  <div className="word-topbar">
   <button title={library?'Скрыть список документов':'Мои документы'} aria-label="Мои документы" aria-expanded={library} onClick={()=>setLibrary(!library)}>{library?<PanelLeftClose size={19}/>:<FolderOpen size={19}/>}</button>
   <div className="word-title"><strong>{doc?.name.replace(/\.docx$/i,'')||'Мои документы'}</strong><span role="status">{busy|| (dirty?'Есть несохранённые изменения':doc?'Все изменения сохранены':'Файлы Word в одном месте')}</span></div>
   {doc&&<><div className="word-mode" aria-label="Режим документа"><button aria-pressed={!editing} disabled={!!busy} onClick={()=>setEditing(false)}><BookOpen size={16}/><span>Чтение</span></button><button aria-pressed={editing} disabled={!!busy||!current} onClick={()=>setEditing(true)}><Pencil size={16}/><span>Редактирование</span></button></div>
    <button className="primary word-save" title="Сохранить (Ctrl+S)" disabled={!!busy||!dirty||!current} onClick={()=>void save()}><Save size={16}/><span>Сохранить</span></button>
    <button title="История версий" aria-label="История версий" aria-expanded={versions} disabled={!!busy} onClick={()=>setVersions(!versions)}><History size={18}/></button>
    <a className={'word-download'+(dirty?' disabled':'')} title={dirty?'Сначала сохраните изменения':'Скачать Word'} aria-label="Скачать Word" aria-disabled={dirty} href={dirty?undefined:base+'/'+doc.id+'/download?revision='+doc.view_revision} onClick={e=>{if(dirty)e.preventDefault();}}><Download size={18}/></a>
    <button className="word-ai-toggle" title="Помощник по документу" aria-label="Помощник по документу" aria-pressed={assistant} onClick={()=>setAssistant(!assistant)}><Sparkles size={18}/><span>Помощник</span></button></>}
  </div>
  {error&&<div className="word-feedback error" role="alert">{error}<button aria-label="Закрыть сообщение об ошибке" onClick={()=>setError('')}><X size={16}/></button></div>}
  {notice&&!busy&&<div className="word-feedback" role="status"><Check size={15}/>{notice}<button aria-label="Закрыть уведомление" onClick={()=>setNotice('')}><X size={16}/></button></div>}
  <div className={'word-layout'+(library?' with-library':'')+(assistant&&doc?' with-assistant':'')}>
   {library&&<aside className="word-library"><div className="word-library-heading"><h2>Мои документы</h2><span>{rows.length}</span></div><div className="word-library-actions"><button className="primary" disabled={!!busy} onClick={()=>openName('create')}><Plus size={16}/>Создать</button><button disabled={!!busy} onClick={()=>uploadInput.current?.click()}><Upload size={16}/>Открыть</button></div>
    {doc&&<div className="word-document-actions" aria-label="Действия с открытым документом"><button disabled={!!busy} onClick={()=>openName('rename')}><Pencil size={15}/>Переименовать</button><button disabled={!!busy||dirty} title={dirty?'Сначала сохраните изменения':'Создать копию открытой версии'} onClick={()=>openName('copy')}><Copy size={15}/>Создать копию</button>{dirty&&<small>Сохраните изменения, чтобы создать копию.</small>}</div>}
    <label className="word-library-search"><Search size={15}/><input aria-label="Поиск документов" placeholder="Найти документ" value={filter} onChange={e=>setFilter(e.target.value)}/></label>
    <div className="word-file-list">{rows.filter(r=>r.name.toLowerCase().includes(filter.toLowerCase())).map(r=><button key={r.id} className={r.id===doc?.id?'active':''} disabled={!!busy} onClick={()=>void load(r.id)}><FileText size={20}/><span>{r.name.replace(/\.docx$/i,'')}<small>{new Date(r.updated_at).toLocaleDateString('ru-RU',{day:'numeric',month:'short'})} · Word</small></span></button>)}{!rows.length&&<p>Здесь появятся ваши документы.</p>}{rows.length>0&&!rows.some(r=>r.name.toLowerCase().includes(filter.toLowerCase()))&&<p>Документы не найдены.</p>}</div>
   </aside>}
   <div className="word-main">
    {versions&&doc&&<section className="word-versions" aria-label="Версии документа"><div><strong>История версий</strong><p>Можно открыть и скачать любую версию или создать её копию.</p></div><select aria-label="Версия документа" disabled={!!busy} value={doc.view_revision} onChange={e=>void load(doc.id,Number(e.target.value))}>{doc.versions.map(v=><option key={v.revision} value={v.revision}>Версия {v.revision}{v.revision===doc.revision?' · текущая':''}{v.revision===1?' · оригинал':''} · {new Date(v.created_at).toLocaleString('ru-RU')}</option>)}</select><button title="Закрыть историю" onClick={()=>setVersions(false)}><X size={17}/></button></section>}
    {doc?<>{!current&&<div className="word-old-version"><History size={16}/>Вы читаете предыдущую версию.<button disabled={!!busy} onClick={()=>openName('copy')}>Создать копию этой версии</button><button disabled={!!busy} onClick={()=>void load(doc.id)}>Открыть текущую</button></div>}
     <WordEditor key={doc.id} doc={doc} editing={editing} disabled={!!busy} onChange={value=>{setChanges(value);setProposal(null);setNotice('');}} onSave={()=>void save()} onSelection={setSelected}/>
    </>:<div className="word-welcome" onDragOver={e=>e.preventDefault()} onDrop={e=>{e.preventDefault();if(!busy&&e.dataTransfer.files[0])void upload(e.dataTransfer.files[0]);}}><div className="word-welcome-icon"><FileText size={42}/></div><h2>Место для ваших мыслей</h2><p>Откройте документ Word или начните с чистого листа.<br/>Читайте, редактируйте и сохраняйте всё здесь.</p><div><button className="primary" disabled={!!busy} onClick={()=>openName('create')}><Plus size={17}/>Новый документ</button><button disabled={!!busy} onClick={()=>uploadInput.current?.click()}><Upload size={17}/>Открыть Word</button></div><small>Можно перетащить сюда файл .docx до 10 МБ</small></div>}
   </div>
   {assistant&&doc&&<aside className="word-assistant"><div className="word-library-heading"><h2><Sparkles size={18}/>Помощник</h2><button aria-label="Закрыть помощника" onClick={()=>setAssistant(false)}><X size={17}/></button></div><p>Поможет разобраться в тексте, исправить ошибки или подобрать формулировку.</p><div className="word-ai-scope">{selected.length?`Выделено абзацев: ${selected.length}`:'Работаем со всем документом'}</div><p className="word-hint">Выделите текст на странице, чтобы работать с отдельным фрагментом. В облачном режиме этот текст передаётся OpenRouter.</p><label>Что нужно сделать?<textarea aria-label="Запрос к ИИ" placeholder="Например: исправь ошибки, сохранив смысл" rows={4} value={instruction} disabled={!!busy} onChange={e=>setInstruction(e.target.value)}/></label><div className="word-ai-actions"><button disabled={!!busy||!current||dirty||!instruction.trim()} onClick={()=>void ai(false)}>Задать вопрос</button><button className="primary" disabled={!!busy||!current||dirty||!instruction.trim()} onClick={()=>void ai(true)}>Предложить правки</button></div>{dirty&&<p className="word-hint">Сначала сохраните ваши изменения.</p>}{answer&&<div className="word-ai-answer"><MarkdownMessage text={answer}/></div>}{proposal&&<section className="word-proposal"><h3>Предлагаемые изменения</h3><p>Проверьте текст перед применением.</p>{proposal.edits.map(edit=><div className="word-diff" key={edit.block_id}><del>{edit.old_text||'(пусто)'}</del><ins>{edit.text||'(пусто)'}</ins></div>)}{proposal.append.map((text,i)=><div className="word-diff" key={i}><ins>{text}</ins></div>)}<button className="primary" disabled={!!busy} onClick={()=>void save(proposal)}>Применить и сохранить</button><button disabled={!!busy} onClick={()=>setProposal(null)}>Отклонить</button></section>}</aside>}
  </div>
  {nameAction&&<div className="word-modal-backdrop" onKeyDown={e=>{if(e.key==='Escape'&&!busy)closeName();if(e.key==='Tab'){const controls=e.currentTarget.querySelectorAll<HTMLElement>('input:not(:disabled),button:not(:disabled)');const first=controls[0],last=controls[controls.length-1];if(!first){e.preventDefault();return;}if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus();}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus();}}}}><form className="word-modal" role="dialog" aria-modal="true" aria-labelledby="document-name-title" onSubmit={e=>{e.preventDefault();void submitName();}}><h2 id="document-name-title">{nameAction==='create'?'Новый документ':nameAction==='rename'?'Переименовать документ':'Создать копию'}</h2>{nameAction==='copy'&&<p>Скопируем сохранённую версию {doc?.view_revision}. Исходный документ и его история останутся на месте.</p>}<label>Название<input autoFocus aria-label="Название документа" value={newName} maxLength={250} required={nameAction!=='create'} disabled={!!busy} placeholder="Новый документ" onFocus={e=>e.target.select()} onChange={e=>setNewName(e.target.value)}/></label><small>Формат .docx добавится автоматически.</small>{error&&<p className="error" role="alert">{error}</p>}<div><button type="button" disabled={!!busy} onClick={closeName}>Отмена</button><button className="primary" disabled={!!busy||(nameAction!=='create'&&!newName.trim())}>{busy?'Подождите…':nameAction==='create'?'Создать документ':nameAction==='rename'?'Переименовать':'Создать копию'}</button></div></form></div>}
 </div>;
}
