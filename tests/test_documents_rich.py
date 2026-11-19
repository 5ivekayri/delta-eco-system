from io import BytesIO
from zipfile import ZipFile
import pytest
from docx import Document
from docx.oxml import OxmlElement
from docx.shared import Pt
from fastapi.testclient import TestClient
from delta_core.documents import rich
from delta_core.documents.rich import RichSaveInput
from delta_contracts.errors import DeltaError
from test_documents import fixture_doc
from test_devices import app,HEADERS


def test_formatted_roundtrip_preserves_package_and_inline_marks():
    original=fixture_doc()
    view=rich.view(original)
    p=view['paragraphs'][1]
    assert p['runs'][0]['bold'] and p['runs'][1]['italic']
    assert view['layout'][2]['type']=='table'
    changed=rich.apply(original,RichSaveInput(base_revision=1,edits=[{
        'block_id':'p1','style':'Normal','alignment':'center','runs':[
            {'text':'Новый ','bold':True,'font':'Arial','size':16,'color':'123456'},
            {'text':'текст','italic':True,'underline':True}]}]))
    doc=Document(BytesIO(changed));p=doc.paragraphs[1]
    assert p.text=='Новый текст' and p.runs[0].bold and p.runs[0].font.size==Pt(16)
    assert p.runs[1].italic and p.runs[1].underline
    assert str(p.runs[0].font.color.rgb)=='123456'
    with ZipFile(BytesIO(original)) as a,ZipFile(BytesIO(changed)) as b:
        for name in a.namelist():
            if name!='word/document.xml':assert a.read(name)==b.read(name)


def test_insert_delete_and_table_cell_edit():
    original=fixture_doc()
    changed=rich.apply(original,RichSaveInput(base_revision=1,delete=['p1'],insertions=[
        {'anchor':'p1','side':'before','paragraphs':[{'runs':[{'text':'Первый новый'}]},{'runs':[{'text':'Второй новый'}]}]},
        {'anchor':'p0','side':'after','paragraphs':[{'runs':[{'text':'После заголовка'}]}]},
    ],edits=[{'block_id':'p5','runs':[{'text':'Понедельник','bold':True}]}]))
    doc=Document(BytesIO(changed))
    assert [p.text for p in doc.paragraphs]==['План проекта','После заголовка','Первый новый','Второй новый']
    assert doc.tables[0].cell(1,1).text=='Понедельник'


def test_protected_content_and_validation():
    document=Document();p=document.add_paragraph('Ссылка');p._p.append(OxmlElement('w:hyperlink'))
    stream=BytesIO();document.save(stream);original=stream.getvalue()
    assert not rich.view(original)['paragraphs'][0]['editable']
    for body in [dict(delete=['p0']),dict(edits=[{'block_id':'p0','runs':[]}]),dict(delete=['p99'])]:
        with pytest.raises(DeltaError):rich.apply(original,RichSaveInput(base_revision=1,**body))
    with pytest.raises(ValueError):RichSaveInput(base_revision=1,edits=[{'block_id':'p1','runs':[{'text':'bad\0'}]}])
    with pytest.raises(DeltaError):rich.apply(fixture_doc(),RichSaveInput(base_revision=1,edits=[{'block_id':'p1','style':'missing-style'}]))


def test_new_document_api_formatted_versions_conflict_and_owner(app):
    with TestClient(app) as client:
        created=client.post('/api/v1/documents/blank',headers=HEADERS,json={'name':'Заметки'})
        assert created.status_code==201,created.text
        doc=created.json();assert doc['name']=='Заметки.docx' and doc['rich']['paragraphs'][0]['id']=='p0'
        url='/api/v1/documents/'+doc['id']
        body={'base_revision':1,'edits':[{'block_id':'p0','runs':[{'text':'Привет','bold':True}]}]}
        saved=client.put(url+'/content',headers=HEADERS,json=body)
        assert saved.status_code==200,saved.text
        assert saved.json()['revision']==2 and saved.json()['rich']['paragraphs'][0]['runs'][0]['bold']
        assert client.put(url+'/content',headers=HEADERS,json=body).status_code==409
        assert client.get(url+'?revision=1',headers=HEADERS).json()['blocks'][0]['text']==''
        assert client.put(url+'/content',json=body).status_code==401
        with pytest.raises(DeltaError):app.state.documents.save('another-owner',doc['id'],RichSaveInput(**body),formatted=True)


def test_first_paragraph_and_insert_outside_table():
    document=Document();out=BytesIO();document.save(out)
    changed=rich.apply(out.getvalue(),RichSaveInput(base_revision=1,insertions=[{'anchor':None,'side':'after','paragraphs':[{'runs':[{'text':'First'}]}]}]))
    assert Document(BytesIO(changed)).paragraphs[0].text=='First'
    document=Document();document.add_table(rows=1,cols=1).cell(0,0).text='Cell'
    out=BytesIO();document.save(out)
    changed=rich.apply(out.getvalue(),RichSaveInput(base_revision=1,insertions=[{'anchor':'t0','side':'before','paragraphs':[{'runs':[{'text':'Before table'}]}]}]))
    doc=Document(BytesIO(changed))
    assert doc.paragraphs[0].text=='Before table' and doc.tables[0].cell(0,0).text=='Cell'
