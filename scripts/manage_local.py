from pathlib import Path
import os, subprocess, sys, signal, time
from dotenv import dotenv_values
import psycopg
from psycopg import sql
import httpx

ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)
ENV = {**os.environ, **{k:v for k,v in dotenv_values(ROOT / '.env').items() if v is not None}}
BIN = ROOT / '.venv/bin'
PID = ROOT / '.runtime/services.pid'

def run(args, **kw):
    return subprocess.run([str(a) for a in args], check=True, **kw)

def wait(url):
    for _ in range(180):
        try:
            if httpx.get(url, timeout=2).status_code == 200: return
        except httpx.HTTPError: pass
        time.sleep(1)
    raise RuntimeError('Service did not become ready: ' + url)

if sys.argv[1] == 'stop':
    if PID.exists():
        try: os.kill(int(PID.read_text()), signal.SIGTERM)
        except ProcessLookupError: PID.unlink(missing_ok=True)
        for _ in range(60):
            if not PID.exists(): break
            time.sleep(1)
    if (ROOT / '.runtime/postgres/postmaster.pid').exists():
        run(['pg_ctl','-D',ROOT/'.runtime/postgres','stop','-m','fast'])
    sys.exit()

if PID.exists():
    try: os.kill(int(PID.read_text()), 0)
    except ProcessLookupError: PID.unlink()
    else: raise SystemExit('Delta already running')
if subprocess.run(['pg_ctl', '-D', str(ROOT / '.runtime/postgres'), 'status'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode != 0:
    run(['pg_ctl','-D',ROOT/'.runtime/postgres','-l',ROOT/'.runtime/postgres.log','-o','-h 127.0.0.1 -p 55432 -k /tmp','start'])
with psycopg.connect(host='127.0.0.1',port=55432,user='postgres',password=ENV['POSTGRES_PASSWORD'],dbname='postgres',autocommit=True) as db:
    for name, key in [('delta_core','CORE_DB_PASSWORD'),('delta_tasks','TASKS_DB_PASSWORD')]:
        if not db.execute('SELECT 1 FROM pg_roles WHERE rolname=%s',(name,)).fetchone():
            db.execute(sql.SQL('CREATE ROLE {} LOGIN PASSWORD {}').format(sql.Identifier(name),sql.Literal(ENV[key])))
        if not db.execute('SELECT 1 FROM pg_database WHERE datname=%s',(name,)).fetchone():
            db.execute(sql.SQL('CREATE DATABASE {} OWNER {}').format(sql.Identifier(name),sql.Identifier(name)))

children=[]
logs=[]
def launch(name,args,env=ENV,cwd=ROOT):
    log=open(ROOT/f'.runtime/{name}.log','a'); logs.append(log)
    p=subprocess.Popen([str(a) for a in args],cwd=cwd,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    children.append(p)

def stop(*args): raise KeyboardInterrupt
signal.signal(signal.SIGTERM,stop)
signal.signal(signal.SIGINT,stop)
PID.write_text(str(os.getpid()))
try:
    for name,port,key in [('tasks',8001,'TASKS_DB_PASSWORD'),('core',8000,'CORE_DB_PASSWORD')]:
        env={**ENV,'DATABASE_URL':f"postgresql+psycopg://delta_{name}:{ENV[key]}@127.0.0.1:55432/delta_{name}",'SERVICE_NAME':f'delta-{name}'}
        run([BIN/'alembic','-c',f'apps/delta-{name}/alembic.ini','upgrade','head'],env=env)
        launch(name,[BIN/'uvicorn',f'delta_{name}.main:create_app','--factory','--host','127.0.0.1','--port',str(port)],env)
        wait(f'http://127.0.0.1:{port}/health')
    launch('ui',['node','node_modules/vite/bin/vite.js','preview','--host','0.0.0.0','--port','8081','--strictPort'],cwd=ROOT/'apps/delta-control-center')
    launch('agent',[BIN/'python','-m','delta_agent.main','--name','Nobara workstation','--config-dir',ROOT/'.runtime/agent','--allow-root',ROOT.parent],env={**ENV,'DELTA_TOKEN':(ROOT/'.runtime/server-agent-session').read_text().strip()})
    wait('http://127.0.0.1:8081')
    print('Delta ready: http://192.168.0.28:8081',flush=True)
    while True:
        for p in children:
            if p.poll() is not None: raise RuntimeError(f'Service exited: {p.args[0]} ({p.returncode})')
        time.sleep(2)
except KeyboardInterrupt:
    pass
finally:
    for p in reversed(children):
        if p.poll() is None: os.killpg(p.pid,signal.SIGTERM)
    for p in children:
        try: p.wait(timeout=20)
        except subprocess.TimeoutExpired: os.killpg(p.pid,signal.SIGKILL); p.wait()
    PID.unlink(missing_ok=True)
    for log in logs: log.close()
