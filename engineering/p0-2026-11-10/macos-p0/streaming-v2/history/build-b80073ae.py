#!/usr/bin/env python3
"""Pinned source rebuild at macOS26; separate mutable attempt output, no installs."""
from pathlib import Path
import argparse,hashlib,json,math,os,re,shutil,struct,subprocess,time,wave
HERE=Path(__file__).resolve().parent;P0=HERE.parent.parent
ROOT=Path('/Users/xiaotwu/.muses/tmp/p0-20261110-01')
SHARED=ROOT/'audio/macos-streaming';OUT=SHARED/'v2';KIT=OUT/'kit'
OLD=SHARED/'build-20261110-234930';SOURCE=ROOT/'source';PARSER=SOURCE/'v2-parser'
PLAN=HERE/'inputs-plan.json'
PUBLIC=SOURCE/'v2-integration/media/TV_SAMSUNG-aqz-KE-bpKQ-0B4A9DD0-6C69-43E2-96F4-80272707AA88.webm'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p,v):p.write_text(json.dumps(v,indent=2,sort_keys=True)+'\n')
def allocated(p):return sum(x.stat().st_blocks*512 for x in p.rglob('*') if x.is_file()) if p.exists() else 0
def budget(extra=0):
 assert sha(HERE/'budget.json')=='a1273271ae7b72d860811c7b9ce3ed59c9249c52c32938b8037ff8566c21b034'
 assert sha(HERE.parent/'streaming-budget.json')=='bd65403b0c768848dc061411f5526a6c190adbf9de8ba523c4614746cc5aa66c'
 assert allocated(OUT)+extra<96*1024**2 and allocated(SHARED)+extra<128*1024**2
 assert shutil.disk_usage(ROOT).free>40*1024**3
def prepare():
 assert not PLAN.exists();budget();rows=[]
 old=json.loads((OLD/'input-manifest.json').read_text())
 assert sha(OLD/'success.json')=='1c7b1979e74ec309aaccd7ca9dc9b467212d641c4d003e5043aa116c093e7f8f'
 for row in old['copies']:assert sha(OLD/row['destination'])==row['sha256']
 def add(source,destination):
  assert source.is_file() and not source.is_symlink()
  rows.append({'source':str(source),'destination':str(destination),'sha256':sha(source),'bytes':source.stat().st_size})
 for p in sorted((OLD/'include').rglob('*')):
  if p.is_file():add(p,Path('include')/p.relative_to(OLD/'include'))
 for p in sorted((OLD/'lib').glob('*.a')):add(p,Path('lib')/p.name)
 for name in ('NativeHost.snapshot.m','NativeTransport.m','probe.bundle.js'):add(OLD/name,Path(name))
 add(OLD/'objects/miniaudio-backend.o',Path('objects/miniaudio-backend.o'))
 for p in sorted((OLD/'fixtures').iterdir()):add(p,Path('fixtures')/p.name)
 q=SOURCE/'quickjs-2026-06-04'
 for name in ('quickjs','dtoa','libregexp','libunicode','cutils'):add(q/(name+'.c'),Path('src/quickjs')/(name+'.c'))
 for p in sorted(q.glob('*.h')):add(p,Path('src/quickjs')/p.name)
 for name,part in (('tree-sitter','lib'),('tree-sitter-javascript','src')):
  for p in sorted((PARSER/name/part).rglob('*')):
   if p.is_file():add(p,Path('src')/name/p.relative_to(PARSER/name))
  add(PARSER/name/'LICENSE',Path('src')/name/'LICENSE')
 for name in ('p0_parser.c','p0_parser.h'):add(P0/'source-v2/parser'/name,Path('src/parser')/name)
 add(P0/'source-v2/transport/DecodeProbe.cpp',Path('include/DecodeProbe.snapshot.cpp'))
 add(P0/'source-v2/transport/muses_decode_probe.h',Path('include/muses_decode_probe.h'))
 generator=Path('/opt/homebrew/bin/ffmpeg').resolve();assert generator.is_file()
 assert PUBLIC.stat().st_size==10258925
 dump(PLAN,{'script_sha256':sha(Path(__file__)),'copies':rows,
  'parent_build_sha256':sha(OLD/'success.json'),'parser_manifest_sha256':sha(P0/'source-v2/parser/manifest.json'),
  'public_reference':{'path':str(PUBLIC),'bytes':PUBLIC.stat().st_size,'sha256':sha(PUBLIC),'video_id':'aqz-KE-bpKQ','codec':'opus','purpose':'read-only offline tail reference, not copied'},
  'generator':{'path':str(generator),'sha256':sha(generator),'development_fixture_only':True,'linked_to_prototype':False}})
 print(json.dumps({'plan_sha256':sha(PLAN),'copy_bytes':sum(x['bytes'] for x in rows)}))
