#!/usr/bin/env python3
"""Offline candidate-5 init diagnosis; 20 MiB scratch, 10 s / 256 MiB per run."""
from pathlib import Path
import datetime,hashlib,json,os,resource,shutil,subprocess,time
HERE=Path(__file__).resolve().parent;SOURCE=HERE.parent
INTEGRATION=Path('/Users/xiaotwu/.muses/tmp/p0-20261110-01/source/v2-integration');ROOT=INTEGRATION/'ios-init-debug';BUILD=INTEGRATION/'build'
QJS=INTEGRATION.parent/'quickjs-2026-06-04';PARSER=INTEGRATION.parent/'v2-parser'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def allocated():return sum(p.lstat().st_blocks*512 for p in [ROOT,*ROOT.rglob('*')])
ROOT.mkdir(exist_ok=True)
for n in ['inputs','tmp','module-cache','results']:(ROOT/n).mkdir(exist_ok=True)
def check():assert allocated()<20*1024**2 and shutil.disk_usage(ROOT).free>40*1024**3
check();assert sha(SOURCE.parent/'run_guarded.py')=='3d07c44fa82f9ee6dd11e9167fc91b63c63724a36adf366ae0f391a98479afe0'
for original,name,expected in [(BUILD/'NativeHost.v2.m','NativeHost.v2.m','90e9952071fee1f3eb193538399ba85d43b9390fc9a156e64c656b9a74ddb5ce'),(INTEGRATION/'iphoneos/MusesP0Source.app/probe.bundle.js','probe.bundle.js','a258ea65c14b005052f88f6c12c85fef1a56764ba6fd93aee0ce8936ecb0115f')]:
    target=ROOT/'inputs'/name
    if not target.exists():assert sha(original)==expected;target.write_bytes(original.read_bytes())
    assert sha(target)==expected
objects=[BUILD/(x+'.o') for x in ['quickjs','dtoa','libregexp','libunicode','cutils','p0_parser','DecodeProbe']]+[PARSER/'build'/(x+'.o') for x in ['tree-sitter','javascript','scanner']]
libraries=[INTEGRATION.parent/'v2-transport/decoder-inputs/lib'/(x+'.a') for x in ['libavformat','libavcodec','libswresample','libavutil']]
inputs=[HERE/'driver.m',ROOT/'inputs/NativeHost.v2.m',ROOT/'inputs/probe.bundle.js',SOURCE/'transport/NativeTransport.m',SOURCE/'transport/muses_transport.h',SOURCE/'transport/muses_decode_probe.h',SOURCE/'parser/p0_parser.h',QJS/'quickjs.h',*objects,*libraries]
before={str(p):sha(p) for p in inputs};env=os.environ.copy();env.update(TMPDIR=str(ROOT/'tmp'),CLANG_MODULE_CACHE_PATH=str(ROOT/'module-cache'))
command=['clang','-std=gnu11','-O2','-g0','-fobjc-arc','-Wno-deprecated-declarations','-Wno-incompatible-pointer-types','-I'+str(ROOT/'inputs'),'-I'+str(SOURCE),'-I'+str(QJS),str(HERE/'driver.m'),str(SOURCE/'transport/NativeTransport.m'),*map(str,objects),*map(str,libraries),'-lc++','-framework','Foundation','-o',str(ROOT/'driver')]
stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ');build=subprocess.run(command,env=env,capture_output=True,timeout=60)
(ROOT/'results'/f'{stamp}-build.stdout').write_bytes(build.stdout);(ROOT/'results'/f'{stamp}-build.stderr').write_bytes(build.stderr)
manifest={'source_hashes':before,'command':command,'build_exit_code':build.returncode,'scratch_limit_bytes':20*1024**2,'free_before_bytes':shutil.disk_usage(ROOT).free,'runner_sha256':sha(Path(__file__))}
(ROOT/'results'/f'{stamp}-build.json').write_text(json.dumps(manifest,indent=2)+'\n')
assert build.returncode==0,'compile failed; evidence preserved'
assert before=={str(p):sha(p) for p in inputs},'inputs changed during build'
manifest['binary_sha256']=sha(ROOT/'driver');runs=[]
cases=[('compile','nul','main',6),('compile','at','main',6),('compile','brace','main',3),('compile','space','main',3),('compile','ndata','main',6),('compile','nul','dispatch',10),('compile','at','dispatch',4),('compile','nul','pthread512',6),('compile','nul','pthread2m',6),('execute-blocked','nul','dispatch',10),('execute-blocked','ndata','dispatch',10)]
for mode,tail,placement,count in cases:
    check();label='-'.join([mode,tail,placement]);outpath=ROOT/'results'/f'{stamp}-{label}.stdout';errpath=ROOT/'results'/f'{stamp}-{label}.stderr'
    started=time.monotonic();peak=0;stop=None
    with outpath.open('wb') as out,errpath.open('wb') as err:
        process=subprocess.Popen([str(ROOT/'driver'),str(ROOT/'inputs/probe.bundle.js'),mode,tail,placement,str(count)],stdout=out,stderr=err,env=env,preexec_fn=lambda:resource.setrlimit(resource.RLIMIT_CORE,(0,0)))
        while process.poll() is None:
            row=subprocess.run(['ps','-o','rss=','-p',str(process.pid)],capture_output=True,text=True).stdout.strip()
            if row:peak=max(peak,int(row)*1024)
            if peak>256*1024**2:stop='rss_limit'
            if time.monotonic()-started>10:stop='deadline'
            if outpath.stat().st_size+errpath.stat().st_size>65536:stop='log_limit'
            if stop:process.kill();break
            time.sleep(.02)
        process.wait()
    events=[]
    for line in outpath.read_bytes().splitlines():
        try:events.append(json.loads(line))
        except (UnicodeDecodeError,json.JSONDecodeError):events.append({'unparsed_line_bytes':len(line)})
    record={'label':label,'exit_code':process.returncode,'guard_stop':stop,'elapsed_ms':round((time.monotonic()-started)*1000),'sampled_peak_rss_bytes':peak,'events':events,'stderr_bytes':errpath.stat().st_size,'stdout_sha256':sha(outpath),'stderr_sha256':sha(errpath),'binary_sha256':manifest['binary_sha256']}
    (ROOT/'results'/f'{stamp}-{label}.json').write_text(json.dumps(record,indent=2)+'\n');runs.append(record)
    print(json.dumps({'label':label,'exit':process.returncode,'stop':stop,'cases':sum(e.get('phase')=='case' for e in events),'types':sorted(set(e.get('exception_category') for e in events if e.get('phase')=='case')),'native_peak_rss':max(e.get('process_maxrss_bytes',0) for e in events) if events else 0}),flush=True)
manifest.update(runs=[{'label':r['label'],'exit_code':r['exit_code'],'guard_stop':r['guard_stop']} for r in runs],scratch_allocated_bytes=allocated(),network_requests=0)
(ROOT/'results'/f'{stamp}-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');check()
print(json.dumps({'manifest':str(ROOT/'results'/f'{stamp}-manifest.json'),'scratch_allocated_bytes':allocated()}))
