#!/usr/bin/env python3
"""Opt-in, sampled disk stop guard for one frozen, empty 0.6.3 acceptance app.

plan/preflight do not create application state. supervise is a FUTURE explicit
launch action. This is not a filesystem quota or a complete OS-residue tracker.
No library/cache deletion, broad process-name kill, login, or environment copy.
"""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shutil
import signal
import stat
import subprocess
import time

HERE = Path(__file__).resolve().parent
HOME_PATH = Path('/Users/xiaotwu')
SCRATCH = HOME_PATH / '.muses/tmp/p0-20261110-01'
APP = SCRATCH / 'interop/macos-baseline/Muses P0 Baseline.app'
MAIN = APP / 'Contents/MacOS/Muses'
BUNDLE = 'com.muses.acceptance.p0-baseline-20261110'
ROOT = HOME_PATH / '.muses/acceptance' / BUNDLE
LIBRARY = HOME_PATH / 'Library'
LEGACY = [LIBRARY / 'Application Support/MusesAcceptance' / BUNDLE,
          LIBRARY / 'Caches/MusesAcceptance' / BUNDLE]
SYSTEM = [LIBRARY / 'Preferences' / (BUNDLE + '.plist'),
          LIBRARY / 'HTTPStorages' / BUNDLE,
          LIBRARY / 'HTTPStorages' / (BUNDLE + '.binarycookies'),
          LIBRARY / 'Caches' / BUNDLE, LIBRARY / 'WebKit' / BUNDLE,
          LIBRARY / 'Cookies' / (BUNDLE + '.binarycookies'),
          LIBRARY / 'Saved Application State' / (BUNDLE + '.savedState')]
BASELINE = HERE.parent / 'baseline'
EXPECTED_TREE = '520b119dc353a248476c3cfdc745e0126cef32762339128a6c21b0c8a6b2e5aa'
EXPECTED_BUDGET = '4a5981dcd9b0e00684026cfb730ae0df99b5e69bd79df2749377195804727e97'
MAX_NODES = 20000


class Refusal(Exception):
    """A fixed, non-secret reason suitable for a receipt."""


def require(condition, reason):
    if not condition:
        raise Refusal(reason)


def sha(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def write_new(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def parents_safe(path, home=HOME_PATH, uid=None):
    uid = os.getuid() if uid is None else uid
    require(path.is_relative_to(home), 'path_outside_home')
    current = home
    parts = path.relative_to(home).parts[:-1]
    for component in [None, *parts]:
        if component is not None:
            current = current / component
        try:
            info = current.lstat()
        except FileNotFoundError:
            continue
        require(stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode), 'unsafe_parent_type')
        require(info.st_uid == uid and not stat.S_IMODE(info.st_mode) & 0o022, 'unsafe_parent_owner_or_mode')


def require_absent(paths, home=HOME_PATH, uid=None):
    for path in paths:
        parents_safe(path, home, uid)
        require(not os.path.lexists(path), 'unknown_existing_runtime_data')


def shared_safe(paths=None, uid=None):
    uid = os.getuid() if uid is None else uid
    paths = paths or [HOME_PATH / '.muses', HOME_PATH / '.muses/acceptance']
    result = []
    for path in paths:
        info = path.lstat()
        require(stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode), 'shared_parent_type')
        require(info.st_uid == uid and stat.S_IMODE(info.st_mode) == 0o700, 'shared_parent_owner_or_mode')
        result.append({'path': str(path), 'uid': info.st_uid, 'mode': '0700', 'dev': info.st_dev, 'ino': info.st_ino})
    return result


def byhost_paths():
    directory = LIBRARY / 'Preferences/ByHost'
    parents_safe(directory / '_checked_parent')
    return sorted(directory.glob(BUNDLE + '.*.plist')) if directory.exists() else []


