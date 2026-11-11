#!/usr/bin/env python3
"""Build the unchanged original audio ABI; six-second shared output is muted."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

HERE=Path(__file__).resolve().parent
P0=HERE.parent.parent
ROOT=Path('/Users/xiaotwu/.muses/tmp/p0-20261110-01')
OWNED=ROOT/'source/v2-transport'
OUT=OWNED/('real-audio-abi-'+time.strftime('%Y%m%d-%H%M%S',time.gmtime()))
TRASH=Path('/Users/xiaotwu/.Trash/Muses-P0-20261110-01')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(ROOT/'budget.json')=='7b27e21065887ba0a9072552afa31f64c307f1df6ff8eb4c3ebac25799fe3cbc'
free=shutil.disk_usage(ROOT).free
owned=sum(p.stat().st_blocks*512 for p in OWNED.rglob('*') if p.is_file())
assert free>40*1024**3 and owned<160*1024**2
original=json.loads((P0/'audio/evidence/artifact-manifest.json').read_text())
locked=json.loads((P0/'audio/source-lock.json').read_text())
OUT.mkdir(parents=True)
provenance={'before_free_bytes':free,'before_owned_allocated_bytes':owned,'owned_cap_bytes':200*1024**2,'copies':[],'readonly_inputs':[]}
for source,name,digest in [
 (TRASH/'audio--sources/miniaudio.h','miniaudio.h',locked['miniaudio']['sha256']),
 (TRASH/'audio--macosx/miniaudio-backend.o','miniaudio-backend.o',original['macosx/miniaudio-backend.o']['sha256'])]:
 assert source.is_file() and sha(source)==digest
 shutil.copy2(source,OUT/name)
 assert sha(OUT/name)==digest
 provenance['copies'].append({'source':str(source),'destination':name,'bytes':source.stat().st_size,'sha256':digest})
inputs=OWNED/'decoder-inputs'
libs=[]
for name in ('avformat','avcodec','swresample','avutil'):
 p=inputs/'lib'/('lib'+name+'.a');expected=original['macosx/lib'+name+'/lib'+name+'.a']['sha256']
 assert sha(p)==expected;libs.append(p);provenance['readonly_inputs'].append({'path':str(p),'sha256':expected,'bytes':p.stat().st_size})
media=ROOT/'source/v2-integration/media'
samples=[(media/'TV_SAMSUNG-aqz-KE-bpKQ-277F8A82-7284-4160-865A-C0D66402825F.m4a',15479228,'f9bf28dcef3bd5b8cad072301303d5e22fdb15252c08520786fb730932828f03'),
 (media/'TV_SAMSUNG-aqz-KE-bpKQ-0B4A9DD0-6C69-43E2-96F4-80272707AA88.webm',10258925,'08dd9fc36d077d0dd39b51f039dc35135e678aa16bb405175d85d34af12605f6')]
for p,length,digest in samples:
 assert p.stat().st_size==length and sha(p)==digest
 provenance['readonly_inputs'].append({'path':str(p),'sha256':digest,'bytes':length})
files=[HERE/'run_real_abi.py',HERE/'RealMediaABITests.cpp',P0/'audio/probe.cpp',P0/'audio/p0_audio.h']
before={str(p):sha(p) for p in files}
(OUT/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
env=dict(os.environ,TMPDIR=str(OUT),CLANG_MODULE_CACHE_PATH=str(OUT/'module-cache'))
sdk=subprocess.check_output(['xcrun','--sdk','macosx','--show-sdk-path'],text=True).strip()
binary=OUT/'real-media-audio-abi'
command=['clang++','-std=c++17','-O2','-pthread','-target','arm64-apple-macos26.0','-isysroot',sdk,
 '-DP0_LIBRARY_ONLY','-I'+str(inputs/'include'),'-I'+str(OUT),'-Wno-deprecated-declarations',
 str(HERE/'RealMediaABITests.cpp'),str(P0/'audio/probe.cpp'),str(OUT/'miniaudio-backend.o'),*map(str,libs),
 '-framework','CoreFoundation','-framework','CoreAudio','-framework','AudioToolbox','-o',str(binary)]
result=subprocess.run(command,env=env,capture_output=True,timeout=45)
(OUT/'build.log').write_bytes(result.stdout+result.stderr)
if result.returncode:print(result.stderr.decode(errors='replace')[:4000]);raise SystemExit(result.returncode)
started=time.monotonic();peak=0;reason=None
with (OUT/'results.jsonl').open('wb') as stdout,(OUT/'stderr.log').open('wb') as stderr:
 proc=subprocess.Popen([str(binary),*[str(s[0]) for s in samples]],env=env,stdout=stdout,stderr=stderr)
 while proc.poll() is None:
  usage=subprocess.run(['ps','-o','rss=','-p',str(proc.pid)],capture_output=True,text=True).stdout.strip()
  if usage:peak=max(peak,int(usage)*1024)
  if peak>256*1024**2 or time.monotonic()-started>15:
   reason='observed_rss_limit' if peak>256*1024**2 else 'external_deadline';proc.terminate();break
  time.sleep(.1)
 try:code=proc.wait(timeout=3)
 except subprocess.TimeoutExpired:proc.kill();code=proc.wait()
assert before=={str(p):sha(p) for p in files}
for p,length,digest in samples:assert p.stat().st_size==length and sha(p)==digest
receipt={'source_sha256':before,'command':command,'exit_code':code,'stop_reason':reason,
 'sampled_peak_rss_bytes':peak,'rss_observation_limit_bytes':256*1024**2,'rss_is_hard_allocator_limit':False,
 'network':False,'phone':False,'audible':False,'human_audibility':'not_tested',
 'files':{p.name:{'sha256':sha(p),'bytes':p.stat().st_size} for p in OUT.iterdir() if p.is_file()}}
(OUT/'manifest.json').write_text(json.dumps(receipt,indent=2)+'\n')
print((OUT/'results.jsonl').read_text());print(json.dumps({'directory':str(OUT),'exit_code':code,'sampled_peak_rss_bytes':peak}))
raise SystemExit(code if not reason else 125)
