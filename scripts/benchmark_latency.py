"""Measure harmless text commands and an optional recorded voice fixture.

Uses .env DELTA_TOKEN unless --session-file supplies an existing web-session token.
Never prints credentials, answers or audio. Live requests appear in chat history.
"""
import argparse
import json
from pathlib import Path
from time import perf_counter
import httpx
from dotenv import dotenv_values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:8081')
    parser.add_argument('--runs', type=int, default=3)
    parser.add_argument('--session-file', type=Path)
    parser.add_argument('--audio', type=Path, help='WAV of a harmless command; its tools will run')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.runs <= 10:
        parser.error('--runs must be 1..10')
    root = Path(__file__).resolve().parents[1]
    headers = {'X-Delta-Request': '1'}
    cookies = {}
    if args.session_file:
        cookies['delta_session'] = args.session_file.read_text().strip()
    else:
        headers['Authorization'] = 'Bearer ' + dotenv_values(root / '.env')['DELTA_TOKEN']
    cases = [('devices', 'покажи устройства'), ('tasks', 'покажи задачи'),
             ('services', 'покажи сервисы'), ('workspaces', 'покажи рабочие пространства'),
             ('conversation', 'Привет. Ответь одним коротким предложением, чем ты можешь помочь.')]
    if args.audio:
        cases.append(('voice', None))
    rows = []
    with httpx.Client(base_url=args.url, headers=headers, cookies=cookies, timeout=150) as client:
        for name, message in cases:
            for run in range(args.runs):
                start = perf_counter()
                if message:
                    response = client.post('/core/api/v1/assistant/message', json={'message':message})
                else:
                    response = client.post('/core/api/v1/assistant/voice',
                        files={'audio':('fixture.wav',args.audio.read_bytes(),'audio/wav')}, data={'voice_id':'piper'})
                body = response.json()
                row = {'case':name, 'run':run + 1, 'http_status':response.status_code,
                       'client_ms':round((perf_counter() - start) * 1000, 2),
                       'request_id':response.headers.get('X-Request-ID'), 'timings':body.get('timings'),
                       'error_code':body.get('error_code'),
                       'tools':[{'tool':r['tool'],'success':r['success']} for r in body.get('tool_results',[])]}
                rows.append(row)
                print(json.dumps(row, ensure_ascii=False), flush=True)
                args.output.write_text(json.dumps(rows, ensure_ascii=False, indent=2))
                if response.status_code in (401,403):
                    raise SystemExit('Authentication failed; use a valid session file with accounts enabled.')


if __name__ == '__main__':
    main()
