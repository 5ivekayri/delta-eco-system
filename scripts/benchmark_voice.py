"""Measure an already-recorded fixture without exposing credentials.

Example: .venv/bin/python scripts/benchmark_voice.py .runtime/voice-check.wav --runs 3
Uses the live LLM/tools; choose a harmless command (e.g. list devices).
Client request timing excludes recording and encoder finalization. The browser
reports the complete interval from recording stop through response receipt.
"""
import argparse
import json
from pathlib import Path
from time import perf_counter

from dotenv import dotenv_values
import httpx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('audio', type=Path)
    parser.add_argument('--runs', type=int, default=3)
    parser.add_argument('--url', default='http://127.0.0.1:8080')
    args = parser.parse_args()
    if not 1 <= args.runs <= 10:
        parser.error('--runs must be between 1 and 10')
    root = Path(__file__).resolve().parents[1]
    token = dotenv_values(root / '.env')['DELTA_TOKEN']
    data = args.audio.read_bytes()
    mime = {'.wav':'audio/wav','.webm':'audio/webm','.ogg':'audio/ogg','.mp4':'audio/mp4','.mp3':'audio/mpeg'}.get(args.audio.suffix)
    if not mime:
        parser.error('Unsupported fixture extension')
    with httpx.Client(base_url=args.url, timeout=180, headers={'Authorization':f'Bearer {token}'}) as client:
        for run in range(args.runs):
            start = perf_counter()
            response = client.post('/core/api/v1/assistant/voice', files={'audio':(args.audio.name, data, mime)})
            body = response.json()
            print(json.dumps({'run':run+1, 'http_status':response.status_code,
                'client_request_ms':round((perf_counter()-start)*1000,2),
                'timings':body.get('timings'), 'error_code':body.get('error_code'),
                'tools':[{'tool':r['tool'],'success':r['success']} for r in body.get('tool_results',[])]}), flush=True)


if __name__ == '__main__':
    main()
