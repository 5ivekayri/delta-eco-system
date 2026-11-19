"""Small word processor model. Patch only changed paragraphs in the original package."""
from base64 import b64encode
import re
from copy import deepcopy
from io import BytesIO
from typing import Literal
from zipfile import ZipFile, ZIP_DEFLATED
from pydantic import Field, model_validator
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from lxml import etree
from delta_contracts.devices import StrictModel
from delta_contracts.errors import DeltaError
from . import ooxml
from .schemas import Edit


class Run(StrictModel):
    text: str = Field(max_length=20000)
    bold: bool = False
    italic: bool = False
    underline: bool = False
    strike: bool = False
    font: str | None = Field(default=None, max_length=100, pattern=r'^[\w .,-]+$')
    size: float | None = Field(default=None, ge=6, le=96)
    color: str | None = Field(default=None, pattern=r'^[0-9A-Fa-f]{6}$')

    @model_validator(mode='after')
    def valid_text(self):
        Edit.xml_text(self.text)
        return self


class RichParagraph(StrictModel):
    runs: list[Run] = Field(default_factory=list, max_length=2000)
    style: str = Field(default='Normal', min_length=1, max_length=100)
    alignment: Literal['left','center','right','justify'] = 'left'

    @model_validator(mode='after')
    def bounded(self):
        if sum(len(r.text) for r in self.runs)>20000:raise ValueError('Paragraph too long')
        return self


class RichEdit(RichParagraph):
    block_id: str = Field(pattern=r'^p[0-9]+$')


class Insertion(StrictModel):
    anchor: str | None = Field(default=None, pattern=r'^[pt][0-9]+$')
    side: Literal['before','after']
    paragraphs: list[RichParagraph] = Field(min_length=1, max_length=100)


class RichSaveInput(StrictModel):
    base_revision: int = Field(ge=1)
    edits: list[RichEdit] = Field(default_factory=list, max_length=1000)
    insertions: list[Insertion] = Field(default_factory=list, max_length=100)
    delete: list[str] = Field(default_factory=list, max_length=1000)


ALIGN = {'left':WD_ALIGN_PARAGRAPH.LEFT,'center':WD_ALIGN_PARAGRAPH.CENTER,
         'right':WD_ALIGN_PARAGRAPH.RIGHT,'justify':WD_ALIGN_PARAGRAPH.JUSTIFY}


def protected(p):
    allowed={qn('w:'+name) for name in ('b','bCs','i','iCs','u','strike','rFonts','sz','szCs','color','lang','noProof')}
    exotic=any(child.tag not in allowed for props in p._p.iter(qn('w:rPr')) for child in props)
    return (exotic or len(p.text)>20000 or len(p.runs)>2000 or any(r.font.size is not None and not 6<=r.font.size.pt<=96 for r in p.runs) or not ooxml.simple(p) or p._p.find('.//'+qn('w:sectPr')) is not None
            or any(n.get(qn('w:type')) not in (None,'textWrapping') for n in p._p.iter(qn('w:br'))))


def style_value(p, name):
    style=p.style;seen=set()
    while style is not None and style.style_id not in seen:
        seen.add(style.style_id)
        value=getattr(style.font,name)
        if value is not None:return value
        style=style.base_style
    return None


def paragraph_data(p):
    runs=[]
    for run in p.runs:
        font=run.font
        runs.append({'text':run.text,'bold':bool(run.bold if run.bold is not None else style_value(p,'bold')),
                     'italic':bool(run.italic if run.italic is not None else style_value(p,'italic')),
                     'underline':bool(run.underline if run.underline is not None else style_value(p,'underline')),
                     'strike':bool(font.strike),'font':font.name if font.name and re.fullmatch(r'[\w .,-]{1,100}',font.name) else None,
                     'size':font.size.pt if font.size is not None else None,
                     'color':str(font.color.rgb) if font.color.rgb is not None else None})
    alignment=p.alignment
    if alignment is None and p.style is not None:alignment=p.style.paragraph_format.alignment
    return {'runs':runs,'style':p.style.name if p.style else 'Normal',
            'alignment':next((key for key,value in ALIGN.items() if value==alignment),'left')}


