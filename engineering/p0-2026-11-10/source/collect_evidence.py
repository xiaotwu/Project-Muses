#!/usr/bin/env python3
"""Copy only bounded sanitized evidence and dependency locks into source control."""
from pathlib import Path
import datetime, hashlib, json, shutil, subprocess
s=Path('/Users/xiaotwu/.muses/tmp/p0-20261110-01/source')
root=Path(__file__).resolve().parent
for n in ('package.json','package-lock.json'):
    shutil.copyfile(s/'deps'/n,root/n)
out=root/'evidence';out.mkdir(exist_ok=True)
for f in sorted((s/'results').glob('*.json')):
    b=f.read_bytes()
    if len(b)>65536 or b'googlevideo.com' in b or b'visitorData' in b:raise SystemExit('unsafe or oversized receipt refused')
    shutil.copyfile(f,out/f.name)
files=[]
for f in sorted(root.rglob('*')):
    if f.is_file() and f.name!='manifest.json':files.append({'path':str(f.relative_to(root)),'bytes':f.stat().st_size,'sha256':hashlib.sha256(f.read_bytes()).hexdigest()})
allocated=sum(f.lstat().st_blocks*512 for f in s.rglob('*'))+s.lstat().st_blocks*512
logical=sum(f.lstat().st_size for f in s.rglob('*') if f.is_file())
artifacts=[]
for p in ('iphoneos/MusesP0Source.app/MusesP0Source','iphoneos/MusesP0Source.app/probe.bundle.js','iphoneos/MusesP0Source.app/Info.plist','iphoneos/MusesP0Source.app/calibration-first.m4a','iphoneos/MusesP0Source.app/calibration-next.m4a','build/probe.bundle.js','build/source-proof','build/source-proof-jsc','youtubekit-build/out/Products/Debug/Probe'):
    f=s/p
    if f.exists():artifacts.append({'path':str(f),'bytes':f.stat().st_size,'sha256':hashlib.sha256(f.read_bytes()).hexdigest()})
lock=json.loads((s/'deps/package-lock.json').read_text())
dependencies=[{'name':k.removeprefix('node_modules/'),'version':v.get('version'),'license':v.get('license'),'integrity':v.get('integrity')} for k,v in lock['packages'].items() if k and (s/'deps'/k).exists()]
manifest={'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source_files':files,'dependencies':dependencies,'quickjs':{'version':'2026-06-04','license':'MIT','archive_sha256':'b376e839b322978313d929fd20663b11ba58b75df5a46c126dd19ea2fa70ad2a'},'youtubekit':{'commit':'7f75a2299dc329c0b7855afb25d47663a02855cb','license':'MIT','helper_license':'Unlicense','archive_sha256':'8272e8acb6f8db7b01f1e3fbb4e0bbee11af0200aa0768091407282a6644e92a','runtime_result':'256MiB aborted; explicit512MiB diagnostic returned streams then exceeded RSS ceiling before complete chunk; no continuity verdict','production_budget_changed':False},'scratch':{'root':str(s),'allocated_bytes':allocated,'logical_file_bytes':logical,'free_bytes':shutil.disk_usage(s).free,'allocation_limit_bytes':1073741824,'cleanup_performed':False},'artifacts':artifacts}
(root/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({'source_files':len(files),'receipts':len(list(out.glob('*.json'))),'scratch_allocated_bytes':allocated,'scratch_logical_bytes':logical,'retained_artifacts':artifacts},indent=2))
