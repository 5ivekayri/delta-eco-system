"""Bounded file storage shared by Core and desktop Agent. Never executes files."""
import base64
import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import tempfile
import threading
import time
from uuid import UUID

TEXT_EXTENSIONS={'.html','.htm','.css','.js','.mjs','.ts','.tsx','.jsx','.json','.md','.txt','.py','.yaml','.yml','.toml','.csv','.svg'}
EXTENSIONS=TEXT_EXTENSIONS|{'.docx'}
MAX_FILE=10*1024*1024
MAX_TEXT=512*1024
LOCK=threading.RLock()


class FileConflict(ValueError):pass


def relative_path(value):
    parts=value.split('/')
    if not value or len(value)>512 or '\\' in value or ':' in value or any(not p or p in {'.','..'} or p.startswith('.') or p.endswith((' ','.')) for p in parts):
        raise ValueError('Use a relative file path without hidden directories')
    if any(ord(c)<32 for c in value) or PurePosixPath(value).suffix.lower() not in EXTENSIONS:
        raise ValueError('Unsupported file type')
    if any(re.fullmatch(r'(?i)(con|prn|aux|nul|com[0-9]|lpt[0-9])(?:\..*)?',p) for p in parts):
        raise ValueError('Reserved filename')
    if any(p.casefold() in {'credentials.json','credentials.yaml','secrets.json','secrets.yaml','id_rsa','id_ed25519'} for p in parts):
        raise ValueError('Credential files are excluded')
    return value


def validate_content(path,data):
    relative_path(path)
    if len(data)>(MAX_FILE if path.lower().endswith('.docx') else MAX_TEXT):raise ValueError('File exceeds size limit')
    if not path.lower().endswith('.docx'):data.decode('utf-8')


def digest(data):return hashlib.sha256(data).hexdigest()


def pack(path,data):
    return {'path':path,'size':len(data),'hash':digest(data),'content_base64':base64.b64encode(data).decode('ascii')}


class FileStore:
    def __init__(self,root):self.root=Path(root).absolute()

    def directory(self,workspace_id):
        key=str(UUID(workspace_id))
        directory=self.root/key
        # Also reject symlinked storage ancestors, including a replaced workspace root.
        if any(p.is_symlink() for p in [directory,*directory.parents]):raise ValueError('Symlinks are not allowed')
        return directory

    def target(self,directory,path):
        relative_path(path)
        target=directory/path
        if any(p.is_symlink() for p in [target,*target.parents]):raise ValueError('Symlinks are not allowed')
        if not target.resolve().is_relative_to(directory.resolve()):raise ValueError('Path outside workspace')
        return target

    def listing(self,directory):
        rows=[]
        if not directory.exists():return rows
        for base,dirs,files in os.walk(directory,followlinks=False):
            dirs[:]=[d for d in dirs if not d.startswith('.') and not (Path(base)/d).is_symlink()]
            for name in sorted(files):
                path=(Path(base)/name).relative_to(directory).as_posix()
                try:target=self.target(directory,path)
                except ValueError:continue
                if not target.is_file():continue
                rows.append({'path':path,'size':target.stat().st_size})
                if len(rows)>128:raise ValueError('Workspace contains too many files (maximum 128)')
        return sorted(rows,key=lambda r:r['path'])

    def execute(self,body):
        with LOCK:
            directory=self.directory(body.workspace_id)
            if body.operation=='list':return {'files':self.listing(directory),'local_path':str(directory)}
            target=self.target(directory,body.path)
            history=directory/'.history'/digest(body.path.encode())
            if history.is_symlink() or history.parent.is_symlink():raise ValueError('Invalid history directory')
            if body.operation=='history':
                return {'versions':[{'hash':p.name,'size':p.stat().st_size,'modified':p.stat().st_mtime} for p in sorted(history.glob('*'),key=lambda p:p.stat().st_mtime,reverse=True) if re.fullmatch('[a-f0-9]{64}',p.name) and not p.is_symlink()][:20]}
            if body.operation=='read':
                source=target
                if body.version:
                    if not re.fullmatch('[a-f0-9]{64}',body.version):raise ValueError('Invalid version')
                    source=history/body.version
                if source.is_symlink() or not source.is_file():raise FileNotFoundError('File not found')
                with source.open('rb') as f:data=f.read(MAX_FILE+1)
                validate_content(body.path,data)
                return pack(body.path,data)
            data=base64.b64decode(body.content_base64,validate=True)
            validate_content(body.path,data)
            if target.exists() and (not target.is_file() or target.stat().st_size>MAX_FILE):
                raise ValueError('Existing file cannot be replaced: unsupported type or size')
            previous=target.read_bytes() if target.is_file() else None
            if (digest(previous) if previous is not None else '')!=body.expected_hash:raise FileConflict('File changed; reload before saving')
            rows=self.listing(directory)
            if len(rows)>=128 and previous is None:raise ValueError('Maximum 128 files')
            if sum(r['size'] for r in rows)-len(previous or b'')+len(data)>64*1024*1024:raise ValueError('Workspace quota is 64 MB')
            history.mkdir(parents=True,exist_ok=True,mode=0o700)
            if previous is not None:
                backup=history/digest(previous)
                if not backup.exists():backup.write_bytes(previous)
            # No unbounded backup growth. Retain the twenty most recent pre-save versions.
            backups=sorted(history.glob('*'),key=lambda p:p.stat().st_mtime,reverse=True)
            for backup in backups[20:]:
                if backup.is_file() and not backup.is_symlink():backup.unlink()
            target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
            fd,temp=tempfile.mkstemp(prefix='.delta-',dir=target.parent)
            try:
                with os.fdopen(fd,'wb') as f:f.write(data)
                os.replace(temp,target)
            finally:
                if os.path.exists(temp):os.unlink(temp)
            return {'path':body.path,'size':len(data),'hash':digest(data)}


def permitted_source(path,roots):
    candidate=Path(path).expanduser().absolute()
    if not candidate.is_file() or candidate.is_symlink():raise ValueError('File is not available')
    resolved=candidate.resolve()
    matched=next((root for root in roots if resolved.is_relative_to(root)),None)
    if matched is None:raise ValueError('File is outside permitted folders')
    relative_path(resolved.relative_to(matched).as_posix())
    if any(p.is_symlink() for p in [candidate,*candidate.parents]):raise ValueError('Symlinks are not allowed')
    return resolved


def search_files(query,roots,cancelled=lambda:False):
    if '/' in query or '\\' in query or not query.strip():raise ValueError('Search by filename only')
    matches=[];seen=set();count=0;start=time.monotonic();truncated=False
    excluded={'node_modules','venv','build','dist','__pycache__','Library','AppData'}
    for root in roots:
        for base,dirs,files in os.walk(root,followlinks=False):
            dirs[:]=sorted(d for d in dirs if not d.startswith('.') and d not in excluded and not (Path(base)/d).is_symlink())
            if cancelled():raise ValueError('Search cancelled')
            count+=len(files)+len(dirs)
            if count>30000 or time.monotonic()-start>5:truncated=True;break
            for name in files:
                if query.casefold() not in name.casefold():continue
                try:p=permitted_source(Path(base)/name,roots)
                except (OSError,ValueError):continue
                if str(p) in seen:continue
                seen.add(str(p));matches.append({'name':name,'path':str(p),'size':p.stat().st_size})
                if len(matches)>=50:truncated=True;break
            if truncated:break
        if truncated:break
    return {'matches':sorted(matches,key=lambda p:(p['name'].casefold()!=query.casefold(),p['path'])), 'truncated':truncated,'roots':[str(r) for r in roots]}
