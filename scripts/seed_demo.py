"""Add missing demo records through public APIs; never reset existing data."""
import argparse
import os
from pathlib import Path

import httpx
from dotenv import dotenv_values

WORKSPACES = ('Master Thesis', 'Dark Weather')
TASKS = ('Prepare API tests', 'Finish architecture', 'Add device agent')


def seed(client):
    def get(path):
        response = client.get(path)
        response.raise_for_status()
        return response.json()

    def post(path, body):
        response = client.post(path, json=body)
        response.raise_for_status()
        return response.json()

    # Preflight both services before creating anything. IoT migration owns defaults.
    workspaces = get('/core/api/v1/workspaces')
    tasks = get('/tasks-api/api/v1/tasks')
    if len(tasks) >= 1000:
        raise ValueError('Task list reached API limit; seed cannot safely check duplicates')
    get('/core/api/v1/iot/state')
    created = {'workspaces': 0, 'tasks': 0}
    for name in WORKSPACES:
        if not any(row['name'].casefold() == name.casefold() for row in workspaces):
            workspaces.append(post('/core/api/v1/workspaces', {'name': name, 'description': 'Demo workspace'}))
            created['workspaces'] += 1
    for title in TASKS:
        if not any(row['title'].casefold() == title.casefold() for row in tasks):
            tasks.append(post('/tasks-api/api/v1/tasks', {'title': title}))
            created['tasks'] += 1
    return created


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://127.0.0.1:8080')
    args = parser.parse_args()
    token = os.environ.get('DELTA_TOKEN') or dotenv_values(Path(__file__).resolve().parents[1] / '.env').get('DELTA_TOKEN')
    if not token:
        parser.error('Set DELTA_TOKEN or configure .env')
    try:
        with httpx.Client(base_url=args.url, headers={'Authorization': f'Bearer {token}'}, timeout=20) as client:
            created = seed(client)
    except (httpx.HTTPError, ValueError) as exc:
        raise SystemExit(f'Seed failed ({type(exc).__name__}); rerun after fixing service availability. Existing data preserved.') from None
    print(f"Demo ready: created {created['workspaces']} workspaces, {created['tasks']} tasks. Existing records preserved.")


if __name__ == '__main__':
    main()
