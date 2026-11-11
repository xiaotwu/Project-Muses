#!/usr/bin/env python3
"""Copy only selected verified inputs out of recoverable Trash, never execute there."""
from pathlib import Path
import hashlib
import json
import shutil
import re

HERE=Path(__file__).resolve().parent
P0=HERE.parents[1]
ROOT=Path('/Users/xiaotwu/.muses/tmp/p0-20261110-01/source/v2-transport')
TRASH=Path('/Users/xiaotwu/.Trash/Muses-P0-20261110-01')
dest=ROOT/'decoder-inputs';dest.mkdir(exist_ok=False)
assert shutil.disk_usage(ROOT).free > 40*1024**3
manifest=json.loads((P0/'audio/evidence/artifact-manifest.json').read_text())
fixtures=json.loads((P0/'audio/evidence/fixture-manifest.json').read_text())
entries=[]
def copy(source,target,expected=None):
    data=source.read_bytes();digest=hashlib.sha256(data).hexdigest()
    if expected:assert digest==expected
    target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    entries.append({'source':str(source),'destination':str(target.relative_to(dest)),'sha256':digest,'bytes':len(data),'previous_manifest_verified':expected is not None})
for name in ['libavformat','libavcodec','libavutil','libswresample']:
    artifact=f'macosx/{name}/{name}.a'
    copy(TRASH/'audio--macosx'/name/f'{name}.a',dest/'lib'/f'{name}.a',manifest[artifact]['sha256'])
    makefile=(TRASH/'audio--sources/ffmpeg-8.0'/name/'Makefile').read_text().replace('\\\n',' ')
    public=re.search(r'^HEADERS\s*=\s*(.*)$',makefile,re.M).group(1).split()
    for header in [TRASH/'audio--sources/ffmpeg-8.0'/name/h for h in public if h.endswith('.h')]:
        copy(header,dest/'include'/name/header.name)
copy(TRASH/'audio--macosx/libavutil/avconfig.h',dest/'include/libavutil/avconfig.h')
for name,item in fixtures.items():copy(TRASH/'audio--fixtures'/name,dest/'fixtures'/name,item['sha256'])
assert sum(x['bytes'] for x in entries)<8*1024**2
(dest/'provenance.json').write_text(json.dumps({'original_source_lock':json.loads((P0/'audio/source-lock.json').read_text()),'copied':entries},indent=2)+'\n')
print(json.dumps({'copied_files':len(entries),'logical_bytes':sum(x['bytes'] for x in entries)}))