def view(data):
    document,paragraphs=ooxml.parse(data)
    by_element={p._p:i for i,p in enumerate(paragraphs)}
    tables=list(document.element.body.iter(qn('w:tbl')))
    blocks=[]; image_budget=6*1024*1024
    for i,p in enumerate(paragraphs):
        images=[]
        for blip in p._p.iter(qn('a:blip')):
            rel=document.part.rels.get(blip.get(qn('r:embed')))
            if rel is None or rel.is_external:continue
            part=rel.target_part
            if part.content_type not in {'image/png','image/jpeg','image/gif','image/webp'}:continue
            if len(part.blob)>image_budget:continue
            image_budget-=len(part.blob)
            images.append('data:'+part.content_type+';base64,'+b64encode(part.blob).decode())
        # itertext includes hyperlinks/field results that python-docx's runs may omit.
        text=''.join(node.text or '' for node in p._p.iter(qn('w:t')))
        blocks.append({'id':f'p{i}','editable':not protected(p),'text':p.text or text,
                       'images':images,**paragraph_data(p)})
    def children(parent):
        result=[]
        for child in parent:
            if child.tag==qn('w:p'):
                result.append({'type':'paragraph','id':f'p{by_element[child]}'})
            elif child.tag==qn('w:tbl'):
                # Complex merged/nested tables remain readable as protected groups.
                complex_table=bool(child.findall('.//'+qn('w:vMerge')) or child.findall('.//'+qn('w:gridSpan')) or child.findall('.//'+qn('w:tbl')))
                rows=[]
                for row in child.findall(qn('w:tr')):
                    rows.append([children(cell) for cell in row.findall(qn('w:tc'))])
                if complex_table:
                    for p in child.iter(qn('w:p')):blocks[by_element[p]]['editable']=False
                result.append({'type':'table','id':f't{tables.index(child)}','rows':rows,'complex':complex_table})
            elif list(child.iter(qn('w:p'))):
                # Content controls and tracked changes must not be rewritten as simple text.
                ids=[]
                for p in child.iter(qn('w:p')):
                    i=by_element[p];blocks[i]['editable']=False;ids.append({'type':'paragraph','id':f'p{i}'})
                result.extend(ids)
        return result
    layout=children(document.element.body)
    return {'paragraphs':blocks,'layout':layout,'styles':[s.name for s in document.styles if s.type==1]}


def write_paragraph(p, value, document):
    if value.style not in document.styles:
        raise DeltaError('INVALID_STYLE','Этот стиль отсутствует в документе. Выберите другой стиль.',422)
    if p.style is not None and p.style.name!=value.style:
        props=p._p.pPr
        if props is not None and props.numPr is not None:props.remove(props.numPr)
    p.style=value.style
    p.alignment=ALIGN[value.alignment]
    p.clear()
    for item in value.runs:
        run=p.add_run(item.text)
        run.bold=item.bold;run.italic=item.italic;run.underline=item.underline;run.font.strike=item.strike
        if item.font:run.font.name=item.font
        if item.size:run.font.size=Pt(item.size)
        if item.color:run.font.color.rgb=RGBColor.from_string(item.color)


def apply(data, changes):
    document,paragraphs=ooxml.parse(data)
    source=view(data);editable={b['id'] for b in source['paragraphs'] if b['editable']}
    by_id={f'p{i}':p for i,p in enumerate(paragraphs)}
    ids=[e.block_id for e in changes.edits]+changes.delete
    if not (changes.edits or changes.insertions or changes.delete):raise DeltaError('EMPTY_EDIT','Нет изменений для сохранения.',422)
    if len(ids)!=len(set(ids)) or any(i not in editable for i in ids):
        raise DeltaError('INVALID_EDIT','Этот фрагмент доступен только для чтения.',422)
    anchors={key:p._p for key,p in by_id.items()}
    anchors.update({f't{i}':t for i,t in enumerate(document.element.body.iter(qn('w:tbl')))})
    for insertion in changes.insertions:
        if insertion.anchor is None:
            for value in insertion.paragraphs:write_paragraph(document.add_paragraph(),value,document)
            continue
        anchor=anchors.get(insertion.anchor)
        if anchor is None or anchor.getparent().tag not in {qn('w:body'),qn('w:tc')}:
            raise DeltaError('INVALID_EDIT','Нельзя добавить абзац в эту область.',422)
        # Tables with merges/content controls are protected as a whole.
        if anchor.getparent().tag==qn('w:tc') and insertion.anchor not in editable:
            raise DeltaError('INVALID_EDIT','Эта таблица доступна только для чтения.',422)
        values=insertion.paragraphs if insertion.side=='before' else reversed(insertion.paragraphs)
        for value in values:
            node=OxmlElement('w:p')
            (anchor.addprevious if insertion.side=='before' else anchor.addnext)(node)
            write_paragraph(Paragraph(node,document),value,document)
    for edit in changes.edits:write_paragraph(by_id[edit.block_id],edit,document)
    for key in changes.delete:
        node=by_id[key]._p;node.getparent().remove(node)
    if not document.element.body.findall(qn('w:p')):document.add_paragraph('')
    for cell in document.element.body.iter(qn('w:tc')):
        if not cell.findall(qn('w:p')):cell.append(OxmlElement('w:p'))
    xml=etree.tostring(document.element,xml_declaration=True,encoding='UTF-8',standalone=True)
    result=BytesIO()
    with ZipFile(BytesIO(data)) as source_zip,ZipFile(result,'w',compression=ZIP_DEFLATED) as target:
        for info in source_zip.infolist():target.writestr(info,xml if info.filename=='word/document.xml' else source_zip.read(info))
    content=result.getvalue();ooxml.parse(content)
    return content
