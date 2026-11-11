#!/usr/bin/env python3
"""Prepare an isolated 0.6.3 baseline without launching it or seeding user data.

The derivative keeps all compiled Mach-O sections and nested bundle bytes.
Only the root identity, disabled authorities and its signature change.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shutil
import stat
import struct
import subprocess
import time

HERE = Path(__file__).resolve().parent
SOURCE = Path('/Users/xiaotwu/.Trash/muses-release-063-nov05-01a18a83-packaging/source/build/Muses.app')
ARCHIVE = SOURCE.parent / 'Muses-0.6.3.zip'
ARCHIVE_SHA = '192b4297c6dac82c5115afb1ba7168bae4e88985959a5852f85344df8b9b5a44'
MAIN_SHA = 'efb7398d007155d23367f7f87e4c4c9b78748b3d95110d5ef91c2fca6ade7c39'
SCRATCH = Path('/Users/xiaotwu/.muses/tmp/p0-20261110-01/interop/macos-baseline')
APP = SCRATCH / 'Muses P0 Baseline.app'
BUNDLE = 'com.muses.acceptance.p0-baseline-20261110'
INFO = 'Contents/Info.plist'
MAIN = 'Contents/MacOS/Muses'
BUDGET = 768 * 1024**2
FREE_FLOOR = 40 * 1024**3


def sha(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024**2), b''):
            result.update(block)
    return result.hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def run(args):
    result = subprocess.run(args, capture_output=True, timeout=90)
    assert result.returncode == 0, Path(args[0]).name + ' failed: ' + result.stderr.decode(errors='replace')[-500:]
    return result


def tree(root):
    result = {}
    pending = [root]
    while pending:
        path = pending.pop()
        st = path.lstat()
        assert st.st_uid == os.getuid(), 'unexpected owner'
        name = str(path.relative_to(root))
        mode = stat.S_IMODE(st.st_mode)
        if stat.S_ISLNK(st.st_mode):
            target = os.readlink(path)
            assert not Path(target).is_absolute() and path.resolve().is_relative_to(root), 'escaping link'
            result[name] = ['link', mode, target]
        elif stat.S_ISDIR(st.st_mode):
            result[name] = ['dir', mode]
            pending.extend(sorted(path.iterdir(), reverse=True))
        else:
            assert stat.S_ISREG(st.st_mode), 'unsupported node'
            result[name] = ['file', mode, st.st_size, sha(path)]
    return result


def compiled_sections(path):
    assert path.stat().st_size < 80 * 1024**2
    data = path.read_bytes()
    assert data[:4] == b'\xcf\xfa\xed\xfe' and struct.unpack_from('<I', data, 4)[0] == 0x0100000C
    cursor, sections = 32, {}
    for _ in range(struct.unpack_from('<I', data, 16)[0]):
        command, size = struct.unpack_from('<II', data, cursor)
        assert size >= 8 and cursor + size <= len(data)
        if command == 0x19:
            for index in range(struct.unpack_from('<I', data, cursor + 64)[0]):
                start = cursor + 72 + 80 * index
                assert start + 80 <= cursor + size
                name = data[start:start+32].hex()
                length, offset = struct.unpack_from('<QI', data, start + 40)
                flags = struct.unpack_from('<I', data, start + 64)[0]
                if offset and flags & 0xff not in (1, 12, 18):
                    assert offset + length <= len(data)
                    sections[name] = hashlib.sha256(data[offset:offset+length]).hexdigest()
        cursor += size
    assert len(sections) >= 8
    return sections


def signature(app):
    run(['codesign', '--verify', '--deep', '--strict', str(app)])
    result = run(['codesign', '-dv', '--verbose=4', str(app)])
    lines = (result.stdout + result.stderr).decode().splitlines()
    team = next(line.split('=', 1)[1] for line in lines if line.startswith('TeamIdentifier='))
    authority = next(line.split('=', 1)[1] for line in lines if line.startswith('Authority='))
    identifier = next(line.split('=', 1)[1] for line in lines if line.startswith('Identifier='))
    assert any('(runtime)' in line for line in lines), 'missing hardened runtime'
    return team, authority, identifier


def inventory():
    assert sha(ARCHIVE) == ARCHIVE_SHA and sha(SOURCE / MAIN) == MAIN_SHA
    info = plistlib.loads((SOURCE / INFO).read_bytes())
    assert (info['CFBundleShortVersionString'], info['CFBundleVersion'], info['LSMinimumSystemVersion']) == ('0.6.3', '20261105.1', '26.0')
    assert signature(SOURCE)[2] == 'com.muses.app'
    files = tree(SOURCE)
    logical = sum(x[2] for x in files.values() if x[0] == 'file')
    assert logical < BUDGET - 64 * 1024**2
    return {'archive_sha256': ARCHIVE_SHA, 'main_sha256': MAIN_SHA,
            'tree_sha256': digest(files), 'logical_bytes': logical, 'nodes': len(files),
            'compiled_sections': compiled_sections(SOURCE / MAIN), 'files': files}


def write_new(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['plan', 'prepare'])
    parser.add_argument('--plan-sha256')
    args = parser.parse_args()
    plan_path = HERE / 'preparation-plan.json'
    before = inventory()
    if args.action == 'plan':
        assert not plan_path.exists() and not APP.exists()
        plan = {'kind': 'isolated_063_derivative_no_launch', 'script_sha256': sha(Path(__file__)),
                'source': str(SOURCE), 'destination': str(APP), 'bundle': BUNDLE,
                'scratch_budget_bytes': BUDGET, 'free_floor_bytes': FREE_FLOOR,
                'measured_free_bytes': shutil.disk_usage(SOURCE).free, 'source_inventory': before}
        write_new(plan_path, plan)
        print(json.dumps({'plan_sha256': sha(plan_path), 'script_sha256': sha(Path(__file__)),
                          'source_logical_bytes': before['logical_bytes'], 'source_nodes': before['nodes']}))
        return
    assert args.plan_sha256 and sha(plan_path) == args.plan_sha256, 'plan drift'
    plan = json.loads(plan_path.read_text())
    assert sha(Path(__file__)) == plan['script_sha256'] and before == plan['source_inventory'], 'input drift'
    assert plan['destination'] == str(APP) and plan['bundle'] == BUNDLE
    assert shutil.disk_usage(SOURCE).free > FREE_FLOOR + BUDGET
    assert not SCRATCH.exists(), 'existing stage requires journal review; do not repeat completed mutations'
    SCRATCH.mkdir(parents=True, mode=0o700)
    journal = SCRATCH / 'preparation-journal.jsonl'

    def event(name, **details):
        with journal.open('a') as stream:
            stream.write(json.dumps({'event': name, 'unix': time.time(), **details}) + '\n')
            stream.flush()
            os.fsync(stream.fileno())

    event('started', plan_sha256=args.plan_sha256, script_sha256=plan['script_sha256'])
    try:
        source_team, signer, _ = signature(SOURCE)
        run(['rsync', '-a', '--extended-attributes', '--exclude=/Contents/Info.plist', str(SOURCE)+'/', str(APP)+'/'])
        copied = tree(APP)
        expected = {k: v for k, v in before['files'].items() if k != INFO}
        assert set(copied) == set(expected)
        for name in expected:
            if copied[name] != expected[name]:
                assert copied[name][0] == expected[name][0] == 'link' and copied[name][2] == expected[name][2]
                os.lchmod(APP / name, expected[name][1])
        assert tree(APP) == expected, 'copy differs'
        event('copy_verified', production_info_written=False)
        safe = plistlib.loads((SOURCE / INFO).read_bytes())
        safe.pop('CFBundleURLTypes', None)
        safe.update(CFBundleIdentifier=BUNDLE, CFBundleName='Muses P0 Baseline',
                    CFBundleDisplayName='Muses P0 Baseline', SUFeedURL='', SUPublicEDKey='',
                    SUEnableAutomaticChecks=False, SUAutomaticallyUpdate=False,
                    MusesUpdateAcceptanceLoopback=False, MusesGoogleOAuthClientID='',
                    MusesGoogleOAuthClientSecret='', MusesWebHomeEnabled=False)
        with (APP / INFO).open('xb') as stream:
            plistlib.dump(safe, stream)
        (APP / INFO).chmod(before['files'][INFO][1])
        entitlements = plistlib.loads(run(['codesign', '-d', '--entitlements', ':-', str(SOURCE)]).stdout)
        ent_path = SCRATCH / 'baseline.entitlements'
        ent_path.write_bytes(plistlib.dumps(entitlements))
        event('isolated_identity_written')
        run(['codesign', '--force', '--options', 'runtime', '--timestamp=none', '--entitlements', str(ent_path), '--sign', signer, str(APP)])
        final_team, _, final_identifier = signature(APP)
        assert final_team == source_team and final_identifier == BUNDLE
        after = tree(APP)
        changed = sorted(k for k in before['files'] if before['files'][k] != after.get(k))
        assert set(after) == set(before['files'])
        assert set(changed) <= {INFO, MAIN, 'Contents/_CodeSignature/CodeResources'}
        assert compiled_sections(APP / MAIN) == before['compiled_sections']
        assert tree(SOURCE) == before['files'], 'official source changed'
        nested = []
        for path in sorted(APP.rglob('Info.plist')):
            if path == APP / INFO: continue
            values = plistlib.loads(path.read_bytes())
            if 'CFBundleIdentifier' in values:
                nested.append({'relative_info': str(path.relative_to(APP)), 'bundle': values['CFBundleIdentifier']})
        receipt = {'outcome': 'prepared_not_launched', 'source_version': '0.6.3', 'source_build': '20261105.1',
                   'source_archive_sha256': ARCHIVE_SHA, 'source_main_sha256': MAIN_SHA,
                   'derived_main_sha256': sha(APP / MAIN), 'compiled_sections_unchanged': len(before['compiled_sections']),
                   'compiled_sections_sha256': digest(before['compiled_sections']), 'changed_nodes': changed,
                   'strict_signature': 'passed', 'same_signing_team': True, 'bundle': BUNDLE,
                   'nested_bundle_identities': nested, 'source_tree_unchanged': True,
                   'plan_sha256': args.plan_sha256, 'script_sha256': plan['script_sha256'],
                   'derivative_tree_sha256': digest(after), 'data_seeded': False, 'launch_performed': False,
                   'free_after_bytes': shutil.disk_usage(SCRATCH).free}
        write_new(HERE / 'preparation-receipt.json', receipt)
        write_new(HERE / 'derivative-manifest.json', after)
        event('completed', receipt_sha256=sha(HERE / 'preparation-receipt.json'))
        print(json.dumps({k: receipt[k] for k in ['outcome', 'derived_main_sha256', 'compiled_sections_unchanged', 'strict_signature']}))
    except BaseException as error:
        event('failed', error_type=type(error).__name__, error=str(error))
        raise


if __name__ == '__main__':
    main()
