"""Offline background worker. No Blender imports, network requests or installer."""
import argparse
import hashlib
import json
import math
import multiprocessing
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import wave

VERSION = '0.4.0'
MODEL_SHA256 = '8c328b45f59d8dd3dff219253ff6a8d6482be57d0133a29140e2febbf8eb8331'


def resources_default():
    return Path(sys.executable).resolve().parents[1] if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[1] / '.build' / 'resources'


def paths(root):
    suffix = '.exe' if os.name == 'nt' else ''
    return (root / 'bin' / ('ffmpeg' + suffix), root / 'bin' / ('ffprobe' + suffix),
            root / 'models/hub/checkpoints/beat_this-final0.ckpt')


def make_reference(path, seconds=24):
    """Copyright-free accented kick/click pattern at 120 BPM."""
    rate = 22050
    samples = []
    for index in range(rate * seconds):
        time = index / rate
        beat = int(time * 2)
        age = time - beat / 2
        accent = 1.0 if beat % 4 == 0 else .65
        kick = math.sin(2 * math.pi * (65 * age + 60 * .02 * (1-math.exp(-age/.02)))) * math.exp(-age * 24)
        click = math.sin(2 * math.pi * 1600 * age) * math.exp(-age * 180)
        bed = .045 * math.sin(2 * math.pi * (110 if beat % 8 < 4 else 146.83) * time)
        samples.append(int(max(-.99, min(.99, accent * (.7*kick + .2*click) + bed)) * 32767))
    with wave.open(str(path), 'wb') as out:
        out.setparams((1, 2, rate, len(samples), 'NONE', 'not compressed'))
        out.writeframes(struct.pack('<' + 'h' * len(samples), *samples))


def self_test(root, data_dir):
    ffmpeg, ffprobe, model = paths(root)
    for tool in (ffmpeg, ffprobe):
        subprocess.run([str(tool), '-version'], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    with model.open('rb') as handle:
        if hashlib.file_digest(handle, 'sha256').hexdigest() != MODEL_SHA256:
            raise ValueError('The bundled model checksum does not match.')
    import analyse
    analyse.ROOT = root
    with tempfile.TemporaryDirectory(prefix='beat-marker-check-') as folder:
        reference = Path(folder) / 'generated reference.wav'
        make_reference(reference)
        result = analyse.analyse(reference, str(ffmpeg), timing='detected', data_dir=data_dir)
        beats = result['beats']
        if len(beats) < 4 or any(not math.isfinite(row['time']) or not 0 <= row['time'] <= 24 for row in beats):
            raise ValueError('The bundled model did not return valid beats for the reference audio.')
        cached = analyse.analyse(reference, str(ffmpeg), timing='detected', data_dir=data_dir)
        if not cached['cached'] or cached['beats'] != beats:
            raise ValueError('Saved analysis could not be reused.')
    return {'ok': True, 'version': VERSION, 'beats': len(beats), 'model_sha256': MODEL_SHA256, 'offline': True}


def main():
    parser = argparse.ArgumentParser(description='Beat Marker offline analysis engine')
    parser.add_argument('--version', action='store_true')
    parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--resources', type=Path, default=resources_default())
    parser.add_argument('--data-dir', type=Path)
    parser.add_argument('--source')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--timing', choices=['auto', 'detected', 'steady'], default='auto')
    args = parser.parse_args()
    if args.version:
        print(json.dumps({'version': VERSION, 'python': sys.version.split()[0], 'frozen': bool(getattr(sys, 'frozen', False))}))
        return 0
    if not args.data_dir:
        parser.error('--data-dir must point to a writable user-data folder')
    args.data_dir.mkdir(parents=True, exist_ok=True)
    root = args.resources.resolve()
    ffmpeg, ffprobe, model = paths(root)
    for path in (ffmpeg, ffprobe, model):
        if not path.is_file():
            raise ValueError('The engine package is incomplete: ' + path.name)
    os.environ['TORCH_HOME'] = str(args.data_dir / 'torch')
    if args.self_test:
        print(json.dumps(self_test(root, args.data_dir)), flush=True)
        return 0
    if not args.source or not args.output:
        parser.error('supply --source and --output, or --self-test')
    import analyse
    analyse.ROOT = root
    result = analyse.analyse(args.source, str(ffmpeg), args.timing, data_dir=args.data_dir)
    analyse.write_json(args.output, result)
    print(json.dumps({'ok': True, 'version': VERSION, 'output': str(args.output), 'beats': len(result['beats'])}), flush=True)
    return 0


if __name__ == '__main__':
    multiprocessing.freeze_support()
    try:
        sys.exit(main())
    except Exception as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}), flush=True)
        sys.exit(1)
