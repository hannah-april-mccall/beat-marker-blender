"""Execute the frozen worker without system Python, FFmpeg or Adobe paths."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def main(root):
    root = Path(root).resolve()
    info = json.loads((root / 'runtime.json').read_text())
    environment = {key: value for key, value in os.environ.items() if key not in ('PYTHONHOME', 'PYTHONPATH', 'LD_LIBRARY_PATH', 'DYLD_LIBRARY_PATH', 'DYLD_FRAMEWORK_PATH')}
    environment['PATH'] = str(Path(os.environ.get('SYSTEMROOT', '/usr')) / ('System32' if os.name == 'nt' else 'bin'))
    with tempfile.TemporaryDirectory(prefix='Beat Marker clean test ') as folder:
        workspace = Path(folder)
        # A symlink-free copy tests relocatability, including paths containing spaces.
        copied = workspace / 'relocated engine'
        shutil.copytree(root, copied, symlinks=False)
        if os.name != 'nt':
            for name in ('engine', 'ffmpeg', 'ffprobe'):
                path = copied / info[name]
                path.chmod(path.stat().st_mode | 0o700)
        executable = copied / info['engine']
        version = json.loads(subprocess.check_output([str(executable), '--version'], env=environment, text=True))
        assert version['version'] == info['version'] and version['frozen']
        result = subprocess.run([str(executable), '--resources', str(copied), '--data-dir', str(workspace / 'user data'), '--self-test'], env=environment, capture_output=True, text=True, timeout=300)
        if result.returncode:
            raise RuntimeError(result.stdout + '\n' + result.stderr)
        receipt = json.loads(result.stdout.strip().splitlines()[-1])
        assert receipt['ok'] and receipt['offline'] and receipt['beats'] >= 4
        assert list((workspace / 'user data/cache').glob('*.json'))
        print(json.dumps({'smoke_test': 'passed', 'platform': info['platform'], 'worker': receipt}), flush=True)


if __name__ == '__main__':
    main(sys.argv[1])
