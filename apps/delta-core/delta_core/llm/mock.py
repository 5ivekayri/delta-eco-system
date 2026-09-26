import json
import re
from .base import LLMProvider,LLMTurn
from delta_contracts.tools import ToolCall


def describe_result(result:dict)->str:
    if not result['success']:
        return 'Не удалось выполнить действие: '+result.get('message','ошибка')
    data=result.get('data');tool=result.get('tool','')
    if tool=='tasks.create':
        return 'Задача добавлена: '+data['title']
    if tool=='devices.list':
        names=[d['display_name'] for d in data if d['status']=='online']
        return 'Подключены: '+', '.join(names) if names else 'Сейчас нет подключённых устройств.'
    if isinstance(data,list):
        return '\n'.join('• '+str(row.get('title',row.get('name',row.get('display_name',row)))) for row in data[:20]) or 'Ничего не найдено.'
    if isinstance(data,dict):
        return data.get('message') or json.dumps(data,ensure_ascii=False)
    return str(data)


class MockLLMProvider(LLMProvider):
    async def respond(self,messages,tools,context):
        if messages[-1]['role']=='tool':
            results=[json.loads(m['content']) for m in messages if m['role']=='tool']
            return LLMTurn(text='\n'.join(describe_result(r) for r in results))
        message=messages[-1]['content'];lower=message.casefold()
        workspace=next((w for w in context.get('workspaces',[]) if w['name'].casefold() in lower or
                        ('диплом' in lower and w['name']=='Master Thesis')),None)
        name=None;arguments={}
        if any(word in lower for word in ['устройств','компьютер','devices']) and not any(word in lower for word in ['открой','open ']):
            name='devices.list'
        elif 'сервис' in lower or 'services' in lower:
            name='services.list'
        elif re.search(r'(добавь|создай|add|create)\s+(задачу|task)',lower):
            name='tasks.create'
            title=re.sub(r'^.*?(?:добавь|создай|add|create)\s+(?:задачу|task)\s*','',message,flags=re.I).strip(' .')
            arguments={'title':title}
            if workspace:arguments['workspace_id']=workspace['id']
        elif 'задач' in lower or 'tasks' in lower:
            name='tasks.list'
            if workspace:arguments['workspace_id']=workspace['id']
        elif 'открой' in lower or lower.startswith('open '):
            if not workspace:return LLMTurn(text='Укажите существующее рабочее пространство.')
            name='workspaces.launch';arguments={'workspace_id':workspace['id']}
            devices=[d for d in context.get('devices',[]) if d['display_name'].casefold() in lower]
            if len(devices)>1:
                return LLMTurn(text='Найдено несколько подходящих устройств. Уточните имя целевого компьютера.')
            if devices:arguments['device_id']=devices[0]['id']
            elif context.get('device_id'):arguments['device_id']=context['device_id']
        elif 'свет' in lower or 'light' in lower:
            name='iot.set_light';arguments={'enabled':not any(w in lower for w in ['выключ','off'])}
        elif 'температур' in lower or 'temperature' in lower:name='iot.get_temperature'
        if name:
            if name not in {t['name'] for t in tools}:return LLMTurn(text='Нужный инструмент сейчас недоступен. Проверьте подключение сервиса.')
            return LLMTurn(calls=[ToolCall(name=name,arguments=arguments)])
        return LLMTurn(text='Mock-режим: попробуйте «покажи устройства», «покажи задачи», «добавь задачу протестировать API» или «открой Dark Weather».')
