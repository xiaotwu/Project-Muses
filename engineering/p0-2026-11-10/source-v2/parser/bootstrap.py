#!/usr/bin/env python3
"""Acquire pinned public parser sources and one bounded public player fixture."""
from pathlib import Path
import hashlib, io, json, re, shutil, tarfile, urllib.request

SCRATCH=Path('/Users/xiaotwu/.muses/tmp/p0-20261110-01/source/v2-parser')
def budget():
    allocated=sum(p.lstat().st_blocks*512 for p in SCRATCH.rglob('*')) if SCRATCH.exists() else 0
    assert allocated < 400*1024*1024
    assert shutil.disk_usage(SCRATCH.parent).free >= 40*1024**3
def fetch(url, limit):
    with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'Muses-P0-parser-proof'}),timeout=20) as r:
        assert r.status==200
        data=r.read(limit+1)
    assert len(data)<=limit
    return data
budget();SCRATCH.mkdir(parents=True,exist_ok=True)
for name in ('tmp','build','fixtures','results'): (SCRATCH/name).mkdir(exist_ok=True)
provenance={'dependencies':[]}
for repo,tag,subdirs,expected in [('tree-sitter','v0.25.10',('lib/','LICENSE'),'ad5040537537012b16ef6e1210a572b927c7cdc2b99d1ee88d44a7dcdc3ff44c'),('tree-sitter-javascript','v0.25.0',('src/','LICENSE'),'9712fc283d3dc01d996d20b6392143445d05867a7aad76fdd723824468428b86')]:
    dest=SCRATCH/repo
    if dest.exists(): raise SystemExit('refuse overwriting pinned parser source')
    blob=fetch(f'https://codeload.github.com/tree-sitter/{repo}/tar.gz/refs/tags/{tag}',20*1024*1024)
    assert hashlib.sha256(blob).hexdigest()==expected,'pinned archive digest mismatch'
    with tarfile.open(fileobj=io.BytesIO(blob),mode='r:gz') as archive:
        entries=archive.getmembers();prefix=entries[0].name.split('/')[0]+'/'
        for entry in entries:
            relative=entry.name.removeprefix(prefix)
            if not any(relative.startswith(s) for s in subdirs):continue
            assert '..' not in Path(relative).parts and not Path(relative).is_absolute()
            if not entry.isfile():continue
            target=dest/relative;target.parent.mkdir(parents=True,exist_ok=True)
            assert entry.size <= 12*1024*1024
            target.write_bytes(archive.extractfile(entry).read())
    provenance['dependencies'].append({'repository':f'https://github.com/tree-sitter/{repo}','tag':tag,'license':'MIT','archive_sha256':hashlib.sha256(blob).hexdigest(),'archive_bytes':len(blob)})
    budget()
iframe=fetch('https://www.youtube.com/iframe_api',1024*1024).decode()
match=re.search(r'player\\/([a-zA-Z0-9_-]+)\\/',iframe)
assert match,'public player identifier missing'
player=fetch(f'https://www.youtube.com/s/player/{match[1]}/player_es6.vflset/en_US/base.js',4*1024*1024)
(SCRATCH/'fixtures/player.js').write_bytes(player)
provenance['public_player']={'sha256':hashlib.sha256(player).hexdigest(),'bytes':len(player),'player_id':match[1],'source':'YouTube public iframe_api -> player_es6 base.js','cookies':False,'cache':False}
(SCRATCH/'results/bootstrap.json').write_text(json.dumps(provenance,indent=2)+'\n')
print(json.dumps(provenance,indent=2));budget()
