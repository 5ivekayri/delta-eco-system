"""Password login over HTTP(S); only the scoped session is persisted."""
import json
from urllib.parse import urlsplit,urlunsplit
from urllib.request import Request,urlopen
from urllib.error import HTTPError,URLError

def endpoint(server,path):
    u=urlsplit(server)
    base=u.path.removesuffix('/ws/agents')
    return urlunsplit(('https' if u.scheme=='wss' else 'http',u.netloc,base+'/api/v1/auth/'+path,'',''))

def login(server,username,password):
    req=Request(endpoint(server,'agent-login'),data=json.dumps({'username':username,'password':password}).encode(),headers={'Content-Type':'application/json'},method='POST')
    try:
        with urlopen(req,timeout=15) as response:return json.load(response)
    except HTTPError as error:
        if error.code==401:raise ValueError('Неверный логин или пароль.') from None
        if error.code==403:raise ValueError('Доступ к устройствам для аккаунта ещё не настроен.') from None
        if error.code==429:raise ValueError('Слишком много попыток. Подождите минуту.') from None
        raise ValueError('Не удалось войти. Проверьте адрес сервера и данные аккаунта.') from None
    except (URLError,TimeoutError):raise ValueError('Нет связи с сервером. Проверьте адрес и сеть.') from None

def logout(server,token):
    req=Request(endpoint(server,'logout'),data=b'{}',headers={'Content-Type':'application/json','Authorization':'Bearer '+token},method='POST')
    with urlopen(req,timeout=10) as response:response.read()


def desktop_request(settings, path, body=None):
    url = endpoint(settings.server, 'unused').removesuffix('auth/unused') + 'desktop/' + path
    data = json.dumps(body).encode() if body is not None else None
    request = Request(url, data=data, headers={'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + settings.token.get_secret_value()})
    try:
        with urlopen(request, timeout=90 if body else 15) as response:
            return json.load(response)
    except HTTPError as error:
        if error.code == 401:
            raise ValueError('Сессия завершилась. Выйдите из аккаунта и войдите снова.') from None
        raise ValueError('Сервер не смог выполнить запрос. Попробуйте ещё раз.') from None
    except (URLError, TimeoutError):
        raise ValueError('Нет ответа от сервера. Проверьте соединение. Отправленную команду проверьте перед повтором.') from None
