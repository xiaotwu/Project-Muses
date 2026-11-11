#!/usr/bin/env python3
"""Bounded live probe with byte-verified build and sanitized immutable receipts."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
SCRATCH = Path('/Users/xiaotwu/.muses/tmp/p0-20261110-01/source/v2-integration')
if len(sys.argv) not in [3, 4]:
    raise SystemExit('usage: run_integration.py MODE CLIENT [aac|opus]')
mode, client = sys.argv[1:3]
codec = sys.argv[3] if len(sys.argv) == 4 else 'aac'
if mode not in ['capabilities', 'resolve_first', 'resolve_next', 'direct_first', 'direct_next'] or client not in ['IOS', 'VISIONOS', 'TV', 'TV_SAMSUNG', 'WEB', 'WEB_EMBEDDED'] or codec not in ['aac', 'opus']:
    raise SystemExit('unknown fixed probe option')
build = json.loads((SCRATCH / 'build/success.json').read_text())
for path, expected in build['source_sha256'].items():
    assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == expected, 'stale source build refused'
binary = SCRATCH / 'build/source-v2'
bundle = SCRATCH / 'build/probe.bundle.js'
assert hashlib.sha256(binary.read_bytes()).hexdigest() == build['binary_sha256'], 'stale binary refused'
assert hashlib.sha256(bundle.read_bytes()).hexdigest() == build['bundle_sha256'], 'stale bundle refused'
begin = time.monotonic()
deadline_seconds = 180
rss_limit = 256 * 1024 * 1024
process = subprocess.Popen([str(binary), str(bundle), mode, client, codec],
    stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True,
    env=dict(os.environ, TMPDIR=str(SCRATCH / 'tmp'), OS_ACTIVITY_MODE='disable'))
peak = 0
reason = None
while process.poll() is None:
    current = subprocess.run(['ps', '-o', 'rss=', '-p', str(process.pid)], capture_output=True, text=True).stdout.strip()
    if current:
        peak = max(peak, int(current) * 1024)
    if peak > rss_limit:
        reason = 'observed_process_rss_limit'
    if time.monotonic() - begin > deadline_seconds:
        reason = 'whole_probe_deadline'
    if reason:
        os.killpg(process.pid, signal.SIGTERM)
        break
    time.sleep(.05)
try:
    output, errors = process.communicate(timeout=5)
except subprocess.TimeoutExpired:
    os.killpg(process.pid, signal.SIGKILL)
    output, errors = process.communicate()
    reason = reason or 'failed_to_stop_after_deadline'
rows = []
redacted = False
if len(output) > 65536 or re.search(rb'https?://|googlevideo\.com|visitorData|authorization\s*[:=]|set-cookie', output, re.I):
    redacted = True
else:
    try:
        rows = [json.loads(line) for line in output.decode().splitlines() if line.strip()]
    except (UnicodeError, ValueError):
        redacted = True
        rows = []
record = {'mode': mode, 'client': client, 'codec': codec, 'exit_code': process.returncode,
          'stop_reason': reason, 'elapsed_seconds': time.monotonic() - begin,
          'sampled_peak_rss_bytes': peak, 'rss_observation_limit_bytes': rss_limit,
          'rss_is_hard_allocator_limit': False, 'external_deadline_seconds': deadline_seconds,
          'binary_sha256': build['binary_sha256'], 'bundle_sha256': build['bundle_sha256'],
          'rows': rows, 'unsafe_or_non_json_stdout_redacted': redacted,
          'stdout_bytes': len(output), 'stderr_bytes': len(errors), 'stderr_sha256': hashlib.sha256(errors).hexdigest()}
stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
evidence = ROOT / 'evidence'
evidence.mkdir(exist_ok=True)
path = evidence / f'{stamp}-{mode}-{client}-{codec}.json'
path.write_text(json.dumps(record, indent=2) + '\n')
for row in rows:
    if row.get('gate') != 'native_media_progress':
        print(json.dumps(row))
print(json.dumps({'receipt': str(path), 'peak_rss_bytes': peak, 'stop_reason': reason, 'stdout_redacted': redacted}))
raise SystemExit(1 if reason or redacted else process.returncode)
