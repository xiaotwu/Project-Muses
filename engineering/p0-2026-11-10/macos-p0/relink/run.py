#!/usr/bin/env python3
"""Offline, guarded source rebuild and static-library replacement experiment."""
import argparse
import difflib
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import signal
import subprocess
import tarfile
import time

HERE=Path(__file__).resolve().parent
P0=HERE.parent.parent
ROOT=Path('/Users/xiaotwu/.muses/tmp/p0-20261110-01')
OLD_TRASH=Path('/Users/xiaotwu/.Trash/Muses-P0-20261110-01')
def sha(path):
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):digest.update(chunk)
    return digest.hexdigest()
def allocated(path):
    return sum(p.stat().st_blocks*512 for p in path.rglob('*') if p.is_file()) if path.exists() else 0
parser=argparse.ArgumentParser()
parser.add_argument('--plan-sha',required=True);parser.add_argument('--script-sha',required=True)
args=parser.parse_args()
assert sha(HERE/'plan.json')==args.plan_sha and sha(Path(__file__))==args.script_sha
plan=json.loads((HERE/'plan.json').read_text())
assert sha(P0/'macos-p0/stage-budget.json')==plan['stage_budget_sha256']
assert sha(P0/'run_guarded.py')==plan['parent_guard_sha256']
assert sha(ROOT/'budget.json')==plan['parent_budget_sha256']
OWNED=Path(plan['scratch'])
assert shutil.disk_usage(ROOT).free>plan['free_floor_bytes']+256*1024**2
assert allocated(OWNED)<plan['scratch_limit_bytes']-160*1024**2,'not enough room for a fresh attempt'
OUT=OWNED/('attempt-'+time.strftime('%Y%m%d-%H%M%S',time.gmtime()))
assert not OUT.exists();OUT.mkdir(parents=True)
INPUT=OUT/'inputs';SOURCE=OUT/'work/sources/ffmpeg-8.0';BUILD=OUT/'work/build';OBJECTS=OUT/'objects';LOG=OUT/'logs'
for path in (INPUT,BUILD,OBJECTS,LOG,OUT/'stock',OUT/'replacement',OUT/'notices'):
    path.mkdir(parents=True,exist_ok=True)
env=dict(os.environ,TMPDIR=str(OUT/'work'),CLANG_MODULE_CACHE_PATH=str(OUT/'work/module-cache'),LC_ALL='C')
entries=[];command_index=0;high=0
def record(stage,state,**values):
    entry={'unix':time.time(),'stage':stage,'state':state,**values}
    with (OUT/'journal.jsonl').open('a') as stream:stream.write(json.dumps(entry,sort_keys=True)+'\n')
    print(json.dumps(entry),flush=True)
def check_budget():
    global high
    usage=allocated(OWNED);high=max(high,usage)
    assert usage<plan['scratch_limit_bytes']-16*1024**2,'scratch stop threshold'
    assert shutil.disk_usage(ROOT).free>plan['free_floor_bytes']+256*1024**2,'free space stop threshold'
def command(argv,name,timeout=180,cwd=None):
    global command_index
    check_budget();command_index+=1
    logfile=LOG/(f'{command_index:02d}-'+name+'.log')
    item={'argv':list(map(str,argv)),'cwd':str(cwd or OUT),'log':str(logfile.relative_to(OUT))}
    entries.append(item)
    with logfile.open('wb') as stream:
        proc=subprocess.Popen(item['argv'],cwd=cwd or OUT,env=env,stdout=stream,stderr=subprocess.STDOUT)
        started=time.monotonic()
        while proc.poll() is None:
            try:
                check_budget()
                assert time.monotonic()-started<timeout,'command deadline'
            except BaseException as error:
                # Under run_guarded this process owns its isolated task group.
                record(name,'stopped',reason=str(error))
                if os.getpgrp()==os.getpid():os.killpg(os.getpgrp(),signal.SIGTERM)
                proc.terminate();raise
            time.sleep(.5)
        item['returncode']=proc.returncode;item['elapsed_seconds']=time.monotonic()-started
    if proc.returncode:
        record(name,'failed',returncode=proc.returncode,log=item['log'])
        raise RuntimeError(f'{name} failed; preserve {logfile}')
    return logfile.read_text(errors='replace')
def copy_checked(source,destination,expected):
    assert source.is_file() and sha(source)==expected,str(source)
    shutil.copy2(source,destination);assert sha(destination)==expected
    return {'source':str(source),'destination':str(destination.relative_to(OUT)),'bytes':source.stat().st_size,'sha256':expected}
def fixture_output(text):
    return [json.loads(line) for line in text.splitlines() if line.startswith('{')]
