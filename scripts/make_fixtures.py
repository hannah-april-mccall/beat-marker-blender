"""Generate small, copyright-free Blender regression fixtures."""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'engine'))
from worker import make_reference


def make(ffmpeg):
    folder = ROOT / '.build/integration'
    folder.mkdir(parents=True, exist_ok=True)
    make_reference(folder / 'reference.wav', seconds=32)
    raw = folder / 'source.rgb'
    with raw.open('wb') as handle:
        for frame in range(500):
            pixel = bytes((frame % 256, (frame * 3) % 256, (frame * 7) % 256))
            handle.write(pixel * (160 * 90))
    subprocess.run([str(ffmpeg), '-nostdin', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', '160x90', '-r', '25', '-i', str(raw), '-i', str(folder / 'reference.wav'), '-t', '20', '-c:v', 'mpeg4', '-q:v', '5', '-c:a', 'pcm_s16le', str(folder / 'source.avi')], check=True)
    raw.unlink()
    return folder


if __name__ == '__main__':
    print(make(sys.argv[1]))
