#!/usr/bin/env python3
"""Bounded ThreadSanitizer proof; invoke through the audio guard."""
import json
from pathlib import Path
import subprocess
import sys
sys.dont_write_bytecode = True
from build import HERE, SCRATCH, run

dest = SCRATCH / 'stress'
dest.mkdir(exist_ok=True)
sdk = subprocess.check_output(['xcrun', '--sdk', 'macosx', '--show-sdk-path'], text=True).strip()
common = ['clang++', '-std=c++17', '-O1', '-gline-tables-only', '-fsanitize=thread',
          '-pthread', '-target', 'arm64-apple-macos26.0', '-isysroot', sdk,
          '-idirafter', str(SCRATCH / 'sources/ffmpeg-8.0'),
          '-I' + str(SCRATCH / 'macosx'), '-I' + str(SCRATCH / 'sources'),
          '-Wno-deprecated-declarations']
run(common + ['-c', HERE/'backend.mm', '-o', dest/'backend.o'], log=dest/'build.log')
run(common + [HERE/'stress.cpp', dest/'backend.o', '-o', dest/'stress',
    *[SCRATCH/'macosx'/f'{name}/{name}.a' for name in ['libavformat','libavcodec','libswresample','libavutil']],
    '-framework','CoreFoundation','-framework','CoreAudio','-framework','AudioToolbox'], log=dest/'build.log')
run([dest/'stress', SCRATCH/'fixtures/tone-a.m4a'], log=dest/'results.log')
