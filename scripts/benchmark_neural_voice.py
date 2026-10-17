"""Run inside the neural image with provisioned models. No assistant/tool calls."""
import argparse
import asyncio
import json
from pathlib import Path
from time import perf_counter
from io import BytesIO
import wave

from delta_contracts.config import Settings
from delta_core.voice.neural import NeuralTTSProvider
from delta_core.voice.tts import PiperTTSProvider


async def run(args):
    settings = Settings(qwen_tts_timeout_seconds=120)
    provider = NeuralTTSProvider(settings, PiperTTSProvider(settings.piper_model))
    started = perf_counter()
    await provider.startup()
    startup_ms = (perf_counter() - started) * 1000
    if provider._model is None:
        raise RuntimeError(provider.startup_error)
    results = []
    for voice in args.voices:
        started = perf_counter()
        try:
            audio, metadata = await provider.synthesize_profile(args.text, voice, strict=True)
            elapsed = (perf_counter() - started) * 1000
            with wave.open(BytesIO(audio)) as wav:
                seconds = wav.getnframes() / wav.getframerate()
            path = Path(args.output) / f'{voice}.wav'
            path.write_bytes(audio)
            results.append(dict(voice=voice, text=args.text, synthesis_ms=round(elapsed, 1),
                                audio_seconds=round(seconds, 2), rtf=round(elapsed / 1000 / seconds, 2), **metadata))
        except Exception as error:
            results.append(dict(voice=voice, error=type(error).__name__, code=getattr(error, 'code', None),
                                elapsed_ms=round((perf_counter() - started) * 1000, 1)))
        print(json.dumps(results[-1], ensure_ascii=False), flush=True)
    report = dict(model='Qwen3-TTS-12Hz-0.6B-CustomVoice', device=settings.qwen_tts_device,
                  threads=settings.qwen_tts_threads, startup_ms=round(startup_ms, 1), results=results)
    (Path(args.output) / 'report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--text', default='Привет! Я Дельта. Чем могу помочь?')
    parser.add_argument('--voices', nargs='+', default=['serena', 'ryan', 'piper'])
    parser.add_argument('--output', default='/output')
    asyncio.run(run(parser.parse_args()))
