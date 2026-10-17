import asyncio
import json
import httpx
from delta_contracts.errors import DeltaError
from delta_contracts.tools import ToolCall
from .base import LLMProvider,LLMTurn


class OpenRouterLLMProvider(LLMProvider):
    def __init__(self,api_key:str,model:str,client:httpx.AsyncClient|None=None, *, router=False, max_tokens=1200):
        self.api_key=api_key;self.model=model;self.client=client
        self.router=router;self.max_tokens=max_tokens

    async def respond(self,messages,tools,context):
        if not self.api_key or not self.model:
            raise DeltaError('LLM_UNAVAILABLE','Configure OPENROUTER_API_KEY and the router/assistant model',503)
        aliases={t['name'].replace('.','__'):t['name'] for t in tools}
        wire=[]
        for message in messages:
            item=dict(message)
            if item.get('tool_calls'):
                item['tool_calls']=[{**call,'function':{**call['function'],'name':call['function']['name'].replace('.','__')}} for call in item['tool_calls']]
            wire.append(item)
        payload={'model':self.model,'messages':wire,'max_tokens':self.max_tokens}
        if self.router:
            payload.update(temperature=0, reasoning={'enabled':False}, provider={'sort':'latency'})
        if tools:
            payload['tools']=[{'type':'function','function':{'name':t['name'].replace('.','__'),'description':t['description'],'parameters':t['input_schema']}} for t in tools]
        own=self.client is None
        client=self.client or httpx.AsyncClient(timeout=60)
        try:
            for attempt in range(2):
                response=await client.post('https://openrouter.ai/api/v1/chat/completions',headers={'Authorization':f'Bearer {self.api_key}'},json=payload)
                try:
                    body=response.json()
                except ValueError:
                    body=None
                error=body.get('error') if isinstance(body,dict) else None
                if response.is_error or error is not None:
                    status=response.status_code
                    if isinstance(error,dict):
                        try:
                            status=int(error.get('code',status))
                        except (ValueError,TypeError):
                            pass
                    if status in {500,502,503,504} and attempt==0:
                        # Only retry inference before returning any tool calls.
                        await asyncio.sleep(.3)
                        continue
                    raise provider_error(status)
                break
            choice=body['choices'][0]
            if choice.get('finish_reason')=='length':
                raise DeltaError('LLM_UNAVAILABLE','Модель исчерпала лимит ответа. Сократите запрос или выберите другую модель; неполные команды не выполнялись.',503)
            message=choice['message']
            if not isinstance(message, dict) or not isinstance(message.get('content') or '', str):
                raise ValueError('Invalid assistant message')
            calls=[ToolCall(id=c['id'],name=aliases[c['function']['name']],arguments=json.loads(c['function']['arguments'])) for c in message.get('tool_calls',[])]
            if not calls and not (message.get('content') or '').strip():
                raise ValueError('Empty model response')
            return LLMTurn(text=message.get('content') or '',calls=calls)
        except httpx.TimeoutException:
            raise DeltaError('LLM_UNAVAILABLE','OpenRouter не ответил вовремя. Попробуйте позже или выберите другую модель.',503) from None
        except httpx.HTTPError:
            raise DeltaError('LLM_UNAVAILABLE','Не удалось соединиться с OpenRouter. Проверьте доступ к сети.',503) from None
        except (ValueError,KeyError,TypeError,IndexError,AttributeError):
            raise DeltaError('LLM_UNAVAILABLE','Модель вернула пустой или некорректный ответ либо вызов неизвестного инструмента. Команды из этого ответа не выполнялись.',503) from None
        finally:
            if own:await client.aclose()


def provider_error(status):
    messages={
        400:'OpenRouter отклонил параметры запроса или выбранная модель не поддерживает инструменты.',
        401:'OpenRouter отклонил API-ключ. Проверьте OPENROUTER_API_KEY в настройках сервера.',
        402:'Недостаточно средств или превышен лимит расходов OpenRouter.',
        403:'OpenRouter запретил запрос. Проверьте доступ к модели и настройки аккаунта.',
        404:'Модель OpenRouter или подходящий провайдер недоступны. Выберите другую модель.',
        429:'Достигнут лимит запросов OpenRouter. Попробуйте позже.',
        502:'Провайдер OpenRouter временно недоступен. Попробуйте позже или выберите другую модель.',
        503:'Модель OpenRouter перегружена. Попробуйте позже или выберите другую модель.',
        504:'Провайдер OpenRouter не ответил вовремя. Попробуйте позже.',
    }
    return DeltaError('LLM_UNAVAILABLE',messages.get(status,'OpenRouter вернул ошибку провайдера. Попробуйте позже или выберите другую модель.'),503)
