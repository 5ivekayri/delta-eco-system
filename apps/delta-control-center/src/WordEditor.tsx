import {useEffect,useMemo,useRef,useState} from 'react';
import {EditorContent,useEditor} from '@tiptap/react';
import {Extension,Node,mergeAttributes,type JSONContent,type Editor} from '@tiptap/core';
import {Plugin} from '@tiptap/pm/state';
import StarterKit from '@tiptap/starter-kit';
import {TextStyle,FontFamily,FontSize,Color} from '@tiptap/extension-text-style';
import TextAlign from '@tiptap/extension-text-align';
import {TableKit} from '@tiptap/extension-table';
import UniqueID from '@tiptap/extension-unique-id';
import {Bold,Italic,Underline,AlignLeft,AlignCenter,AlignRight,AlignJustify,Undo2,Redo2,Search,ChevronDown,X} from 'lucide-react';
import {wordContent,collectChanges,validWordOrder,type WordDocument,type RichChanges,type Layout,type WordParagraph} from './wordModel';

const Paragraph=Node.create({name:'paragraph',group:'block',content:'inline*',
 addAttributes:()=>({wordStyle:{default:'Normal',parseHTML:e=>e.getAttribute('data-word-style')||'Normal',renderHTML:a=>({'data-word-style':a.wordStyle})}}),
 parseHTML:()=>[{tag:'p'},{tag:'h1',getAttrs:()=>({wordStyle:'Heading 1'})},{tag:'h2',getAttrs:()=>({wordStyle:'Heading 2'})},{tag:'h3',getAttrs:()=>({wordStyle:'Heading 3'})}],
 renderHTML:({HTMLAttributes})=>['p',mergeAttributes(HTMLAttributes),0],
});
const WordObject=Node.create({name:'wordObject',group:'block',atom:true,selectable:false,draggable:false,
 addAttributes:()=>({blockId:{default:null},text:{default:''},images:{default:[]},object:{default:null},paragraphs:{default:null}}),
 renderHTML:()=>['div',{'class':'word-object'}],
 addNodeView:()=>({node})=>{
  const dom=document.createElement('div');dom.className='word-object';dom.contentEditable='false';dom.setAttribute('aria-label','Фрагмент только для чтения');
  if(node.attrs.object){
   const blocks=new Map<string,WordParagraph>((JSON.parse(node.attrs.paragraphs) as WordParagraph[]).map(p=>[p.id,p]));
   function build(item:Layout):HTMLElement{
    if(item.type==='paragraph'){const p=document.createElement('p');const data=blocks.get(item.id);p.textContent=data?.text||'';for(const src of data?.images??[]){const img=document.createElement('img');img.src=src;img.alt='Иллюстрация документа';p.append(img);}return p;}
    const table=document.createElement('table');for(const row of item.rows){const tr=document.createElement('tr');for(const cell of row){const td=document.createElement('td');cell.forEach(child=>td.append(build(child)));tr.append(td);}table.append(tr);}return table;
   }
   dom.append(build(JSON.parse(node.attrs.object)));
  }else{
   const p=document.createElement('p');p.textContent=node.attrs.text;if(!node.attrs.text&&!node.attrs.images.length){p.textContent='Объект Word — доступен в скачанном файле';p.className='word-object-placeholder';}dom.append(p);
   for(const src of node.attrs.images){if(!/^data:image\/(png|jpeg|gif|webp);base64,/.test(src))continue;const img=document.createElement('img');img.src=src;img.alt='Иллюстрация документа';dom.append(img);}
  }
  dom.title='Этот объект сохранится в Word. Его содержимое доступно только для чтения.';
  return {dom};
 },
});
const WordAttributes=Extension.create({name:'wordAttributes',addGlobalAttributes:()=>[
 {types:['table'],attributes:{wordTableId:{default:null}}},
 {types:['tableCell'],attributes:{wordScope:{default:null}}},
]});
function fixedStructure(root:JSONContent):string {
 const result:unknown[]=[];
 function visit(node:JSONContent){
  if(node.type==='wordObject')result.push(['object',node.attrs]);
  if(node.type==='table')result.push(['table',node.attrs?.wordTableId]);
  if(node.type==='tableCell')result.push(['cell',node.attrs?.wordScope,node.attrs?.colspan,node.attrs?.rowspan]);
  node.content?.forEach(visit);
 }
 visit(root);return JSON.stringify(result);
}
const ProtectObjects=Extension.create({name:'protectWordObjects',addProseMirrorPlugins(){return [new Plugin({
 filterTransaction:(transaction,state)=>!transaction.docChanged||(fixedStructure(transaction.doc.toJSON())===fixedStructure(state.doc.toJSON())&&validWordOrder(state.doc.toJSON(),transaction.doc.toJSON())),
})];}});
const labels:Record<string,string>={'Normal':'Обычный текст','Title':'Название','Subtitle':'Подзаголовок','Heading 1':'Заголовок 1','Heading 2':'Заголовок 2','Heading 3':'Заголовок 3','List Bullet':'Маркированный список','List Number':'Нумерованный список'};

