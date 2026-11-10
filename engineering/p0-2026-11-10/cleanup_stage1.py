#!/usr/bin/env python3
"""Recoverably retire only the frozen reference/interop scratch inventory."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

p = argparse.ArgumentParser()
p.add_argument('--plan', type=Path, required=True)
p.add_argument('--plan-sha256', required=True)
p.add_argument('--script-sha256', required=True)
a = p.parse_args()
assert hashlib.sha256(Path(__file__).read_bytes()).hexdigest() == a.script_sha256
assert hashlib.sha256(a.plan.read_bytes()).hexdigest() == a.plan_sha256
plan = json.loads(a.plan.read_text())
owned = Path(plan['owned_root'])
trash = Path(plan['trash_root'])
journal_path = a.plan.with_name('cleanup-stage1-journal.json')
if journal_path.exists():
    journal = json.loads(journal_path.read_text())
    assert journal['plan_sha256'] == a.plan_sha256
    assert journal['script_sha256'] == a.script_sha256
else:
    journal = {'plan_sha256': a.plan_sha256, 'script_sha256': a.script_sha256,
               'started_unix': time.time(), 'free_before': shutil.disk_usage(owned).free,
               'actions': [], 'failures': []}

def save():
    temp = journal_path.with_suffix('.pending')
    temp.write_text(json.dumps(journal, indent=2) + '\n')
    temp.replace(journal_path)

def done(key):
    return any(x.get('key') == key and x.get('complete') for x in journal['actions'])

def receipt(key, **data):
    journal['actions'].append({'key': key, 'complete': True, 'time_unix': time.time(), **data})
    save()

def inventory(root):
    count = logical = blocks = 0
    digest = hashlib.sha256()
    pending = [root]
    while pending:
        path = pending.pop()
        st = path.lstat()
        assert st.st_uid == os.getuid()
        count += 1
        blocks += st.st_blocks * 512
        if path.is_file() and not path.is_symlink():
            logical += st.st_size
        digest.update(json.dumps([str(path.relative_to(root)), st.st_mode, st.st_size,
                                  st.st_mtime_ns, st.st_ino]).encode())
        if path.is_dir() and not path.is_symlink():
            pending.extend(sorted(path.iterdir(), reverse=True))
    return {'entries': count, 'logical_file_bytes': logical, 'allocated_bytes': blocks,
            'metadata_sha256': digest.hexdigest()}

save()
try:
    adb = '/Users/xiaotwu/Library/Android/sdk/platform-tools/adb'
    target = plan['stop']
    pid = target['emulator_pid']
    if not done('stop-emulator'):
        current = subprocess.run(['ps', '-p', str(pid), '-o', 'command='], capture_output=True, text=True)
        if current.returncode == 0:
            assert '-avd ' + target['emulator_name'] in current.stdout
            assert '-port ' + str(target['emulator_port']) in current.stdout
            result = subprocess.run([adb, '-P', str(target['adb_port']), '-s',
                                     'emulator-' + str(target['emulator_port']), 'emu', 'kill'],
                                    capture_output=True, text=True, timeout=15)
            assert result.returncode == 0, result.stderr
            end = time.monotonic() + 12
            while subprocess.run(['ps', '-p', str(pid), '-o', 'pid='], capture_output=True).returncode == 0:
                if time.monotonic() > end:
                    raise RuntimeError('owned emulator did not exit; no file moves performed')
                time.sleep(0.25)
        receipt('stop-emulator', already_stopped=current.returncode != 0)
    if not done('stop-dedicated-adb'):
        devices = subprocess.run([adb, '-P', str(target['adb_port']), 'devices'], capture_output=True, text=True, timeout=10)
        assert devices.returncode == 0
        assert len([s for s in devices.stdout.splitlines()[1:] if s.strip()]) == 0
        subprocess.run([adb, '-P', str(target['adb_port']), 'kill-server'], check=True, timeout=10)
        receipt('stop-dedicated-adb')
    for entry in plan['moves']:
        src = Path(entry['source'])
        dst = trash / entry['destination_name']
        key = 'move:' + str(src)
        if done(key):
            assert not src.exists() and dst.exists(), 'completed move changed; stop for review'
            continue
        assert src.is_relative_to(owned) or str(src) == '/Users/xiaotwu/.android/avd/Muses_P0_BitChord_191.ini'
        assert src.exists() and not src.is_symlink() and not dst.exists()
        if 'required_sha256' in entry:
            assert hashlib.sha256(src.read_bytes()).hexdigest() == entry['required_sha256']
        command = ['lsof', '-nP', '+D', str(src)] if src.is_dir() else ['lsof', '-nP', str(src)]
        handles = subprocess.run(command, capture_output=True, text=True, timeout=25)
        assert handles.returncode == 1 and not handles.stdout and not handles.stderr, 'open handles or inconclusive lsof: ' + str(src)
        measured = inventory(src)
        trash.mkdir(parents=True, exist_ok=True)
        assert src.stat().st_dev == trash.stat().st_dev
        receipt('preflight:' + str(src), inventory=measured, open_handles=0)
        src.rename(dst)
        receipt(key, destination=str(dst), inventory=measured)
    journal['completed_unix'] = time.time()
    journal['free_after'] = shutil.disk_usage(owned).free
    journal['physical_recovery_claim_bytes'] = 0
    journal['note'] = 'Same-volume recoverable moves; APFS free-space change is not exclusive recovery.'
    save()
    print(json.dumps({'complete': True, 'moves': sum(x['key'].startswith('move:') for x in journal['actions']),
                      'allocated_bytes_in_trash': sum(x.get('inventory', {}).get('allocated_bytes', 0) for x in journal['actions'] if x['key'].startswith('move:')),
                      'free_before': journal['free_before'], 'free_after': journal['free_after'],
                      'physical_recovery_claim_bytes': 0}))
except BaseException as error:
    journal['failures'].append({'time_unix': time.time(), 'type': type(error).__name__, 'message': str(error)})
    save()
    raise
