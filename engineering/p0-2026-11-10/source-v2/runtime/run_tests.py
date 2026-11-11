#!/usr/bin/env python3
"""Bounded offline runs; preserve each attempt before reporting its status."""
from pathlib import Path
import argparse, datetime, hashlib, json, os, resource, shutil, subprocess, time

HERE = Path(__file__).resolve().parent
ROOT = Path('/Users/xiaotwu/.muses/tmp/p0-20261110-01/source/v2-integration/runtime')
PARSER = ROOT.parents[1] / 'v2-parser'
def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def allocated(): return sum(p.lstat().st_blocks * 512 for p in [ROOT, *ROOT.rglob('*')])
def check():
    assert allocated() < 50 * 1024**2
    assert shutil.disk_usage(ROOT).free >= 40 * 1024**3
assert digest(HERE / 'runtime-budget.json') == '2b16b9514c052087ff107883faab0c69501619fa881ce6a4f8c853d098fe71ee'
assert digest(HERE.parents[1] / 'run_guarded.py') == '3d07c44fa82f9ee6dd11e9167fc91b63c63724a36adf366ae0f391a98479afe0'
parser = argparse.ArgumentParser()
parser.add_argument('mode', choices=['baseline', 'ng'])
args = parser.parse_args()
check()
fixed = PARSER / 'build/extract.bundle.js'
assert digest(fixed) == '17a300a3ef421c50922459a2f5bc086a121c2156ceedd50a8b3c8cc8c003b7dd'
corrected = ROOT / 'inputs/extract.corrected.bundle.js'
if corrected.exists(): assert corrected.read_bytes() == fixed.read_bytes()
else: corrected.write_bytes(fixed.read_bytes())
bootstrap = json.loads((ROOT / 'results/bootstrap.json').read_text())
for name, item in bootstrap['inputs'].items(): assert digest(ROOT / 'inputs' / name) == item['sha256']
inputs = ROOT / 'inputs'
env = os.environ.copy()
env.update(TMPDIR=str(ROOT / 'tmp'), CLANG_MODULE_CACHE_PATH=str(ROOT / 'module-cache'))
def no_core(): resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
def run(label, command):
    check()
    stem = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ') + '-' + label
    stdout_path, stderr_path = (ROOT / 'results' / (stem + suffix) for suffix in ['.stdout', '.stderr'])
    started = time.monotonic(); peak = 0; reason = None
    with stdout_path.open('wb') as out, stderr_path.open('wb') as err:
        process = subprocess.Popen(command, stdout=out, stderr=err, env=env, preexec_fn=no_core)
        while process.poll() is None:
            row = subprocess.run(['ps', '-o', 'rss=', '-p', str(process.pid)], capture_output=True, text=True).stdout.strip()
            if row: peak = max(peak, int(row) * 1024)
            if peak > 256 * 1024**2: reason = 'process_rss_limit'
            if time.monotonic() - started > 20: reason = 'deadline'
            if stdout_path.stat().st_size + stderr_path.stat().st_size > 65536: reason = 'output_limit'
            if reason: process.kill(); break
            time.sleep(.02)
        process.wait()
    events = []
    for line in stdout_path.read_bytes()[:65536].splitlines():
        try: events.append(json.loads(line))
        except (UnicodeDecodeError, json.JSONDecodeError): events.append({'non_json_output_bytes': len(line)})
    receipt = {
        'label': label, 'command': command, 'exit_code': process.returncode, 'guard_stop': reason,
        'elapsed_ms': round((time.monotonic() - started) * 1000), 'observed_peak_rss_bytes': peak,
        'rss_limit_bytes': 256 * 1024**2, 'events': events,
        'stdout_sha256': digest(stdout_path), 'stderr_sha256': digest(stderr_path),
        'stderr_bytes': stderr_path.stat().st_size, 'binary_sha256': digest(Path(command[0])),
        'corrected_bundle_sha256': digest(corrected), 'runner_sha256': digest(Path(__file__)),
        'core_dumps': False, 'scratch_allocated_bytes': allocated()
    }
    path = ROOT / 'results' / (stem + '.json')
    path.write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps({'receipt': str(path), **receipt}, indent=2), flush=True)
    check()
    return process.returncode == 0 and reason is None
if args.mode == 'baseline':
    binary = PARSER / 'build/quickjs-phase'
    results = [run('quickjs-corrected-full-parse', [str(binary), str(corrected), str(inputs / 'player.js'), str(ROOT / 'build/baseline-full-solver.js'), 'parse_only']),
               run('quickjs-corrected-reduced-extract', [str(binary), str(corrected), str(inputs / 'reduced.js'), str(ROOT / 'build/baseline-reduced-solver.js'), 'extract'])]
else:
    binary = ROOT / 'build/embedding-ng'
    results = []
    for label, arguments in [
        ('ng-corrected-full-parse', ['full-parse', str(corrected), str(inputs / 'player.js'), str(inputs / 'reference-solver.js')]),
        ('ng-corrected-reduced-extract', ['reduced-extract', str(corrected), str(inputs / 'reduced.js'), str(inputs / 'reference-solver.js')]),
        ('ng-explicit-oom', ['oom']), ('ng-cancel', ['cancel']), ('ng-context-oom', ['context-oom']),
        ('ng-fetch-smoke', ['fetch-smoke', str(ROOT / 'build/fetch-smoke.bundle.js')])]:
        results.append(run(label, [str(binary), *arguments]))
raise SystemExit(0 if all(results) else 1)
