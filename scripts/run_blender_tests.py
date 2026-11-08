"""Run portable regression fixtures against an isolated Blender process."""
import argparse
import hashlib
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from make_fixtures import make


def download_blender():
    version = '5.2.3'
    system = {'darwin': 'macos-arm64.dmg', 'win32': 'windows-x64.zip', 'linux': 'linux-x64.tar.xz'}[sys.platform]
    name = 'blender-' + version + '-' + system
    base = 'https://download.blender.org/release/Blender5.2/'
    destination = ROOT / '.build/blender-download'
    destination.mkdir(parents=True, exist_ok=True)
    checksums = urllib.request.urlopen(base + 'blender-' + version + '.sha256', timeout=120).read().decode()
    expected = next(line.split()[0] for line in checksums.splitlines() if line.split()[-1].lstrip('*') == name)
    archive = destination / name
    if not archive.is_file():
        with urllib.request.urlopen(base + name, timeout=180) as response, archive.open('wb') as out:
            shutil.copyfileobj(response, out)
    with archive.open('rb') as handle:
        assert hashlib.file_digest(handle, 'sha256').hexdigest() == expected, 'Blender archive checksum mismatch'
    if sys.platform == 'win32':
        with zipfile.ZipFile(archive) as package:
            package.extractall(destination)
        return next(destination.glob('blender-*/blender.exe'))
    if sys.platform == 'darwin':
        mount = destination / 'mount'
        mount.mkdir(exist_ok=True)
        subprocess.run(['hdiutil', 'attach', '-nobrowse', '-readonly', '-mountpoint', str(mount), str(archive)], check=True)
        try:
            app = destination / 'Blender.app'
            if not app.exists():
                shutil.copytree(mount / 'Blender.app', app, symlinks=True)
        finally:
            subprocess.run(['hdiutil', 'detach', str(mount)], check=True)
        return app / 'Contents/MacOS/Blender'
    with tarfile.open(archive) as package:
        package.extractall(destination, filter='data')
    return next(destination.glob('blender-*/blender'))


def main(blender=None):
    executable = Path(blender).resolve() if blender else download_blender()
    suffix = '.exe' if os.name == 'nt' else ''
    make(ROOT / '.build/native/bin' / ('ffmpeg' + suffix))
    environment = dict(os.environ, BLENDER_USER_CONFIG=str(ROOT / '.build/blender-test-config'))
    for script in ('blender_markers.py', 'blender_alignment.py', 'blender_engine.py'):
        subprocess.run([str(executable), '--background', '--factory-startup', '--python-exit-code', '1', '--python', str(ROOT / 'tests' / script)], env=environment, cwd=ROOT, check=True, timeout=600)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--blender')
    main(parser.parse_args().blender)
