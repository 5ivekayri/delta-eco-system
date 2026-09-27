"""Offline downstream intent/slot evaluation of saved STT results; no live tools."""
import argparse
import asyncio
import json
from pathlib import Path
from benchmark_intents import specifications, equal_slots
from delta_core.assistant.intents import LocalIntentRouter


async def analyze(corpus, report):
    async def lookup():
        return corpus['tasks']
    router = LocalIntentRouter(lookup)
    positive_count = sum(command['intent'] is not None for command in corpus['commands'])
    for model in report['models'].values():
        correct = slots = incorrect_acceptances = 0
        assert len(model['rows']) == len(corpus['commands'])
        for row, command in zip(model['rows'], corpus['commands']):
            assert row['reference'] == command['text']
            decision = await router.route(row['transcript'], specifications(), corpus['context'])
            intent = decision.call.name if decision.call and decision.confidence >= .9 else None
            row['local_intent'] = intent
            row['intent_correct'] = intent == command['intent']
            row['slots_correct'] = equal_slots(decision.slots, command['slots']) if command['intent'] else None
            correct += row['intent_correct']
            slots += bool(row['slots_correct'] and row['intent_correct'])
            incorrect_acceptances += bool(intent and (intent != command['intent'] or not row['slots_correct']))
        model['downstream_intent_accuracy'] = correct / len(corpus['commands'])
        model['downstream_intent_and_slots_accuracy'] = slots / positive_count
        model['incorrect_local_acceptances'] = incorrect_acceptances
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--corpus', type=Path, default=Path('benchmarks/russian_commands.json'))
    parser.add_argument('--results', type=Path, default=Path('benchmarks/stt_results.json'))
    args = parser.parse_args()
    report = asyncio.run(analyze(json.loads(args.corpus.read_text()), json.loads(args.results.read_text())))
    args.results.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({name:{k:v for k,v in model.items() if k != 'rows'} for name,model in report['models'].items()}, indent=2))
