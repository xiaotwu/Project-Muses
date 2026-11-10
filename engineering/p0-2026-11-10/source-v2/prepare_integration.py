#!/usr/bin/env python3
"""Restore only pinned public build dependencies into bounded active scratch."""
import hashlib
import json
from pathlib import Path
import shutil

SOURCE = Path(__file__).resolve().parent
SCRATCH = Path('/Users/xiaotwu/.muses/tmp/p0-20261110-01/source/v2-integration')
OLD = Path('/Users/xiaotwu/.Trash/Muses-P0-20261110-01/source--deps')
SCRATCH.mkdir(parents=True, exist_ok=True)
for name in ['tmp', 'build', 'results', 'media']:
    (SCRATCH / name).mkdir(exist_ok=True)
lock = SOURCE.parent / 'source/package-lock.json'
assert (OLD / 'package-lock.json').read_bytes() == lock.read_bytes()
destination = SCRATCH / 'deps'
if not destination.exists():
    shutil.copytree(OLD, destination, symlinks=True)
assert (destination / 'package-lock.json').read_bytes() == lock.read_bytes()
manifest = {'origin': 'read-only retained public pinned dependencies',
            'package_lock_sha256': hashlib.sha256(lock.read_bytes()).hexdigest(),
            'runtime_subprocess_dependency': False,
            'esbuild_sha256': hashlib.sha256((destination / 'node_modules/@esbuild/darwin-arm64/bin/esbuild').read_bytes()).hexdigest()}
(SCRATCH / 'dependency-restore.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps(manifest))
