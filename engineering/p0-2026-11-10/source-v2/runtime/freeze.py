#!/usr/bin/env python3
"""Freeze small offline receipts/notices and inventory owned cleanup candidates."""
from pathlib import Path
import datetime, hashlib, json, re, shutil, subprocess

HERE = Path(__file__).resolve().parent
ROOT = Path('/Users/xiaotwu/.muses/tmp/p0-20261110-01/source/v2-integration/runtime')
PARSER = ROOT.parents[1] / 'v2-parser'
DEPS = ROOT.parent / 'deps/node_modules'
GUARDS = ROOT.parents[2] / 'coordination/receipts'
def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def copy_frozen(source, target):
    data = source.read_bytes()
    if target.exists(): assert target.read_bytes() == data, 'Frozen evidence mismatch'
    else: target.write_bytes(data)
evidence = HERE / 'evidence'
evidence.mkdir(exist_ok=True)
for p in sorted((ROOT / 'results').iterdir()):
    assert p.is_file() and p.stat().st_size <= 128 * 1024
    copy_frozen(p, evidence / p.name)
old = PARSER / 'results/20261110T215615.569158Z-quickjs-full-parse-only.json'
copy_frozen(old, evidence / ('historical-incomplete-shim-' + old.name))
for name in ['5be4232155a540d0aae0e595d0f276c5', 'fb8f8a3702504c9ca8a81043256598b9',
             '048f8269583241bd9b48a2ae5e703d4a', '50404bfb1deb465583c3ac2db66a587a',
             '16714b20adbf4b108ecd2bc66c340c24', 'bfcb14c1f0c24e27a963d6d2c98dc9f9',
             '9c4a7a92515e44b3b76d4693c33c5d7b']:
    copy_frozen(GUARDS / (name + '.json'), evidence / ('guard-' + name + '.json'))
notices, seen = [], set()
for name in ['quickjs-amalgam.c', 'quickjs.h', 'quickjs-libc.h']:
    data = (ROOT / 'upstream' / name).read_text()
    for match in re.finditer(r'/\*.*?\*/', data, re.S):
        block = match.group()
        if 'Permission is hereby granted' in block and block not in seen:
            seen.add(block)
            notices.append(f'Source: QuickJS-NG v0.18.0 {name}, line {data.count(chr(10), 0, match.start()) + 1}\n{block}')
notices.append('Source: web-streams-polyfill 4.2.0 LICENSE\n' + (DEPS / 'web-streams-polyfill/LICENSE').read_text())
text = '\n\n'.join(notices) + '\n'
assert 'UNICODE LICENSE V3' in text and len(text.encode()) < 64 * 1024
(HERE / 'THIRD_PARTY_NOTICES.txt').write_text(text)
files = []
for p in sorted(ROOT.rglob('*')):
    st = p.lstat()
    assert not p.is_symlink()
    if p.is_file(): files.append({'path': str(p), 'logical_bytes': st.st_size, 'allocated_bytes': st.st_blocks * 512, 'sha256': digest(p)})
opened = subprocess.run(['lsof', '+D', str(ROOT)], capture_output=True, text=True)
assert opened.returncode in [0, 1] and not opened.stdout.strip(), 'Owned scratch still open'
stat_entries = [ROOT, *ROOT.rglob('*')]
unique = {}
for p in stat_entries:
    st = p.lstat(); unique[(st.st_dev, st.st_ino)] = st.st_blocks * 512
inventory = {
    'created_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'candidate_root': str(ROOT), 'scope': 'Owned obsolete offline runtime comparison scratch; parent coordinated recoverable cleanup only',
    'active_process_handles': [], 'lsof_exit_code': opened.returncode, 'open_files': [],
    'logical_file_bytes': sum(x['logical_bytes'] for x in files),
    'allocated_unique_inode_bytes': sum(unique.values()), 'file_count': len(files),
    'actual_free_bytes': shutil.disk_usage(ROOT).free, 'scratch_limit_bytes': 50 * 1024**2,
    'deletion_performed': False, 'files': files,
    'retention_note': 'All small attempt/guard receipts and stdout/stderr are frozen in runtime/evidence; archive/input/binary hashes retained. No media, cookies, auth tokens or user data were read.'
}
assert inventory['allocated_unique_inode_bytes'] < inventory['scratch_limit_bytes']
(HERE / 'cleanup-candidates.json').write_text(json.dumps(inventory, indent=2) + '\n')
for path in evidence.glob('20261110T22180*-ng-*.json'):
    receipt = json.loads(path.read_text()); assert receipt['exit_code'] == 0 and receipt['guard_stop'] is None
    assert all(event.get('process_maxrss_bytes', 0) < 256 * 1024**2 for event in receipt['events'])
manifest = {
    'scope': 'Final source/evidence checkpoint; earlier attempt manifests are immutable historical records',
    'files': {str(p.relative_to(HERE)): {'sha256': digest(p), 'bytes': p.stat().st_size} for p in sorted(HERE.rglob('*')) if p.is_file() and p.name != 'manifest.json'},
    'final_native_binary_sha256': digest(ROOT / 'build/embedding-ng'),
    'final_ng_guard_receipt': '9c4a7a92515e44b3b76d4693c33c5d7b',
    'ng_final_checks': 6, 'adopted': False, 'original_engine_retained': True
}
(HERE / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps({'frozen_files': len(manifest['files']), 'scratch_allocated_bytes': inventory['allocated_unique_inode_bytes'], 'scratch_logical_file_bytes': inventory['logical_file_bytes'], 'open_files': 0, 'final_binary_sha256': manifest['final_native_binary_sha256']}, indent=2))
