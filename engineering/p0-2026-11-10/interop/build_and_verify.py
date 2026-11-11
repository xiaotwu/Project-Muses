#!/usr/bin/env python3
"""Run via the frozen parent run_guarded.py, never as an unbudgeted build."""
import hashlib
import json
import os
from pathlib import Path
import platform
import select
import sqlite3
import subprocess
import time
import uuid

SOURCE = Path(__file__).resolve().parent
SCRATCH = Path('/Users/xiaotwu/.muses/tmp/p0-20261110-01/interop')
RUN = SCRATCH / ('run-' + time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:6])
RUN.mkdir(parents=True)
ENV = os.environ.copy()
for key, relative in {
    'CARGO_HOME': 'cargo-home', 'CARGO_TARGET_DIR': 'cargo-target',
    'TMPDIR': 'tmp', 'SWIFT_MODULECACHE_PATH': 'swift-module-cache',
    'CLANG_MODULE_CACHE_PATH': 'clang-module-cache',
    'DOTNET_CLI_HOME': 'dotnet-home', 'NUGET_PACKAGES': 'nuget-packages',
    'NUGET_HTTP_CACHE_PATH': 'nuget-http', 'XDG_CACHE_HOME': 'xdg-cache',
    'XDG_DATA_HOME': 'xdg-data', 'XDG_CONFIG_HOME': 'xdg-config',
}.items():
    path = RUN / relative
    path.mkdir()
    ENV[key] = str(path)
