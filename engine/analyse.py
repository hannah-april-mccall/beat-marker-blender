#!/usr/bin/env python3
"""Local-only Beat This! inference. JSON output; no Premiere or network access required."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from rhythm import recover

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault('TORCH_HOME', str(ROOT / 'models'))

def status(message):
    print(message, file=sys.stderr, flush=True)

def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp-' + str(os.getpid()))
    temp.write_text(json.dumps(data, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    os.replace(temp, path)

def beat_labels(beats, downbeats):
    """Do not invent beat positions before the first bar anchor or with no anchors."""
    down = set(float(x) for x in downbeats)
    rows, bar, position = [], 0, None
    for raw in beats:
        t = float(raw)
        if t in down:
            bar += 1
            position = 1
        elif position is not None:
            position += 1
        rows.append({'time': round(t, 8), 'beat': position, 'bar': bar or None})
    # Use the first complete detected bar to number a short opening pickup.
    anchors = [i for i, row in enumerate(rows) if row['beat'] == 1]
    if len(anchors) >= 2:
        first, second = anchors[:2]
        length = second - first
        if 0 < first < length:
            for i in range(first):
                rows[i]['beat'] = length - first + i + 1
                rows[i]['bar'] = 0
    return rows

def activity_bounds(signal, sr):
    import numpy as np
    block = max(1, int(sr * .1))
    padded = np.pad(signal, (0, (-len(signal)) % block))
    rms = np.sqrt(np.mean(padded.reshape(-1, block).astype(float) ** 2, axis=1))
    threshold = max(.00001, float(np.percentile(rms, 95)) * .001)
    active = np.flatnonzero(rms > threshold)
    return (float(active[0] * .1), min(len(signal)/sr, float((active[-1]+1)*.1))) if len(active) else (0., 0.)

def analyse(source, ffmpeg, timing='auto', meter='auto', data_dir=None):
    import numpy as np
    import soundfile as sf
    import torch
    torch.set_num_threads(max(1, min(4, os.cpu_count() or 1)))
    from beat_this.inference import Audio2Beats
    source = Path(source).resolve(strict=True)
    st = source.stat()
    checkpoint = ROOT / 'models' / 'hub' / 'checkpoints' / 'beat_this-final0.ckpt'
    if not checkpoint.is_file():
        raise RuntimeError('The Beat This! model is missing. Run the supplied setup script first.')
    fingerprint = hashlib.sha256(json.dumps([str(source), st.st_size, st.st_mtime_ns, 'final0-v1'],ensure_ascii=False).encode()).hexdigest()
    cache = (Path(data_dir) if data_dir else ROOT) / 'cache' / (fingerprint + '.json')
    if cache.exists():
        raw = json.loads(cache.read_text(encoding='utf-8'))
        if 'activityStart' not in raw:
            audio = subprocess.run([ffmpeg, '-nostdin', '-v', 'error', '-i', str(source), '-vn', '-ac', '1', '-ar', '22050', '-f', 'f32le', 'pipe:1'],capture_output=True,check=True)
            raw['activityStart'], raw['activityEnd'] = activity_bounds(np.frombuffer(audio.stdout, dtype='<f4'), 22050)
            write_json(cache, raw)
        raw['cached'] = True
        status('Using saved full-song analysis.')
        return recover(raw, timing, meter)
    status('Decoding the complete source song…')
    with tempfile.TemporaryDirectory(prefix='beatmarker-') as tmp:
        wav = Path(tmp) / 'audio.wav'
        proc = subprocess.run([ffmpeg, '-nostdin', '-hide_banner', '-loglevel', 'error', '-y', '-i', str(source), '-vn', '-ac', '1', '-ar', '22050', '-c:a', 'pcm_s16le', str(wav)],capture_output=True,text=True)
        if proc.returncode:
            raise RuntimeError('Cannot decode this audio: ' + proc.stderr[-1500:])
        signal, sr = sf.read(str(wav), dtype='float32')
    if len(signal) < sr:
        raise ValueError('Choose audio longer than one second.')
    if float(np.max(np.abs(signal))) < 0.00001:
        raise ValueError('The source audio is silent.')
    status('Finding beats and bar starts…')
    tracker = Audio2Beats(checkpoint_path=str(checkpoint), device='cpu', dbn=False)
    beats, downbeats = tracker(signal, sr)
    intervals = np.diff(beats)
    intervals = intervals[intervals > 0]
    rows = beat_labels(beats, downbeats)
    first, last = activity_bounds(signal, sr)
    raw = {'schema':1,'engine':'Beat This! final0','source':str(source),'fingerprint':fingerprint,'duration':len(signal)/sr,'activityStart':first,'activityEnd':last,'medianBpm':float(60/np.median(intervals)) if len(intervals) else None,'beats':rows,'downbeatCount':int(len(downbeats)),'cached':False,'createdAt':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())}
    write_json(cache,raw)
    return recover(raw,timing,meter)

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',required=True)
    parser.add_argument('--output',required=True)
    parser.add_argument('--ffmpeg',required=True)
    parser.add_argument('--timing',choices=['auto','detected','steady'],default='auto')
    parser.add_argument('--meter',choices=['auto','2','3','4'],default='auto')
    args=parser.parse_args()
    try:
        result=analyse(args.source,args.ffmpeg,args.timing,args.meter)
        write_json(Path(args.output),result)
        print(json.dumps({'ok':True,'output':args.output,'beats':len(result['beats'])}),flush=True)
    except Exception as exc:
        status(str(exc))
        print(json.dumps({'ok':False,'error':str(exc)}),flush=True)
        sys.exit(1)
