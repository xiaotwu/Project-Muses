#!/usr/bin/env python3
"""Offline controller policy tests and device-SDK syntax check; never deploys."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

HERE=Path(__file__).resolve().parent
ROOT=Path('/Users/xiaotwu/.muses/tmp/p0-20261110-01')
OWNED=ROOT/'source/v2-transport'
OUT=OWNED/('ios-controller-'+time.strftime('%Y%m%d-%H%M%S',time.gmtime()))
assert hashlib.sha256((ROOT/'budget.json').read_bytes()).hexdigest()=='7b27e21065887ba0a9072552afa31f64c307f1df6ff8eb4c3ebac25799fe3cbc'
assert shutil.disk_usage(ROOT).free>40*1024**3
assert sum(p.stat().st_blocks*512 for p in OWNED.rglob('*') if p.is_file())<160*1024**2
OUT.mkdir(parents=True)
env=dict(os.environ,TMPDIR=str(OUT),CLANG_MODULE_CACHE_PATH=str(OUT/'module-cache'))
files=[HERE/'iOSMain.m',HERE/'RunPolicy.h',HERE/'PolicyTests.c',HERE/'verify.py']
before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
commands=[]
def run(command,name):
    commands.append(command)
    result=subprocess.run(command,env=env,capture_output=True,timeout=45)
    (OUT/name).write_bytes(result.stdout+result.stderr)
    if result.returncode:
        print((result.stdout+result.stderr).decode(errors='replace')[:6000]);raise SystemExit(result.returncode)
    return result
sdk=subprocess.check_output(['xcrun','--sdk','iphoneos','--show-sdk-path'],text=True).strip()
run(['xcrun','--sdk','iphoneos','clang','-target','arm64-apple-ios17.0','-isysroot',sdk,'-fobjc-arc','-fsyntax-only','-Werror','-Wno-deprecated-declarations','-Wno-incompatible-pointer-types',str(HERE/'iOSMain.m')],'ios-syntax.log')
for mode,flags in [('normal',[]),('tsan',['-fsanitize=thread','-g'])]:
    binary=OUT/('policy-'+mode)
    run(['clang','-std=c11','-O1','-pthread','-Wall','-Wextra','-Werror',*flags,str(HERE/'PolicyTests.c'),'-o',str(binary)],mode+'-build.log')
    result=run([str(binary)],mode+'-run.log')
    print(result.stdout.decode().strip(),mode)
assert before=={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
receipt={'source_sha256':before,'commands':commands,'network':False,'phone':False,'audio':False,
         'files':{p.name:{'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size} for p in OUT.iterdir() if p.is_file()}}
(OUT/'manifest.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(OUT)
