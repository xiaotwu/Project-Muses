#!/usr/bin/env python3
"""Compile C ABI objects under the frozen source guard; never deploy devices."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess

HERE=Path(__file__).resolve().parent
ROOT=Path('/Users/xiaotwu/.muses/tmp/p0-20261110-01/source/v2-transport')
ROOT.mkdir(exist_ok=True)
assert sum(p.lstat().st_blocks*512 for p in ROOT.rglob('*')) < 184*1024**2
assert shutil.disk_usage(ROOT).free > 40*1024**3
manifest={}
for sdk,triple in [('macosx','arm64-apple-macos26.0'),('iphoneos','arm64-apple-ios17.0')]:
    path=ROOT/sdk;path.mkdir(exist_ok=True)
    sdkpath=subprocess.check_output(['xcrun','--sdk',sdk,'--show-sdk-path'],text=True).strip()
    argv=['clang','-fobjc-arc','-O2','-Wno-deprecated-declarations','-target',triple,'-isysroot',sdkpath,'-c',str(HERE/'NativeTransport.m'),'-o',str(path/'NativeTransport.o')]
    with (path/'build.log').open('a') as log:
        log.write(json.dumps(argv)+'\n');log.flush()
        subprocess.run(argv,stdout=log,stderr=subprocess.STDOUT,check=True)
    manifest[sdk]={'sha256':hashlib.sha256((path/'NativeTransport.o').read_bytes()).hexdigest(),'bytes':(path/'NativeTransport.o').stat().st_size,'argv':argv}
(ROOT/'objects-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({k:{'sha256':v['sha256'],'bytes':v['bytes']} for k,v in manifest.items()}))
