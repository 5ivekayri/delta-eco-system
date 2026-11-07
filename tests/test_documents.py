from io import BytesIO
from zipfile import ZipFile,ZIP_DEFLATED
from unittest.mock import AsyncMock
import pytest
from docx import Document
from docx.oxml import OxmlElement
from fastapi.testclient import TestClient
from delta_core.llm.base import LLMTurn
from delta_contracts.tools import ToolCall
from delta_contracts.errors import DeltaError
from delta_core.documents.ooxml import blocks,parse,apply
from delta_core.documents.schemas import SaveInput
from test_devices import app,HEADERS


def fixture_doc():
    doc=Document();doc.add_heading('План проекта',0)
    p=doc.add_paragraph();p.add_run('Первый ').bold=True;p.add_run('текст').italic=True
    table=doc.add_table(rows=2,cols=2);table.cell(0,0).text='Этап';table.cell(0,1).text='Срок'
    table.cell(1,0).text='Запуск';table.cell(1,1).text='Пятница'
    doc.sections[0].header.paragraphs[0].text='Сохранить колонтитул'
    out=BytesIO();doc.save(out);return out.getvalue()


def upload(client):
    response=client.post('/api/v1/documents',headers=HEADERS,files={'file':('план.docx',fixture_doc())})
    assert response.status_code==201,response.text
    return response.json()['id']


def test_docx_round_trip_versions_and_conflict(app):
    with TestClient(app) as client:
        doc_id=upload(client);url='/api/v1/documents/'+doc_id
        first=client.get(url,headers=HEADERS).json()
        assert any(b['location'] and b['text']=='Пятница' for b in first['blocks'])
        body={'base_revision':1,'edits':[{'block_id':'p1','old_text':'Первый текст','text':'Исправленный текст'}],'append':['Новый абзац']}
        saved=client.put(url,headers=HEADERS,json=body)
        assert saved.status_code==200,saved.text
        assert saved.json()['revision']==2 and saved.json()['blocks'][1]['text']=='Исправленный текст'
        assert client.put(url,headers=HEADERS,json=body).status_code==409
        original=client.get(url+'/download?revision=1',headers=HEADERS).content
        edited=client.get(url+'/download',headers=HEADERS).content
        assert original==fixture_doc() or Document(BytesIO(original)).paragraphs[1].text=='Первый текст'
        with ZipFile(BytesIO(original)) as a,ZipFile(BytesIO(edited)) as b:
            assert a.namelist()==b.namelist()
            for name in a.namelist():
                if name!='word/document.xml':assert a.read(name)==b.read(name)
        changed=Document(BytesIO(edited));assert changed.paragraphs[1].runs[0].bold
        assert changed.tables[0].cell(1,1).text=='Пятница'
        assert len(saved.json()['versions'])==2
        assert client.get(url,headers={}).status_code==401
        with pytest.raises(DeltaError):app.state.documents.source('another-owner',doc_id)


def test_ai_proposes_only_then_user_applies(app):
    with TestClient(app) as client:
        doc_id=upload(client);url='/api/v1/documents/'+doc_id
        app.state.assistant.provider.respond=AsyncMock(return_value=LLMTurn(calls=[ToolCall(name='documents.propose_changes',arguments={
            'edits':[{'block_id':'p1','old_text':'Первый текст','text':'Улучшенный текст'}],'append':[]})]))
        response=client.post(url+'/propose',headers=HEADERS,json={'revision':1,'instruction':'Улучши текст','block_ids':['p1']})
        assert response.status_code==200,response.text
        assert client.get(url,headers=HEADERS).json()['revision']==1
        assert client.put(url,headers=HEADERS,json=response.json()).json()['revision']==2
        assert client.post(url+'/propose',headers=HEADERS,json={'revision':1,'instruction':'Правь'}).status_code==409


def test_ai_selection_and_question(app):
    with TestClient(app) as client:
        doc_id=upload(client);url='/api/v1/documents/'+doc_id
        mock=AsyncMock(return_value=LLMTurn(text='Срок — пятница.'));app.state.assistant.provider.respond=mock
        response=client.post(url+'/ask',headers=HEADERS,json={'revision':1,'instruction':'Какой срок?','block_ids':['p5']})
        assert response.status_code==200,response.text
        assert 'пятница' in response.json()['answer']
        sent=str(mock.call_args.args[0]);assert 'Пятница' in sent and 'Первый текст' not in sent
        assert client.post(url+'/ask',headers=HEADERS,json={'revision':1,'instruction':'?','block_ids':['p999']}).status_code==422
        assert client.get(url,headers=HEADERS).json()['revision']==1


def test_invalid_uploads_and_bounded_chunked_body(app):
    with TestClient(app) as client:
        for filename,content in [('x.doc',fixture_doc()),('x.docx',b'not-a-zip')]:
            assert client.post('/api/v1/documents',headers=HEADERS,files={'file':(filename,content)}).status_code==422
        def huge():
            for _ in range(12):yield b'x'*(1024*1024)
        assert client.post('/api/v1/documents',headers={**HEADERS,'Content-Type':'application/octet-stream'},content=huge()).status_code==413
    out=BytesIO()
    with ZipFile(out,'w',ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml','<!DOCTYPE test [<!ENTITY x "y">]><test/>');z.writestr('word/document.xml','<test/>')
    with pytest.raises(DeltaError):parse(out.getvalue())


def test_complex_blocks_readonly_and_invalid_edits():
    doc=Document();p=doc.add_paragraph('Before');p._p.append(OxmlElement('w:hyperlink'))
    output=BytesIO();doc.save(output);data=output.getvalue()
    assert not blocks(data)[0]['editable']
    with pytest.raises(DeltaError):apply(data,SaveInput(base_revision=1,edits=[{'block_id':'p0','old_text':'Before','text':'After'}]))
    with pytest.raises(DeltaError):apply(fixture_doc(),SaveInput(base_revision=1,edits=[{'block_id':'p1','old_text':'stale','text':'After'}]))


def test_ai_rejects_out_of_scope_or_arbitrary_commands(app):
    with TestClient(app) as client:
        doc_id=upload(client)
        for call in [ToolCall(name='shell',arguments={'command':'whoami'}),ToolCall(name='documents.propose_changes',arguments={'edits':[{'block_id':'p1','old_text':'Первый текст','text':'Bad'}]})]:
            app.state.assistant.provider.respond=AsyncMock(return_value=LLMTurn(calls=[call]))
            response=client.post('/api/v1/documents/'+doc_id+'/propose',headers=HEADERS,json={'revision':1,'instruction':'Перепиши','block_ids':['p0']})
            assert response.status_code in {422,502}
        assert client.get('/api/v1/documents/'+doc_id,headers=HEADERS).json()['revision']==1
