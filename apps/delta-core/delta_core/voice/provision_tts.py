"""Explicit setup only: python -m delta_core.voice.provision_tts."""
import argparse
from pathlib import Path
from piper.download_voices import download_voice
from delta_contracts.config import Settings

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--force', action='store_true', help='Replace a damaged or partial download')
    args = parser.parse_args()
    settings = Settings()
    path = Path(settings.piper_model)
    if not settings.piper_model or path.suffix != '.onnx' or not path.stem.startswith('ru_RU-'):
        raise SystemExit('Set PIPER_MODEL to the path of a Russian Piper .onnx model first.')
    path.parent.mkdir(parents=True, exist_ok=True)
    download_voice(path.stem, path.parent, force_redownload=args.force)
    print('Piper model/config installed. Restart Core to load the voice.')
