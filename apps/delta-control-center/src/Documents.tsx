import {useEffect,useState} from 'react';
import {Upload,Download,FileText,Sparkles,Save} from 'lucide-react';
import {request} from './api';
import {MarkdownMessage} from './MarkdownMessage';

type Row={id:string;name:string;revision:number;updated_at:string};
type Block={id:string;text:string;style:string;editable:boolean;location:null|{table:number;row:number;cell:number}};
type Doc=Row&{view_revision:number;blocks:Block[];versions:{revision:number;created_at:string}[]};
type Edit={block_id:string;old_text:string;text:string};
type Proposal={base_revision:number;edits:Edit[];append:string[]};
const base='/core/api/v1/documents';

export function Documents({onDirty}:{onDirty?:(dirty:boolean)=>void}) {
 const [rows,setRows]=useState<Row[]>([]),[doc,setDoc]=useState<Doc|null>(null);
 const [draft,setDraft]=useState<Record<string,string>>({}),[added,setAdded]=useState('');
 const [selected,setSelected]=useState<string[]>([]),[instruction,setInstruction]=useState('');
 const [proposal,setProposal]=useState<Proposal|null>(null),[answer,setAnswer]=useState('');
 const [busy,setBusy]=useState(''),[error,setError]=useState(''),[notice,setNotice]=useState('');
 const edits:Edit[]=doc?doc.blocks.filter(b=>draft[b.id]!==undefined&&draft[b.id]!==b.text).map(b=>({block_id:b.id,old_text:b.text,text:draft[b.id]})):[];
 const dirty=edits.length>0||!!added.trim(),current=doc?.view_revision===doc?.revision;
 useEffect(()=>{onDirty?.(dirty);return()=>onDirty?.(false);},[dirty,onDirty]);
 useEffect(()=>{const warn=(e:BeforeUnloadEvent)=>{if(dirty){e.preventDefault();e.returnValue='';}};window.addEventListener('beforeunload',warn);return()=>window.removeEventListener('beforeunload',warn);},[dirty]);
 useEffect(()=>{request<Row[]>(base).then(setRows).catch(e=>setError(e.message));},[]);
 function accept(d:Doc){setDoc(d);setDraft({});setAdded('');setSelected([]);setProposal(null);setAnswer('');}
 async function load(id:string,revision?:number){
  if(dirty&&!confirm('Есть несохранённые правки. Перейти без сохранения?'))return;
  setBusy('Открываю документ…');setError('');setNotice('');
  try{accept(await request<Doc>(base+'/'+id+(revision?'?revision='+revision:'')));}catch(e){setError((e as Error).message);}finally{setBusy('');}
 }
 async function upload(file:File){
  if(!file.name.toLowerCase().endsWith('.docx')||file.size>10*1024*1024){setError('Выберите DOCX размером до 10 МБ.');return;}
  if(dirty&&!confirm('Перейти к загружаемому документу без сохранения правок?'))return;
  setBusy('Загружаю документ…');setError('');setNotice('');
  try{const form=new FormData();form.append('file',file);const row=await request<Row>(base,{method:'POST',body:form});
   setRows(await request<Row[]>(base));accept(await request<Doc>(base+'/'+row.id));setNotice('Документ загружен. Исходная версия сохранена.');
  }catch(e){setError((e as Error).message);}finally{setBusy('');}
 }
 async function save(changes:Proposal){
  if(!doc)return;setBusy('Сохраняю новую версию…');setError('');setNotice('');
  try{accept(await request<Doc>(base+'/'+doc.id,{method:'PUT',body:JSON.stringify(changes)}));setRows(await request<Row[]>(base));setNotice('Новая версия сохранена. Предыдущие версии доступны в списке.');}
  catch(e){setError((e as Error).message);}finally{setBusy('');}
 }
 async function ai(edit:boolean){
  if(!doc)return;setBusy(edit?'ИИ готовит предложения…':'ИИ читает документ…');setError('');setNotice('');setProposal(null);setAnswer('');
  try{const result=await request<Proposal&{answer:string}>(base+'/'+doc.id+(edit?'/propose':'/ask'),{method:'POST',body:JSON.stringify({revision:doc.revision,instruction,block_ids:selected})});
   if(edit)setProposal(result);else setAnswer(result.answer);
  }catch(e){setError((e as Error).message);}finally{setBusy('');}
 }
 return <div className="documents">
  <div className="toolbar"><p>Загрузите Word, отредактируйте текст и сохраните новую версию.</p>
   <label className="document-upload"><Upload size={16}/> Загрузить DOCX<input aria-label="Загрузить DOCX" type="file" accept=".docx" disabled={!!busy} onChange={e=>{const file=e.target.files?.[0];e.target.value='';if(file)void upload(file);}}/></label></div>
  {error&&<div className="error" role="alert">{error}</div>}{notice&&<p role="status">{notice}</p>}{busy&&<p role="status" aria-live="polite">{busy}</p>}
  <div className="document-layout">
   <article className="document-library"><h2>Мои документы</h2>{rows.length===0&&<p>Пока нет документов. Начните с загрузки .docx.</p>}
    {rows.map(r=><button className={doc?.id===r.id?'active':''} disabled={!!busy} key={r.id} onClick={()=>void load(r.id)}><FileText size={16}/><span>{r.name}<small>Версия {r.revision}</small></span></button>)}
   </article>
   {doc?<><article className="document-editor"><div className="document-heading"><h2>{doc.name}</h2><a href={base+'/'+doc.id+'/download?revision='+doc.view_revision}><Download size={16}/> Скачать DOCX</a></div>
    <label>Версия<select aria-label="Версия документа" disabled={!!busy} value={doc.view_revision} onChange={e=>void load(doc.id,Number(e.target.value))}>{doc.versions.map(v=><option key={v.revision} value={v.revision}>{v.revision}{v.revision===1?' — исходник':''}{v.revision===doc.revision?' — текущая':''}</option>)}</select></label>
    <p className="document-note">Текстовое представление. Изображения, колонтитулы и разметка страниц сохраняются в DOCX. Правка абзаца использует формат его первого фрагмента; сложные объекты доступны только для чтения.</p>
    {!current&&<p>Предыдущая версия доступна для чтения и скачивания. Для правок откройте текущую.</p>}
    <div className="document-blocks">{doc.blocks.map((b,i)=><div className={'document-block'+(b.location?' document-cell':'')} key={b.id}>
     <label className="document-block-label"><input type="checkbox" aria-label={'Выбрать абзац '+(i+1)} disabled={!!busy||!current||dirty} checked={selected.includes(b.id)} onChange={e=>setSelected(e.target.checked?[...selected,b.id]:selected.filter(id=>id!==b.id))}/>
      Абзац {i+1} · {b.location?`Таблица ${b.location.table}, строка ${b.location.row}, ячейка ${b.location.cell}`:b.style}{!b.editable?' · только чтение':''}</label>
     <textarea aria-label={'Текст абзаца '+(i+1)} readOnly={!b.editable||!current||!!busy} rows={Math.min(12,Math.max(2,Math.ceil((draft[b.id]??b.text).length/70)))} value={draft[b.id]??b.text} onChange={e=>{setDraft({...draft,[b.id]:e.target.value});setProposal(null);}}/>
    </div>)}</div>
    {current&&<><label>Новый абзац в конце<textarea aria-label="Новый абзац" value={added} disabled={!!busy} onChange={e=>{setAdded(e.target.value);setProposal(null);}}/></label>
     <button disabled={!!busy||!dirty} onClick={()=>void save({base_revision:doc.revision,edits,append:added.trim()?[added]:[]})}><Save size={16}/> Сохранить правки</button></>}
   </article><article className="document-ai"><h2><Sparkles size={19}/> ИИ для документа</h2>
    <p>{selected.length?`Выбрано абзацев: ${selected.length}`:'Без выделения ИИ получит весь текст документа.'}</p><p className="document-note">При обращении к ИИ текст передаётся выбранной модели Delta, включая OpenRouter в облачном и автоматическом режиме. Для большого документа выберите нужные абзацы.</p>
    <label>Вопрос или инструкция<textarea aria-label="Запрос к ИИ" placeholder="Кратко изложи содержание или исправь ошибки, сохранив смысл" rows={5} value={instruction} disabled={!!busy} onChange={e=>setInstruction(e.target.value)}/></label>
    <div className="actions"><button disabled={!!busy||!current||dirty||!instruction.trim()} onClick={()=>void ai(false)}>Спросить ИИ</button><button disabled={!!busy||!current||dirty||!instruction.trim()} onClick={()=>void ai(true)}>Предложить правки</button></div>
    {dirty&&<p>Сохраните ручные правки перед обращением к ИИ.</p>}
    {answer&&<div aria-label="Ответ ИИ"><MarkdownMessage text={answer}/></div>}
    {proposal&&<section aria-label="Предложения ИИ"><h3>Проверьте изменения</h3><p>Документ пока не изменён.</p>{proposal.edits.map(edit=><div className="document-diff" key={edit.block_id}><small>Абзац {Number(edit.block_id.slice(1))+1}</small><strong>Было</strong><pre>{edit.old_text||'(пусто)'}</pre><strong>Станет</strong><pre>{edit.text||'(пусто)'}</pre></div>)}{proposal.append.map((text,i)=><div className="document-diff" key={'new'+i}><strong>Новый абзац</strong><pre>{text}</pre></div>)}
     <div className="actions"><button disabled={!!busy} onClick={()=>void save(proposal)}>Применить и сохранить</button><button disabled={!!busy} onClick={()=>setProposal(null)}>Отклонить</button></div></section>}
   </article></>:<article className="document-empty"><FileText size={40}/><h2>Документ под рукой</h2><p>Выберите файл слева или загрузите DOCX. Оригинал останется доступным после редактирования.</p></article>}
  </div>
 </div>;
}
