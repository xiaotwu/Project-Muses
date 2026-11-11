#!/usr/bin/env python3
"""Offline fixtures only: no GUI/app process, network, sound or recording."""
import sys
sys.dont_write_bytecode = True
import importlib.util
import json
import os
from pathlib import Path
import stat
import time
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('runtime_guard', HERE / 'runtime_guard.py')
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)
BUDGET = guard.load_budget()
SCRATCH = Path(BUDGET['test_scratch'])
ATTEMPT = SCRATCH / time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())


class Offline(unittest.TestCase):
    def setUp(self):
        self.root = ATTEMPT / self._testMethodName
        self.root.mkdir(mode=0o700)

    def refused(self, reason, fn, *args, **kwargs):
        with self.assertRaisesRegex(guard.Refusal, '^' + reason + '$'):
            fn(*args, **kwargs)

    def test_absent_and_each_unknown_root(self):
        roots = [self.root / name for name in ['new', 'legacy-data', 'legacy-cache']]
        guard.require_absent(roots, home=self.root)
        for root in roots:
            root.mkdir(mode=0o700)
            self.refused('unknown_existing_runtime_data', guard.require_absent, [root], home=self.root)

    def test_unknown_system_data(self):
        root = self.root / 'preferences.plist'
        root.write_text('synthetic, not personal preferences')
        self.refused('unknown_existing_runtime_data', guard.require_absent, [root], home=self.root)

    def test_parent_symlink(self):
        target = self.root / 'target'
        target.mkdir(mode=0o700)
        link = self.root / 'link'
        link.symlink_to(target)
        self.refused('unsafe_parent_type', guard.require_absent, [link / 'new'], home=self.root)

    def test_parent_owner_and_mode(self):
        self.refused('unsafe_parent_owner_or_mode', guard.require_absent, [self.root / 'new'], home=self.root, uid=os.getuid() + 1)
        self.root.chmod(0o770)
        self.refused('unsafe_parent_owner_or_mode', guard.require_absent, [self.root / 'new'], home=self.root)

    def test_shared_mode_not_repaired(self):
        before = self.root.stat().st_mode
        self.assertEqual(guard.shared_safe([self.root])[0]['mode'], '0700')
        self.root.chmod(0o755)
        self.refused('shared_parent_owner_or_mode', guard.shared_safe, [self.root])
        self.assertEqual(stat.S_IMODE(self.root.stat().st_mode), 0o755)
        self.assertEqual(stat.S_IMODE(before), 0o700)

    def test_sparse_logical_accounting(self):
        path = self.root / 'sparse'
        with path.open('wb') as stream:
            stream.truncate(2 * 1024**2)
        result = guard.measure([path])
        self.assertEqual(result['logical_bytes'], 2 * 1024**2)
        self.assertEqual(result['accounted_bytes'], max(result['allocated_bytes'], result['logical_bytes']))
        self.assertEqual(guard.measure([path, path])['accounted_bytes'], result['accounted_bytes'])

    def test_owner_hardlink_and_symlink_rejection(self):
        source = self.root / 'source'
        source.write_bytes(b'fixture')
        self.refused('runtime_owner_changed', guard.measure, [source], uid=os.getuid() + 1)
        linked = self.root / 'hardlink'
        os.link(source, linked)
        self.refused('unexpected_runtime_hardlink', guard.measure, [source, linked])
        link = self.root / 'symlink'
        link.symlink_to(source)
        self.refused('unexpected_runtime_symlink', guard.measure, [link])
        self.assertEqual(guard.measure([link], allowed_links={str(link): str(source)})['logical_bytes'], 0)

    def test_budgets(self):
        free = BUDGET['free_floor_bytes'] + 100 * 1024**2
        self.assertIsNone(guard.limit_reason(0, 0, free, BUDGET))
        self.assertEqual(guard.limit_reason(95 * 1024**2, 0, free, BUDGET), 'runtime_observed_stop_threshold')
        self.assertEqual(guard.limit_reason(128 * 1024**2, 0, free, BUDGET), 'runtime_observed_stop_threshold')
        self.assertEqual(guard.limit_reason(0, BUDGET['interop_allocation_bytes'], free, BUDGET), 'combined_interop_stop_threshold')
        self.assertEqual(guard.limit_reason(0, 0, BUDGET['free_floor_bytes'], BUDGET), 'free_space_stop_threshold')

    def test_minimal_environment(self):
        env = guard.minimal_environment(self.root / 'tmp')
        self.assertEqual(set(env), {'PATH', 'LANG', 'LC_ALL', 'TMPDIR', 'PYTHONNOUSERSITE', 'PYTHONDONTWRITEBYTECODE'})
        self.assertNotIn('HOME', env)
        self.assertFalse(any(k.startswith('MUSES_') for k in env))
        self.assertEqual(env['TMPDIR'], str(self.root / 'tmp') + '/')

    def test_plan_hash_and_script_drift(self):
        path = self.root / 'plan.json'
        guard.write_new(path, guard.plan_values(BUDGET))
        expected = guard.sha(path)
        guard.verify_plan(path, expected, BUDGET)
        self.refused('plan_hash_mismatch', guard.verify_plan, path, '0' * 64, BUDGET)
        changed = json.loads(path.read_text())
        changed['script_sha256'] = '0' * 64
        path.write_text(json.dumps(changed))
        self.refused('plan_or_script_drift', guard.verify_plan, path, guard.sha(path), BUDGET)

    def test_process_reuse_and_observed_lineage(self):
        parent = {'pid': 100, 'ppid': 1, 'uid': os.getuid(), 'start_sec': 5, 'start_usec': 1, 'path': '/fixture/app/main'}
        child = dict(parent, pid=101, ppid=100, path='/fixture/app/helper')
        stranger = dict(parent, pid=102, ppid=1, path='/fixture/app/helper')
        known = {100: parent}
        guard.discover_owned([parent, child, stranger], known, {}, validator=lambda *args: True)
        self.assertEqual(set(known), {100, 101})
        reused = dict(parent, start_usec=2)
        known = {100: parent}
        guard.discover_owned([reused, child], known, {}, validator=lambda *args: True)
        self.assertEqual(set(known), {100})
        signals = []
        sent, skipped = guard.stop_verified(known, lambda pid: reused, lambda *args: signals.append(args), {}, validator=lambda *args: True)
        self.assertEqual((sent, skipped, signals), ([], [100], []))
        sent, skipped = guard.stop_verified(known, lambda pid: parent, lambda *args: signals.append(args), {}, validator=lambda *args: True)
        self.assertEqual(sent, [100])
        self.assertEqual(skipped, [])

    def test_exact_executable_hash(self):
        executable = self.root / 'main'
        executable.write_bytes(b'not executable test bytes')
        executable.chmod(0o700)
        item = {'uid': os.getuid(), 'path': str(executable)}
        manifest = {'main': ['file', 0o700, executable.stat().st_size, guard.sha(executable)]}
        self.assertTrue(guard.executable_in_app(item, manifest, self.root))
        executable.write_bytes(b'changed')
        self.assertFalse(guard.executable_in_app(item, manifest, self.root))
        self.assertFalse(guard.executable_in_app(dict(item, path='/usr/bin/true'), manifest, self.root))

    def mock_supervise(self, external=False, over_budget=False):
        app = self.root / 'fixture.app'
        app.mkdir(mode=0o700)
        manifest = {}
        for name in ['main', 'helper']:
            path = app / name
            path.write_bytes(b'OFFLINE FIXTURE; never executed')
            path.chmod(0o700)
            manifest[name] = ['file', 0o700, path.stat().st_size, guard.sha(path)]
        moment = time.time()
        main = {'pid': 90001, 'ppid': 1, 'uid': os.getuid(), 'start_sec': int(moment),
                'start_usec': int(moment % 1 * 1e6), 'path': str(app / 'main')}
        items = {90001: main, 90002: dict(main, pid=90002, ppid=90001, path=str(app / 'helper'))}
        if external:
            items[90003] = dict(main, pid=90003, ppid=90001, path='/outside/fixture/helper')
        class FakeProcesses:
            def get(self, pid): return items.get(pid)
            def all(self): return list(items.values())
        class FakeOpen:
            def wait(self, timeout): return 0
        root = self.root / 'runtime'
        signal_log = []
        def signal_fixture(pid, sig):
            signal_log.append(pid)
            items.pop(pid, None)
        receipt = {}
        budget = dict(BUDGET, poll_seconds=0.001)
        actual_measure = guard.measure
        def measured(*args, **kwargs):
            values = actual_measure(*args, **kwargs)
            if over_budget: values['accounted_bytes'] = 128 * 1024**2
            return values
        with patch.multiple(guard, APP=app, MAIN=app / 'main', ROOT=root, LEGACY=[], SYSTEM=[]), \
             patch.object(guard, 'byhost_paths', return_value=[]), \
             patch.object(guard, 'shared_safe', return_value=[{'fixed': True}]), \
             patch.object(guard, 'measure', side_effect=measured), \
             patch.object(guard, 'allocated_scratch', return_value=0), \
             patch.object(guard.subprocess, 'Popen', return_value=FakeOpen()) as launch, \
             patch.object(guard.os, 'kill', side_effect=signal_fixture):
            guard.supervise(0.002, budget, manifest, FakeProcesses(), receipt)
            self.assertEqual(launch.call_count, 1)
            self.assertEqual(launch.call_args.kwargs['env'], guard.minimal_environment(root / 'tmp'))
        self.assertTrue(root.exists())  # Success and failure retain all state.
        self.assertFalse(receipt['library_or_cache_deleted'])
        self.assertEqual(set(signal_log), {90001, 90002})
        self.assertFalse(receipt['unobserved_or_external_helpers_proven_absent'])
        return receipt

    def test_mock_complete_stops_verified_only(self):
        result = self.mock_supervise()
        self.assertEqual(result['outcome'], 'observation_completed')
        self.assertEqual(result['remaining_verified_pids'], [])

    def test_mock_budget_failure_retains_state(self):
        result = self.mock_supervise(over_budget=True)
        self.assertEqual(result['outcome'], 'failed')
        self.assertEqual(result['reason'], 'runtime_observed_stop_threshold')

    def test_mock_external_helper_prevents_success(self):
        result = self.mock_supervise(external=True)
        self.assertEqual(result['outcome'], 'failed')
        self.assertEqual(result['reason'], 'app_or_helper_shutdown_incomplete')
        self.assertEqual(result['remaining_observed_external_pids'], [90003])


