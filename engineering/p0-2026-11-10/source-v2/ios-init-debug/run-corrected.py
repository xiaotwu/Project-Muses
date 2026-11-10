#!/usr/bin/env python3
"""Offline verification of the actual corrected helper/host; no HTTP task starts."""
from pathlib import Path
import datetime,hashlib,json,os,resource,shutil,subprocess,time
HERE=Path(__file__).resolve().parent;SOURCE=HERE.parent
INTEGRATION=Path('/Users/xiaotwu/.muses/tmp/p0-20261110-01/source/v2-integration');ROOT=INTEGRATION/'ios-init-debug';BUILD=INTEGRATION/'build'
QJS=INTEGRATION.parent/'quickjs-2026-06-04';PARSER=INTEGRATION.parent/'v2-parser'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def allocated():return sum(p.lstat().st_blocks*512 for p in [ROOT,*ROOT.rglob('*')])
def check():assert allocated()<20*1024**2 and shutil.disk_usage(ROOT).free>40*1024**3
check();assert sha(SOURCE.parent/'run_guarded.py')=='3d07c44fa82f9ee6dd11e9167fc91b63c63724a36adf366ae0f391a98479afe0'
FROZEN=ROOT/'corrected-inputs';FROZEN.mkdir(exist_ok=True)
for original,name,expected in [(BUILD/'NativeHost.v2.m','NativeHost.v2.m','f37159192477d9ddc8316d96f7884185d59b27e301e1152124bb684e99dd5fa8'),(SOURCE/'NativeInput.inc','NativeInput.inc','aa93db0a62f144dd8faf512a1a083c4ee17a45dfa7ad8d17720ef74adbfa7963')]:
    target=FROZEN/name
    if not target.exists():assert sha(original)==expected;target.write_bytes(original.read_bytes())
    assert sha(target)==expected
bundle=ROOT/'inputs/probe.bundle.js';assert sha(bundle)=='a258ea65c14b005052f88f6c12c85fef1a56764ba6fd93aee0ce8936ecb0115f'
fixture=FROZEN/'isolated-fixture.js';fixture.write_text("const result=JSON.parse(nativeEval(\"return {answer:42,label:'π🎵'};\"));if(result.answer!==42||result.label!=='π🎵')throw Error('fixture');nativeFinish(0);\n")
objects=[BUILD/(x+'.o') for x in ['quickjs','dtoa','libregexp','libunicode','cutils','p0_parser','DecodeProbe']]+[PARSER/'build'/(x+'.o') for x in ['tree-sitter','javascript','scanner']]
libraries=[INTEGRATION.parent/'v2-transport/decoder-inputs/lib'/(x+'.a') for x in ['libavformat','libavcodec','libswresample','libavutil']]
inputs=[Path(__file__),HERE/'corrected-driver.m',FROZEN/'NativeHost.v2.m',FROZEN/'NativeInput.inc',fixture,bundle,SOURCE/'transport/NativeTransport.m',SOURCE/'transport/muses_transport.h',SOURCE/'transport/muses_decode_probe.h',SOURCE/'parser/p0_parser.h',QJS/'quickjs.h',*objects,*libraries]
before={str(p):sha(p) for p in inputs};env=os.environ.copy();env.update(TMPDIR=str(ROOT/'tmp'),CLANG_MODULE_CACHE_PATH=str(ROOT/'module-cache'))
binary=ROOT/'corrected-driver';command=['clang','-std=gnu11','-O2','-g0','-fobjc-arc','-Wno-deprecated-declarations','-Wno-incompatible-pointer-types','-I'+str(FROZEN),'-I'+str(SOURCE),'-I'+str(QJS),str(HERE/'corrected-driver.m'),str(SOURCE/'transport/NativeTransport.m'),*map(str,objects),*map(str,libraries),'-lc++','-framework','Foundation','-o',str(binary)]
stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ');build=subprocess.run(command,env=env,capture_output=True,timeout=60)
prefix=ROOT/'results'/f'{stamp}-corrected';Path(str(prefix)+'-build.stdout').write_bytes(build.stdout);Path(str(prefix)+'-build.stderr').write_bytes(build.stderr)
manifest={'source_hashes':before,'command':command,'build_exit_code':build.returncode,'scratch_limit_bytes':20*1024**2,'free_before_bytes':shutil.disk_usage(ROOT).free,'runner_sha256':sha(Path(__file__))}
Path(str(prefix)+'-build.json').write_text(json.dumps(manifest,indent=2)+'\n');assert build.returncode==0,'compile failed; evidence preserved'
assert before=={str(p):sha(p) for p in inputs},'inputs changed during build';manifest['binary_sha256']=sha(binary);runs=[]
cases=[('helpers','main',1),('actual','main',6),('actual','dispatch',10),('actual','pthread512',6),('fixture','dispatch',12),('isolated','main',1)]
for mode,placement,count in cases:
    check();label='-'.join([mode,placement]);outpath=Path(str(prefix)+'-'+label+'.stdout');errpath=Path(str(prefix)+'-'+label+'.stderr');started=time.monotonic();peak=0;stop=None
    with outpath.open('wb') as out,errpath.open('wb') as err:
        process=subprocess.Popen([str(binary),str(fixture if mode=='fixture' else bundle),placement,mode,str(count)],stdout=out,stderr=err,env=env,preexec_fn=lambda:resource.setrlimit(resource.RLIMIT_CORE,(0,0)))
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
    Path(str(prefix)+'-'+label+'.json').write_text(json.dumps(record,indent=2)+'\n');runs.append(record)
    summary=next((e for e in reversed(events) if e.get('gate')=='corrected_input_summary'),{})
    print(json.dumps({'label':label,'exit':process.returncode,'stop':stop,'summary':summary}),flush=True)
manifest.update(runs=[{'label':r['label'],'exit_code':r['exit_code'],'guard_stop':r['guard_stop']} for r in runs],scratch_allocated_bytes=allocated(),network_requests=0)
Path(str(prefix)+'-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');check()
print(json.dumps({'manifest':str(prefix)+'-manifest.json','scratch_allocated_bytes':allocated()}))
assert all(r['exit_code']==0 and r['guard_stop'] is None for r in runs),'one or more offline checks failed; evidence preserved'
