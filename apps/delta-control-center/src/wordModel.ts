import type {JSONContent} from '@tiptap/core';
export type WordRun={text:string;bold:boolean;italic:boolean;underline:boolean;strike:boolean;font:string|null;size:number|null;color:string|null};
export type WordParagraph={id:string;editable:boolean;text:string;style:string;alignment:string;runs:WordRun[];images:string[]};
export type Layout={type:'paragraph';id:string}|{type:'table';id:string;rows:Layout[][][];complex:boolean};
export type WordDocument={id:string;name:string;revision:number;view_revision:number;updated_at:string;blocks:{id:string;text:string;editable:boolean;style:string}[];versions:{revision:number;created_at:string}[];rich:{paragraphs:WordParagraph[];layout:Layout[];styles?:string[]}};
export type ParagraphValue={runs:WordRun[];style:string;alignment:string};
export type RichChanges={base_revision:number;edits:(ParagraphValue&{block_id:string})[];insertions:{anchor:string|null;side:'before'|'after';paragraphs:ParagraphValue[]}[];delete:string[]};

export function wordContent(document:WordDocument):JSONContent {
 const blocks=new Map(document.rich.paragraphs.map(p=>[p.id,p]));
 function content(layout:Layout[],scope='body'):JSONContent[]{return layout.map((item,index)=>{
  if(item.type==='table') {
   const tableId=item.id;
   if(item.complex)return {type:'wordObject',attrs:{blockId:tableId,object:JSON.stringify(item),paragraphs:JSON.stringify(document.rich.paragraphs),text:'Таблица со сложной разметкой'}};
   return {type:'table',attrs:{wordTableId:tableId},content:item.rows.map((row,r)=>({type:'tableRow',content:row.map((cell,c)=>({type:'tableCell',attrs:{wordScope:tableId+'-'+r+'-'+c},content:content(cell,tableId+'-'+r+'-'+c)}))}))};
  }
  const p=blocks.get(item.id)!;
  if(!p.editable)return {type:'wordObject',attrs:{blockId:p.id,text:p.text,images:p.images,object:null,paragraphs:null}};
  const inline:JSONContent[]=[];
  for(const run of p.runs){
   const marks:NonNullable<JSONContent['marks']>=[];
   for(const name of ['bold','italic','underline','strike'] as const)if(run[name])marks.push({type:name});
   if(run.font||run.size||run.color)marks.push({type:'textStyle',attrs:{fontFamily:run.font,fontSize:run.size?run.size+'pt':null,color:run.color?'#'+run.color:null}});
   run.text.split('\n').forEach((text,i)=>{if(i)inline.push({type:'hardBreak'});if(text)inline.push({type:'text',text,marks});});
  }
  return {type:'paragraph',attrs:{blockId:p.id,wordStyle:p.style,textAlign:p.alignment},content:inline};
 });}
 return {type:'doc',content:content(document.rich.layout)};
}

