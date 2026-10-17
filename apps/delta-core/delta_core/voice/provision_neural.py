"""Explicit deployment step; runtime never downloads model weights."""
import argparse
from huggingface_hub import snapshot_download

MODEL = 'Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice'
REVISION = '85e237c12c027371202489a0ec509ded67b5e4b5'

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--directory', default='/models/qwen')
    args = parser.parse_args()
    snapshot_download(MODEL, revision=REVISION, local_dir=args.directory)
    print('Qwen3-TTS CustomVoice provisioned:', args.directory)