def inspect(path):
 result=subprocess.run(['otool','-l',str(path)],capture_output=True,text=True,check=True)
 text=result.stdout;sections=re.split(r'(?m)^([^\n]+):\n',text);members=[]
 for i in range(1,len(sections),2):
  name,body=sections[i:i+2];build=re.findall(r'cmd LC_BUILD_VERSION\s+cmdsize \d+\s+platform (\w+)\s+minos ([0-9.]+)\s+sdk ([0-9.]+)',body)
  legacy=re.findall(r'cmd LC_VERSION_MIN_MACOSX\s+cmdsize \d+\s+version ([0-9.]+)\s+sdk ([0-9.]+)',body)
  if not build and not legacy:continue
  for platform,minimum,sdk in build:
   assert platform in ('1','macos'),(path,name,platform)
   assert tuple(map(int,minimum.split('.'))) <= (26,0),(path,name,minimum)
   members.append({'member':name.split('(')[-1].rstrip(')') if '(' in name else path.name,'minimum':minimum,'sdk':sdk,'command':'LC_BUILD_VERSION'})
  for minimum,sdk in legacy:
   assert tuple(map(int,minimum.split('.'))) <= (26,0)
   members.append({'member':name,'minimum':minimum,'sdk':sdk,'command':'LC_VERSION_MIN_MACOSX'})
 assert members,('missing deployment information',path)
 if path.suffix=='.a':
  names=subprocess.check_output(['ar','-t',str(path)],text=True).splitlines();names=[n for n in names if n and not n.startswith('__.SYMDEF')]
  assert len(names)==len(members),('uninspected archive members',path,len(names),len(members))
 return {'path':str(path),'sha256':sha(path),'otool_stdout_sha256':hashlib.sha256(text.encode()).hexdigest(),'members':members}
