#!/usr/bin/env python3
"""Fetch one SHA-pinned public QuickJS-NG source artifact within 50 MiB."""
from pathlib import Path
import hashlib, json, shutil, stat, urllib.request, zipfile

ROOT = Path('/Users/xiaotwu/.muses/tmp/p0-20261110-01/source/v2-integration/runtime')
URL = 'https://github.com/quickjs-ng/quickjs/releases/download/v0.18.0/quickjs-amalgam.zip'
EXPECTED = '6c05066a6b62b483e2ba0f83d7a16688c6958182b214bfd693529434cef84a9e'
LIMIT = 50 * 1024 * 1024

def allocated():
    return sum(p.lstat().st_blocks * 512 for p in [ROOT, *ROOT.rglob('*')]) if ROOT.exists() else 0

ROOT.mkdir(parents=True, exist_ok=True)
assert allocated() < LIMIT and shutil.disk_usage(ROOT).free >= 40 * 1024**3
for name in ['downloads', 'upstream', 'build', 'tmp', 'module-cache', 'inputs', 'results']:
    (ROOT / name).mkdir(exist_ok=True)
archive = ROOT / 'downloads/quickjs-amalgam-v0.18.0.zip'
if not archive.exists():
    with urllib.request.urlopen(urllib.request.Request(URL, headers={'User-Agent': 'Muses-P0-source-validation'}), timeout=30) as response:
        data = response.read(600001)
    assert len(data) == 571908, 'Pinned artifact byte count mismatch'
    assert hashlib.sha256(data).hexdigest() == EXPECTED, 'Pinned source SHA mismatch'
    archive.write_bytes(data)
assert hashlib.sha256(archive.read_bytes()).hexdigest() == EXPECTED
with zipfile.ZipFile(archive) as package:
    members = package.infolist()
    assert len(members) <= 32 and sum(m.file_size for m in members) <= 8 * 1024 * 1024
    for member in members:
        relative = Path(member.filename)
        assert not relative.is_absolute() and '..' not in relative.parts
        assert not stat.S_ISLNK(member.external_attr >> 16)
        target = ROOT / 'upstream' / relative
        if member.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(package.read(member))
        else:
            assert target.read_bytes() == package.read(member), 'Existing extraction mismatch'
inputs = {}
source = Path('/Users/xiaotwu/.muses/tmp/p0-20261110-01/source/v2-parser')
for name, original in [('player.js', 'fixtures/player.js'), ('reduced.js', 'fixtures/reduced.js'),
                       ('reference-solver.js', 'fixtures/solver.js'), ('extract.bundle.js', 'build/extract.bundle.js')]:
    data = (source / original).read_bytes()
    assert len(data) <= 4 * 1024 * 1024
    target = ROOT / 'inputs' / name
    if target.exists():
        assert target.read_bytes() == data, 'Do not silently replace a frozen input'
    else:
        target.write_bytes(data)
    inputs[name] = {'original': str(source / original), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
manifest = {'version': 'v0.18.0', 'source_url': URL, 'archive_bytes': archive.stat().st_size,
            'archive_sha256': EXPECTED, 'inputs': inputs,
            'upstream_files': {str(p.relative_to(ROOT / 'upstream')): hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in sorted((ROOT / 'upstream').rglob('*')) if p.is_file()},
            'scratch_limit_bytes': LIMIT, 'allocated_bytes': allocated()}
assert allocated() < LIMIT
(ROOT / 'results/bootstrap.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps(manifest, indent=2))
