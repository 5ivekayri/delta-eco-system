"""macOS synthetic benchmark audio, not a substitute for human microphone data."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import wave

parser = argparse.ArgumentParser()
parser.add_argument('--corpus', type=Path, default=Path('benchmarks/russian_commands.json'))
parser.add_argument('--output', type=Path, default=Path('.runtime/voice-corpus'))
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
commands = json.loads(args.corpus.read_text())['commands']
manifest = []
for index, command in enumerate(commands):
    stem = args.output / f'{index:03d}'
    subprocess.run(['/usr/bin/say', '-v', 'Milena', '-r', '170', '-o', str(stem.with_suffix('.aiff')), command['text']], check=True)
    subprocess.run(['/usr/bin/afconvert', '-f', 'WAVE', '-d', 'LEI16@16000', '-c', '1', str(stem.with_suffix('.aiff')), str(stem.with_suffix('.wav'))], check=True)
    with wave.open(str(stem.with_suffix('.wav')), 'rb') as audio:
        duration = audio.getnframes() / audio.getframerate()
        if duration < .1:
            raise RuntimeError('Speech synthesis produced empty audio; run with host speech-service access')
    manifest.append({'index':index, 'text':command['text'], 'duration_seconds':duration,
                     'sha256':hashlib.sha256(stem.with_suffix('.wav').read_bytes()).hexdigest()})
(args.output / 'manifest.json').write_text(json.dumps({'voice':'macOS Milena','rate':170,'samples':manifest}, ensure_ascii=False, indent=2))
print(f'Generated {len(commands)} nonempty WAV files')
