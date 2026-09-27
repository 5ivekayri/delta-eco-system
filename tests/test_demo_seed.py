import importlib.util
from pathlib import Path

import httpx
import pytest

spec=importlib.util.spec_from_file_location('seed_demo',Path(__file__).resolve().parents[1]/'scripts/seed_demo.py')
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_seed_repeated_run_preserves_existing_data_and_iot():
    workspaces=[{'name':'master thesis','description':'User description'}]
    tasks=[{'title':'Prepare API tests','status':'done'}]
    def handler(request):
        import json
        path=request.url.path
        if path.endswith('/state'):
            assert request.method=='GET'
            return httpx.Response(200,json={'desk_light':True})
        rows=workspaces if path.endswith('/workspaces') else tasks
        if request.method=='POST':
            rows.append(json.loads(request.content))
            return httpx.Response(201,json=rows[-1])
        assert request.method=='GET'
        return httpx.Response(200,json=rows)
    with httpx.Client(base_url='http://delta',transport=httpx.MockTransport(handler)) as client:
        assert module.seed(client)=={'workspaces':1,'tasks':2}
        assert module.seed(client)=={'workspaces':0,'tasks':0}
    assert workspaces[0]['description']=='User description'
    assert tasks[0]['status']=='done'


def test_unavailable_tasks_prevents_partial_seed():
    def handler(request):
        assert request.method=='GET'
        return httpx.Response(503 if '/tasks' in request.url.path else 200,json=[])
    with httpx.Client(base_url='http://delta',transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(httpx.HTTPStatusError):
            module.seed(client)
