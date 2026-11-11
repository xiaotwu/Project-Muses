#!/usr/bin/env python3
"""Freeze this completed offline stage, preserving all fixtures for root cleanup."""
import sys
sys.dont_write_bytecode = True
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import time

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('runtime_guard', HERE / 'runtime_guard.py')
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)
EVIDENCE = HERE / 'evidence'
SOURCE = Path('/Users/xiaotwu/Code/Muses-Polyhymnia')
RELEASE = '12260f050a374ee949053e8f63b039fe20f15148'
PLAN_SHA = '2453e166a266c9d74bd5b3c77d397f245b2a0ab3a24d1773b7b21d590b109b9a'
SCRIPT_SHA = '8e1f7c0860b8e3068afcbfe95e179b563ef4a9d74769ef34db92d71c3603f483'


def command(args):
    result = subprocess.run(args, capture_output=True, timeout=20)
    guard.require(result.returncode == 0, 'evidence_command_failed')
    return result.stdout


def copy_new(source, target):
    with Path(source).open('rb') as original, Path(target).open('xb') as copied:
        shutil.copyfileobj(original, copied, 1024 * 1024)


def main():
    budget = guard.load_budget()
    guard.require(guard.sha(HERE / 'runtime_guard.py') == SCRIPT_SHA, 'script_not_frozen')
    guard.verify_plan(HERE / 'launch-plan.json', PLAN_SHA, budget)
    attempts = list(Path(budget['test_scratch']).glob('*/test-receipt.json'))
    guard.require(len(attempts) == 1, 'test_attempt_count_changed')
    receipt = json.loads(attempts[0].read_text())
    guard.require(receipt['passed'] and receipt['script_sha256'] == SCRIPT_SHA, 'test_receipt_mismatch')
    copy_new(attempts[0], EVIDENCE / 'test-receipt.json')
    copy_new(attempts[0].parent / 'tests.log', EVIDENCE / 'tests.log')
    plan_receipt = next(EVIDENCE.glob('*-plan.json'))
    preflight_receipt = next(EVIDENCE.glob('*-preflight.json'))
    copy_new(plan_receipt, EVIDENCE / 'plan-receipt.json')
    copy_new(preflight_receipt, EVIDENCE / 'preflight-receipt.json')
    for name, receipt_id in [
        ('test-guard', '2841d3e0a59b4306a02932d9f8fbef9b'),
        ('plan-guard', '721bb95e08dd4273922aaa93a88a4543'),
        ('preflight-guard', '9b3afcfaed32456583f87f50e9862696')]:
        copy_new(guard.SCRATCH / 'coordination/receipts' / (receipt_id + '.json'), EVIDENCE / (name + '.json'))

    paths = ['App/MusesApp.swift', 'Infrastructure/MusesDataPaths.swift', 'Persistence/MusesModelContainer.swift',
             'Infrastructure/MediaCacheBudget.swift', 'Infrastructure/SharedStreamResource.swift',
             'Infrastructure/MediaFileCache.swift', 'Infrastructure/RebuildableJSONCache.swift',
             'Infrastructure/YTDlpSearchCache.swift', 'Infrastructure/HomeFeedCache.swift',
             'Services/Discovery/CachedMusicCatalogProvider.swift', 'Infrastructure/ArtworkCache.swift',
             'Infrastructure/WaveformCache.swift', 'Services/Lyrics/LyricsDocumentCache.swift',
             'Infrastructure/StreamURLCache.swift', 'Infrastructure/YTDlpBridge.swift',
             'Infrastructure/YTDlpRunner.swift', 'Services/YouTube/KeychainStore.swift',
             'Services/YouTube/GoogleOAuthSession.swift', 'Services/Update/UpdateService.swift',
             'Services/Update/SparkleUpdateEngine.swift', 'Services/Update/UpdateTransactionStore.swift']
    source_records = []
    for item in paths:
        relative = 'Sources/Muses/' + item
        published = command(['git', '-C', str(SOURCE), 'show', RELEASE + ':' + relative])
        current_hash = guard.sha(SOURCE / relative)
        guard.require(hashlib.sha256(published).hexdigest() == current_hash, 'audited_source_drift')
        source_records.append({'path': relative, 'sha256': current_hash, 'matches_release_commit': True})
    diff = command(['git', '-C', str(SOURCE), 'diff', '--name-only', RELEASE, '--', 'Sources']).decode()
    guard.require(not diff, 'source_tree_diff')
    guard.write_new(EVIDENCE / 'source-audit.json', {
        'observed_unix': time.time(), 'repository': str(SOURCE), 'release_commit': RELEASE,
        'checkout_head': command(['git', '-C', str(SOURCE), 'rev-parse', 'HEAD']).decode().strip(),
        'source_diff_against_release': [], 'release_document': 'docs/engineering/release-0.6.3.md',
        'release_document_sha256': guard.sha(SOURCE / 'docs/engineering/release-0.6.3.md'),
        'source_files': source_records,
        'runtime_values_or_credentials_read': False,
        'api_evidence': {'proc_pidinfo_flavor': 3, 'bsd_info_size_bytes': 136,
                         'fields_used': ['pid', 'ppid', 'uid', 'start_sec', 'start_usec', 'proc_pidpath'],
                         'open_environment_contract': 'local open(1): opened applications inherit launcher environment'}})

    root = Path(budget['test_scratch'])
    entries, seen, logical_unique, allocated = [], set(), 0, 0
    for path in [root, *sorted(root.rglob('*'))]:
        info = path.lstat()
        guard.require(info.st_uid == os.getuid(), 'fixture_owner_changed')
        entry = {'relative_path': str(path.relative_to(root)), 'uid': info.st_uid,
                 'mode': oct(stat.S_IMODE(info.st_mode)), 'dev': info.st_dev, 'ino': info.st_ino,
                 'allocated_bytes': info.st_blocks * 512}
        size = info.st_size if stat.S_ISREG(info.st_mode) else 0
        entry['logical_bytes'] = size
        if stat.S_ISLNK(info.st_mode):
            entry.update(type='symlink', target=os.readlink(path))
        elif stat.S_ISREG(info.st_mode):
            entry.update(type='file', sha256=guard.sha(path), nlink=info.st_nlink)
        else:
            guard.require(stat.S_ISDIR(info.st_mode), 'unexpected_fixture_type')
            entry['type'] = 'directory'
        entries.append(entry)
        key = (info.st_dev, info.st_ino)
        if key not in seen:
            logical_unique += size
            allocated += info.st_blocks * 512
            seen.add(key)
    guard.require(max(logical_unique, allocated) < budget['test_scratch_limit_bytes'], 'test_scratch_limit')
    handles = subprocess.run(['/usr/sbin/lsof', '-nP', '+D', str(root), '-Fpn'], capture_output=True, timeout=20)
    guard.require(handles.returncode == 1 and not handles.stdout, 'fixture_handles_remain_or_lsof_failed')
    active_app = [p['pid'] for p in guard.Processes().all() if Path(p['path']).is_relative_to(guard.APP)]
    guard.require(not active_app, 'baseline_process_exists')
    guard.require_absent([guard.ROOT, *guard.LEGACY, *guard.SYSTEM, *guard.byhost_paths()])
    guard.write_new(EVIDENCE / 'cleanup-inventory.json', {
        'observed_unix': time.time(), 'cleanup_executed': False, 'eligible_for_root_recoverable_cleanup': True,
        'root': str(root), 'owner_uid': os.getuid(), 'purpose': 'completed offline tests only; no live app or user data',
        'logical_bytes_unique_inode': logical_unique, 'allocated_bytes_unique_inode': allocated,
        'logical_bytes_per_path': sum(e['logical_bytes'] for e in entries),
        'allocated_bytes_per_path': sum(e['allocated_bytes'] for e in entries),
        'unique_inodes': len(seen), 'lsof_returncode': handles.returncode, 'lsof_open_handles': 0,
        'baseline_process_ids': active_app, 'runtime_roots_still_absent': True,
        'free_bytes_at_inventory': shutil.disk_usage(root).free,
        'retained': [str(guard.APP), str(HERE)],
        'hardlinks': 'one deliberate fixture pair; accounted once per inode',
        'entries': entries})
    files = []
    for path in sorted(HERE.rglob('*')):
        if path.is_file():
            files.append({'path': str(path.relative_to(HERE)), 'bytes': path.stat().st_size, 'sha256': guard.sha(path)})
    guard.write_new(EVIDENCE / 'source-hashes.json', {
        'frozen_unix': time.time(), 'scope': 'completed offline runtime audit and preparation; no live app test',
        'plan_sha256': PLAN_SHA, 'script_sha256': SCRIPT_SHA, 'files': files})
    print(json.dumps({'files': len(files), 'test_cases': receipt['tests_run'],
                      'cleanup_logical_bytes': logical_unique, 'cleanup_allocated_bytes': allocated,
                      'manifest_sha256': guard.sha(EVIDENCE / 'source-hashes.json'),
                      'no_app_process': True, 'no_runtime_created': True}))


if __name__ == '__main__':
    main()