export function paragraphValue(node:JSONContent):ParagraphValue {
 const runs:WordRun[]=[];
 for(const child of node.content??[]){
  const marks=child.marks??[],style=marks.find(m=>m.type==='textStyle')?.attrs??{};
  const run:WordRun={text:child.type==='hardBreak'?'\n':child.text??'',bold:marks.some(m=>m.type==='bold'),italic:marks.some(m=>m.type==='italic'),underline:marks.some(m=>m.type==='underline'),strike:marks.some(m=>m.type==='strike'),font:style.fontFamily||null,size:style.fontSize?parseFloat(style.fontSize):null,color:style.color?normalizeColor(style.color):null};
  if(!run.text)continue;
  const last=runs.at(-1);
  if(last&&JSON.stringify({...last,text:''})===JSON.stringify({...run,text:''}))last.text+=run.text;else runs.push(run);
 }
 return {runs,style:node.attrs?.wordStyle||'Normal',alignment:node.attrs?.textAlign||'left'};
}
function normalizeColor(value:string):string|null {
 if(/^#[0-9a-f]{6}$/i.test(value))return value.slice(1).toUpperCase();
 const rgb=value.match(/^rgb\(\s*(\d+),\s*(\d+),\s*(\d+)\s*\)$/);
 return rgb?rgb.slice(1).map(v=>Number(v).toString(16).padStart(2,'0')).join('').toUpperCase():null;
}
function scopes(root:JSONContent){
 const result=new Map<string,JSONContent[]>();
 function visit(node:JSONContent,key:string){
  if(node.type==='doc'||node.type==='tableCell')result.set(key,node.content??[]);
  (node.content??[]).forEach(child=>{if(child.type==='tableCell')visit(child,child.attrs?.wordScope);else if(child.content)visit(child,key);});
 }
 visit(root,'body');return result;
}
export function collectChanges(original:JSONContent,next:JSONContent,revision:number):RichChanges {
 const oldScopes=scopes(original),newScopes=scopes(next),known=new Map<string,JSONContent>(),retained=new Set<string>();
 oldScopes.forEach(nodes=>nodes.forEach(n=>{if(n.type==='paragraph'&&/^p\d+$/.test(n.attrs?.blockId))known.set(n.attrs?.blockId,n);}));
 const result:RichChanges={base_revision:revision,edits:[],insertions:[],delete:[]};
 newScopes.forEach((nodes,key)=>{
  let pending:ParagraphValue[]=[];let previous:string|undefined;
  for(const node of nodes){
   const id=node.attrs?.blockId??node.attrs?.wordTableId;
   if(node.type==='paragraph'&&!known.has(id)){pending.push(paragraphValue(node));continue;}
   if(pending.length){
    if(id&&/^[pt]\d+$/.test(id))result.insertions.push({anchor:id,side:'before',paragraphs:pending});
    else if(previous)result.insertions.push({anchor:previous,side:'after',paragraphs:pending});
    else {const attrs=oldScopes.get(key)?.find(n=>/^[pt]\d+$/.test(n.attrs?.blockId??n.attrs?.wordTableId))?.attrs;const anchor=attrs?.blockId??attrs?.wordTableId??null;if(!anchor&&key!=='body')throw new Error('Не удалось определить место нового абзаца. Отмените последнее изменение.');result.insertions.push({anchor,side:'before',paragraphs:pending});}
    pending=[];
   }
   if(id&&/^[pt]\d+$/.test(id))previous=id;
   if(node.type==='paragraph'&&known.has(id)){
    retained.add(id);
    if(JSON.stringify(paragraphValue(node))!==JSON.stringify(paragraphValue(known.get(id)!)))result.edits.push({block_id:id,...paragraphValue(node)});
   }
  }
  if(pending.length){
   const attrs=oldScopes.get(key)?.find(n=>/^[pt]\d+$/.test(n.attrs?.blockId??n.attrs?.wordTableId))?.attrs;
   const anchor=previous??attrs?.blockId??attrs?.wordTableId??null;
   if(!anchor&&key!=='body')throw new Error('Добавьте текст рядом с существующим абзацем.');
   result.insertions.push({anchor,side:previous?'after':'before',paragraphs:pending});
  }
 });
 result.delete=[...known.keys()].filter(id=>!retained.has(id));return result;
}
export const hasChanges=(changes:RichChanges)=>!!(changes.edits.length||changes.insertions.length||changes.delete.length);

// Native drag/drop must not move existing Word paragraphs across cells or reorder
// IDs: the patch format deliberately supports text, insertion and deletion only.
export function validWordOrder(before:JSONContent,after:JSONContent):boolean {
 const old=scopes(before),next=scopes(after);
 const id=(n:JSONContent)=>n.attrs?.blockId??n.attrs?.wordTableId;
 const ids=(nodes:JSONContent[])=>nodes.map(id).filter(value=>/^[pt]\d+$/.test(value));
 const known=new Set([...old.values()].flatMap(ids));
 const retained=new Set([...next.values()].flatMap(ids));
 for(const [key,nodes] of old){
  const expected=[...new Set(ids(nodes).filter(value=>retained.has(value)))];
  const actual=[...new Set(ids(next.get(key)??[]).filter(value=>known.has(value)))];
  if(JSON.stringify(expected)!==JSON.stringify(actual))return false;
 }
 return true;
}
