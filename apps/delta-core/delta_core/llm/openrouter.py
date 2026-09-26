import json
import httpx
from delta_contracts.errors import DeltaError
from delta_contracts.tools import ToolCall
from .base import LLMProvider,LLMTurn


class OpenRouterLLMProvider(LLMProvider):
    def __init__(self,api_key:str,model:str,client:httpx.AsyncClient|None=None):
        self.api_key=api_key;self.model=model;self.client=client

    async def respond(self,messages,tools,context):
        if not self.api_key or not self.model:
            raise DeltaError('LLM_UNAVAILABLE','Configure OPENROUTER_API_KEY and OPENROUTER_MODEL',503)
        aliases={t['name'].replace('.','__'):t['name'] for t in tools}
        wire=[]
        for message in messages:
            item=dict(message)
            if item.get('tool_calls'):
                item['tool_calls']=[{**call,'function':{**call['function'],'name':call['function']['name'].replace('.','__')}} for call in item['tool_calls']]
            wire.append(item)
        payload={'model':self.model,'messages':wire,'max_tokens':1200}
        if tools:
            payload['tools']=[{'type':'function','function':{'name':t['name'].replace('.','__'),'description':t['description'],'parameters':t['input_schema']}} for t in tools]
        own=self.client is None
        client=self.client or httpx.AsyncClient(timeout=60)
        try:
            response=await client.post('https://openrouter.ai/api/v1/chat/completions',headers={'Authorization':f'Bearer {self.api_key}'},json=payload)
            response.raise_for_status()
            message=response.json()['choices'][0]['message']
            if not isinstance(message, dict) or not isinstance(message.get('content') or '', str):
                raise ValueError('Invalid assistant message')
            calls=[ToolCall(id=c['id'],name=aliases[c['function']['name']],arguments=json.loads(c['function']['arguments'])) for c in message.get('tool_calls',[])]
            return LLMTurn(text=message.get('content') or '',calls=calls)
        except (httpx.HTTPError,ValueError,KeyError,TypeError,IndexError,AttributeError):
            raise DeltaError('LLM_UNAVAILABLE','OpenRouter request failed or returned invalid tool calls',503)
        finally:
            if own:await client.aclose()
