# Building Beat Marker

## Layout

- `beat_marker/`: Blender extension source; no heavy imports in Blender.
- `engine/`: offline background worker, original full-source analysis and musical recovery.
- `scripts/`: verified asset downloads, native tools, frozen worker and packaging.
- `tests/`: platform-independent runtime checks and Blender integration checks.
- `.github/workflows/`: platform builds and private/public GitHub releases.

The worker runs in a separate process and returns JSON. The add-on continues to own source/timeline mapping, markers, edit planning and native Undo. It never imports PyTorch into Blender.

## Local build

Use Python 3.12, a native C toolchain, Bash and Make. On Windows use MSYS2 UCRT64 for FFmpeg; run Python packaging steps in the normal Windows Python environment. Build on the target operating system and processor architecture.

```sh
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install torch==2.6.0 torchaudio==2.6.0
python -m pip install -r engine/requirements.txt pyinstaller==6.16.0
python scripts/fetch_assets.py
bash scripts/build_ffmpeg.sh
python -m unittest discover -s tests -p 'test_*.py'
python scripts/build.py
```

For Windows/Linux, install PyTorch from `https://download.pytorch.org/whl/cpu` to avoid a GPU/CUDA distribution. Mac releases target Apple silicon, matching Blender 5.2's official Mac build.

The built extension ZIP and its SHA-256 file are written to `dist/`. The worker's own Python and libraries are frozen into the package; end users do not run these build commands or install Python.

## Build checks

Each package is copied to a new directory containing spaces. The frozen executable runs with the system/Adobe development paths removed, verifies the model, analyses generated 120 BPM audio, checks finite timestamps and reuses the cached result. FFmpeg/FFprobe are executed from the package. Platform-specific results are retained with the release build.

The Blender integration test runs in a separate background process with factory settings, generated media and isolated preferences. It checks source offsets, marker selection, removal ownership and clip alignment. It does not read or modify an existing project.

## Supported targets

| Package | Target |
|---|---|
| `macos-arm64` | Apple silicon; build minimum deployment target recorded by the native binaries |
| `windows-x64` | Windows x64; Python 3.12 and CPU PyTorch |
| `linux-x64` | glibc 2.35+, built on Ubuntu 22.04 |

Binary builds must be tested on their native runners before treating that platform as verified. Native engine checks do not establish interactive Blender UI compatibility on every operating system. macOS packages use PyInstaller's ad-hoc signing; Apple Developer ID signing/notarisation and Windows publisher signing are not configured in this initial GitHub build.

## Persistent files

The add-on stores caches in `bpy.utils.extension_path_user(__package__)`, outside the installed code. If an installer discards executable bits, it prepares a runnable copy of the immutable runtime in that user directory. No files are installed into Blender's Python environment or Adobe's extension directories. There is no runtime dependency download.

## Releasing

The release workflow builds the platform packages, runs their checks and attaches successful packages to a prerelease tagged with the manifest version. The repository visibility controls who can access those releases. The workflow uses the repository-scoped GitHub Actions token; no personal access token is stored.

Keep large generated binaries/models out of Git history. Public build inputs are checksum-verified. Changing dependency versions requires a fresh frozen-engine and Blender integration check.
