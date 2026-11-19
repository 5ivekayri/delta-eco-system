import {expect,it} from 'vitest';
import {collectChanges,hasChanges,wordContent,type WordDocument} from './wordModel';
const document:WordDocument={id:'doc',name:'test.docx',revision:1,view_revision:1,updated_at:'',versions:[],blocks:[],rich:{layout:[{type:'paragraph',id:'p0'},{type:'paragraph',id:'p1'}],paragraphs:[
 {id:'p0',text:'Title',style:'Title',alignment:'left',editable:true,images:[],runs:[{text:'Title',bold:true,italic:false,underline:false,strike:false,font:null,size:null,color:null}]},
 {id:'p1',text:'Hello world',style:'Normal',alignment:'left',editable:true,images:[],runs:[{text:'Hello ',bold:false,italic:false,underline:false,strike:false,font:null,size:null,color:null},{text:'world',bold:false,italic:false,underline:false,strike:false,font:null,size:null,color:null}]},
]}};
it('does not save a new version when adjacent runs are normalized',()=>{
 const original=wordContent(document),next=structuredClone(original);
 next.content![1].content=[{type:'text',text:'Hello world',marks:[]}];
 expect(hasChanges(collectChanges(original,next,1))).toBe(false);
});
it('keeps inline marks and inserts new paragraphs at the cursor position',()=>{
 const original=wordContent(document),next=structuredClone(original);
 next.content!.splice(1,0,{type:'paragraph',attrs:{blockId:'new-id',wordStyle:'Normal'},content:[{type:'text',text:'Inserted',marks:[{type:'underline'}]}]});
 next.content![2].content![1].marks=[{type:'italic'},{type:'textStyle',attrs:{fontSize:'16pt',fontFamily:'Arial',color:'#123456'}}];
 const result=collectChanges(original,next,1);
 expect(result.insertions[0]).toMatchObject({anchor:'p1',side:'before',paragraphs:[{runs:[{text:'Inserted',underline:true}]}]});
 expect(result.edits[0].runs[1]).toMatchObject({text:'world',italic:true,size:16,font:'Arial',color:'123456'});
 expect(result.delete).toEqual([]);
});
it('merging paragraphs removes the former paragraph explicitly',()=>{
 const original=wordContent(document),next=structuredClone(original);
 next.content!.pop();next.content![0].content![0].text='Title Hello world';
 const result=collectChanges(original,next,1);
 expect(result.delete).toEqual(['p1']);expect(result.edits).toHaveLength(1);
});
it('anchors text inserted before a leading table outside its cells',()=>{
 const table={type:'table',attrs:{wordTableId:'t0'},content:[]};
 const original={type:'doc',content:[table]},next={type:'doc',content:[{type:'paragraph',attrs:{blockId:'new'},content:[{type:'text',text:'Before'}]},table]};
 expect(collectChanges(original,next,1).insertions[0]).toMatchObject({anchor:'t0',side:'before'});
});
it('allows writing the first paragraph of an empty Word package',()=>{
 const original={type:'doc',content:[]},next={type:'doc',content:[{type:'paragraph',attrs:{blockId:'new'},content:[{type:'text',text:'First'}]}]};
 expect(collectChanges(original,next,1).insertions[0]).toMatchObject({anchor:null});
});
it('rejects reordering existing IDs while allowing splits and deletions',async()=>{
 const {validWordOrder}=await import('./wordModel');
 const before=wordContent(document),after=structuredClone(before);
 after.content!.reverse();expect(validWordOrder(before,after)).toBe(false);
 after.content=[before.content![0]];expect(validWordOrder(before,after)).toBe(true);
 after.content=[before.content![0],before.content![0],before.content![1]];expect(validWordOrder(before,after)).toBe(true);
});

it('allows the ID extension to assign a fresh ID after a paragraph split',async()=>{
 const {validWordOrder}=await import('./wordModel');
 const before=wordContent(document),split=structuredClone(before);
 split.content!.splice(1,0,structuredClone(split.content![0]));
 const normalized=structuredClone(split);normalized.content![1].attrs!.blockId='new-id';
 expect(validWordOrder(split,normalized)).toBe(true);
});
