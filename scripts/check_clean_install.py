"""Check empty-volume bootstrap with built images; preserve the running Delta project."""
import argparse
import io
import json
import os
from pathlib import Path
import secrets
import subprocess
import time
import wave

import httpx
from seed_demo import seed


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--docker',default='docker')
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    project='delta-acceptance-'+secrets.token_hex(4)
    directory=root/'.runtime'/project
    directory.mkdir(parents=True,mode=0o700)
    values={key:secrets.token_hex(24) for key in ('DELTA_TOKEN','POSTGRES_PASSWORD','CORE_DB_PASSWORD','TASKS_DB_PASSWORD')}
    config=directory/'acceptance.env'
    config.touch(mode=0o600)
    config.write_text(''.join(f'{key}={value}\n' for key,value in values.items()))
    environment={**os.environ,**values}
    command=[args.docker,'compose','--project-name',project,'--env-file',str(config),
             '-f','docker-compose.yml','-f','docker/compose.acceptance.yml']
    checks=[]
    started=time.monotonic()
    with (directory/'compose.log').open('w') as log:
        def compose(*arguments):
            subprocess.run([*command,*arguments],cwd=root,env=environment,stdout=log,stderr=subprocess.STDOUT,check=True)
        try:
            compose('up','-d','--no-build','--wait','--wait-timeout','180')
            checks.append('empty PostgreSQL bootstrap and service health')
            with httpx.Client(base_url='http://127.0.0.1:18080',headers={'Authorization':f"Bearer {values['DELTA_TOKEN']}"},timeout=30) as client:
                def get(path):
                    response=client.get(path);response.raise_for_status();return response.json()
                assert client.get('/').status_code==200
                assert client.get('/core/api/v1/devices',headers={'Authorization':'invalid'}).status_code==401
                for path in ('/core/api/v1/devices','/core/api/v1/workspaces','/tasks-api/api/v1/tasks'):
                    assert get(path)==[],path
                state=get('/core/api/v1/iot/state')
                assert (state['desk_light'],state['temperature'],state['brightness'],state['motion'])==(False,23.0,30,True)
                checks.append('empty API data, authentication, IoT migration defaults')
                assert seed(client)=={'workspaces':2,'tasks':3}
                assert seed(client)=={'workspaces':0,'tasks':0}
                checks.append('demo seed and repeat-run idempotence')
                deadline=time.monotonic()+30
                while time.monotonic()<deadline:
                    if any(s['service_id']=='delta-tasks' and s['status']=='online' for s in get('/core/api/v1/services')):
                        break
                    time.sleep(.5)
                else:
                    raise AssertionError('Tasks discovery failed')
                response=client.post('/core/api/v1/assistant/message',json={'message':'Покажи задачи'})
                response.raise_for_status();body=response.json()
                assert body['route_source']=='local' and len(body['tool_results'])==1
                assert body['tool_results'][0]['success'] and len(body['tool_results'][0]['data'])==3
                checks.append('manifest discovery and local Assistant to Tasks')
                audio=io.BytesIO()
                with wave.open(audio,'wb') as wav:
                    wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(16000);wav.writeframes(b'\0'*3200)
                response=client.post('/core/api/v1/assistant/voice',files={'audio':('silence.wav',audio.getvalue(),'audio/wav')})
                assert response.status_code==503 and response.json()['error_code']=='STT_UNAVAILABLE'
                checks.append('empty model cache returns explicit STT_UNAVAILABLE')
                compose('restart','delta-core','delta-tasks')
                deadline=time.monotonic()+90
                while time.monotonic()<deadline:
                    try:
                        if len(get('/core/api/v1/workspaces'))==2 and len(get('/tasks-api/api/v1/tasks'))==3:
                            break
                    except (httpx.HTTPError,ValueError):
                        pass
                    time.sleep(1)
                else:
                    raise AssertionError('Persistence after restart failed')
                checks.append('Core and Tasks persistence after restart')
            report={'project':project,'checks':checks,'elapsed_seconds':round(time.monotonic()-started,2),
                    'models':'empty volumes; unavailable path checked, downloads not performed'}
            (directory/'report.json').write_text(json.dumps(report,indent=2)+'\n')
            print(json.dumps(report,indent=2),flush=True)
        finally:
            compose('down')  # Only this isolated project; retain volumes for inspection.
            print(f'Isolated containers stopped; report and log: {directory}',flush=True)


if __name__=='__main__':
    main()
