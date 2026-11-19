import hashlib,hmac,secrets,time
from sqlalchemy import select,delete
from sqlalchemy.orm import Session
from .models import User,LoginSession

def hash_password(password):
    salt=secrets.token_hex(16)
    digest=hashlib.scrypt(password.encode(),salt=bytes.fromhex(salt),n=16384,r=8,p=1).hex()
    return salt+':'+digest

def check_password(password,encoded):
    salt,digest=encoded.split(':')
    actual=hashlib.scrypt(password.encode(),salt=bytes.fromhex(salt),n=16384,r=8,p=1).hex()
    return hmac.compare_digest(actual,digest)

def digest_token(token):return hashlib.sha256(token.encode()).hexdigest()

def resolve(engine,token,kind):
    if not token or len(token)>256:return None
    with Session(engine) as db:
        entry=db.scalar(select(LoginSession).where(LoginSession.digest==digest_token(token),LoginSession.kind==kind,LoginSession.expires>time.time()))
        user=db.get(User,entry.user_id) if entry else None
        return {'id':user.id,'username':user.username,'role':user.role} if user and user.active else None

def issue(db,user,kind):
    token=secrets.token_urlsafe(48)
    db.execute(delete(LoginSession).where(LoginSession.expires<time.time()))
    db.add(LoginSession(digest=digest_token(token),user_id=user.id,kind=kind,expires=time.time()+(86400 if kind=='web' else 2592000)))
    db.commit()
    return token
