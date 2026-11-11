#!/usr/bin/env python3
"""Bounded sanitizer-preserving capture. Invoke through run_guarded.py."""
import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

scratch = Path('/Users/xiaotwu/.muses/tmp/p0-20261110-01/source')
mode = sys.argv[1] if len(sys.argv) > 1 else 'catalog'
if mode not in {'catalog', 'media', 'media_direct', 'media_direct_next', 'range_probe', 'hls_probe', 'background_first', 'background_next', 'cancel', 'interrupt', 'memory', 'sandbox'}:
    raise SystemExit('unknown mode')
started = time.monotonic()
result = subprocess.run([str(scratch / 'build/source-proof'), str(scratch / 'build/probe.bundle.js'), mode], capture_output=True, timeout=100)
output = result.stdout.decode('utf-8', errors='replace')
if len(output) > 65536 or b'googlevideo.com' in result.stdout or b'visitorData' in result.stdout or b'signatureCipher' in result.stdout:
    raise SystemExit('unexpected receipt data refused')
stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
receipt = {'mode':mode, 'timestamp':stamp, 'exit_code':result.returncode, 'elapsed_seconds':time.monotonic()-started, 'stdout':output, 'stderr_bytes':len(result.stderr), 'bundle_sha256':hashlib.sha256((scratch / 'build/probe.bundle.js').read_bytes()).hexdigest(), 'host_sha256':hashlib.sha256((scratch / 'build/source-proof').read_bytes()).hexdigest()}
path = scratch / 'results' / f'{stamp}-{mode}.json'
path.write_text(json.dumps(receipt, indent=2) + '\n')
print(output, end='')
print('Sanitized source receipt:', path)
raise SystemExit(result.returncode)
