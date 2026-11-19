from unittest.mock import AsyncMock
from uuid import uuid4
import base64
from fastapi.testclient import TestClient
import pytest
from delta_contracts.devices import WorkspaceFilesPayload
from delta_contracts.workspace_files import FileStore,FileConflict,search_files,permitted_source
from delta_contracts.tools import ToolCall
from delta_core.llm.base import LLMTurn
from test_devices import app,HEADERS
from test_documents import fixture_doc


def setup(client):
    r=client.post('/api/v1/workspaces',headers=HEADERS,json={'name':'Studio','work_type':'website','storage_mode':'cloud'})
    assert r.status_code==201,r.text
    return '/api/v1/workspaces/'+r.json()['id']+'/studio'


def test_cloud_files_conflicts_versions_restore(app,tmp_path):
    app.state.studio.store=FileStore(tmp_path/'store')
    with TestClient(app) as client:
        url=setup(client)
        assert client.put(url+'/file',headers=HEADERS,json={'path':'index.html','text':'<h1>First</h1>'}).status_code==200
        first=client.get(url+'/file?path=index.html',headers=HEADERS).json()
        assert first['text']=='<h1>First</h1>'
        assert client.put(url+'/file',headers=HEADERS,json={'path':'index.html','text':'Lost edit'}).status_code==409
        second=client.put(url+'/file',headers=HEADERS,json={'path':'index.html','text':'<h1>Second</h1>','expected_hash':first['hash']}).json()
        versions=client.get(url+'/history?path=index.html',headers=HEADERS).json()['versions']
        assert versions[0]['hash']==first['hash']
        assert client.post(url+'/restore',headers=HEADERS,json={'path':'index.html','version':first['hash'],'expected_hash':second['hash']}).status_code==200
        assert client.get(url+'/preview',headers=HEADERS).json()['assets']['index.html']=='<h1>First</h1>'
        assert client.get(url+'/files').status_code==401
        for path in ['../outside.txt','/tmp/file.txt','.env','src/../../file.py','a\\b.txt','credentials.json']:
            assert client.put(url+'/file',headers=HEADERS,json={'path':path,'text':'no'}).status_code==422


def test_workspace_docx_import_edit_and_original(app,tmp_path):
    app.state.studio.store=FileStore(tmp_path/'store')
    with TestClient(app) as client:
        url=setup(client)
        response=client.post(url+'/upload',headers=HEADERS,files={'file':('план.docx',fixture_doc())})
        assert response.status_code==201,response.text
        first=client.get(url+'/file',headers=HEADERS,params={'path':'план.docx'}).json()
        assert first['kind']=='document'
        result=client.put(url+'/document',headers=HEADERS,json={'path':'план.docx','expected_hash':first['hash'],'edits':[{'block_id':'p1','old_text':'Первый текст','text':'Новый текст'}]})
        assert result.status_code==200,result.text
        old=client.get(url+'/file',headers=HEADERS,params={'path':'план.docx','version':first['hash']}).json()
        assert old['blocks'][1]['text']=='Первый текст'
        assert client.post(url+'/upload',headers=HEADERS,files={'file':('bad.docx',b'not zip')}).status_code==422
        assert client.post(url+'/new-document',headers=HEADERS,json={'path':'new.docx','text':'Hello'}).status_code==201
        assert client.get(url+'/file?path=new.docx',headers=HEADERS).json()['blocks'][0]['text']=='Hello'


def test_local_mode_dispatches_only_to_selected_agent(app,tmp_path):
    from sqlalchemy.orm import Session
    from delta_core.devices.models import Device
    from delta_contracts.storage import utcnow
    with TestClient(app) as client:
        with Session(app.state.engine) as db:
            d=Device(device_uid='studio',display_name='PC',hostname='pc',os='linux',architecture='x64',username='test',agent_version='0.4.0',capabilities=['workspace_files'],status='online',last_seen=utcnow());db.add(d);db.commit();did=d.id
        assert client.post('/api/v1/workspaces',headers=HEADERS,json={'name':'bad','storage_mode':'local'}).status_code==422
        row=client.post('/api/v1/workspaces',headers=HEADERS,json={'name':'local','storage_mode':'local','storage_device_id':did}).json()
        app.state.devices.dispatch=AsyncMock(return_value={'success':True,'data':{'files':[],'local_path':'managed'}})
        assert client.get('/api/v1/workspaces/'+row['id']+'/studio/files',headers=HEADERS).json()['files']==[]
        args=app.state.devices.dispatch.call_args.args
        assert args[0]==did and args[1].action=='workspace_files'
        assert args[1].payload['workspace_id']==row['id']


