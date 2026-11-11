#!/usr/bin/env python3
"""Copy exact small inputs, compile isolated local/public streaming binaries."""
from pathlib import Path
import hashlib,json,os,shutil,subprocess,time
HERE=Path(__file__).resolve().parent;P0=HERE.parent.parent
ROOT=Path('/Users/xiaotwu/.muses/tmp/p0-20261110-01');OUT=ROOT/'audio/macos-streaming'
INTEGRATION=ROOT/'source/v2-integration/build';TRANSPORT=ROOT/'source/v2-transport';PARSER=ROOT/'source/v2-parser/build'
KIT=ROOT/'audio/macos-relink/attempt-20261110-232515'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(HERE.parent/'streaming-budget.json')=='bd65403b0c768848dc061411f5526a6c190adbf9de8ba523c4614746cc5aa66c'
assert sha(ROOT/'budget.json')=='7b27e21065887ba0a9072552afa31f64c307f1df6ff8eb4c3ebac25799fe3cbc'
assert shutil.disk_usage(ROOT).free>40*1024**3
assert sum(p.stat().st_blocks*512 for p in OUT.rglob('*') if p.is_file())<96*1024**2
RUN=OUT/('build-'+time.strftime('%Y%m%d-%H%M%S',time.gmtime()));RUN.mkdir(parents=True)
INC=RUN/'include';OBJ=RUN/'objects';LIB=RUN/'lib'
for p in (INC/'transport',INC/'parser',OBJ,LIB,RUN/'fixtures'):p.mkdir(parents=True,exist_ok=True)
desktop=json.loads((INTEGRATION/'success.json').read_text())
for p,expected in desktop['source_sha256'].items():assert sha(Path(p))==expected,'root source snapshot changed'
assert sha(INTEGRATION/'NativeHost.v2.m')==desktop['generated_host_sha256']
assert sha(INTEGRATION/'probe.bundle.js')==desktop['bundle_sha256']
assert sha(INTEGRATION/'source-v2')==desktop['binary_sha256']
copies=[]
def copy(source,destination):
 expected=sha(source);shutil.copy2(source,destination);assert sha(destination)==expected
 copies.append({'source':str(source),'destination':str(destination.relative_to(RUN)),'sha256':expected,'bytes':source.stat().st_size})
copy(INTEGRATION/'NativeHost.v2.m',RUN/'NativeHost.snapshot.m');copy(INTEGRATION/'probe.bundle.js',RUN/'probe.bundle.js')
copy(P0/'source-v2/transport/NativeTransport.m',RUN/'NativeTransport.m')
copy(P0/'source-v2/transport/muses_transport.h',INC/'transport/muses_transport.h')
copy(P0/'source-v2/parser/p0_parser.h',INC/'parser/p0_parser.h')
copy(HERE/'stream_source.h',INC/'stream_source.h')
copy(KIT/'inputs/miniaudio.h',INC/'miniaudio.h');copy(KIT/'objects/miniaudio-backend.o',OBJ/'miniaudio-backend.o')
for p in (TRANSPORT/'decoder-inputs/include').rglob('*'):
 if p.is_file():
  d=INC/p.relative_to(TRANSPORT/'decoder-inputs/include');d.parent.mkdir(parents=True,exist_ok=True);copy(p,d)
for name in ('libavformat','libavcodec','libswresample','libavutil'):copy(KIT/'stock'/(name+'.a'),LIB/(name+'.a'))
qjs=ROOT/'source/quickjs-2026-06-04'
for p in qjs.glob('*.h'):copy(p,INC/p.name)
for name in ('quickjs','dtoa','libregexp','libunicode','cutils','p0_parser'):copy(INTEGRATION/(name+'.o'),OBJ/(name+'.o'))
for name in ('tree-sitter','javascript','scanner'):copy(PARSER/(name+'.o'),OBJ/(name+'.o'))
for p in (TRANSPORT/'long-fixtures').iterdir():
 if p.is_file():copy(p,RUN/'fixtures'/p.name)
(RUN/'SourceResolver.m').write_text('#define P0_IOS\n#include "NativeHost.snapshot.m"\n'+(HERE/'SourceAdapter.inc').read_text())
sources={str(p):sha(p) for p in HERE.iterdir() if p.is_file()}
(RUN/'input-manifest.json').write_text(json.dumps({'copies':copies,'source_sha256':sources,'desktop_success_sha256':sha(INTEGRATION/'success.json'),'desktop_binary_sha256':desktop['binary_sha256']},indent=2)+'\n')
env=dict(os.environ,TMPDIR=str(RUN),CLANG_MODULE_CACHE_PATH=str(RUN/'module-cache'))
sdk=subprocess.check_output(['xcrun','--sdk','macosx','--show-sdk-path'],text=True).strip()
common=['-target','arm64-apple-macos26.0','-isysroot',sdk,'-O2','-I'+str(INC),'-I'+str(INC/'transport')]
commands=[]
def run(argv,name):
 commands.append(argv);r=subprocess.run(argv,env=env,capture_output=True,timeout=60)
 (RUN/(name+'.log')).write_bytes(r.stdout+r.stderr)
 if r.returncode:print(r.stderr.decode(errors='replace')[:4000]);raise SystemExit(r.returncode)
run(['clang',*common,'-fobjc-arc','-Wno-deprecated-declarations','-Wno-incompatible-pointer-types','-c',str(RUN/'SourceResolver.m'),'-o',str(OBJ/'SourceResolver.o')],'resolver-build')
run(['clang++',*common,'-std=c++17','-pthread','-Wno-deprecated-declarations','-Wall','-Wextra','-c',str(HERE/'Streaming.cpp'),'-o',str(OBJ/'Streaming.o')],'stream-build')
for variant in ('local','public'):
 transport=OBJ/('transport-'+variant+'.o')
 run(['clang',*common,'-fobjc-arc','-Wno-deprecated-declarations',*(['-DMT_TESTING'] if variant=='local' else []),'-c',str(RUN/'NativeTransport.m'),'-o',str(transport)],variant+'-transport-build')
 objects=[OBJ/(name+'.o') for name in ('Streaming','SourceResolver','miniaudio-backend','quickjs','dtoa','libregexp','libunicode','cutils','p0_parser','tree-sitter','javascript','scanner')]
 run(['clang++',*common,*map(str,objects),str(transport),*[str(LIB/(name+'.a')) for name in ('libavformat','libavcodec','libswresample','libavutil')],'-framework','Foundation','-framework','CoreFoundation','-framework','CoreAudio','-framework','AudioToolbox','-o',str(RUN/('stream-'+variant))],variant+'-link')
assert sources=={str(p):sha(p) for p in HERE.iterdir() if p.is_file()}
assert sum(p.stat().st_blocks*512 for p in OUT.rglob('*') if p.is_file())<128*1024**2
receipt={'source_sha256':sources,'commands':commands,'binary_sha256':{v:sha(RUN/('stream-'+v)) for v in ('local','public')},'generated_source_sha256':sha(RUN/'SourceResolver.m')}
(RUN/'success.json').write_text(json.dumps(receipt,indent=2)+'\n');(OUT/'current-build.txt').write_text(str(RUN)+'\n')
print(json.dumps({'build':'pass','directory':str(RUN),'binary_sha256':receipt['binary_sha256']}))
