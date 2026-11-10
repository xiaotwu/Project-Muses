#!/usr/bin/env python3
"""Journal exact same-volume recoverable moves from a hash-frozen P0 plan."""
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
root = Path('/Users/xiaotwu/.muses/tmp/p0-20261110-01')
trash = Path('/Users/xiaotwu/.Trash/Muses-P0-20261110-01')
journal_path = a.plan.with_name(a.plan.stem + '-journal.json')
journal = json.loads(journal_path.read_text()) if journal_path.exists() else {
    'plan_sha256': a.plan_sha256, 'script_sha256': a.script_sha256,
    'started_unix': time.time(), 'free_before': shutil.disk_usage(root).free,
    'actions': [], 'failures': []}
assert journal['plan_sha256'] == a.plan_sha256 and journal['script_sha256'] == a.script_sha256

def save():
    temp = journal_path.with_suffix('.pending')
    temp.write_text(json.dumps(journal, indent=2) + '\n')
    temp.replace(journal_path)

def inventory(path):
    stack = [path]
    logical = allocated = count = 0
    fingerprint = hashlib.sha256()
    while stack:
        f = stack.pop()
        st = f.lstat()
        assert st.st_uid == os.getuid()
        count += 1
        allocated += st.st_blocks * 512
        if f.is_file() and not f.is_symlink():
            logical += st.st_size
        fingerprint.update(json.dumps([str(f.relative_to(path)), st.st_ino,
                                       st.st_mode, st.st_size, st.st_mtime_ns]).encode())
        if f.is_dir() and not f.is_symlink():
            stack.extend(sorted(f.iterdir(), reverse=True))
    return {'entries': count, 'logical_file_bytes': logical, 'allocated_bytes': allocated,
            'metadata_sha256': fingerprint.hexdigest()}

save()
try:
    for item in plan['moves']:
        src = Path(item['source'])
        dst = trash / item['destination_name']
        assert src.is_relative_to(root) and src != root
        assert dst.parent == trash
        completed = [x for x in journal['actions'] if x.get('source') == str(src) and x.get('complete')]
        if completed:
            assert not src.exists() and dst.exists(), 'completed move changed'
            continue
        pending = [x for x in journal['actions'] if x.get('source') == str(src) and not x.get('complete')]
        if pending and not src.exists() and dst.exists():
            assert len(pending) == 1 and inventory(dst) == pending[0]['inventory'], 'interrupted move needs manual review'
            pending[0]['complete'] = True
            pending[0]['reconciled_after_interruption'] = time.time()
            save()
            continue
        if pending:
            assert len(pending) == 1 and src.exists() and not dst.exists(), 'ambiguous unfinished move'
            assert inventory(src) == pending[0]['inventory'], 'unfinished source changed'
        assert src.exists() and not src.is_symlink() and not dst.exists()
        if item.get('required_sha256'):
            assert hashlib.sha256(src.read_bytes()).hexdigest() == item['required_sha256']
        cmd = ['lsof', '-nP', '+D', str(src)] if src.is_dir() else ['lsof', '-nP', str(src)]
        handles = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
        assert handles.returncode == 1 and not handles.stdout and not handles.stderr, 'active or inconclusive handles: ' + str(src)
        before = inventory(src)
        trash.mkdir(parents=True, exist_ok=True)
        assert src.stat().st_dev == trash.stat().st_dev
        if not pending:
            journal['actions'].append({'source': str(src), 'destination': str(dst),
                                       'inventory': before, 'open_handles': 0,
                                       'complete': False, 'time_unix': time.time()})
        save()
        src.rename(dst)
        (pending[0] if pending else journal['actions'][-1])['complete'] = True
        save()
    journal['completed_unix'] = time.time()
    journal['free_after'] = shutil.disk_usage(root).free
    journal['physical_recovery_claim_bytes'] = 0
    save()
    print(json.dumps({'complete': True, 'moved_paths': len(journal['actions']),
                      'allocated_bytes_in_trash': sum(x['inventory']['allocated_bytes'] for x in journal['actions']),
                      'free_before': journal['free_before'], 'free_after': journal['free_after'],
                      'physical_recovery_claim_bytes': 0}))
except BaseException as error:
    journal['failures'].append({'time_unix': time.time(), 'type': type(error).__name__, 'message': str(error)})
    save()
    raise