def test_assistant_actually_writes_and_does_not_choose_ambiguous_match(app,tmp_path):
    app.state.studio.store=FileStore(tmp_path/'store')
    with TestClient(app) as client:
        url=setup(client)
        app.state.assistant.provider.respond=AsyncMock(side_effect=[
            LLMTurn(calls=[ToolCall(name='workspace.write_file',arguments={'path':'index.html','text':'<h1>Landing</h1>'})]),LLMTurn(text='Готово')])
        response=client.post(url+'/chat',headers=HEADERS,json={'instruction':'Сделай лендинг'})
        assert response.json()['changed_files']==['index.html']
        assert client.get(url+'/file?path=index.html',headers=HEADERS).json()['text']=='<h1>Landing</h1>'
        app.state.devices.dispatch=AsyncMock(return_value={'success':True,'data':{'matches':[{'name':'x.docx','path':'/one/x.docx'},{'name':'x.docx','path':'/two/x.docx'}]}})
        app.state.assistant.provider.respond=AsyncMock(return_value=LLMTurn(calls=[ToolCall(name='workspace.search_computer',arguments={'query':'x.docx','device_id':str(uuid4())})]))
        result=client.post(url+'/chat',headers=HEADERS,json={'instruction':'Импортируй x.docx'}).json()
        assert len(result['matches'])==2 and 'Выберите' in result['answer']
        assert app.state.devices.dispatch.await_count==1


def test_search_boundaries_and_same_filename(tmp_path):
    allowed=tmp_path/'allowed';allowed.mkdir()
    for d in ['a','b','.hidden','node_modules']:
        (allowed/d).mkdir();(allowed/d/'report.txt').write_text('hello')
    outside=tmp_path/'outside';outside.mkdir();(outside/'secret.txt').write_text('hidden')
    (allowed/'shortcut').symlink_to(outside,target_is_directory=True)
    found=search_files('report',[allowed])
    assert len(found['matches'])==2
    assert not search_files('secret',[allowed])['matches']
    with pytest.raises(ValueError):permitted_source(outside/'secret.txt',[allowed])
    with pytest.raises(ValueError):permitted_source(allowed/'.hidden/report.txt',[allowed])


def test_file_store_rejects_symlinks_and_stale_writes(tmp_path):
    key=str(uuid4());store=FileStore(tmp_path/'store')
    def call(op,path,**kwargs):return store.execute(WorkspaceFilesPayload(workspace_id=key,operation=op,path=path,**kwargs))
    first=call('write','src/app.js',content_base64=base64.b64encode(b'hello').decode())
    with pytest.raises(FileConflict):call('write','src/app.js',content_base64=base64.b64encode(b'world').decode())
    outside=tmp_path/'outside';outside.mkdir()
    (store.directory(key)/'escape').symlink_to(outside,target_is_directory=True)
    with pytest.raises(ValueError):call('write','escape/evil.txt',content_base64='aGk=')
    assert call('read','src/app.js')['hash']==first['hash']


def test_tasks_proxy_retries_only_reads(app):
    import httpx
    with TestClient(app) as client:
        app.state.http.request=AsyncMock(side_effect=[httpx.RemoteProtocolError('connection closed'),httpx.Response(200,json=[])])
        assert client.get('/api/v1/task-proxy/tasks',headers=HEADERS).status_code==200
        assert app.state.http.request.await_count==2
        app.state.http.request=AsyncMock(side_effect=httpx.RemoteProtocolError('connection closed'))
        assert client.post('/api/v1/task-proxy/tasks',headers=HEADERS,json={'title':'Do not duplicate'}).status_code==503
        assert app.state.http.request.await_count==1
