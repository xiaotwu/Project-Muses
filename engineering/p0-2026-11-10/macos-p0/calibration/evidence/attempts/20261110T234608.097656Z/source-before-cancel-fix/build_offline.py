#!/usr/bin/env python3
"""Build an idle app and test synthetic PCM; never launch an audio-device app."""
from pathlib import Path
import datetime,hashlib,json,os,plistlib,resource,shutil,subprocess,time
HERE=Path(__file__).resolve().parent;P0=HERE.parents[1]
SCRATCH=Path('/Users/xiaotwu/.muses/tmp/p0-20261110-01/interop/macos-calibration')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def allocated():return sum(p.lstat().st_blocks*512 for p in [SCRATCH,*SCRATCH.rglob('*')])
budget_path=HERE.parent/'calibration-budget.json'
assert sha(budget_path)=='c5febd8b5b649d0848edc2ceef083dd8c0de616933ac321abbc676ea4dadf871'
assert sha(P0/'run_guarded.py')=='3d07c44fa82f9ee6dd11e9167fc91b63c63724a36adf366ae0f391a98479afe0'
SCRATCH.mkdir(exist_ok=True)
for name in ['tmp','module-cache','attempts']:(SCRATCH/name).mkdir(exist_ok=True)
def check():assert allocated()<64*1024**2 and shutil.disk_usage(SCRATCH).free>=40*1024**3
check();stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ');ATTEMPT=SCRATCH/'attempts'/stamp;ATTEMPT.mkdir()
env=os.environ.copy();env.update(TMPDIR=str(SCRATCH/'tmp'),CLANG_MODULE_CACHE_PATH=str(SCRATCH/'module-cache'))
source_files=[HERE/n for n in ['calibration.h','calibration.c','CalibrationApp.m','offline-tests.c','entitlements.plist','build_offline.py']]
manifest={'source_hashes':{p.name:sha(p) for p in source_files},'budget_sha256':sha(budget_path),'free_before_bytes':shutil.disk_usage(SCRATCH).free,'scratch_limit_bytes':64*1024**2,'commands':[],'app_launched':False,'microphone_permission_requested':False,'physical_audio_run':False}
def command(label,args,timeout=40):
    check();result=subprocess.run(args,env=env,capture_output=True,timeout=timeout)
    (ATTEMPT/(label+'.stdout')).write_bytes(result.stdout);(ATTEMPT/(label+'.stderr')).write_bytes(result.stderr)
    manifest['commands'].append({'label':label,'args':args,'exit':result.returncode,'stdout_sha256':sha(ATTEMPT/(label+'.stdout')),'stderr_sha256':sha(ATTEMPT/(label+'.stderr'))})
    (ATTEMPT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    if result.returncode:raise RuntimeError(label+' failed; complete diagnostic preserved in '+str(ATTEMPT/(label+'.stderr')))
    return result
common=['clang','-std=gnu11','-O2','-Wall','-Wextra','-Werror','-mmacosx-version-min=26.0','-I'+str(HERE)]
core=ATTEMPT/'calibration.o';command('compile-core',common+['-c',str(HERE/'calibration.c'),'-o',str(core)])
test=ATTEMPT/'offline-tests';command('compile-tests',common+[str(core),str(HERE/'offline-tests.c'),'-o',str(test)])
app=ATTEMPT/'MusesAcousticCalibration.app';contents=app/'Contents';(contents/'MacOS').mkdir(parents=True);(contents/'Resources').mkdir()
binary=contents/'MacOS/MusesAcousticCalibration'
command('compile-app',common+['-fobjc-arc','-Wno-deprecated-declarations',str(core),str(HERE/'CalibrationApp.m'),'-framework','AppKit','-framework','Foundation','-framework','AVFoundation','-framework','AVFAudio','-framework','CoreAudio','-o',str(binary)])
info={'CFBundleIdentifier':'org.muses.p0.acoustic-calibration.20261110','CFBundleName':'Muses Acoustic Calibration','CFBundleDisplayName':'Muses 声学校准','CFBundleExecutable':'MusesAcousticCalibration','CFBundlePackageType':'APPL','CFBundleVersion':'1','CFBundleShortVersionString':'0.1','LSMinimumSystemVersion':'26.0','NSPrincipalClass':'NSApplication','NSHighResolutionCapable':True,'NSMicrophoneUsageDescription':'仅在你点击开始短时校准后，采集最多8秒环境音，用于确认内建扬声器的校准声音到达麦克风的时间。原始录音不保存。'}
info['P0CalibrationSourceSetSHA256']=hashlib.sha256(json.dumps(manifest['source_hashes'],sort_keys=True).encode()).hexdigest()
(contents/'Info.plist').write_bytes(plistlib.dumps(info));command('sign-app',['codesign','--force','--sign','-','--timestamp=none','--options','runtime','--entitlements',str(HERE/'entitlements.plist'),str(app)])
command('verify-signature',['codesign','--verify','--deep','--strict',str(app)])
links=command('test-dependencies',['otool','-L',str(test)]).stdout.decode();assert 'AVFoundation' not in links and 'CoreAudio' not in links and 'AVFAudio' not in links
out=ATTEMPT/'tests.stdout';err=ATTEMPT/'tests.stderr';started=time.monotonic();peak=0;stop=None
with out.open('wb') as stdout,err.open('wb') as stderr:
    process=subprocess.Popen([str(test)],stdout=stdout,stderr=stderr,env=env,preexec_fn=lambda:resource.setrlimit(resource.RLIMIT_CORE,(0,0)))
    while process.poll() is None:
        rss=subprocess.run(['ps','-o','rss=','-p',str(process.pid)],capture_output=True,text=True).stdout.strip()
        if rss:peak=max(peak,int(rss)*1024)
        if peak>256*1024**2:stop='rss_limit'
        if time.monotonic()-started>60:stop='time_limit'
        if out.stat().st_size+err.stat().st_size>128*1024:stop='output_limit'
        if stop:process.kill();break
        time.sleep(.05)
    process.wait()
manifest['offline_test']={'exit':process.returncode,'stop':stop,'elapsed_ms':round((time.monotonic()-started)*1000),'sampled_peak_rss_bytes':peak,'binary_sha256':sha(test),'stdout_sha256':sha(out),'stderr_sha256':sha(err)}
manifest['app']={'path':str(app),'binary_sha256':sha(binary),'info_sha256':sha(contents/'Info.plist'),'signing':'ad hoc, hardened runtime, audio-input entitlement; not notarized','launched':False}
manifest['source_hashes_after']={p.name:sha(p) for p in source_files};assert manifest['source_hashes']==manifest['source_hashes_after']
manifest['scratch_allocated_bytes']=allocated();manifest['free_after_bytes']=shutil.disk_usage(SCRATCH).free
(ATTEMPT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');check()
events=[json.loads(line) for line in out.read_text().splitlines()];summary=events[-1]
print(json.dumps({'attempt':str(ATTEMPT),'test_summary':summary,'test_exit':process.returncode,'app_launched':False,'scratch_allocated_bytes':allocated()}))
assert process.returncode==0 and stop is None,'offline tests failed; evidence preserved'