def measure(roots, uid=None, allowed_links=None):
    """Unique inode sum of max(logical, allocated); no symlink traversal."""
    uid = os.getuid() if uid is None else uid
    allowed_links = allowed_links or {}
    seen, stack = set(), list(roots)
    logical = allocated = accounted = nodes = 0
    while stack:
        path = stack.pop()
        try:
            info = path.lstat()
        except FileNotFoundError:
            continue
        nodes += 1
        require(nodes <= MAX_NODES, 'inventory_node_limit')
        require(info.st_uid == uid, 'runtime_owner_changed')
        if stat.S_ISLNK(info.st_mode):
            require(str(path) in allowed_links and os.readlink(path) == allowed_links[str(path)], 'unexpected_runtime_symlink')
        elif stat.S_ISDIR(info.st_mode):
            try:
                stack.extend(path.iterdir())
            except FileNotFoundError:
                continue
        else:
            require(stat.S_ISREG(info.st_mode), 'unexpected_runtime_node')
            require(info.st_nlink == 1, 'unexpected_runtime_hardlink')
        key = (info.st_dev, info.st_ino)
        if key in seen:
            continue
        seen.add(key)
        size = info.st_size if stat.S_ISREG(info.st_mode) else 0
        blocks = info.st_blocks * 512
        logical += size
        allocated += blocks
        accounted += max(size, blocks)
    return {'logical_bytes': logical, 'allocated_bytes': allocated,
            'accounted_bytes': accounted, 'unique_inodes': len(seen), 'visited_nodes': nodes}


def app_inventory():
    expected = json.loads((BASELINE / 'derivative-manifest.json').read_text())
    require(digest(expected) == EXPECTED_TREE, 'baseline_manifest_drift')
    actual, pending = {}, [APP]
    while pending:
        path = pending.pop()
        info = path.lstat()
        require(info.st_uid == os.getuid(), 'app_owner_changed')
        name, mode = str(path.relative_to(APP)), stat.S_IMODE(info.st_mode)
        if stat.S_ISLNK(info.st_mode):
            target = os.readlink(path)
            require(not Path(target).is_absolute() and path.resolve().is_relative_to(APP), 'app_link_escape')
            actual[name] = ['link', mode, target]
        elif stat.S_ISDIR(info.st_mode):
            actual[name] = ['dir', mode]
            pending.extend(path.iterdir())
        else:
            require(stat.S_ISREG(info.st_mode), 'unexpected_app_node')
            actual[name] = ['file', mode, info.st_size, sha(path)]
    require(actual == expected, 'baseline_app_drift')
    info = plistlib.loads((APP / 'Contents/Info.plist').read_bytes())
    require(info['CFBundleIdentifier'] == BUNDLE and 'LSEnvironment' not in info, 'app_identity_or_environment')
    for key in ['SUFeedURL', 'SUPublicEDKey', 'MusesGoogleOAuthClientID', 'MusesGoogleOAuthClientSecret']:
        require(info.get(key) == '', 'app_authority_enabled')
    for key in ['SUEnableAutomaticChecks', 'SUAutomaticallyUpdate', 'MusesWebHomeEnabled']:
        require(info.get(key) is False, 'app_service_enabled')
    verified = subprocess.run(['/usr/bin/codesign', '--verify', '--deep', '--strict', str(APP)], capture_output=True, timeout=45)
    require(verified.returncode == 0, 'signature_verification_failed')
    return expected


def minimal_environment(tmp):
    # Deliberately no os.environ read, HOME reassignment, MUSES_*, OAuth or cookie values.
    return {'PATH': '/usr/bin:/bin:/usr/sbin:/sbin', 'LANG': 'en_US.UTF-8',
            'LC_ALL': 'en_US.UTF-8', 'TMPDIR': str(tmp) + '/',
            'PYTHONNOUSERSITE': '1', 'PYTHONDONTWRITEBYTECODE': '1'}


class BSDInfo(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint32) for name in
                ['flags', 'status', 'xstatus', 'pid', 'ppid', 'uid', 'gid', 'ruid', 'rgid', 'svuid', 'svgid', 'rfu']]
    _fields_ += [('comm', ctypes.c_char * 16), ('name', ctypes.c_char * 32)]
    _fields_ += [(name, ctypes.c_uint32) for name in ['nfiles', 'pgid', 'pjobc', 'e_tdev', 'e_tpgid']]
    _fields_ += [('nice', ctypes.c_int32), ('start_sec', ctypes.c_uint64), ('start_usec', ctypes.c_uint64)]


