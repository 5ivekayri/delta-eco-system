import asyncio,time
from fastapi import APIRouter,Request,Response
from fastapi.responses import JSONResponse
from pydantic import Field,field_validator
from sqlalchemy import select,delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from delta_contracts.devices import StrictModel
from delta_contracts.errors import DeltaError
from .models import User,LoginSession
from .service import hash_password,check_password,resolve,issue,digest_token

router=APIRouter(prefix='/api/v1/auth')
class Credentials(StrictModel):
    username:str=Field(min_length=3,max_length=64,pattern=r'^[A-Za-z0-9_.-]+$')
    password:str=Field(min_length=10,max_length=128)
    @field_validator('username')
    @classmethod
    def normalize(cls,v):return v.lower()

async def throttle(request):
    state=request.app.state
    if not hasattr(state,'login_attempts'):state.login_attempts={}
    key=request.client.host if request.client else 'unknown'
    now=time.monotonic()
    state.login_attempts={k:[t for t in times if t>now-60] for k,times in state.login_attempts.items() if times and times[-1]>now-60}
    if len(state.login_attempts)>10000:raise DeltaError('TRY_LATER','Попробуйте через минуту.',429)
    attempts=state.login_attempts.setdefault(key,[])
    if len(attempts)>=10:raise DeltaError('TRY_LATER','Слишком много попыток. Подождите минуту.',429)
    attempts.append(now)

@router.post('/register')
async def register(body:Credentials,request:Request):
    await throttle(request)
    hashed=await asyncio.to_thread(hash_password,body.password)
    with Session(request.app.state.engine) as db:
        db.add(User(username=body.username,password_hash=hashed,role='pending'))
        try:db.commit()
        except IntegrityError:raise DeltaError('USERNAME_TAKEN','Это имя уже занято. Выберите другое.',409) from None
    return {'success':True,'message':'Аккаунт создан. Войдите, чтобы проверить доступ.'}

async def login_for(body,request,kind):
    await throttle(request)
    with Session(request.app.state.engine) as db:
        user=db.scalar(select(User).where(User.username==body.username))
        # Always perform a password KDF, including for unknown accounts.
        encoded=user.password_hash if user else '00'*16+':'+'00'*64
        valid=await asyncio.to_thread(check_password,body.password,encoded)
        if not valid or not user or not user.active:raise DeltaError('LOGIN_FAILED','Неверный логин или пароль.',401)
        if kind=='agent' and user.role!='admin':raise DeltaError('ACCESS_PENDING','Аккаунт создан, но доступ к устройствам пока не настроен.',403)
        token=issue(db,user,kind)
        return token,{'id':user.id,'username':user.username,'role':user.role}

@router.post('/login')
async def login(body:Credentials,request:Request,response:Response):
    token,user=await login_for(body,request,'web')
    response.set_cookie('delta_session',token,httponly=True,samesite='strict',secure=request.url.scheme=='https',max_age=86400,path='/')
    response.headers['Cache-Control']='no-store'
    return user

@router.post('/agent-login')
async def agent_login(body:Credentials,request:Request,response:Response):
    token,user=await login_for(body,request,'agent')
    response.headers['Cache-Control']='no-store'
    return {'token':token,'user':user,'expires_in':2592000}

@router.get('/me')
def me(request:Request):
    user=resolve(request.app.state.engine,request.cookies.get('delta_session',''),'web')
    if not user:raise DeltaError('UNAUTHORIZED','Войдите в аккаунт.',401)
    return user

@router.post('/logout')
def logout(request:Request,response:Response):
    if request.cookies.get('delta_session') and request.headers.get('x-delta-request')!='1':
        raise DeltaError('FORBIDDEN','Обновите страницу и повторите запрос.',403)
    token=request.cookies.get('delta_session','') or request.headers.get('authorization','').removeprefix('Bearer ')
    with Session(request.app.state.engine) as db:
        db.execute(delete(LoginSession).where(LoginSession.digest==digest_token(token)));db.commit()
    response.delete_cookie('delta_session',path='/')
    return {'success':True}

async def authorize(request):
    path=request.url.path
    if path in {'/api/v1/auth/login','/api/v1/auth/register','/api/v1/auth/agent-login','/api/v1/auth/me','/api/v1/auth/logout'}:
        return None
    desktop_routes = {('GET', '/api/v1/desktop/devices'),
                      ('POST', '/api/v1/desktop/message')}
    if (request.method, path) in desktop_routes:
        token = request.headers.get('authorization', '').removeprefix('Bearer ')
        user = resolve(request.app.state.engine, token, 'agent')
        if not user:return JSONResponse({'message':'Войдите снова.','error_code':'UNAUTHORIZED'},401)
        if user['role'] != 'admin':return JSONResponse({'message':'Доступ ещё не настроен.'},403)
        request.state.user = user
        return None
    user=resolve(request.app.state.engine,request.cookies.get('delta_session',''),'web')
    if not user:return JSONResponse({'message':'Войдите в аккаунт.','error_code':'UNAUTHORIZED'},401)
    if user['role']!='admin':return JSONResponse({'message':'Доступ ещё не настроен.','error_code':'ACCESS_PENDING'},403)
    if request.method not in {'GET','HEAD','OPTIONS'} and request.headers.get('x-delta-request')!='1':
        return JSONResponse({'message':'Обновите страницу и повторите запрос.'},403)
    request.state.user=user
    return None
