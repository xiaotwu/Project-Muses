#!/usr/bin/env python3
"""Run one P0 process group within the frozen scratch/free-space budget."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time
import uuid

ROOT = Path('/Users/xiaotwu/.muses/tmp/p0-20261110-01')

def allocated(path):
    total = 0
    seen = set()
    stack = [path]
    while stack:
        p = stack.pop()
        try:
            st = p.lstat()
            key = (st.st_dev, st.st_ino)
            if key in seen:
                continue
            seen.add(key)
            total += st.st_blocks * 512
            if p.is_dir() and not p.is_symlink():
                stack.extend(p.iterdir())
        except FileNotFoundError:
            pass
    return total

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--allocation', required=True)
    parser.add_argument('--timeout', type=float, default=1800)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    frozen = (ROOT / 'budget.json').read_bytes()
    budget = json.loads(frozen)
    if args.allocation not in budget['allocations'] or not command:
        parser.error('known allocation and executable required')
    receipt_dir = ROOT / 'coordination' / 'receipts'
    receipt_dir.mkdir(exist_ok=True)
    receipt = receipt_dir / (uuid.uuid4().hex + '.json')
    started = time.time()
    high = {'total': 0, 'allocation': 0}
    child = None
    reason = None
    def check():
        size = allocated(ROOT)
        owned = allocated(ROOT / args.allocation)
        free = shutil.disk_usage(ROOT).free
        high['total'] = max(high['total'], size)
        high['allocation'] = max(high['allocation'], owned)
        if size >= budget['total_budget_bytes'] - 256 * 1024**2:
            return 'aggregate scratch stop threshold'
        if owned >= budget['allocations'][args.allocation] - 64 * 1024**2:
            return 'allocation stop threshold'
        if free <= budget['free_space_floor_bytes'] + 256 * 1024**2:
            return 'free space stop threshold'
        return None
    try:
        reason = check()
        if not reason:
            child = subprocess.Popen(command, start_new_session=True)
            while child.poll() is None:
                reason = check()
                if time.time() - started > args.timeout:
                    reason = 'time budget'
                if reason:
                    break
                time.sleep(2)
    except BaseException as error:
        reason = type(error).__name__
    finally:
        if child is not None and child.poll() is None:
            os.killpg(child.pid, signal.SIGTERM)
            try:
                child.wait(timeout=8)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
        check()
        result = {
            'allocation': args.allocation,
            'budget_sha256': hashlib.sha256(frozen).hexdigest(),
            'runner_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'command_sha256': hashlib.sha256(json.dumps(command).encode()).hexdigest(),
            'executable': command[0], 'pid': child.pid if child else None,
            'started_unix': started, 'elapsed_seconds': time.time() - started,
            'returncode': child.returncode if child else None,
            'stop_reason': reason, 'high_water_allocated_bytes': high,
            'remaining_free_bytes': shutil.disk_usage(ROOT).free,
        }
        receipt.write_text(json.dumps(result, indent=2) + '\n')
        print('P0 receipt:', receipt, flush=True)
    return 125 if reason else child.returncode

if __name__ == '__main__':
    raise SystemExit(main())
