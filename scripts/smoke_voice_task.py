"""Verify real STT → tasks.create → Piper → persisted task/activity; delete only the created task."""
import argparse
import base64
import io
import json
from pathlib import Path
import time
import wave

from dotenv import dotenv_values
import httpx


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('audio',type=Path,help='WAV with a short Russian task creation command')
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[1]
    token=dotenv_values(root/'.env')['DELTA_TOKEN']
    with httpx.Client(base_url='http://127.0.0.1:8080',headers={'Authorization':f'Bearer {token}'},timeout=180) as client:
        before=client.get('/tasks-api/api/v1/tasks');before.raise_for_status()
        existing={row['id'] for row in before.json()}
        task_id=None
        try:
            response=client.post('/core/api/v1/assistant/voice',files={'audio':('command.wav',args.audio.read_bytes(),'audio/wav')})
            response.raise_for_status();body=response.json()
            created=[r for r in body['tool_results'] if r['tool']=='tasks.create' and r['success']]
            assert len(created)==1, 'Expected one successful task creation'
            task_id=created[0]['data']['id']
            assert task_id not in existing, 'Result must identify a newly created task'
            assert len(body['tool_results'])==1
            assert body['route_source']=='local'
            assert body['timings']['router_calls']==body['timings']['response_generation_calls']==0
            task=client.get('/tasks-api/api/v1/tasks/'+task_id);task.raise_for_status()
            assert task.json()['title']==created[0]['data']['title']
            assert body['audio_available'] and body['tts_provider']=='piper'
            with wave.open(io.BytesIO(base64.b64decode(body['audio_base64'])),'rb') as audio:
                assert audio.getnframes()>0 and audio.getframerate()>0
            deadline=time.monotonic()+10
            while time.monotonic()<deadline:
                events=client.get('/core/api/v1/activity',params={'event_type':'TASK_CREATED','limit':100})
                events.raise_for_status()
                if any(row['details'].get('data',{}).get('id')==task_id for row in events.json()['items']):
                    break
                time.sleep(.25)
            else:
                raise AssertionError('Task activity not persisted')
            print(json.dumps({'verified':'voice, persisted task, Piper WAV, activity','timings':body['timings']},ensure_ascii=False))
        finally:
            if task_id and task_id not in existing:
                cleanup=client.delete('/tasks-api/api/v1/tasks/'+task_id)
                cleanup.raise_for_status()


if __name__=='__main__':
    main()
