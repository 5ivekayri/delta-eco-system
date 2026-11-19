import pytest
from fastapi.testclient import TestClient
from delta_contracts.errors import DeltaError
from delta_core.documents.schemas import RenameInput, CopyInput
from test_devices import app, HEADERS
from test_documents import upload


def test_rename_keeps_versions_and_detects_stale_name(app):
    with TestClient(app) as client:
        url='/api/v1/documents/'+upload(client)
        before=client.get(url,headers=HEADERS).json()
        content=client.get(url+'/download',headers=HEADERS).content
        body={'name':'  Новый план.DOCX  ','base_name':before['name']}
        renamed=client.patch(url,headers=HEADERS,json=body)
        assert renamed.status_code==200,renamed.text
        assert renamed.json()['name']=='Новый план.docx'
        assert client.patch(url,headers=HEADERS,json=body).status_code==409
        after=client.get(url,headers=HEADERS).json()
        assert after['revision']==before['revision'] and after['versions']==before['versions']
        download=client.get(url+'/download',headers=HEADERS)
        assert download.content==content and 'filename*=UTF-8' in download.headers['content-disposition']
        # An existing editor can still save content after a metadata-only rename.
        saved=client.put(url,headers=HEADERS,json={'base_revision':1,'append':['После переименования']})
        assert saved.status_code==200 and saved.json()['name']=='Новый план.docx'


def test_copy_historical_revision_is_exact_and_independent(app):
    with TestClient(app) as client:
        url='/api/v1/documents/'+upload(client)
        original=client.get(url+'/download',headers=HEADERS).content
        client.put(url,headers=HEADERS,json={'base_revision':1,'append':['Новая версия']}).raise_for_status()
        response=client.post(url+'/copy',headers=HEADERS,json={'name':'Шаблон','revision':1})
        assert response.status_code==201,response.text
        copy=response.json();copy_url='/api/v1/documents/'+copy['id']
        assert copy_url!=url and copy['name']=='Шаблон.docx'
        assert copy['revision']==1 and len(copy['versions'])==1
        assert client.get(copy_url+'/download',headers=HEADERS).content==original
        client.put(copy_url,headers=HEADERS,json={'base_revision':1,'append':['Только в копии']}).raise_for_status()
        source=client.get(url,headers=HEADERS).json()
        assert source['revision']==2 and len(source['versions'])==2
        assert source['blocks'][-1]['text']=='Новая версия'
        count=len(client.get('/api/v1/documents',headers=HEADERS).json())
        assert client.post(url+'/copy',headers=HEADERS,json={'name':'Нет версии','revision':99}).status_code==404
        assert len(client.get('/api/v1/documents',headers=HEADERS).json())==count


def test_library_mutations_require_authentication_and_ownership(app):
    with TestClient(app) as client:
        doc_id=upload(client);url='/api/v1/documents/'+doc_id
        assert client.patch(url,json={'name':'New','base_name':'план.docx'}).status_code==401
        assert client.post(url+'/copy',json={'name':'Copy','revision':1}).status_code==401
        service=app.state.documents
        for operation,body in [(service.rename,RenameInput(name='New',base_name='план.docx')),
                               (service.copy,CopyInput(name='Copy',revision=1))]:
            with pytest.raises(DeltaError) as error:operation('someone-else',doc_id,body)
            assert error.value.code=='DOCUMENT_NOT_FOUND'
        assert len(service.listing('development'))==1


@pytest.mark.parametrize('name',['   ','.docx','../escape','folder/name','folder\\name','bad\nname','x'*251])
def test_library_rejects_invalid_names_without_mutation(app,name):
    with TestClient(app) as client:
        doc_id=upload(client);url='/api/v1/documents/'+doc_id
        assert client.patch(url,headers=HEADERS,json={'name':name,'base_name':'план.docx'}).status_code==422
        assert client.post(url+'/copy',headers=HEADERS,json={'name':name,'revision':1}).status_code==422
        assert client.post('/api/v1/documents/blank',headers=HEADERS,json={'name':name}).status_code==422
        assert len(app.state.documents.listing('development'))==1
