"""Fetch only public, versioned build inputs and verify their SHA-256 digests."""
import hashlib
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / '.build/assets'
INPUTS = {
    'ffmpeg-7.1.2.tar.xz': (
        'https://ffmpeg.org/releases/ffmpeg-7.1.2.tar.xz',
        '089bc60fb59d6aecc5d994ff530fd0dcb3ee39aa55867849a2bbc4e555f9c304'),
    'beat_this-final0.ckpt': (
        'https://cloud.cp.jku.at/public.php/dav/files/7ik4RrBKTS273gp/final0.ckpt',
        '8c328b45f59d8dd3dff219253ff6a8d6482be57d0133a29140e2febbf8eb8331'),
}


def digest(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def main():
    ASSETS.mkdir(parents=True, exist_ok=True)
    for filename, (url, expected) in INPUTS.items():
        path = ASSETS / filename
        if not path.is_file() or digest(path) != expected:
            temporary = path.with_suffix(path.suffix + '.part')
            with urllib.request.urlopen(url, timeout=120) as response, temporary.open('wb') as out:
                while chunk := response.read(1024 * 1024):
                    out.write(chunk)
            if digest(temporary) != expected:
                raise RuntimeError('Downloaded build input failed verification: ' + filename)
            temporary.replace(path)
        print('Verified build input: ' + filename, flush=True)


if __name__ == '__main__':
    main()