def main():
    guard.require(not SCRATCH.exists(), 'existing_test_stage_requires_review')
    guard.require(guard.shutil.disk_usage(SCRATCH.parent).free > BUDGET['free_floor_bytes'] + BUDGET['test_scratch_limit_bytes'], 'test_free_space')
    SCRATCH.mkdir(mode=0o700)
    ATTEMPT.mkdir(mode=0o700)
    log_path = ATTEMPT / 'tests.log'
    with log_path.open('x') as stream:
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Offline))
    if not result.wasSuccessful():
        print(log_path.read_text())
    # Fixtures deliberately include links and wrong modes; account without reading
    # their content or treating expected rejections as real runtime eligibility.
    logical = sum(p.lstat().st_size for p in ATTEMPT.rglob('*') if stat.S_ISREG(p.lstat().st_mode))
    allocated = guard.allocated_scratch(SCRATCH)
    report = {'tests_run': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
              'passed': result.wasSuccessful(), 'scratch': str(SCRATCH), 'logical_bytes_per_path': logical,
              'allocated_bytes_unique_inode': allocated, 'scratch_limit_bytes': BUDGET['test_scratch_limit_bytes'],
              'actual_app_launched': False, 'actual_signals_sent': False, 'network_used': False,
              'audio_played_or_recorded': False, 'script_sha256': guard.sha(HERE / 'runtime_guard.py'),
              'test_sha256': guard.sha(__file__), 'budget_sha256': guard.EXPECTED_BUDGET}
    guard.write_new(ATTEMPT / 'test-receipt.json', report)
    print(json.dumps(report))
    guard.require(max(logical, allocated) < BUDGET['test_scratch_limit_bytes'], 'test_scratch_limit')
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