def build(expected):
 assert sha(PLAN)==expected;plan=json.loads(PLAN.read_text());assert plan['script_sha256']==sha(Path(__file__));budget(12*1024**2)
 OUT.mkdir(exist_ok=True);RUN=OUT/('build-'+time.strftime('%Y%m%d-%H%M%S',time.gmtime()));RUN.mkdir();(RUN/'objects').mkdir()
 own={str(p):sha(p) for p in HERE.iterdir() if p.is_file()};commands=[]
 env=dict(os.environ,TMPDIR=str(RUN),CLANG_MODULE_CACHE_PATH=str(RUN/'module-cache'))
 sdk=subprocess.check_output(['xcrun','--sdk','macosx','--show-sdk-path'],text=True).strip()
 common=['-target','arm64-apple-macos26.0','-isysroot',sdk,'-O2','-g0']
 inc=['-I'+str(KIT/'include'),'-I'+str(KIT/'include/transport')]
 def run(args,name,timeout=90):
  budget();commands.append(args);result=subprocess.run(args,env=env,capture_output=True,timeout=timeout)
  (RUN/(name+'.log')).write_bytes(result.stdout+result.stderr)
  dump(RUN/'journal.json',{'commands':commands,'last':name,'last_returncode':result.returncode})
  if result.returncode:raise RuntimeError(name+' failed; retained log')
  budget()
 if not KIT.exists():
  KIT.mkdir()
  for row in plan['copies']:
   source=Path(row['source']);assert sha(source)==row['sha256'];dest=KIT/row['destination'];dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,dest);assert sha(dest)==row['sha256']
  (KIT/'objects').mkdir(exist_ok=True)
  q=KIT/'src/quickjs';ts=KIT/'src/tree-sitter/lib';js=KIT/'src/tree-sitter-javascript/src'
  for unit in ('quickjs','dtoa','libregexp','libunicode','cutils'):
   run(['clang',*common,'-std=gnu11','-DNDEBUG','-DCONFIG_VERSION="2026-06-04"','-D_GNU_SOURCE','-I'+str(q),'-c',str(q/(unit+'.c')),'-o',str(KIT/'objects'/(unit+'.o'))],unit)
  for name,source,includes in [('tree-sitter',ts/'src/lib.c',[ts/'include',ts/'src']),('javascript',js/'parser.c',[js]),('scanner',js/'scanner.c',[js]),('p0_parser',KIT/'src/parser/p0_parser.c',[ts/'include'])]:
   run(['clang',*common,'-std=gnu11',*['-I'+str(p) for p in includes],'-c',str(source),'-o',str(KIT/'objects'/(name+'.o'))],name)
  generator=Path(plan['generator']['path']);assert sha(generator)==plan['generator']['sha256']
  run([str(generator),'-version'],'fixture-generator-version')
  for name,rate,frames,codec in [('aac-short',44100,59257,'aac'),('aac-tiny',44100,3661,'aac'),('opus-short',48000,59731,'libopus')]:
   wav=KIT/'fixtures'/(name+'.wav')
   with wave.open(str(wav),'wb') as output:
    output.setnchannels(2);output.setsampwidth(2);output.setframerate(rate);state=0x12345678;data=bytearray()
    for i in range(frames):
     state=(1664525*state+1013904223)&0xffffffff;noise=((state>>8)/16777216-.5)*.07
     tone=.26*math.sin(2*math.pi*(331*i/rate+117*(i/rate)**2)) if i<frames-1600 else .47*math.sin(2*math.pi*1793*i/rate)
     left=max(-.9,min(.9,tone+noise));right=max(-.9,min(.9,tone*.73-noise));data.extend(struct.pack('<hh',round(left*32767),round(right*32767)))
    output.writeframes(data)
   target=KIT/'fixtures'/(name+('.m4a' if codec=='aac' else '.webm'))
   run([str(generator),'-nostdin','-v','error','-i',str(wav),'-c:a',codec,'-b:a','128k',*(['-movflags','+faststart'] if codec=='aac' else []),str(target)],name+'-encode')
  run([str(generator),'-nostdin','-v','error','-i',str(KIT/'fixtures/aac-short.m4a'),'-c','copy','-output_ts_offset','1','-movflags','+faststart',str(KIT/'fixtures/aac-positive-offset.m4a')],'offset-fixture')
  dump(KIT/'ready.json',{'plan_sha256':sha(PLAN),'files':{str(p.relative_to(KIT)):sha(p) for p in KIT.rglob('*') if p.is_file()}})
 else:
  ready=json.loads((KIT/'ready.json').read_text());assert ready['plan_sha256']==sha(PLAN)
  for path,h in ready['files'].items():assert sha(KIT/path)==h
 # A tiny adapter/header changes independently of the frozen copied host.
 shutil.copy2(HERE/'stream_source.h',RUN/'stream_source.h')
 (RUN/'SourceResolver.m').write_text('#define P0_IOS\n#include "'+str(KIT/'NativeHost.snapshot.m')+'"\n'+(HERE/'SourceAdapter.inc').read_text())
 actualInc=['-I'+str(RUN),*inc]
 run(['clang',*common,*actualInc,'-fobjc-arc','-Wno-deprecated-declarations','-Wno-incompatible-pointer-types','-c',str(RUN/'SourceResolver.m'),'-o',str(RUN/'objects/SourceResolver.o')],'resolver')
 run(['clang++',*common,*actualInc,'-std=c++17','-pthread','-Wno-deprecated-declarations','-Wall','-Wextra','-c',str(HERE/'Streaming.cpp'),'-o',str(RUN/'objects/Streaming.o')],'stream')
 run(['clang++',*common,*actualInc,'-std=c++17','-Wno-deprecated-declarations','-c',str(HERE/'Reference.cpp'),'-o',str(RUN/'objects/Reference.o')],'reference')
 objects=[KIT/'objects'/(n+'.o') for n in ('miniaudio-backend','quickjs','dtoa','libregexp','libunicode','cutils','tree-sitter','javascript','scanner','p0_parser')]
 libs=sorted((KIT/'lib').glob('*.a'));frameworks=['-framework','Foundation','-framework','CoreFoundation','-framework','CoreAudio','-framework','AudioToolbox']
 for variant in ('local','public'):
  transport=RUN/'objects'/('transport-'+variant+'.o')
  run(['clang',*common,*actualInc,'-fobjc-arc','-Wno-deprecated-declarations',*(['-DMT_TESTING'] if variant=='local' else []),'-c',str(KIT/'NativeTransport.m'),'-o',str(transport)],variant+'-transport')
  run(['clang++',*common,str(RUN/'objects/Streaming.o'),str(RUN/'objects/SourceResolver.o'),*map(str,objects),str(transport),*map(str,libs),*frameworks,'-o',str(RUN/('stream-'+variant))],variant+'-link')
 run(['clang++',*common,str(RUN/'objects/Reference.o'),str(RUN/'objects/transport-local.o'),*map(str,libs),'-framework','Foundation','-o',str(RUN/'reference')],'reference-link')
 deployments=[inspect(p) for p in [*objects,*libs,*sorted((RUN/'objects').glob('*.o')),RUN/'stream-local',RUN/'stream-public',RUN/'reference']]
 dump(RUN/'deployment.json',{'method':'otool -l every linked object/archive member and final binary; ar -t count cross-check','maximum_minimum_version':'26.0','runtime_on_macos_26':False,'artifacts':deployments})
 assert own=={str(p):sha(p) for p in HERE.iterdir() if p.is_file()};budget()
 dump(RUN/'success.json',{'source_sha256':own,'input_plan_sha256':sha(PLAN),'kit_ready_sha256':sha(KIT/'ready.json'),'commands':commands,'deployment_sha256':sha(RUN/'deployment.json'),
  'binary_sha256':{name:sha(RUN/name) for name in ('stream-local','stream-public','reference')}})
 (OUT/'current-build.txt').write_text(str(RUN)+'\n');print(json.dumps({'build':'pass','directory':str(RUN),'owned_allocated_bytes':allocated(OUT),'shared_allocated_bytes':allocated(SHARED)}))
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--prepare',action='store_true');parser.add_argument('--plan-sha');args=parser.parse_args()
 prepare() if args.prepare else build(args.plan_sha)
