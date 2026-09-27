"""Compare startup-reused STT models on identical, already recorded Russian audio."""
import argparse
import asyncio
import gc
import json
from pathlib import Path
import platform
import re
from statistics import mean, median
from time import perf_counter

from delta_core.voice.stt import WhisperSTTProvider


def words(text):
    return re.findall(r'\w+', text.casefold().replace('ё', 'е'))


def edit_distance(reference, hypothesis):
    previous = list(range(len(hypothesis) + 1))
    for i, a in enumerate(reference, 1):
        current = [i]
        for j, b in enumerate(hypothesis, 1):
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j-1] + (a != b)))
        previous = current
    return previous[-1]


async def benchmark(args):
    corpus = json.loads(args.corpus.read_text())
    manifest = json.loads((args.audio_dir / 'manifest.json').read_text())
    report = {'platform':platform.platform(), 'processor':platform.machine(),
              'audio_source':manifest['voice'], 'speech_rate':manifest['rate'],
              'commands':len(corpus['commands']), 'settings':{'language':'ru','cpu_threads':2,'beam_size':1,'vad_filter':True,'word_timestamps':False},
              'models':{}}
    for name in args.models:
        provider = WhisperSTTProvider(name, args.cache_dir, 60, 'ru')
        start = perf_counter()
        await provider.startup()
        load_ms = (perf_counter()-start)*1000
        if provider.startup_error:
            raise RuntimeError(f'{name}: {provider.startup_error}')
        await provider.transcribe((args.audio_dir / '000.wav').read_bytes())
        rows = []
        for index, command in enumerate(corpus['commands']):
            path = args.audio_dir / f'{index:03d}.wav'
            audio = path.read_bytes()
            import hashlib
            assert hashlib.sha256(audio).hexdigest() == manifest['samples'][index]['sha256']
            assert manifest['samples'][index]['text'] == command['text']
            start = perf_counter()
            transcript = await provider.transcribe(audio)
            elapsed = (perf_counter()-start)*1000
            reference, hypothesis = words(command['text']), words(transcript)
            rows.append({'index':index,'reference':command['text'],'transcript':transcript,'stt_ms':elapsed,
                         'word_errors':edit_distance(reference, hypothesis),'reference_words':len(reference),
                         'exact_match':reference == hypothesis})
            if (index+1)%5 == 0:
                print(f'{name}: {index+1}/{len(corpus["commands"])}', flush=True)
        report['models'][name] = {'startup_ms':load_ms,'compute_type':provider.compute_type,
            'average_stt_ms':mean(r['stt_ms'] for r in rows),'median_stt_ms':median(r['stt_ms'] for r in rows),
            'word_error_rate':sum(r['word_errors'] for r in rows)/sum(r['reference_words'] for r in rows),
            'normalized_exact_match_accuracy':mean(r['exact_match'] for r in rows), 'rows':rows}
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
        print(json.dumps({name:{k:v for k,v in report['models'][name].items() if k != 'rows'}}), flush=True)
        del provider
        gc.collect()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--corpus',type=Path,required=True)
    parser.add_argument('--audio-dir',type=Path,required=True)
    parser.add_argument('--cache-dir',default='/models/whisper')
    parser.add_argument('--models',nargs='+',default=['small','base'])
    parser.add_argument('--output',type=Path,required=True)
    asyncio.run(benchmark(parser.parse_args()))
