"""Resolve the offline runtime shipped inside a platform-specific release."""
import json
import os
from pathlib import Path
import platform
import shutil
import tempfile

VERSION = '0.4.0'


def platform_key():
    machine = platform.machine().lower()
    architecture = {'amd64': 'x64', 'x86_64': 'x64', 'aarch64': 'arm64'}.get(machine, machine)
    system = {'Darwin': 'macos', 'Windows': 'windows', 'Linux': 'linux'}.get(platform.system())
    if not system:
        raise ValueError('This operating system is not supported by the bundled engine.')
    return system + '-' + architecture


def validate(root, expected_platform=None):
    root = Path(root).resolve()
    manifest = root / 'runtime.json'
    if not manifest.is_file():
        raise ValueError('Install the complete Beat Marker release ZIP for your computer. The source-code ZIP has no analysis engine.')
    data = json.loads(manifest.read_text(encoding='utf-8'))
    if data.get('version') != VERSION:
        raise ValueError('The bundled engine version does not match this add-on. Reinstall the complete release ZIP.')
    if data.get('platform') != (expected_platform or platform_key()):
        raise ValueError('This engine is for ' + str(data.get('platform')) + '. Install the release for ' + (expected_platform or platform_key()) + '.')
    paths = {}
    for name in ('engine', 'ffmpeg', 'ffprobe', 'model'):
        path = (root / data[name]).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError('The bundled engine is incomplete: ' + name + '. Reinstall the complete release ZIP.')
        paths[name] = path
    return data, paths


def prepare(state_dir, bundled_root=None):
    root = Path(bundled_root) if bundled_root else Path(__file__).resolve().parent / 'runtime'
    data, paths = validate(root)
    if os.name == 'nt' or all(os.access(paths[name], os.X_OK) for name in ('engine', 'ffmpeg', 'ffprobe')):
        return root, paths
    # Some ZIP installers discard executable bits. Keep the installation read-only:
    # prepare a runnable copy in the extension's persistent user directory instead.
    target = Path(state_dir) / 'runtimes' / (data['version'] + '-' + data['platform'] + '-' + data['build_id'])
    if not target.is_dir():
        target.parent.mkdir(parents=True, exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix='.runtime-', dir=target.parent))
        try:
            shutil.copytree(root, stage, dirs_exist_ok=True, symlinks=False)
            _, copied = validate(stage)
            for name in ('engine', 'ffmpeg', 'ffprobe'):
                copied[name].chmod(copied[name].stat().st_mode | 0o700)
            try:
                stage.rename(target)
            except FileExistsError:
                pass  # Another Blender instance prepared the same immutable build.
        finally:
            if stage.exists():
                shutil.rmtree(stage)
    _, paths = validate(target)
    if not all(os.access(paths[name], os.X_OK) for name in ('engine', 'ffmpeg', 'ffprobe')):
        raise ValueError('The engine cannot run from Blender’s user-data folder. Check that the folder allows executable files.')
    return target, paths


def process_environment():
    # A worker must load its own native libraries, rather than Blender's copies.
    environment = dict(os.environ)
    for name in ('PYTHONHOME', 'PYTHONPATH', 'LD_LIBRARY_PATH', 'DYLD_LIBRARY_PATH', 'DYLD_FRAMEWORK_PATH'):
        environment.pop(name, None)
    return environment
