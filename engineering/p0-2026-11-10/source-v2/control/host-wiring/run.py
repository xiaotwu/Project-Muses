#!/usr/bin/env python3
"""No network: link frozen generated host to its existing native objects."""
from pathlib import Path
import datetime,hashlib,json,os,resource,shutil,subprocess,time
HERE=Path(__file__).resolve().parent
SOURCE=HERE.parents[1]
INTEGRATION=Path('/Users/xiaotwu/.muses/tmp/p0-20261110-01/source/v2-integration')
ROOT=INTEGRATION/'control'
OWN=ROOT/'host-wiring'
BUILD=INTEGRATION/'build'
PARSER=INTEGRATION.parent/'v2-parser'
QJS=INTEGRATION.parent/'quickjs-2026-06-04'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def allocated():return sum(p.lstat().st_blocks*512 for p in [ROOT,*ROOT.rglob('*')])
def check():
    assert allocated()<10*1024**2
    assert shutil.disk_usage(ROOT).free>=40*1024**3
OWN.mkdir(exist_ok=True)
for name in ['inputs','results']:(OWN/name).mkdir(exist_ok=True)
assert sha(SOURCE.parent/'run_guarded.py')=='3d07c44fa82f9ee6dd11e9167fc91b63c63724a36adf366ae0f391a98479afe0'
check();receipt=json.loads((BUILD/'success.json').read_text())
assert receipt['binary_sha256']=='3d8365b3c4f099e4ff5d116e7fb343e3aa325a5dfae99271bdc8abbeb5d6ec5e'
assert receipt['generated_host_sha256']=='1f10d3e9fc4591615005e718bce1ec90850c704eb4bf0bfa7188d51c995b3bb8'
host=BUILD/'NativeHost.v2.m';assert sha(host)==receipt['generated_host_sha256']
player=PARSER/'fixtures/player.js';assert sha(player)=='5f2035b38e20c1e57ad8e51ada9ea82d1eaac59f2a4603ebd851f421e3a3f5dd'
def frozen_copy(source,target):
    if target.exists():assert target.read_bytes()==source.read_bytes()
    else:target.write_bytes(source.read_bytes())
frozen_copy(host,OWN/'inputs/NativeHost.v2.m');frozen_copy(player,OWN/'inputs/player.js')
frozen_copy(BUILD/'success.json',OWN/'inputs/desktop-build.json')
objects=[BUILD/(name+'.o') for name in ['quickjs','dtoa','libregexp','libunicode','cutils','p0_parser','DecodeProbe']]
objects += [PARSER/'build'/(name+'.o') for name in ['tree-sitter','javascript','scanner']]
libraries=[INTEGRATION.parent/'v2-transport/decoder-inputs/lib'/(name+'.a') for name in ['libavformat','libavcodec','libswresample','libavutil']]
inputs=[HERE/'driver.m',OWN/'inputs/NativeHost.v2.m',SOURCE/'NativeControl.inc',SOURCE/'NativeHooks.inc',SOURCE/'transport/NativeTransport.m',SOURCE/'transport/muses_transport.h',SOURCE/'transport/muses_decode_probe.h',SOURCE/'parser/p0_parser.h',QJS/'quickjs.h',*objects,*libraries,*HERE.glob('*.js')]
before={str(p):sha(p) for p in inputs}
for p in [SOURCE/'NativeControl.inc',SOURCE/'NativeHooks.inc',SOURCE/'transport/NativeTransport.m',SOURCE/'transport/muses_transport.h',SOURCE/'transport/muses_decode_probe.h',SOURCE/'parser/p0_parser.h',QJS/'quickjs.h']:
    assert before[str(p)]==receipt['source_sha256'][str(p)]
env=os.environ.copy();env.update(TMPDIR=str(ROOT/'tmp'),CLANG_MODULE_CACHE_PATH=str(ROOT/'module-cache'))
binary=OWN/'driver'
command=['clang','-std=gnu11','-O2','-g0','-fobjc-arc','-Wno-deprecated-declarations','-Wno-incompatible-pointer-types','-I'+str(OWN/'inputs'),'-I'+str(SOURCE),'-I'+str(QJS),str(HERE/'driver.m'),str(SOURCE/'transport/NativeTransport.m'),*map(str,objects),*map(str,libraries),'-lc++','-framework','Foundation','-o',str(binary)]
stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ');record={'command':command,'source_hashes':before,'input_player_sha256':sha(player),'desktop_build_receipt_sha256':sha(OWN/'inputs/desktop-build.json'),'runner_sha256':sha(Path(__file__))};status=1
try:
    completed=subprocess.run(command,env=env,capture_output=True,timeout=60)
    (OWN/'results'/f'{stamp}-compile.stdout').write_bytes(completed.stdout);(OWN/'results'/f'{stamp}-compile.stderr').write_bytes(completed.stderr)
    record['build_exit_code']=completed.returncode
    assert completed.returncode==0,'native build failed'
    assert before=={str(p):sha(p) for p in inputs},'driver inputs changed while building'
    check();start=time.monotonic();peak=0;stop=None
    outpath=OWN/'results'/f'{stamp}.stdout';errpath=OWN/'results'/f'{stamp}.stderr'
    with outpath.open('wb') as out,errpath.open('wb') as err:
        process=subprocess.Popen([str(binary),str(HERE),str(OWN/'inputs/player.js')],env=env,stdout=out,stderr=err,preexec_fn=lambda:resource.setrlimit(resource.RLIMIT_CORE,(0,0)))
        while process.poll() is None:
            rss=subprocess.run(['ps','-o','rss=','-p',str(process.pid)],capture_output=True,text=True).stdout.strip()
            if rss:peak=max(peak,int(rss)*1024)
            if peak>256*1024**2:stop='rss_limit'
            if time.monotonic()-start>10:stop='timeout'
            if outpath.stat().st_size+errpath.stat().st_size>65536:stop='log_limit'
            if stop:process.kill();break
            time.sleep(.02)
        process.wait()
    events=[json.loads(line) for line in outpath.read_text().splitlines()]
    assert all(e.get('process_maxrss_bytes',0)<256*1024**2 for e in events),'native recorded RSS limit'
    record.update(exit_code=process.returncode,stop_reason=stop,elapsed_ms=round((time.monotonic()-start)*1000),observed_peak_rss_bytes=peak,events=events,stderr_bytes=errpath.stat().st_size,binary_sha256=sha(binary),stdout_sha256=sha(outpath),stderr_sha256=sha(errpath))
    status=0 if process.returncode==0 and not stop else 1
except Exception as error:record['runner_failure']=type(error).__name__
record.update(status=status,scratch_allocated_bytes=allocated(),scratch_limit_bytes=10*1024**2,network_requests=0)
(OWN/'results'/f'{stamp}-host-wiring.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record,indent=2));check()
raise SystemExit(status)