class Processes:
    def __init__(self):
        self.lib = ctypes.CDLL('/usr/lib/libproc.dylib', use_errno=True)
        self.lib.proc_pidinfo.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_int]
        self.lib.proc_pidpath.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]
        self.lib.proc_listallpids.argtypes = [ctypes.c_void_p, ctypes.c_int]
        require(ctypes.sizeof(BSDInfo) == 136, 'process_abi_size')

    def get(self, pid):
        info, path = BSDInfo(), ctypes.create_string_buffer(4096)
        if self.lib.proc_pidinfo(pid, 3, 0, ctypes.byref(info), ctypes.sizeof(info)) != ctypes.sizeof(info):
            return None
        if self.lib.proc_pidpath(pid, path, len(path)) <= 0:
            return None
        return {'pid': pid, 'ppid': info.ppid, 'uid': info.uid, 'start_sec': info.start_sec,
                'start_usec': info.start_usec, 'path': os.fsdecode(path.value)}

    def all(self):
        values = (ctypes.c_int * 16384)()
        count = self.lib.proc_listallpids(values, ctypes.sizeof(values))
        require(0 <= count < len(values), 'process_inventory_limit')
        return [item for pid in values[:count] if pid > 0 if (item := self.get(pid))]


def same_process(a, b):
    return bool(a and b and all(a[k] == b[k] for k in ['pid', 'uid', 'start_sec', 'start_usec', 'path']))


def executable_in_app(item, manifest, app=None, uid=None):
    app = APP if app is None else app
    uid = os.getuid() if uid is None else uid
    path = Path(item['path'])
    if item['uid'] != uid or not path.is_relative_to(app):
        return False
    relative = str(path.relative_to(app))
    expected = manifest.get(relative)
    if not expected or expected[0] != 'file' or not expected[1] & 0o111:
        return False
    try:
        info = path.lstat()
        return stat.S_ISREG(info.st_mode) and info.st_uid == uid and sha(path) == expected[3]
    except OSError:
        return False


def discover_owned(snapshot, known, manifest, app=None, validator=None):
    """Only observed descendants of a still-matching generation can become owned."""
    app = APP if app is None else app
    validator = executable_in_app if validator is None else validator
    current = {item['pid']: item for item in snapshot}
    changed = True
    while changed:
        changed = False
        for item in snapshot:
            if item['pid'] in known:
                continue
            parent = known.get(item['ppid'])
            if same_process(parent, current.get(item['ppid'])) and validator(item, manifest, app):
                known[item['pid']] = dict(item)
                changed = True
    return known


def discover_external(snapshot, known, external):
    """Track, but never signal, observed related executables outside the app."""
    current = {item['pid']: item for item in snapshot}
    changed = True
    while changed:
        changed = False
        for item in snapshot:
            if item['pid'] in known or item['pid'] in external:
                continue
            parent = known.get(item['ppid']) or external.get(item['ppid'])
            if same_process(parent, current.get(item['ppid'])):
                require(len(external) < 256, 'external_helper_observation_limit')
                external[item['pid']] = dict(item)
                changed = True
    return external


def stop_verified(known, getter, killer, manifest, validator=None):
    validator = executable_in_app if validator is None else validator
    sent, skipped = [], []
    for item in reversed(list(known.values())):
        current = getter(item['pid'])
        if current is None:
            continue
        if same_process(item, current) and validator(current, manifest):
            try:
                killer(item['pid'], signal.SIGTERM)
                sent.append(item['pid'])
            except ProcessLookupError:
                pass
        else:
            skipped.append(item['pid'])
    return sent, skipped


def limit_reason(runtime_bytes, interop_bytes, free_bytes, budget):
    if runtime_bytes >= budget['runtime_stop_threshold_bytes'] - budget['runtime_receipts_reserve_bytes']:
        return 'runtime_observed_stop_threshold'
    if interop_bytes + runtime_bytes >= budget['interop_allocation_bytes'] - 64 * 1024**2:
        return 'combined_interop_stop_threshold'
    if free_bytes <= budget['free_floor_bytes'] + 32 * 1024**2:
        return 'free_space_stop_threshold'
    return None


def load_budget():
    path = HERE / 'budget.json'
    require(sha(path) == EXPECTED_BUDGET, 'budget_drift')
    return json.loads(path.read_text())


def preflight(budget):
    shared = shared_safe()
    require_absent([ROOT, *LEGACY, *SYSTEM, *byhost_paths()])
    parents_safe(APP / '_checked_parent')
    manifest = app_inventory()
    processes = Processes()
    require(not any(Path(p['path']).is_relative_to(APP) for p in processes.all()), 'isolated_app_already_running')
    # The enclosing guard measures all P0 scratch. This local check also counts
    # runtime bytes outside scratch, so they cannot escape the interop budget.
    app_bytes = sum(v[2] for v in manifest.values() if v[0] == 'file')
    require(app_bytes < budget['baseline_app_subbudget_bytes'], 'baseline_app_subbudget')
    allocated = allocated_scratch(SCRATCH / 'interop')
    free = shutil.disk_usage(HOME_PATH).free
    require(limit_reason(0, allocated, free, budget) is None, 'preflight_space_limit')
    return {'shared_parents': shared, 'app_logical_bytes': app_bytes, 'interop_allocated_bytes': allocated,
            'free_bytes': free, 'absent_root_count': 1 + len(LEGACY) + len(SYSTEM),
            'byhost_matches': 0, 'baseline_tree_sha256': EXPECTED_TREE}, manifest, processes


