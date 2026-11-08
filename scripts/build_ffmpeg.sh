#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p .build/ffmpeg .build/native
prefix="$(cd .build/native && pwd)"
if [[ ! -d .build/ffmpeg/ffmpeg-7.1.2 ]]; then
  tar -xf .build/assets/ffmpeg-7.1.2.tar.xz -C .build/ffmpeg
fi
source_dir="$(cd .build/ffmpeg/ffmpeg-7.1.2 && pwd)"
mkdir -p .build/ffmpeg/build
cd .build/ffmpeg/build
flags=(
  "--prefix=$prefix" --disable-everything --disable-autodetect --disable-doc
  --disable-debug --disable-shared --enable-static --disable-x86asm
  --disable-network --disable-avdevice --enable-ffmpeg --enable-ffprobe
  --enable-protocol=file,pipe
  --enable-demuxer=aac,aiff,ape,asf,avi,caf,flac,matroska,mov,mp3,mpegts,ogg,wav,wv,rawvideo
  --enable-decoder=aac,alac,ape,flac,mp1float,mp2float,mp3float,opus,vorbis,wmav1,wmav2,wmapro,wmalossless,wavpack,pcm_s16le,pcm_s16be,pcm_s24le,pcm_s24be,pcm_s32le,pcm_s32be,pcm_f32le,pcm_f32be,pcm_f64le,pcm_f64be,pcm_u8,pcm_s8,adpcm_ima_wav,h264,hevc,mpeg4,mpeg2video,prores,vp8,vp9,rawvideo
  --enable-parser=aac,aac_latm,flac,mpegaudio,opus,vorbis,h264,hevc,mpeg4video
  --enable-encoder=pcm_s16le,pcm_f32le,pcm_s32le,mpeg4
  --enable-muxer=wav,f32le,s16le,avi,mov,mp4,null
  --enable-filter=aresample,anull,aformat,format,scale
  --enable-swresample --enable-swscale
)
case "$(uname -s)" in
  MINGW*|MSYS*) flags+=(--target-os=mingw32 --enable-w32threads --disable-pthreads '--extra-ldflags=-static -static-libgcc') ;;
esac
"$source_dir/configure" "${flags[@]}"
make -j"${BM_BUILD_JOBS:-2}"
make install
cp ffbuild/config.log "$prefix/config.log"
printf '%s\n' "${flags[@]}" > "$prefix/configure-flags.txt"
cp "$source_dir/COPYING.LGPLv2.1" "$prefix/COPYING.LGPLv2.1"
cp "$source_dir/LICENSE.md" "$prefix/LICENSE.md"
