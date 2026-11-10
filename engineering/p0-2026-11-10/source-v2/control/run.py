#!/usr/bin/env python3
"""Guarded local control tests, under a separate 10 MiB scratch sublimit."""
from pathlib import Path
import datetime,hashlib,json,os,shutil,subprocess,time
HERE=Path(__file__).resolve().parent
ROOT=Path('/Users/xiaotwu/.muses/tmp/p0-20261110-01/source/v2-integration/control')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def allocated():return sum(p.lstat().st_blocks*512 for p in [ROOT,*ROOT.rglob('*')])
ROOT.mkdir(exist_ok=True)
for name in ['build','tmp','module-cache','results']:(ROOT/name).mkdir(exist_ok=True)
def check():
    assert allocated()<10*1024**2
    assert shutil.disk_usage(ROOT).free>=40*1024**3
assert sha(HERE.parents[1]/'run_guarded.py')=='3d07c44fa82f9ee6dd11e9167fc91b63c63724a36adf366ae0f391a98479afe0'
check();env=os.environ.copy();env.update(TMPDIR=str(ROOT/'tmp'),CLANG_MODULE_CACHE_PATH=str(ROOT/'module-cache'))
stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
commands=[];runs=[];status=0
try:
    for name in ['control_tests','production_smoke']:
        command=['cc','-std=gnu11','-O2','-g0','-fobjc-arc','-framework','Foundation','-pthread',str(HERE/(name+'.m')),'-o',str(ROOT/'build'/name)]
        commands.append(command);subprocess.run(command,env=env,check=True);check()
    sdk=subprocess.check_output(['xcrun','--sdk','iphoneos','--show-sdk-path'],text=True).strip()
    command=['xcrun','--sdk','iphoneos','clang','-target','arm64-apple-ios17.0','-isysroot',sdk,'-std=gnu11','-O2','-g0','-fobjc-arc','-c',str(HERE/'production_smoke.m'),'-o',str(ROOT/'build/control-ios.o')]
    commands.append(command);subprocess.run(command,env=env,check=True);check()
    for name in ['control_tests','production_smoke']:
        path=ROOT/'build'/name;started=time.monotonic();completed=subprocess.run([str(path)],env=env,capture_output=True,timeout=10)
        assert len(completed.stdout)+len(completed.stderr)<16384
        (ROOT/'results'/f'{stamp}-{name}.stdout').write_bytes(completed.stdout)
        (ROOT/'results'/f'{stamp}-{name}.stderr').write_bytes(completed.stderr)
        runs.append({'name':name,'exit_code':completed.returncode,'elapsed_ms':round((time.monotonic()-started)*1000),'stdout':completed.stdout.decode(),'stderr':completed.stderr.decode(),'binary_sha256':sha(path)})
        if completed.returncode:status=1
except Exception as error:
    runs.append({'build_or_runner_failure':type(error).__name__});status=1
manifest={'commands':commands,'runs':runs,'source_hashes':{str(p.relative_to(HERE.parent)):sha(p) for p in [HERE.parent/'NativeControl.inc',HERE/'control_tests.m',HERE/'production_smoke.m',HERE/'run.py']},'output_hashes':{p.name:sha(p) for p in (ROOT/'build').iterdir() if p.is_file()},'scratch_limit_bytes':10*1024**2,'scratch_allocated_bytes':allocated(),'actual_free_bytes':shutil.disk_usage(ROOT).free,'network_requests':0,'status':status}
(ROOT/'results'/f'{stamp}-control.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps(manifest,indent=2));check()
raise SystemExit(status)
