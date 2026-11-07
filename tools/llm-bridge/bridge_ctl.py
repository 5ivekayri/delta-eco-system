"""Local controls; credentials are read from the server and never printed."""
import argparse
import json
import httpx
from bridge import load_configuration

parser=argparse.ArgumentParser()
parser.add_argument('action', choices=['status','auto','local','openrouter'])
args=parser.parse_args()
_,key=load_configuration()
with httpx.Client(base_url='http://127.0.0.1:8092',headers={'Authorization':'Bearer '+key},timeout=10) as client:
    response=client.get('/control/status') if args.action=='status' else client.post('/control/mode',json={'mode':args.action})
    if response.is_error:
        raise SystemExit(f'Bridge returned HTTP {response.status_code}')
    print(json.dumps(response.json(),ensure_ascii=False,indent=2))
