"""Offline labeled corpus evaluation; never invokes live tools or an LLM."""
import argparse
import asyncio
import json
from pathlib import Path
from statistics import mean
from time import perf_counter

from delta_contracts.devices import EmptyPayload
from delta_contracts.tasks import task_manifest
from delta_contracts.workspaces import LaunchInput
from delta_core.assistant.intents import LocalIntentRouter, normalized

ROOT = Path(__file__).resolve().parents[1]


def specifications():
    # IoT contracts are explicit benchmark fixtures; production requires registration.
    return task_manifest()['tools'] + [
        {'name': 'devices.list', 'input_schema': EmptyPayload.model_json_schema()},
        {'name': 'workspaces.launch', 'input_schema': LaunchInput.model_json_schema()},
        {'name': 'iot.set_light', 'input_schema': {'type':'object','properties':{'enabled':{'type':'boolean'},'device_name':{'type':'string'}},'required':['enabled'],'additionalProperties':False}},
        {'name': 'iot.get_temperature', 'input_schema': EmptyPayload.model_json_schema()},
    ]


def equal_slots(actual, expected):
    return {k:normalized(v) if isinstance(v, str) else v for k,v in actual.items()} == {
        k:normalized(v) if isinstance(v, str) else v for k,v in expected.items()}


async def evaluate(corpus, repeats=100):
    async def lookup():
        return corpus['tasks']
    router = LocalIntentRouter(lookup)
    specs = specifications()
    samples, rows = [], []
    for _ in range(repeats):
        for command in corpus['commands']:
            start = perf_counter()
            decision = await router.route(command['text'], specs, corpus['context'])
            samples.append((perf_counter() - start) * 1000)
            if _ == 0:
                intent = decision.call.name if decision.call and decision.confidence >= .9 else None
                rows.append({'text':command['text'], 'expected':command['intent'], 'actual':intent,
                             'intent_correct':intent == command['intent'],
                             'slots_correct':equal_slots(decision.slots, command['slots']) if command['intent'] else None,
                             'arguments':decision.call.arguments if intent else None})
    slots = [r['slots_correct'] for r in rows if r['slots_correct'] is not None]
    nonempty_slots = [row['slots_correct'] for row, command in zip(rows, corpus['commands']) if command['intent'] and command['slots']]
    return {'commands':len(rows), 'repeats':repeats, 'threshold':.9,
            'intent_accuracy':mean(r['intent_correct'] for r in rows),
            'slot_exact_match_accuracy':mean(slots), 'slot_denominator':len(slots),
            'nonempty_slot_exact_match_accuracy':mean(nonempty_slots), 'nonempty_slot_denominator':len(nonempty_slots),
            'average_routing_ms':mean(samples), 'max_routing_ms':max(samples), 'rows':rows}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--corpus', type=Path, default=ROOT / 'benchmarks/russian_commands.json')
    parser.add_argument('--repeats', type=int, default=100)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error('--repeats must be positive')
    result = asyncio.run(evaluate(json.loads(args.corpus.read_text()), args.repeats))
    output = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(output + '\n')
    print(json.dumps({k:v for k,v in result.items() if k != 'rows'}, ensure_ascii=False))