ENV.update({
    'CARGO_INCREMENTAL': '0', 'DOTNET_CLI_TELEMETRY_OPTOUT': '1',
    'DOTNET_SKIP_FIRST_TIME_EXPERIENCE': '1',
    'DOTNET_CLI_WORKLOAD_UPDATE_NOTIFY_DISABLE': '1',
    'DOTNET_CLI_USE_MSBUILD_SERVER': '0', 'MSBUILDDISABLENODEREUSE': '1',
    'DOTNET_CLI_DO_NOT_USE_MSBUILD_SERVER': '1',
    'DOTNET_GENERATE_ASPNET_CERTIFICATE': 'false',
    'DOTNET_ADD_GLOBAL_TOOLS_TO_PATH': 'false', 'DOTNET_NOLOGO': '1',
})
report = {'run': str(RUN), 'platform': platform.platform(), 'steps': [], 'commands': [], 'result': 'running'}
def run(name, command):
    started = time.monotonic()
    result = subprocess.run([str(x) for x in command], env=ENV, cwd=SOURCE, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    log = RUN / (name + '.log')
    log.write_text(result.stdout)
    report['commands'].append([str(x) for x in command])
    report['steps'].append({'name': name, 'exit': result.returncode, 'seconds': round(time.monotonic() - started, 3), 'log': str(log), 'log_sha256': hashlib.sha256(log.read_bytes()).hexdigest()})
    print(name + ': ' + result.stdout[-5000:], flush=True)
    if result.returncode: raise RuntimeError(name + ' failed')
    return result.stdout

try:
    for name, command in [('rust-version', ['rustc', '--version']), ('cargo-version', ['cargo', '--version']), ('swift-version', ['swiftc', '--version']), ('dotnet-version', ['dotnet', '--version'])]:
        run(name, command)
    run('rust-build', ['cargo', 'build', '--offline', '--manifest-path', SOURCE / 'Cargo.toml'])
    run('rust-tests', ['cargo', 'test', '--offline', '--manifest-path', SOURCE / 'Cargo.toml'])
    dylib = RUN / 'cargo-target/debug/deps/libmuses_p0_core.dylib'
    ENV['MUSES_P0_DYLIB'] = str(dylib)
    dylib_hash = hashlib.sha256(dylib.read_bytes()).hexdigest()
    report['dylib'] = {'path': str(dylib), 'sha256': dylib_hash}
    report['dylib']['swift_install_name_path'] = str(dylib)
    swift = RUN / 'swift-proof'
    run('swift-build', ['swiftc', '-module-cache-path', ENV['SWIFT_MODULECACHE_PATH'], '-I', SOURCE / 'include', '-L', dylib.parent, '-lmuses_p0_core', '-Xlinker', '-rpath', '-Xlinker', dylib.parent, SOURCE / 'swift/main.swift', '-o', swift])
    run('swift-linkage', ['otool', '-L', swift])
    net_bin = RUN / 'net-bin'
    net_obj = RUN / 'net-obj'
    properties = ['-p:BaseIntermediateOutputPath=' + str(net_obj) + '/', '-p:MSBuildProjectExtensionsPath=' + str(net_obj) + '/', '-p:OutputPath=' + str(net_bin) + '/']
    run('csharp-build', ['dotnet', 'build', SOURCE / 'csharp/Interop.csproj', '--disable-build-servers', '--configfile', SOURCE / 'csharp/NuGet.Config', *properties])
    managed = ['dotnet', net_bin / 'Interop.dll']
    foreign = RUN / 'foreign-fixture.sqlite3'
    with sqlite3.connect(foreign) as db:
        db.execute('CREATE TABLE foreign_table(value TEXT)')
        db.execute("INSERT INTO foreign_table VALUES('synthetic preserved data')")
    foreign_before = hashlib.sha256(foreign.read_bytes()).hexdigest()
    run('csharp-foreign-schema', [*managed, 'foreign', foreign])
    if hashlib.sha256(foreign.read_bytes()).hexdigest() != foreign_before:
        raise RuntimeError('foreign database bytes changed')
    report['foreign_schema_unchanged_sha256'] = foreign_before
    database = RUN / 'fixture.sqlite3'
    run('swift-seed', [swift, 'seed', database])
    run('csharp-resume', [*managed, 'resume', database])
    run('swift-verify', [swift, 'verify', database])
    child = subprocess.Popen([str(swift), 'pending', str(database)], env=ENV, cwd=SOURCE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        ready, _, _ = select.select([child.stdout], [], [], 15)
        if not ready: raise RuntimeError('pending process did not start')
        line = child.stdout.readline()
        if not line.startswith('PENDING generation=7 '): raise RuntimeError('unexpected pending marker: ' + line)
        report['crash_child'] = {'pid': child.pid, 'marker': line.strip()}
        run('csharp-owner-lock', [*managed, 'busy', database])
        child.kill()
        report['crash_child']['returncode'] = child.wait(timeout=10)
    finally:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=10)
    run('csharp-crash-recovery', [*managed, 'recover', database])
    alias = RUN / 'fixture-hardlink.sqlite3'
    os.link(database, alias)
    run('csharp-hardlink-rejection', [*managed, 'alias', alias])
    with sqlite3.connect(database) as db:
        report['sqlite'] = {'version': sqlite3.sqlite_version, 'integrity_check': db.execute('PRAGMA integrity_check').fetchone()[0], 'foreign_key_check': db.execute('PRAGMA foreign_key_check').fetchall(), 'application_id': db.execute('PRAGMA application_id').fetchone()[0], 'user_version': db.execute('PRAGMA user_version').fetchone()[0], 'state': db.execute('SELECT * FROM p0_state').fetchall(), 'rows': db.execute('SELECT count(*) FROM p0_queue').fetchone()[0]}
        if report['sqlite']['integrity_check'] != 'ok' or report['sqlite']['foreign_key_check']:
            raise RuntimeError('database integrity failed')
    if hashlib.sha256(dylib.read_bytes()).hexdigest() != dylib_hash: raise RuntimeError('dylib changed between clients')
    report['result'] = 'passed'
except Exception as error:
    report['result'] = 'failed'
    report['error'] = str(error)
    raise
finally:
    report['sources'] = {str(p.relative_to(SOURCE)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(SOURCE.rglob('*')) if p.is_file() and p.suffix in ('.rs', '.toml', '.h', '.modulemap', '.swift', '.cs', '.csproj', '.Config', '.py', '.lock')}
    (RUN / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    print('Interop manifest: ' + str(RUN / 'manifest.json'), flush=True)