def allocated_scratch(path):
    # Read-only accounting of the shared allocation; no assumptions about its
    # other agents' symlinks/hardlinks and no mutation of their files.
    total, seen, pending = 0, set(), [path]
    while pending:
        entry = pending.pop()
        try:
            info = entry.lstat()
            key = (info.st_dev, info.st_ino)
            if key in seen:
                continue
            seen.add(key)
            total += info.st_blocks * 512
            if stat.S_ISDIR(info.st_mode):
                pending.extend(entry.iterdir())
        except FileNotFoundError:
            pass
    return total


def plan_values(budget):
    return {'kind': 'future_sampled_baseline_launch_guard', 'script_sha256': sha(__file__),
            'budget_sha256': EXPECTED_BUDGET, 'app': str(APP), 'bundle': BUNDLE,
            'root': str(ROOT), 'legacy_roots': list(map(str, LEGACY)), 'system_watch_paths': list(map(str, SYSTEM)),
            'byhost_pattern': str(LIBRARY / 'Preferences/ByHost' / (BUNDLE + '.*.plist')),
            'baseline_tree_sha256': EXPECTED_TREE, 'budget': budget,
            'environment_keys': sorted(minimal_environment(ROOT / 'tmp')),
            'permissions': {'delete_files': False, 'change_volume': False, 'record_audio': False,
                            'app_launch': 'only explicit supervise action', 'signals': ['SIGTERM_verified_generation']},
            'limits': ['sampled_stop_not_quota', 'only_observed_children_proven', 'system_storage_not_exhaustive']}


def verify_plan(path, expected_sha, budget):
    require(expected_sha and sha(path) == expected_sha, 'plan_hash_mismatch')
    require(json.loads(path.read_text()) == plan_values(budget), 'plan_or_script_drift')


