"""Bounded DOCX reads and text-only edits; preserve all other ZIP members verbatim."""
from io import BytesIO
from zipfile import ZipFile, BadZipFile, ZIP_DEFLATED
from copy import deepcopy
from docx import Document
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph
from lxml import etree
from delta_contracts.errors import DeltaError

MAX_UPLOAD = 10 * 1024 * 1024
MAX_EXPANDED = 40 * 1024 * 1024


def invalid(message='Некорректный DOCX. Загрузите обычный файл Word без макросов.'):
    return DeltaError('INVALID_DOCX', message, 422)


def parse(data):
    if len(data)>MAX_UPLOAD:raise DeltaError('DOCUMENT_TOO_LARGE','Максимальный размер DOCX — 10 МБ.',413)
    try:
        with ZipFile(BytesIO(data)) as archive:
            entries=archive.infolist();names=[i.filename for i in entries]
            if len(entries)>2000 or len(names)!=len(set(names)) or sum(i.file_size for i in entries)>MAX_EXPANDED:raise invalid()
            if any(i.flag_bits & 1 or '..' in i.filename.split('/') or i.filename.startswith('/') for i in entries):raise invalid()
            if any('vbaproject' in n.lower() or n.startswith(('word/embeddings/','word/activeX/')) for n in names):raise invalid('Макросы и вложенные исполняемые объекты не поддерживаются.')
            if not {'[Content_Types].xml','word/document.xml'}.issubset(names):raise invalid()
            for i in entries:
                if i.filename.endswith(('.xml','.rels')):
                    if i.file_size>8*1024*1024:raise invalid()
                    xml=archive.read(i)
                    if b'<!DOCTYPE' in xml.upper() or b'<!ENTITY' in xml.upper():raise invalid()
                    tree=etree.fromstring(xml,etree.XMLParser(resolve_entities=False,no_network=True,load_dtd=False))
                    if tree.getroottree().docinfo.doctype:raise invalid()
            document=Document(BytesIO(data))
        paragraphs=[Paragraph(p,document) for p in document.element.body.iter(qn('w:p'))]
        if len(paragraphs)>10000:raise invalid('Слишком много абзацев: максимум 10 000.')
        return document,paragraphs
    except DeltaError:raise
    except (BadZipFile,KeyError,ValueError,TypeError,RuntimeError,etree.XMLSyntaxError,OSError) as error:
        raise invalid() from None


def simple(paragraph):
    for node in paragraph._p:
        if node.tag==qn('w:pPr'):continue
        if node.tag!=qn('w:r'):return False
        if any(child.tag not in {qn('w:rPr'),qn('w:t'),qn('w:br'),qn('w:tab')} for child in node):return False
    return True


def blocks(data):
    document,paragraphs=parse(data)
    result=[]
    tables=list(document.element.body.iter(qn('w:tbl')))
    for i,p in enumerate(paragraphs):
        cells=list(p._p.iterancestors(qn('w:tc')))
        cell=cells[0] if cells else None
        table=next(p._p.iterancestors(qn('w:tbl')),None)
        row=next(p._p.iterancestors(qn('w:tr')),None)
        location=None
        if table is not None and cell is not None and row is not None:
            location={'table':tables.index(table)+1,'row':list(table.findall(qn('w:tr'))).index(row)+1,
                      'cell':list(row.findall(qn('w:tc'))).index(cell)+1}
        result.append({'id':f'p{i}','text':p.text,'style':p.style.name if p.style else 'Normal',
                       'editable':simple(p),'location':location})
    return result


def validate_changes(current,changes):
    by_id={b['id']:b for b in current};seen=set()
    for edit in changes.edits:
        block=by_id.get(edit.block_id)
        if not block or not block['editable'] or edit.block_id in seen:raise DeltaError('INVALID_EDIT','Недоступный или повторяющийся абзац.',422)
        if block['text']!=edit.old_text:raise DeltaError('DOCUMENT_CONFLICT','Текст изменился. Загрузите актуальную версию.',409)
        seen.add(edit.block_id)
    if not changes.edits and not changes.append:raise DeltaError('EMPTY_EDIT','Нет изменений для сохранения.',422)


def apply(data,changes):
    validate_changes(blocks(data),changes)
    document,paragraphs=parse(data)
    for edit in changes.edits:
        p=paragraphs[int(edit.block_id[1:])]
        if p.text==edit.text:continue
        # Preserve paragraph style and first-run formatting. Complex inline objects are read-only.
        first=deepcopy(p.runs[0]._r.rPr) if p.runs and p.runs[0]._r.rPr is not None else None
        p.clear();run=p.add_run(edit.text)
        if first is not None:run._r.insert(0,first)
    for text in changes.append:document.add_paragraph(text)
    xml=etree.tostring(document.element,xml_declaration=True,encoding='UTF-8',standalone=True)
    result=BytesIO()
    with ZipFile(BytesIO(data)) as source,ZipFile(result,'w',compression=ZIP_DEFLATED) as target:
        for info in source.infolist():
            target.writestr(info,xml if info.filename=='word/document.xml' else source.read(info))
    content=result.getvalue()
    parse(content)
    return content