try:
    record('preflight','pass',plan_sha256=args.plan_sha,script_sha256=args.script_sha,free_bytes=shutil.disk_usage(ROOT).free)
    before_sources={str(p):sha(p) for p in (HERE/'plan.json',HERE/'run.py',P0/'audio/probe.cpp',P0/'audio/backend.mm',P0/'audio/p0_audio.h',P0/'audio/source-lock.json',P0.parent.parent/'LICENSE')}
    (OUT/'execution-lock.json').write_text(json.dumps({'source_sha256':before_sources,'plan':plan},indent=2)+'\n')
    copies=[]
    copies.append(copy_checked(OLD_TRASH/'audio--ffmpeg-8.0.tar.xz',INPUT/'ffmpeg-8.0.tar.xz',plan['ffmpeg_archive_sha256']))
    copies.append(copy_checked(OLD_TRASH/'audio--sources/miniaudio.h',INPUT/'miniaudio.h',plan['miniaudio_header_sha256']))
    fixture_manifest=json.loads((P0/'audio/evidence/fixture-manifest.json').read_text())
    for name in ('tone-a.m4a','tone-b.webm'):
        copies.append(copy_checked(OLD_TRASH/'audio--fixtures'/name,INPUT/name,fixture_manifest[name]['sha256']))
    for name in ('probe.cpp','backend.mm','p0_audio.h'):
        copies.append(copy_checked(P0/'audio'/name,INPUT/name,sha(P0/'audio'/name)))
    (OUT/'copy-provenance.json').write_text(json.dumps(copies,indent=2)+'\n')
    with tarfile.open(INPUT/'ffmpeg-8.0.tar.xz') as tar:
        members=tar.getmembers()
        assert sum(m.size for m in members if m.isfile())<90*1024**2
        for member in members:
            path=PurePosixPath(member.name)
            assert not path.is_absolute() and '..' not in path.parts and path.parts[0]=='ffmpeg-8.0'
            assert member.isfile() or member.isdir(),'unexpected archive node type'
        for member in members:
            destination=OUT/'work/sources'/member.name
            if member.isdir():destination.mkdir(parents=True,exist_ok=True)
            else:
                destination.parent.mkdir(parents=True,exist_ok=True)
                with tar.extractfile(member) as src,destination.open('wb') as dst:shutil.copyfileobj(src,dst)
                destination.chmod(member.mode & 0o777)
    check_budget();record('exact_sources','pass',copies=len(copies),archive_sha256=sha(INPUT/'ffmpeg-8.0.tar.xz'))
    for name in ('COPYING.LGPLv2.1','LICENSE.md'):
        shutil.copy2(SOURCE/name,OUT/'notices'/('FFmpeg-'+name))
    shutil.copy2(P0.parent.parent/'LICENSE',OUT/'notices/Muses-MIT-LICENSE.txt')
    header=(INPUT/'miniaudio.h').read_text()
    assert 'ALTERNATIVE 2 - MIT No Attribution' in header
    # Retain the full authoritative dual-license tail, not a paraphrased license.
    license_start=header.rfind('This software is available as a choice of the following licenses')
    assert license_start>=0,'miniaudio license section missing'
    (OUT/'notices/miniaudio-license.txt').write_text(header[license_start:])
    (OUT/'notices/NOTICES.md').write_text('''# P0 relink experiment notices

FFmpeg 8.0: exact release source archive is supplied in inputs/ffmpeg-8.0.tar.xz; selected configuration reports LGPL version 2.1 or later. The archive also contains optional code under other licenses; GPL/version3/nonfree components are disabled for this build. See FFmpeg-LICENSE.md and FFmpeg-COPYING.LGPLv2.1. Source: https://ffmpeg.org/releases/ffmpeg-8.0.tar.xz

miniaudio 0.11.26: exact header is supplied in inputs/miniaudio.h, with its complete license text. MIT No Attribution alternative selected. Source: https://github.com/mackron/miniaudio/tree/0.11.26

Original Muses P0 probe.cpp, backend.mm and p0_audio.h are marked MIT in their source. They are copied unchanged and supplied beside the frozen application objects. The two tone fixtures were generated for P0; no personal audio was used. Homebrew FFmpeg was used only in the earlier fixture-generation step, never linked into this prototype.

replacement.patch records the only intentional library-source modification: an observable av_version_info marker. This is not a decoder improvement, a library upgrade, or a legal determination about a product distribution. No production app, release, Developer ID identity or notarization was used.
''')
    sdk=subprocess.check_output(['xcrun','--sdk','macosx','--show-sdk-path'],text=True).strip()
    toolchain={name:subprocess.check_output(argv,text=True,stderr=subprocess.STDOUT).strip() for name,argv in {
        'clang':['clang','--version'],'sdk_version':['xcrun','--sdk','macosx','--show-sdk-version'],
        'xcode':['xcodebuild','-version'],'os':['sw_vers'],'make':['make','--version'],
        'linker':['xcrun','ld','-version_details']}.items()}
    (OUT/'toolchain.json').write_text(json.dumps({'sdk':sdk,**toolchain},indent=2)+'\n')
    original_config=json.loads((OLD_TRASH/'audio--macosx/configure-command.json').read_text())
    config=[str(SOURCE/'configure'),*original_config[1:]]
    for index,arg in enumerate(config):
        if arg.startswith('--extra-cflags='):config[index]='--extra-cflags=-target arm64-apple-macos26.0 -isysroot '+sdk
        if arg.startswith('--extra-ldflags='):config[index]='--extra-ldflags=-target arm64-apple-macos26.0 -isysroot '+sdk
    for expected in ('--disable-gpl','--disable-version3','--disable-nonfree','--disable-autodetect','--enable-static','--disable-shared'):
        assert expected in config
    (OUT/'configure-command.json').write_text(json.dumps(config,indent=2)+'\n')
    command(config,'configure',cwd=BUILD)
    config_h=(BUILD/'config.h').read_text()
    for symbol in ('CONFIG_GPL','CONFIG_GPLV3','CONFIG_VERSION3','CONFIG_NONFREE'):
        assert re.search(r'^#define '+symbol+r' 0$',config_h,re.M),symbol
    assert '#define FFMPEG_LICENSE "LGPL version 2.1 or later"' in config_h
    command(['make','-j4'],'ffmpeg-stock-build',timeout=600,cwd=BUILD)
    library_names=['libavformat','libavcodec','libswresample','libavutil']
    for name in library_names:shutil.copy2(BUILD/name/(name+'.a'),OUT/'stock'/(name+'.a'))
    for name in ('config.h','config_components.h','ffbuild/config.mak'):
        destination=OUT/'config'/name;destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(BUILD/name,destination)
    common=['clang++','-std=c++17','-O2','-pthread','-fno-lto','-target','arm64-apple-macos26.0','-isysroot',sdk,
        '-idirafter',str(SOURCE),'-I'+str(BUILD),'-I'+str(INPUT),'-Wno-deprecated-declarations']
    command(common+['-c',str(INPUT/'probe.cpp'),'-o',str(OBJECTS/'app.o')],'application-object')
    command(common+['-c',str(INPUT/'backend.mm'),'-o',str(OBJECTS/'miniaudio-backend.o')],'miniaudio-object')
    object_hashes={p.name:sha(p) for p in OBJECTS.iterdir() if p.is_file()}
    (OUT/'objects/frozen.json').write_text(json.dumps(object_hashes,indent=2)+'\n')
    def link(output,libraries):
        assert object_hashes=={name:sha(OBJECTS/name) for name in object_hashes}
        argv=['clang++','-target','arm64-apple-macos26.0','-isysroot',sdk,'-fno-lto',str(OBJECTS/'app.o'),str(OBJECTS/'miniaudio-backend.o'),*map(str,libraries),
            '-framework','CoreFoundation','-framework','CoreAudio','-framework','AudioToolbox','-o',str(output)]
        command(argv,output.parent.name+'-link')
        unsigned=sha(output)
        command(['codesign','--force','--sign','-','--options','runtime','--timestamp=none',str(output)],output.parent.name+'-sign')
        command(['codesign','--verify','--strict','--verbose=2',str(output)],output.parent.name+'-signature-check')
        detail=command(['codesign','--display','--verbose=4',str(output)],output.parent.name+'-signature-details')
        assert 'runtime' in detail and 'Signature=adhoc' in detail
        dependencies=command(['otool','-L',str(output)],output.parent.name+'-dependencies')
        assert not any(name in dependencies for name in ('libavcodec','libavformat','libavutil','libswresample','/opt/homebrew'))
        undefined=command(['nm','-u',str(output)],output.parent.name+'-undefined')
        assert not re.search(r'\b_dlopen\b|\b_dlsym\b',undefined)
        return {'command':argv,'unsigned_sha256':unsigned,'signed_sha256':sha(output)}
    stock_libraries=[OUT/'stock'/(name+'.a') for name in library_names]
    stock_hashes={p.name:sha(p) for p in stock_libraries}
    stock_link=link(OUT/'stock/audio-probe',stock_libraries)
    record('stock','pass',application_objects=object_hashes,libraries=stock_hashes)
    version=SOURCE/'libavutil/version.c';before=version.read_text()
    assert before.count('    return FFMPEG_VERSION;')==1
    after=before.replace('    return FFMPEG_VERSION;','    return FFMPEG_VERSION "+muses-p0-relink-1";')
    patch=''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='a/libavutil/version.c',tofile='b/libavutil/version.c'))
    (OUT/'replacement.patch').write_text(patch);version.write_text(after)
    command(['make','-j4','libavutil/libavutil.a'],'ffmpeg-replacement-build',timeout=180,cwd=BUILD)
    replacement_library=OUT/'replacement/libavutil.a';shutil.copy2(BUILD/'libavutil/libavutil.a',replacement_library)
    assert sha(replacement_library)!=stock_hashes['libavutil.a']
    members={}
    for label,path in [('stock',OUT/'stock/libavutil.a'),('replacement',replacement_library)]:
        content=subprocess.check_output(['ar','-p',str(path),'version.o']);members[label]=hashlib.sha256(content).hexdigest()
    assert members['stock']!=members['replacement']
    replacement_libraries=[*stock_libraries[:-1],replacement_library]
    replacement_link=link(OUT/'replacement/audio-probe',replacement_libraries)
    assert stock_link['signed_sha256']!=replacement_link['signed_sha256']
    tests={}
    for variant in ('stock','replacement'):
        output=command([str(OUT/variant/'audio-probe'),'tests',str(INPUT/'tone-a.m4a'),str(INPUT/'tone-b.webm')],variant+'-audio-regression',timeout=30)
        tests[variant]=fixture_output(output)
        dependency=tests[variant][0]
        assert dependency['ffmpeg']==('8.0' if variant=='stock' else '8.0+muses-p0-relink-1')
        assert dependency['license']=='LGPL version 2.1 or later' and dependency['runtime_linking'] is False
    # Producer scheduling can change a ring's observed high-water mark; it is
    # recorded but is not a decoded-output equivalence criterion.
    comparable=lambda rows:[{k:v for k,v in row.items() if k!='ring_high_frames'} for row in rows[1:]]
    assert comparable(tests['stock'])==comparable(tests['replacement']),'deterministic regression differs after marker replacement'
    output=command([str(OUT/'replacement/audio-probe'),'session',str(INPUT/'tone-a.m4a'),str(INPUT/'tone-b.webm')],'replacement-muted-native',timeout=15)
    tests['replacement_native']=fixture_output(output)
    assert tests['replacement_native'][-1]['muted'] is True and tests['replacement_native'][-1]['transitions']==1
    assert object_hashes=={name:sha(OBJECTS/name) for name in object_hashes}
    assert stock_hashes=={p.name:sha(p) for p in stock_libraries}
    assert before_sources=={path:sha(Path(path)) for path in before_sources}
    (OUT/'link-manifest.json').write_text(json.dumps({'objects':object_hashes,'stock':stock_link,'replacement':replacement_link,
        'stock_libraries':stock_hashes,'replacement_library_sha256':sha(replacement_library),'version_object_sha256':members},indent=2)+'\n')
    (OUT/'results.json').write_text(json.dumps(tests,indent=2)+'\n')
    command(['nm','-g',str(OBJECTS/'app.o')],'application-object-symbols')
    retained=[p for p in OUT.rglob('*') if p.is_file() and 'work' not in p.relative_to(OUT).parts]
    inventory={str(p.relative_to(OUT)):{'sha256':sha(p),'logical_bytes':p.stat().st_size,'allocated_bytes':p.stat().st_blocks*512} for p in retained}
    (OUT/'success.json').write_text(json.dumps({'kind':'macos_static_lgpl_relink_technical_proof','plan_sha256':args.plan_sha,'script_sha256':args.script_sha,
        'commands':entries,'retained_files':inventory,'scratch_high_allocated_bytes':high,'remaining_free_bytes':shutil.disk_usage(ROOT).free,
        'working_tree_cleanup':{'path':str(OUT/'work'),'logical_bytes':sum(p.stat().st_size for p in (OUT/'work').rglob('*') if p.is_file()),'allocated_bytes':allocated(OUT/'work'),'status':'completed; eligible for recoverable cleanup after inventory/open-file check'},
        'human_audibility':False,'phone':False,'external_network':False,'production_distribution_compliance':'not_determined'},indent=2)+'\n')
    record('complete','pass',directory=str(OUT),replacement_library_sha256=sha(replacement_library),success_sha256=sha(OUT/'success.json'))
except BaseException as error:
    (OUT/'failure.json').write_text(json.dumps({'error_type':type(error).__name__,'detail':str(error),'commands':entries,'plan_sha256':args.plan_sha,'script_sha256':args.script_sha},indent=2)+'\n')
    record('attempt','failed',error_type=type(error).__name__,detail=str(error));raise
