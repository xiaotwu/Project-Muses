#!/usr/bin/env python3
"""Copy bounded receipts/logs and hashes, never compiler caches, into the worktree."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
sys.dont_write_bytecode = True
from build import HERE, SCRATCH

out = HERE / 'evidence'
out.mkdir(exist_ok=True)
def copy(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    assert source.stat().st_size < 1024 * 1024
    shutil.copy2(source, target)

for platform in ['macosx', 'iphoneos']:
    for name in ['configure-command.json', 'configure.log', 'probe-build.log']:
        copy(SCRATCH/platform/name, out/platform/name)
latest = sorted(p for p in (SCRATCH/'results').iterdir() if p.is_dir())[-1]
for path in latest.iterdir():
    copy(path, out/'final-run'/path.name)
if (SCRATCH/'results/local.jsonl').exists():
    copy(SCRATCH/'results/local.jsonl', out/'failed-first-run.jsonl')
copy(SCRATCH/'stress/results.log', out/'thread-sanitizer.log')
copy(SCRATCH/'fixtures/manifest.json', out/'fixture-manifest.json')
copy(SCRATCH/'fixtures/generator-version.txt', out/'fixture-generator.txt')
for name in ['COPYING.LGPLv2.1', 'LICENSE.md']:
    copy(SCRATCH/'sources/ffmpeg-8.0'/name, out/'licenses'/name)
for receipt in (SCRATCH.parent/'coordination/receipts').glob('*.json'):
    if json.loads(receipt.read_text()).get('allocation') == 'audio':
        copy(receipt, out/'receipts'/receipt.name)
commands = {
    'compiler': ['clang', '--version'],
    'os': ['sw_vers'],
    'mac-dependencies': ['otool', '-L', str(SCRATCH/'macosx/audio-probe')],
    'mac-signature': ['codesign', '-dvv', str(SCRATCH/'macosx/audio-probe')],
    'mac-signature-verify': ['codesign', '--verify', '--strict', '--verbose=2', str(SCRATCH/'macosx/audio-probe')],
    'mac-entitlements': ['codesign', '-d', '--entitlements', ':-', str(SCRATCH/'macosx/audio-probe')],
    'ios-symbols': ['nm', '-gU', str(SCRATCH/'iphoneos/audio-probe.o')],
}
for name, command in commands.items():
    result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    (out/(name+'.txt')).write_text(result.stdout + f'\nexit={result.returncode}\n')
    assert result.returncode == 0
for platform, name in [('macosx','audio-probe'), ('iphoneos','miniaudio-backend.o')]:
    symbols = subprocess.check_output(['nm','-u',str(SCRATCH/platform/name)], text=True)
    forbidden = [line for line in symbols.splitlines() if any(x in line for x in ['_dlopen','_dlsym','_dlclose'])]
    assert not forbidden
    (out/(platform+'-runtime-linking.json')).write_text(json.dumps({'forbidden_imports':forbidden,'checked_artifact':name},indent=2)+'\n')

manifest = {}
for platform in ['macosx','iphoneos']:
    paths = [SCRATCH/platform/'miniaudio-backend.o']
    paths += [SCRATCH/platform/name/f'{name}.a' for name in ['libavformat','libavcodec','libswresample','libavutil']]
    paths += [SCRATCH/platform/('audio-probe' if platform == 'macosx' else 'audio-probe.o')]
    for path in paths:
        manifest[str(path.relative_to(SCRATCH))] = {'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'logical_bytes':path.stat().st_size,'allocated_bytes':path.stat().st_blocks*512}
(out/'artifact-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
inventory = []
for path in SCRATCH.iterdir():
    files = [path] if path.is_file() else list(path.rglob('*'))
    logical = sum(p.stat().st_size for p in files if p.is_file())
    allocated = sum(p.lstat().st_blocks*512 for p in files if not p.is_symlink())
    inventory.append({'path':str(path),'logical_bytes':logical,'allocated_bytes':allocated})
(out/'scratch-inventory.json').write_text(json.dumps({'paths':inventory,'actual_free_bytes':shutil.disk_usage(SCRATCH).free,'cleanup':'Not deleted. Root coordinates recoverable cleanup; active iOS integration still depends on iphoneos artifacts.'},indent=2)+'\n')
(out/'run-origin.json').write_text(json.dumps({'final_results':str(latest),'scratch':str(SCRATCH)},indent=2)+'\n')
source_manifest = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in HERE.iterdir()
                   if p.is_file() and p.suffix in ['.py','.cpp','.mm','.h','.json','.md']}
(out/'harness-source-manifest.json').write_text(json.dumps(source_manifest,indent=2)+'\n')
print(json.dumps({'evidence_files':len(list(out.rglob('*'))),'evidence_logical_bytes':sum(p.stat().st_size for p in out.rglob('*') if p.is_file())}))
