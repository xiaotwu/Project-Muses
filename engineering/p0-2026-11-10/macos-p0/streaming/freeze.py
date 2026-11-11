#!/usr/bin/env python3
"""Freeze bounded evidence and inventory only; never remove scratch or data."""
from pathlib import Path
import argparse, hashlib, json, os, shutil, subprocess, time

HERE = Path(__file__).resolve().parent
ROOT = Path('/Users/xiaotwu/.muses/tmp/p0-20261110-01')
OWNED = ROOT / 'audio/macos-streaming'
PLAN = HERE / 'freeze-plan.json'
EVIDENCE = HERE / 'evidence'
BUILDS = ('build-20261110-234236', 'build-20261110-234930')
RUNS = ('local-20261110-234358', 'public-20261110-234622',
        'local-20261110-235204', 'public-20261110-235239')
RECEIPTS = ('523266306b2948b8ab667366e9e74358', '88a7f77d5d984e9587e34e2461ec9690',
            'e6c4fc2778cd489ab77b3ead026d210b', '15de5414af5144f8b47853ae1f777875',
            'ab909b2def484950b31dd7d2eeed681b', 'f98a84aa07454cac979e72c6015689f5')

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def dump(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')

def inventory(path):
    files = sorted(p for p in path.rglob('*') if p.is_file()) if path.is_dir() else [path]
    return {'path': str(path), 'files': len(files),
            'logical_bytes': sum(p.stat().st_size for p in files),
            'allocated_file_blocks_bytes': sum(p.stat().st_blocks * 512 for p in files),
            'entries': [{'relative_path': str(p.relative_to(path)) if path.is_dir() else p.name,
                         'bytes': p.stat().st_size, 'allocated_bytes': p.stat().st_blocks * 512,
                         'sha256': sha(p)} for p in files]}

def check_budget():
    assert sha(HERE.parent / 'streaming-budget.json') == 'bd65403b0c768848dc061411f5526a6c190adbf9de8ba523c4614746cc5aa66c'
    assert sha(ROOT / 'budget.json') == '7b27e21065887ba0a9072552afa31f64c307f1df6ff8eb4c3ebac25799fe3cbc'
    assert shutil.disk_usage(ROOT).free > 40 * 1024**3
    assert sum(p.stat().st_blocks * 512 for p in OWNED.rglob('*') if p.is_file()) < 128 * 1024**2

def prepare():
    assert not PLAN.exists(), 'freeze plan already exists; preserve it'
    check_budget()
    copies = []
    def add(source, destination):
        assert source.is_file() and not source.is_symlink()
        copies.append({'source': str(source), 'destination': str(destination),
                       'bytes': source.stat().st_size, 'sha256': sha(source)})
    for name in BUILDS:
        for path in sorted((OWNED / name).iterdir()):
            if path.name in ('input-manifest.json', 'success.json') or path.suffix == '.log':
                add(path, Path(name) / path.name)
    for name in RUNS:
        for path in sorted((OWNED / name).iterdir()):
            add(path, Path(name) / path.name)
    for name in RECEIPTS:
        add(ROOT / 'coordination/receipts' / (name + '.json'), Path('receipts') / (name + '.json'))
    add(HERE.parent / 'streaming-budget.json', Path('streaming-budget.json'))
    assert sum(row['bytes'] for row in copies) < 2 * 1024**2
    sources = {str(p): sha(p) for p in sorted(HERE.iterdir()) if p.is_file()}
    dump(PLAN, {'purpose': 'Copy bounded evidence and read-only inventory; no cleanup execution',
                'script_sha256': sha(Path(__file__)), 'source_sha256': sources, 'copies': copies,
                'current_build': str(OWNED / BUILDS[-1]), 'scratch': str(OWNED),
                'owned_limit_bytes': 128 * 1024**2, 'output_limit_bytes': 2 * 1024**2})
    print(json.dumps({'plan_sha256': sha(PLAN), 'script_sha256': sha(Path(__file__)),
                      'copy_bytes': sum(row['bytes'] for row in copies)}))

def freeze(expected):
    assert expected and sha(PLAN) == expected, 'freeze plan changed'
    plan = json.loads(PLAN.read_text())
    assert plan['script_sha256'] == sha(Path(__file__)), 'freeze script changed'
    for path, expected_sha in plan['source_sha256'].items():
        assert sha(Path(path)) == expected_sha, 'source changed: ' + path
    check_budget()
    assert not EVIDENCE.exists(), 'evidence already exists; preserve it'
    EVIDENCE.mkdir()
    for row in plan['copies']:
        source = Path(row['source'])
        assert sha(source) == row['sha256'], 'input changed: ' + str(source)
        destination = EVIDENCE / row['destination']
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        assert sha(destination) == row['sha256']
    observed = subprocess.run(['lsof', '-nP', '+D', str(OWNED)], capture_output=True, text=True, timeout=30)
    assert observed.returncode in (0, 1), 'lsof failed'
    process = subprocess.run(['ps', '-axo', 'pid,ppid,comm'], capture_output=True, text=True, check=True)
    active = [line for line in process.stdout.splitlines()
              if str(OWNED) + '/' in line and any('/stream-' + v in line for v in ('local', 'public'))]
    assert not active, 'streaming process still active'
    rows = []
    for path in sorted(OWNED.iterdir()):
        row = inventory(path)
        row['disposition'] = ('retain_current_integration_kit' if path.name == BUILDS[-1]
                              else 'retain_current_pointer' if path.name == 'current-build.txt'
                              else 'eligible_for_coordinator_recoverable_cleanup_after_evidence_verification')
        row['owner'] = 'P0 audio streaming subagent'
        rows.append(row)
    dump(EVIDENCE / 'cleanup-inventory.json', {
        'observed_unix': time.time(), 'paths': rows, 'cleanup_executed': False,
        'lsof_exit_code': observed.returncode, 'lsof_stdout': observed.stdout,
        'lsof_stderr': observed.stderr, 'active_streaming_processes': active,
        'logical_bytes': sum(row['logical_bytes'] for row in rows),
        'allocated_file_blocks_bytes': sum(row['allocated_file_blocks_bytes'] for row in rows),
        'actual_free_bytes_at_observation': shutil.disk_usage(ROOT).free,
        'physical_bytes_recovered_by_this_agent': 0,
        'note': 'Allocated file blocks are not an APFS space recovery measurement. No files were moved or deleted.'})
    tools = {}
    for name, command in [('macos', ['sw_vers']), ('xcode', ['xcodebuild', '-version']),
                          ('clang', ['clang', '--version']), ('sdk', ['xcrun', '--sdk', 'macosx', '--show-sdk-path'])]:
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        tools[name] = {'command': command, 'stdout': result.stdout, 'stderr': result.stderr}
    dump(EVIDENCE / 'toolchain.json', tools)
    latest = json.loads((OWNED / BUILDS[-1] / 'success.json').read_text())
    for name, expected_sha in latest['binary_sha256'].items():
        assert sha(OWNED / BUILDS[-1] / ('stream-' + name)) == expected_sha
    files = {str(p.relative_to(EVIDENCE)): {'sha256': sha(p), 'bytes': p.stat().st_size}
             for p in sorted(EVIDENCE.rglob('*')) if p.is_file()}
    assert sum(item['bytes'] for item in files.values()) < plan['output_limit_bytes']
    dump(EVIDENCE / 'manifest.json', {
        'frozen_unix': time.time(), 'freeze_plan_sha256': sha(PLAN),
        'freeze_script_sha256': sha(Path(__file__)), 'source_sha256': plan['source_sha256'],
        'authoritative_build': BUILDS[-1], 'authoritative_local': RUNS[-2],
        'authoritative_public': RUNS[-1], 'binary_sha256': latest['binary_sha256'],
        'files': files, 'speaker_first_sound_measured': False,
        'production_application_integrated': False, 'cleanup_executed': False})
    print(json.dumps({'manifest_sha256': sha(EVIDENCE / 'manifest.json'),
                      'evidence_files': len(files), 'evidence_bytes': sum(row['bytes'] for row in files.values()),
                      'scratch_allocated_file_blocks_bytes': sum(row['allocated_file_blocks_bytes'] for row in rows),
                      'evidence': str(EVIDENCE)}))

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--plan-sha')
    args = parser.parse_args()
    prepare() if args.prepare else freeze(args.plan_sha)
