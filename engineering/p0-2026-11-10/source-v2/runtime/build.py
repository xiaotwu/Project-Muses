#!/usr/bin/env python3
"""Offline embedding build. Invoke only through the frozen parent disk guard."""
from pathlib import Path
import datetime, hashlib, json, os, shutil, subprocess

HERE = Path(__file__).resolve().parent
ROOT = Path('/Users/xiaotwu/.muses/tmp/p0-20261110-01/source/v2-integration/runtime')
PARSER = ROOT.parents[1] / 'v2-parser'
DEPS = ROOT.parent / 'deps/node_modules'
def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def allocated(): return sum(p.lstat().st_blocks * 512 for p in [ROOT, *ROOT.rglob('*')])
def check():
    assert allocated() < 50 * 1024**2
    assert shutil.disk_usage(ROOT).free >= 40 * 1024**3
assert digest(HERE / 'runtime-budget.json') == '2b16b9514c052087ff107883faab0c69501619fa881ce6a4f8c853d098fe71ee'
assert digest(HERE.parents[1] / 'run_guarded.py') == '3d07c44fa82f9ee6dd11e9167fc91b63c63724a36adf366ae0f391a98479afe0'
bootstrap = json.loads((ROOT / 'results/bootstrap.json').read_text())
for name, sha in bootstrap['upstream_files'].items(): assert digest(ROOT / 'upstream' / name) == sha
for name, item in bootstrap['inputs'].items(): assert digest(ROOT / 'inputs' / name) == item['sha256']
check()
fixed = PARSER / 'build/extract.bundle.js'
assert digest(fixed) == '17a300a3ef421c50922459a2f5bc086a121c2156ceedd50a8b3c8cc8c003b7dd'
corrected = ROOT / 'inputs/extract.corrected.bundle.js'
if corrected.exists(): assert corrected.read_bytes() == fixed.read_bytes()
else: corrected.write_bytes(fixed.read_bytes())
env = os.environ.copy()
env.update(TMPDIR=str(ROOT / 'tmp'), CLANG_MODULE_CACHE_PATH=str(ROOT / 'module-cache'))
commands = []
def run(command):
    check(); commands.append(command); subprocess.run(command, env=env, check=True); check()
upstream = ROOT / 'upstream'
build = ROOT / 'build'
common = ['-std=gnu11', '-O2', '-g0', '-fwrapv', '-DQUICKJS_NG_BUILD', '-I' + str(upstream)]
run(['cc', *common, '-c', str(upstream / 'quickjs-amalgam.c'), '-o', str(build / 'quickjs-ng-macos.o')])
run(['cc', *common, str(HERE / 'embedding.c'), str(build / 'quickjs-ng-macos.o'), '-lm', '-lpthread', '-o', str(build / 'embedding-ng')])
run([str(DEPS / '@esbuild/darwin-arm64/bin/esbuild'), str(HERE / 'fetch-smoke.mjs'), '--bundle', '--format=iife', '--platform=neutral', '--target=es2022', '--alias:web-streams-polyfill=' + str(DEPS / 'web-streams-polyfill/dist/ponyfill.mjs'), '--outfile=' + str(build / 'fetch-smoke.bundle.js')])
sdk = subprocess.check_output(['xcrun', '--sdk', 'iphoneos', '--show-sdk-path'], text=True).strip()
ios = ['xcrun', '--sdk', 'iphoneos', 'clang', '-target', 'arm64-apple-ios17.0', '-isysroot', sdk, *common]
run([*ios, '-c', str(upstream / 'quickjs-amalgam.c'), '-o', str(build / 'quickjs-ng-ios.o')])
run([*ios, '-c', str(HERE / 'embedding.c'), '-o', str(build / 'embedding-ios.o')])
manifest = {
    'commands': commands,
    'inputs': {p.name: {'sha256': digest(p), 'bytes': p.stat().st_size} for p in (ROOT / 'inputs').iterdir() if p.is_file()},
    'source_hashes': {p.name: digest(p) for p in HERE.iterdir() if p.is_file()},
    'outputs': {p.name: {'sha256': digest(p), 'bytes': p.stat().st_size} for p in build.iterdir() if p.is_file()},
    'macos_compiler': subprocess.check_output(['cc', '--version'], text=True).splitlines()[0],
    'ios_sdk': sdk,
    'scratch_allocated_bytes': allocated(),
    'actual_free_bytes': shutil.disk_usage(ROOT).free,
    'corrected_bundle_note': 'Same scoped structuredClone as the frozen P0 host and disabled upstream log output; earlier copied bundle is preserved.'
}
receipt = ROOT / 'results' / (datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ') + '-build.json')
receipt.write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps({'receipt': str(receipt), 'outputs': manifest['outputs'], 'scratch_allocated_bytes': allocated()}, indent=2))