export function WordEditor({doc,editing,disabled,onChange,onSave,onSelection}:{doc:WordDocument;editing:boolean;disabled:boolean;onChange:(changes:RichChanges)=>void;onSave:()=>void;onSelection:(ids:string[])=>void}){
 const initial=useMemo(()=>wordContent(doc),[doc]);
 const canvas=useRef<HTMLDivElement>(null),scrollPosition=useRef(0),cursor=useRef(1);
 const baseline=useRef<JSONContent>(initial);const callbacks=useRef({onChange,onSave,onSelection});callbacks.current={onChange,onSave,onSelection};
 const [zoom,setZoom]=useState(100),[search,setSearch]=useState(''),[searchOpen,setSearchOpen]=useState(false),[found,setFound]=useState('');
 const [count,setCount]=useState(0),[format,setFormat]=useState({style:'Normal',font:'Arial',size:'11',bold:false,italic:false,underline:false,align:'left'});
 const editor=useEditor({
  extensions:[StarterKit.configure({paragraph:false,heading:false,bulletList:false,orderedList:false,listItem:false,listKeymap:false,blockquote:false,codeBlock:false,code:false,horizontalRule:false,link:false,trailingNode:false}),Paragraph,WordObject,WordAttributes,ProtectObjects,
   TextStyle,FontFamily,FontSize,Color,TextAlign.configure({types:['paragraph']}),TableKit.configure({table:{resizable:false}}),UniqueID.configure({attributeName:'blockId',types:['paragraph']})],
  content:initial,editable:editing&&!disabled,
  editorProps:{attributes:{class:'word-page',role:'textbox','aria-label':'Текст документа','aria-multiline':'true','aria-readonly':String(!editing||disabled),spellcheck:'true'},
   handleKeyDown:(_view,event)=>{if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='s'){event.preventDefault();callbacks.current.onSave();return true;}return false;},
  },
  onCreate:({editor})=>{baseline.current=editor.getJSON();setCount(editor.getText().trim().split(/\s+/).filter(Boolean).length);editor.commands.setTextSelection(Math.min(cursor.current,editor.state.doc.content.size));requestAnimationFrame(()=>{if(canvas.current)canvas.current.scrollTop=scrollPosition.current;});},
  onUpdate:({editor})=>{callbacks.current.onChange(collectChanges(baseline.current,editor.getJSON(),doc.revision));setCount(editor.getText().trim().split(/\s+/).filter(Boolean).length);},
  onSelectionUpdate:({editor})=>{
   const ids:string[]=[];const {from,to,empty}=editor.state.selection;cursor.current=from;
   if(!empty)editor.state.doc.nodesBetween(from,to,node=>{if(node.type.name==='paragraph'&&/^p\d+$/.test(node.attrs.blockId))ids.push(node.attrs.blockId);});
   callbacks.current.onSelection([...new Set(ids)]);updateFormat(editor);
  },
  onTransaction:({editor})=>updateFormat(editor),
 },[doc.id,doc.view_revision]);
 function updateFormat(e:Editor){const p=e.getAttributes('paragraph'),s=e.getAttributes('textStyle');setFormat({style:p.wordStyle||'Normal',font:s.fontFamily||'Calibri',size:String(parseFloat(s.fontSize)||(({'Title':28,'Subtitle':16,'Heading 1':22,'Heading 2':17,'Heading 3':14} as Record<string,number>)[p.wordStyle]??11)),bold:e.isActive('bold'),italic:e.isActive('italic'),underline:e.isActive('underline'),align:p.textAlign||'left'});}
 // useEditor replaces its instance on revision changes; effects can still see the old one.
 useEffect(()=>{if(!editor||editor.isDestroyed)return;editor.setEditable(editing&&!disabled,false);if(editing&&!disabled)editor.commands.focus(undefined,{scrollIntoView:false});},[editor,editing,disabled]);
 function findNext(){if(!editor||!search)return;const matches:{from:number;to:number}[]=[];editor.state.doc.descendants((node,pos)=>{if(node.type.name==='paragraph'){const hay=node.textBetween(0,node.content.size,'','\n').toLocaleLowerCase(),needle=search.toLocaleLowerCase();let i=hay.indexOf(needle);while(i!==-1){matches.push({from:pos+1+i,to:pos+1+i+needle.length});i=hay.indexOf(needle,i+needle.length);}return false;}});if(!matches.length){setFound('Не найдено');return;}const match=matches.find(m=>m.from>=editor.state.selection.to)??matches[0];editor.chain().setTextSelection(match).scrollIntoView().run();setFound(`${matches.indexOf(match)+1} из ${matches.length}`);}
 if(!editor)return <p role="status">Открываем страницы…</p>;
 const lock=!editing||disabled;
 function tool(label:string,icon:React.ReactNode,active:boolean,action:()=>void){return <button key={label} type="button" title={label} aria-label={label} aria-pressed={active} disabled={lock} onMouseDown={e=>e.preventDefault()} onClick={action}>{icon}</button>;}
 return <>
  <div className="word-ribbon" role="toolbar" aria-label="Форматирование текста">
   <div className="word-tool-group"><button title="Отменить (Ctrl+Z)" aria-label="Отменить" disabled={lock||!editor.can().undo()} onClick={()=>editor.chain().focus().undo().run()}><Undo2 size={17}/></button><button title="Повторить (Ctrl+Shift+Z)" aria-label="Повторить" disabled={lock||!editor.can().redo()} onClick={()=>editor.chain().focus().redo().run()}><Redo2 size={17}/></button></div>
   <div className="word-tool-group"><select aria-label="Стиль абзаца" disabled={lock} value={format.style} onChange={e=>editor.chain().focus().updateAttributes('paragraph',{wordStyle:e.target.value}).run()}>
    {[...new Set([format.style,...Object.keys(labels).filter(s=>doc.rich.styles?.includes(s))])].map(style=><option key={style} value={style}>{labels[style]||style}</option>)}
   </select></div>
   <div className="word-tool-group"><select aria-label="Шрифт" disabled={lock} value={format.font} onChange={e=>editor.chain().focus().setFontFamily(e.target.value).run()}>{[...new Set([format.font,'Arial','Calibri','Times New Roman','Georgia','Verdana'])].map(font=><option key={font}>{font}</option>)}</select>
    <select aria-label="Размер шрифта" disabled={lock} value={format.size} onChange={e=>editor.chain().focus().setFontSize(e.target.value+'pt').run()}>{[...new Set([format.size,'8','10','11','12','14','16','18','20','24','28','36','48'])].sort((a,b)=>+a-+b).map(size=><option key={size}>{size}</option>)}</select></div>
   <div className="word-tool-group">{tool('Полужирный (Ctrl+B)',<Bold size={17}/>,format.bold,()=>editor.chain().focus().toggleBold().run())}{tool('Курсив (Ctrl+I)',<Italic size={17}/>,format.italic,()=>editor.chain().focus().toggleItalic().run())}{tool('Подчёркнутый (Ctrl+U)',<Underline size={17}/>,format.underline,()=>editor.chain().focus().toggleUnderline().run())}</div>
   <div className="word-tool-group">{(['left','center','right','justify'] as const).map((align,i)=>tool(['По левому краю','По центру','По правому краю','По ширине'][i],[<AlignLeft size={17}/>,<AlignCenter size={17}/>,<AlignRight size={17}/>,<AlignJustify size={17}/>][i],format.align===align,()=>editor.chain().focus().setTextAlign(align).run()))}</div>
   <button title="Найти в документе" aria-label="Найти в документе" aria-pressed={searchOpen} onClick={()=>setSearchOpen(!searchOpen)}><Search size={17}/></button>
  </div>
  {searchOpen&&<form className="word-search" onSubmit={e=>{e.preventDefault();findNext();}}><Search size={16}/><input autoFocus aria-label="Найти текст" placeholder="Найти в документе" value={search} onChange={e=>{setSearch(e.target.value);setFound('');}}/><span role="status">{found}</span><button disabled={!search} title="Следующее совпадение"><ChevronDown size={17}/></button><button type="button" title="Закрыть поиск" onClick={()=>setSearchOpen(false)}><X size={17}/></button></form>}
  <div ref={canvas} onScroll={e=>{scrollPosition.current=e.currentTarget.scrollTop;}} className={'word-canvas'+(!editing?' word-reading':'')}><div className="word-sheet-wrap" style={{zoom:zoom/100}}><EditorContent editor={editor}/></div></div>
  <div className="word-statusbar"><span>{editing?'Редактирование':'Чтение'} <span aria-hidden="true">·</span> Слов: {count}</span><label>Масштаб <select aria-label="Масштаб документа" value={zoom} onChange={e=>setZoom(Number(e.target.value))}>{[60,75,90,100,125,150].map(z=><option key={z} value={z}>{z}%</option>)}</select></label></div>
 </>;
}
