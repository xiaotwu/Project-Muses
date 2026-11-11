#!/usr/bin/env python3
"""P0-only native audio proof. Invoke through ../run_guarded.py --allocation audio.

No package installation; all dependencies/builds/test media stay in scratch.
The fixture generator is a developer tool and is never linked into the proof.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tarfile
import urllib.request

HERE = Path(__file__).resolve().parent
SCRATCH = Path('/Users/xiaotwu/.muses/tmp/p0-20261110-01/audio')
FFMPEG_SHA = 'b2751fccb6cc4c77708113cd78b561059b6fa904b24162fa0be2d60273d27b8e'

def bootstrap():
    lock = json.loads((HERE / 'source-lock.json').read_text())
    (SCRATCH / 'sources').mkdir(parents=True, exist_ok=True)
    for name, target in [('ffmpeg', SCRATCH / 'ffmpeg-8.0.tar.xz'),
                         ('miniaudio', SCRATCH / 'sources/miniaudio.h')]:
        item = lock[name]
        if not target.exists():
            partial = target.with_name(target.name + '.partial')
            urllib.request.urlretrieve(item['url'], partial)
            assert hashlib.sha256(partial.read_bytes()).hexdigest() == item['sha256']
            partial.replace(target)
        assert hashlib.sha256(target.read_bytes()).hexdigest() == item['sha256']
    if not (SCRATCH / 'sources/ffmpeg-8.0').exists():
        with tarfile.open(SCRATCH / 'ffmpeg-8.0.tar.xz') as archive:
            archive.extractall(SCRATCH / 'sources', filter='data')

def run(args, cwd=None, log=None):
    print('+', ' '.join(map(str, args)), flush=True)
    if log:
        with open(log, 'a') as output:
            output.write('\nCOMMAND ' + json.dumps(list(map(str, args))) + '\n')
            output.flush()
            subprocess.run(list(map(str, args)), cwd=cwd, stdout=output,
                           stderr=subprocess.STDOUT, check=True)
    else:
        subprocess.run(list(map(str, args)), cwd=cwd, check=True)

def build(platform):
    source = SCRATCH / 'sources' / 'ffmpeg-8.0'
    assert hashlib.sha256((SCRATCH / 'ffmpeg-8.0.tar.xz').read_bytes()).hexdigest() == FFMPEG_SHA
    lock = json.loads((HERE / 'source-lock.json').read_text())
    assert hashlib.sha256((SCRATCH / 'sources/miniaudio.h').read_bytes()).hexdigest() == lock['miniaudio']['sha256']
    dest = SCRATCH / platform
    dest.mkdir(exist_ok=True)
    sdk = subprocess.check_output(['xcrun', '--sdk', platform, '--show-sdk-path'], text=True).strip()
    triple = 'arm64-apple-macos26.0' if platform == 'macosx' else 'arm64-apple-ios17.0'
    flags = f'-target {triple} -isysroot {sdk}'
    config = [source / 'configure', '--disable-everything', '--disable-autodetect',
              '--disable-gpl', '--disable-version3', '--disable-nonfree',
              '--disable-programs', '--disable-doc', '--disable-debug',
              '--disable-avdevice', '--disable-avfilter', '--disable-swscale',
              '--enable-avcodec', '--enable-avformat', '--enable-avutil',
              '--enable-swresample', '--enable-decoder=aac,opus',
              '--enable-parser=aac,opus', '--enable-demuxer=mov,matroska',
              '--enable-protocol=file,http,tcp', '--enable-network',
              '--enable-pthreads', '--enable-static', '--disable-shared',
              '--cc=clang', '--cxx=clang++', '--arch=aarch64', '--target-os=darwin',
              '--enable-cross-compile', f'--extra-cflags={flags}',
              f'--extra-ldflags={flags}']
    (dest / 'configure-command.json').write_text(json.dumps(list(map(str, config)), indent=2) + '\n')
    if not (dest / 'config.h').exists():
        run(config, cwd=dest, log=dest / 'configure.log')
    run(['make', '-j4'], cwd=dest, log=dest / 'build.log')
    common = ['clang++', '-std=c++17', '-O2', '-pthread', '-target', triple,
              '-isysroot', sdk, '-idirafter', str(source), '-I' + str(dest),
              '-I' + str(SCRATCH / 'sources'), '-Wno-deprecated-declarations']
    run(common + ['-c', HERE / 'backend.mm', '-o', dest / 'miniaudio-backend.o'],
        log=dest / 'probe-build.log')
    if platform == 'macosx':
        run(common + [HERE / 'probe.cpp', dest / 'miniaudio-backend.o', '-o', dest / 'audio-probe',
            dest / 'libavformat/libavformat.a', dest / 'libavcodec/libavcodec.a',
            dest / 'libswresample/libswresample.a', dest / 'libavutil/libavutil.a',
            '-framework', 'CoreFoundation', '-framework', 'CoreAudio',
            '-framework', 'AudioToolbox'], log=dest / 'probe-build.log')
    else:
        run(common + ['-DP0_LIBRARY_ONLY', '-c', HERE / 'probe.cpp',
                      '-o', dest / 'audio-probe.o'], log=dest / 'probe-build.log')

def fixtures():
    output = SCRATCH / 'fixtures'
    output.mkdir(exist_ok=True)
    tool = '/opt/homebrew/bin/ffmpeg'
    run([tool, '-version'], log=output / 'generator-version.txt')
    for name, freq, codec, extra in [('tone-a.m4a', 440, 'aac', ['-movflags', '+faststart']),
                                    ('tone-b.webm', 660, 'libopus', [])]:
        run([tool, '-v', 'error', '-nostdin', '-y', '-f', 'lavfi', '-i',
             f'sine=frequency={freq}:sample_rate=48000:duration=4', '-ac', '2',
             '-c:a', codec, '-b:a', '96k', *extra, output / name])
    manifest = {p.name: {'bytes': p.stat().st_size, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
                for p in output.iterdir() if p.suffix in ['.m4a', '.webm']}
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['bootstrap', 'macosx', 'iphoneos', 'fixtures'])
    options = parser.parse_args()
    if options.action == 'bootstrap':
        bootstrap()
    elif options.action == 'fixtures':
        fixtures()
    else:
        build(options.action)
