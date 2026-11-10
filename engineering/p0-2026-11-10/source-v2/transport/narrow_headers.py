#!/usr/bin/env python3
"""One recoverable correction of the failed broad header copy; no disposal."""
from pathlib import Path
import hashlib,json,re,subprocess,sys
HERE=Path(__file__).resolve().parent
ROOT=Path('/Users/xiaotwu/.muses/tmp/p0-20261110-01/source/v2-transport')
DEST=ROOT/'decoder-inputs'
TRASH=Path('/Users/xiaotwu/.Trash/Muses-P0-20261110-01')
PLAN=ROOT/'narrow-headers-plan.json'
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
if sys.argv[1]=='prepare':
    public=set()
    for name in ['libavformat','libavcodec','libavutil','libswresample']:
        text=(TRASH/'audio--sources/ffmpeg-8.0'/name/'Makefile').read_text().replace('\\\n',' ')
        public.update('include/'+name+'/'+x for x in re.search(r'^HEADERS\s*=\s*(.*)$',text,re.M).group(1).split() if x.endswith('.h'))
    public.add('include/libavutil/avconfig.h')
    moves=[{'source':str(p),'target':str(ROOT/'Trash/unused-private-headers'/p.relative_to(DEST)), 'sha256':digest(p)}
           for p in sorted((DEST/'include').rglob('*.h')) if str(p.relative_to(DEST)) not in public]
    PLAN.write_text(json.dumps({'scope':str(DEST),'moves':moves,'script_sha256':digest(Path(__file__))},indent=2)+'\n')
    print(json.dumps({'plan_sha256':digest(PLAN),'script_sha256':digest(Path(__file__)),'move_count':len(moves)}))
else:
    assert digest(PLAN)==sys.argv[2] and digest(Path(__file__))==sys.argv[3]
    plan=json.loads(PLAN.read_text());assert plan['script_sha256']==sys.argv[3]
    opened=subprocess.run(['lsof','+D',str(DEST)],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    assert not opened.stdout,'active input files'
    journal=ROOT/'narrow-headers-journal.jsonl'
    assert not journal.exists(),'do not replay completed mutations'
    for item in plan['moves']:
        source,target=Path(item['source']),Path(item['target'])
        assert source.is_relative_to(DEST/'include') and target.is_relative_to(ROOT/'Trash')
        assert digest(source)==item['sha256'] and not target.exists()
    with journal.open('x') as log:
        for item in plan['moves']:
            source,target=Path(item['source']),Path(item['target']);target.parent.mkdir(parents=True,exist_ok=True)
            source.rename(target);log.write(json.dumps({'status':'moved',**item})+'\n');log.flush()
    entries=[]
    for p in sorted(DEST.rglob('*')):
        if not p.is_file():continue
        relative=p.relative_to(DEST)
        if relative.parts[0]=='lib':original=TRASH/'audio--macosx'/p.stem/p.name
        elif relative.parts[0]=='fixtures':original=TRASH/'audio--fixtures'/p.name
        elif p.name=='avconfig.h':original=TRASH/'audio--macosx/libavutil/avconfig.h'
        else:original=TRASH/'audio--sources/ffmpeg-8.0'/Path(*relative.parts[1:])
        assert digest(p)==digest(original)
        entries.append({'source':str(original),'destination':str(relative),'sha256':digest(p),'bytes':p.stat().st_size})
    (DEST/'provenance.json').write_text(json.dumps({'correction_plan_sha256':sys.argv[2],'copied':entries},indent=2)+'\n')
    print(json.dumps({'retained_input_bytes':sum(x['bytes'] for x in entries),'moved_private_headers':len(plan['moves'])}))
