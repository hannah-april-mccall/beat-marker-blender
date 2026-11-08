"""Build a platform-specific, offline Blender extension from this checkout."""
import argparse
from datetime import datetime, timezone
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = tomllib.loads((ROOT / 'beat_marker/blender_manifest.toml').read_text())['version']


def platform_key():
    architecture = {'x86_64': 'x64', 'amd64': 'x64', 'aarch64': 'arm64'}.get(platform.machine().lower(), platform.machine().lower())
    return {'darwin': 'macos', 'win32': 'windows', 'linux': 'linux'}[sys.platform] + '-' + architecture


def licenses(destination):
    destination.mkdir(parents=True, exist_ok=True)
    inventory = []
    for distribution in metadata.distributions():
        name = distribution.metadata.get('Name', 'unknown')
        version = distribution.version
        inventory.append({'name': name, 'version': version, 'license': distribution.metadata.get('License-Expression') or distribution.metadata.get('License', ''), 'source': distribution.metadata.get('Home-page', '')})
        for relative in distribution.files or []:
            if any('license' in part.lower() or 'copying' in part.lower() or 'notice' in part.lower() for part in relative.parts):
                path = Path(distribution.locate_file(relative))
                if path.is_file():
                    target = destination / name / str(relative).replace('../', '')
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(path, target)
    (destination / 'python-packages.json').write_text(json.dumps(sorted(inventory, key=lambda r: r['name'].lower()), indent=2) + '\n')
    # Python's redistributed runtime license is outside package metadata.
    for candidate in (Path(sys.base_prefix) / 'LICENSE.txt', Path(sys.base_prefix) / 'LICENSE'):
        if candidate.is_file():
            shutil.copy2(candidate, destination / 'PYTHON-LICENSE.txt')
            break


def build(skip_freeze=False):
    key = platform_key()
    stage = ROOT / '.build/stage' / key / 'beat_marker'
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    for source in (ROOT / 'beat_marker').iterdir():
        if source.is_file() and source.suffix in ('.py', '.toml') or source.is_file() and source.name == 'LICENSE':
            shutil.copy2(source, stage / source.name)
    manifest = stage / 'blender_manifest.toml'
    blender_platform = {'macos-arm64': 'macos-arm64', 'macos-x64': 'macos-x64', 'windows-x64': 'windows-x64', 'linux-x64': 'linux-x64'}[key]
    manifest.write_text(manifest.read_text().replace('[permissions]', f'platforms = ["{blender_platform}"]\n\n[permissions]'))
    runtime = stage / 'runtime'
    runtime.mkdir()
    if not skip_freeze:
        command = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onedir', '--name', 'beat-marker-engine',
                   '--distpath', str(ROOT / '.build/frozen'), '--workpath', str(ROOT / '.build/pyinstaller'),
                   '--specpath', str(ROOT / '.build'), '--paths', str(ROOT / 'engine')]
        for name in ('beat_this', 'rotary_embedding_torch', 'einops', 'soxr', 'soundfile'):
            command += ['--collect-all', name]
        for name in ('beat-this', 'torch', 'torchaudio', 'einops', 'rotary-embedding-torch'):
            command += ['--copy-metadata', name]
        command += [str(ROOT / 'engine/worker.py')]
        environment = dict(os.environ, PYINSTALLER_CONFIG_DIR=str(ROOT / '.build/pyinstaller-cache'))
        subprocess.run(command, check=True, cwd=ROOT, env=environment)
    shutil.copytree(ROOT / '.build/frozen/beat-marker-engine', runtime / 'engine', symlinks=False)
    suffix = '.exe' if os.name == 'nt' else ''
    (runtime / 'bin').mkdir()
    for name in ('ffmpeg', 'ffprobe'):
        shutil.copy2(ROOT / '.build/native/bin' / (name + suffix), runtime / 'bin' / (name + suffix))
    model = runtime / 'models/hub/checkpoints/beat_this-final0.ckpt'
    model.parent.mkdir(parents=True)
    shutil.copy2(ROOT / '.build/assets/beat_this-final0.ckpt', model)
    license_dir = runtime / 'licenses'
    licenses(license_dir)
    ffmpeg_licenses = license_dir / 'FFmpeg'
    ffmpeg_licenses.mkdir()
    for name in ('COPYING.LGPLv2.1', 'LICENSE.md', 'configure-flags.txt'):
        shutil.copy2(ROOT / '.build/native' / name, ffmpeg_licenses / name)
    # Corresponding source and the exact configuration travel with every binary.
    shutil.copy2(ROOT / '.build/assets/ffmpeg-7.1.2.tar.xz', ffmpeg_licenses / 'ffmpeg-7.1.2.tar.xz')
    shutil.copy2(ROOT / 'scripts/build_ffmpeg.sh', ffmpeg_licenses / 'build_ffmpeg.sh')
    shutil.copy2(ROOT / 'engine/BEAT-THIS-LICENSE.txt', license_dir / 'BEAT-THIS-LICENSE.txt')
    shutil.copy2(ROOT / 'LICENSE', license_dir / 'BEAT-MARKER-LICENSE.txt')
    shutil.copy2(ROOT / 'THIRD_PARTY_NOTICES.md', license_dir / 'THIRD_PARTY_NOTICES.md')
    identity = hashlib.sha256((key + VERSION).encode())
    for path in sorted(runtime.rglob('*')):
        if path.is_file():
            identity.update(str(path.relative_to(runtime)).encode())
            with path.open('rb') as handle:
                identity.update(hashlib.file_digest(handle, 'sha256').digest())
    build_id = identity.hexdigest()[:16]
    info = {'version': VERSION, 'platform': key, 'build_id': build_id,
            'built_utc': datetime.now(timezone.utc).isoformat(),
            'engine': 'engine/beat-marker-engine' + suffix, 'ffmpeg': 'bin/ffmpeg' + suffix,
            'ffprobe': 'bin/ffprobe' + suffix, 'model': str(model.relative_to(runtime)),
            'python': sys.version.split()[0]}
    (runtime / 'runtime.json').write_text(json.dumps(info, indent=2) + '\n')
    (ROOT / '.build/current-runtime.txt').write_text(str(runtime))
    subprocess.run([sys.executable, str(ROOT / 'scripts/smoke_test.py'), str(runtime)], check=True, cwd=ROOT)
    destination = ROOT / 'dist'
    destination.mkdir(exist_ok=True)
    archive = destination / f'beat-marker-blender-{VERSION}-{key}.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as package:
        for source in sorted(stage.rglob('*')):
            if source.is_file():
                package.write(source, source.relative_to(stage.parent))
    sha = hashlib.file_digest(archive.open('rb'), 'sha256').hexdigest()
    archive.with_suffix('.zip.sha256').write_text(sha + '  ' + archive.name + '\n')
    print('Built and tested: ' + str(archive), flush=True)
    return archive


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--skip-freeze', action='store_true')
    build(parser.parse_args().skip_freeze)