def supervise(seconds, budget, manifest, processes, receipt):
    known, external, remaining, skipped = {}, {}, [], []
    receipt.update(outcome='failed', reason='launch_not_observed', launch_performed=False, data_deleted=False)
    started, interrupted = time.monotonic(), []
    old_handlers = {}
    for sig in [signal.SIGTERM, signal.SIGINT]:
        old_handlers[sig] = signal.signal(sig, lambda signum, frame: interrupted.append(signum))
    opener = None
    try:
        # Exclusive creation only after a second clean preflight; never resume an
        # unknown/previous namespace automatically and never chmod shared parents.
        shared_before = shared_safe()
        require_absent([ROOT, *LEGACY, *SYSTEM, *byhost_paths()])
        ROOT.mkdir(mode=0o700)
        root_identity = ROOT.stat()
        (ROOT / 'tmp').mkdir(mode=0o700)
        receipt['created_runtime_root'] = str(ROOT)
        launch_unix = time.time()
        opener = subprocess.Popen(['/usr/bin/open', '-n', '-W', str(APP)], env=minimal_environment(ROOT / 'tmp'))
        receipt['launch_performed'] = True
        main_seen = False
        while True:
            require(shared_safe() == shared_before, 'shared_parent_changed')
            current_root = ROOT.lstat()
            require((current_root.st_dev, current_root.st_ino) == (root_identity.st_dev, root_identity.st_ino), 'runtime_root_replaced')
            require(not any(os.path.lexists(path) for path in LEGACY), 'legacy_root_created')
            snapshot = processes.all()
            for item in snapshot:
                if item['path'] == str(MAIN) and item['pid'] not in known:
                    require(not main_seen and item['start_sec'] + item['start_usec'] / 1e6 >= launch_unix - 1,
                            'unexpected_app_generation')
                    require(executable_in_app(item, manifest), 'unverified_main_executable')
                    known[item['pid']], main_seen = item, True
            discover_owned(snapshot, known, manifest)
            discover_external(snapshot, known, external)
            # Known updater symlink points into the already-counted namespace.
            allowed = {str(LIBRARY / 'Caches' / BUNDLE): str(ROOT / 'cache/updates' / BUNDLE)}
            sample = measure([ROOT, *SYSTEM, *byhost_paths()], allowed_links=allowed)
            receipt['runtime_peak_accounted_bytes'] = max(receipt.get('runtime_peak_accounted_bytes', 0), sample['accounted_bytes'])
            receipt['last_runtime_sample'] = sample
            reason = limit_reason(sample['accounted_bytes'], allocated_scratch(SCRATCH / 'interop'), shutil.disk_usage(HOME_PATH).free, budget)
            if reason:
                raise Refusal(reason)
            if interrupted:
                raise Refusal('supervisor_interrupted')
            live_main = any(item['path'] == str(MAIN) and same_process(item, processes.get(item['pid'])) for item in known.values())
            if main_seen and not live_main:
                receipt.update(outcome='observation_completed', reason='app_exited')
                break
            if not main_seen and time.monotonic() - started > 10:
                raise Refusal('launch_not_observed')
            if time.monotonic() - started >= seconds:
                require(main_seen, 'launch_not_observed')
                receipt.update(outcome='observation_completed', reason='planned_duration_reached')
                break
            time.sleep(budget['poll_seconds'])
    except Refusal as error:
        receipt.update(outcome='failed', reason=str(error))
    except BaseException as error:
        receipt.update(outcome='failed', reason='supervisor_' + type(error).__name__)
    finally:
        # Even a natural GUI exit is followed by finite cleanup of only previously
        # observed, hash-verified helper generations. No name-based or PID-only kill.
        sent, skipped = stop_verified(known, processes.get, os.kill, manifest)
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            remaining = [item for item in known.values() if same_process(item, processes.get(item['pid']))]
            if not remaining:
                break
            time.sleep(0.1)
        residual_in_app = [p['pid'] for p in processes.all() if Path(p['path']).is_relative_to(APP)]
        residual_external = [p['pid'] for p in external.values() if same_process(p, processes.get(p['pid']))]
        if remaining or skipped or residual_in_app or residual_external:
            receipt.update(outcome='failed', reason='app_or_helper_shutdown_incomplete')
        receipt.update(signalled_verified_pids=sent, skipped_changed_pids=skipped,
                       remaining_verified_pids=[p['pid'] for p in remaining], residual_in_app_pids=residual_in_app,
                       remaining_observed_external_pids=residual_external,
                       elapsed_seconds=time.monotonic() - started,
                       unobserved_or_external_helpers_proven_absent=False,
                       raw_environment_read=False, library_or_cache_deleted=False)
        if opener is not None:
            try:
                opener.wait(timeout=1)
            except subprocess.TimeoutExpired:
                receipt['open_waiter_still_running'] = True
                receipt['outcome'] = 'failed'
        for sig, handler in old_handlers.items():
            signal.signal(sig, handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['plan', 'preflight', 'supervise'])
    parser.add_argument('--plan-sha256')
    parser.add_argument('--seconds', type=float, default=60)
    parser.add_argument('--launch-isolated-app', action='store_true')
    args = parser.parse_args()
    plan_path = HERE / 'launch-plan.json'
    receipt = {'action': args.action, 'unix': time.time(), 'script_sha256': sha(__file__), 'launch_performed': False}
    try:
        budget = load_budget()
        if args.action != 'plan':
            verify_plan(plan_path, args.plan_sha256, budget)
        report, manifest, processes = preflight(budget)
        receipt['preflight'] = report
        if args.action == 'plan':
            write_new(plan_path, plan_values(budget))
            receipt.update(outcome='plan_frozen_no_launch', plan_sha256=sha(plan_path))
        elif args.action == 'preflight':
            receipt.update(outcome='preflight_passed_no_launch', plan_sha256=args.plan_sha256)
        else:
            require(args.launch_isolated_app and 0 < args.seconds <= 900, 'explicit_bounded_launch_required')
            supervise(args.seconds, budget, manifest, processes, receipt)
    except Refusal as error:
        receipt.update(outcome='failed', reason=str(error))
    except BaseException as error:
        receipt.update(outcome='failed', reason=type(error).__name__)
    output = HERE / 'evidence'
    output.mkdir(exist_ok=True)
    path = output / (time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()) + '-' + str(time.time_ns()) + '-' + args.action + '.json')
    write_new(path, receipt)
    print(json.dumps({'outcome': receipt['outcome'], 'receipt': str(path), 'plan_sha256': receipt.get('plan_sha256')}))
    return 1 if receipt['outcome'] == 'failed' else 0


if __name__ == '__main__':
    raise SystemExit(main())
