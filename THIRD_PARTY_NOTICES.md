# Third-party notices

## Beat This!

Beat This! 1.1.0 and its published `final0` checkpoint are distributed by the authors under MIT.

- Copyright © 2024 Institute of Computational Perception, JKU Linz, Austria.
- Source: https://github.com/CPJKU/beat_this
- Model: https://cloud.cp.jku.at/public.php/dav/files/7ik4RrBKTS273gp/final0.ckpt
- Checkpoint SHA-256: `8c328b45f59d8dd3dff219253ff6a8d6482be57d0133a29140e2febbf8eb8331`
- Full licence: `engine/BEAT-THIS-LICENSE.txt`, also copied into each runtime's licences folder.

The authors' training recordings have their own rights and licences. No training recordings are included in this project.

## Python and Python packages

Release runtimes contain Python, PyTorch, TorchAudio, NumPy, SoundFile/libsndfile, einops, rotary-embedding-torch, soxr and their dependencies. Each retains its original copyright and licence. Each release includes the detected licence files and an exact package/version inventory in `runtime/licenses/`. PyInstaller's bootloader is distributed under its GPL exception, permitting redistribution of the frozen application under its own licence.

Package sources are available from their respective PyPI project pages and upstream repositories. Beat Marker's complete build scripts and version constraints are included in this repository. No CUDA runtime is required; Windows and Linux use the CPU PyTorch wheels.

## FFmpeg and FFprobe

This project builds FFmpeg **7.1.2** from the official source without GPL/nonfree components, external codec libraries or network protocols. The result is licensed under **LGPL v2.1 or later**. It is used as a separate executable, not linked into Blender.

- Project and copyright details: https://ffmpeg.org/
- Source: https://ffmpeg.org/releases/ffmpeg-7.1.2.tar.xz
- Source SHA-256: `089bc60fb59d6aecc5d994ff530fd0dcb3ee39aa55867849a2bbc4e555f9c304`
- Every runtime includes the corresponding source archive, `COPYING.LGPLv2.1`, `LICENSE.md`, the build script and exact configure flags in `runtime/licenses/FFmpeg/`.
- No patches are applied. You may rebuild and replace the `ffmpeg` and `ffprobe` executables in the runtime's `bin` folder.

## Example media

Automated checks generate their own audio/video fixtures. Songs, downloaded stock clips, personal media, local machine configuration and private project files are not part of this repository or its release packages.
