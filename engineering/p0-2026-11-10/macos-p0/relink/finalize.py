#!/usr/bin/env python3
"""Bounded receipts and exact cleanup inventory; does not delete or move files."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

HERE=Path(__file__).resolve().parent
ROOT=Path('/Users/xiaotwu/.muses/tmp/p0-20261110-01')
ATTEMPT=ROOT/'audio/macos-relink/attempt-20261110-232515'
OUT=HERE/'evidence'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(HERE/'plan.json')=='ca860bbbe87b0af4cb9574d844fbefcd47d02585870881fc593c0a3d3e196423'
assert sha(HERE/'run.py')=='0d835613db8ee10324bee6d9bc8c29ddb97e07ed7af7f40fa86bd564f916dc0c'
success=json.loads((ATTEMPT/'success.json').read_text())
assert sha(ATTEMPT/'success.json')=='b9031a2d1f319b811120948d0d9be70cdea6b9dd9e0711f5994ea36b4c66df90'
for name,record in success['retained_files'].items():
    if name=='journal.jsonl':
        # The final record seals success.json, whose snapshot covers the journal prefix.
        lines=(ATTEMPT/name).read_bytes().splitlines(keepends=True)
        assert hashlib.sha256(b''.join(lines[:-1])).hexdigest()==record['sha256']
        assert json.loads(lines[-1])['success_sha256']==sha(ATTEMPT/'success.json')
    else:assert sha(ATTEMPT/name)==record['sha256'],name
assert not OUT.exists(),'do not rewrite frozen evidence'
OUT.mkdir()
selected=['success.json','execution-lock.json','copy-provenance.json','toolchain.json','configure-command.json',
          'link-manifest.json','results.json','replacement.patch','journal.jsonl','objects/frozen.json']
selected += [str(p.relative_to(ATTEMPT)) for folder in ('logs','config','notices') for p in (ATTEMPT/folder).rglob('*') if p.is_file()]
for name in selected:
    source=ATTEMPT/name;assert source.stat().st_size<512*1024
    destination=OUT/name;destination.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,destination)
receipt=ROOT/'coordination/receipts/0aa1d4acfc714288ba1250cb1e043da0.json'
guard=json.loads(receipt.read_text());assert guard['returncode']==0 and guard['stop_reason'] is None
shutil.copy2(receipt,OUT/'guard-receipt.json')
opened=subprocess.run(['lsof','+D',str(ATTEMPT/'work')],capture_output=True,text=True)
assert opened.returncode==1 and not opened.stdout,'keep active work'
files=sorted(p for p in (ATTEMPT/'work').rglob('*') if p.is_file())
tree=[{'path':str(p.relative_to(ATTEMPT/'work')),'bytes':p.stat().st_size,'allocated':p.stat().st_blocks*512,'sha256':sha(p)} for p in files]
digest=hashlib.sha256(json.dumps(tree,sort_keys=True,separators=(',',':')).encode()).hexdigest()
cleanup={'owner':'p0_audio','exact_path':str(ATTEMPT/'work'),'status':'completed and eligible for coordinator recoverable cleanup',
         'file_count':len(files),'logical_bytes':sum(x['bytes'] for x in tree),'allocated_bytes':sum(x['allocated'] for x in tree),
         'sorted_file_inventory_sha256':digest,'inventory_format':'JSON list sorted by relative POSIX path; fields path,bytes,allocated,sha256; sorted object keys and separators comma/colon',
         'open_files_observed':0,'preserve':[str(ATTEMPT/p) for p in ('inputs','objects','stock','replacement','notices','config','logs')],
         'cleanup_executed':False,'physical_bytes_recovered':0,'actual_free_bytes':shutil.disk_usage(ROOT).free}
(OUT/'cleanup-plan.json').write_text(json.dumps(cleanup,indent=2)+'\n')
kit=[p for p in ATTEMPT.rglob('*') if p.is_file() and 'work' not in p.relative_to(ATTEMPT).parts]
package={'root':str(ATTEMPT),'files':{str(p.relative_to(ATTEMPT)):{'sha256':sha(p),'logical_bytes':p.stat().st_size,'allocated_bytes':p.stat().st_blocks*512} for p in kit},
         'logical_bytes':sum(p.stat().st_size for p in kit),'allocated_bytes':sum(p.stat().st_blocks*512 for p in kit),
         'sdk_included':False,'production_distribution_compliance':'not_determined'}
(OUT/'package-index.json').write_text(json.dumps(package,indent=2)+'\n')
manifest={'source_sha256':{p.name:sha(p) for p in HERE.iterdir() if p.is_file()},
          'evidence':{str(p.relative_to(OUT)):{'sha256':sha(p),'bytes':p.stat().st_size} for p in OUT.rglob('*') if p.is_file()},
          'results':'pass; source-built component replaced, frozen application objects unchanged, signed regressions passed',
          'failed_attempts':0,'phone':False,'human_audibility_tested':False,'external_network':False}
(OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({'manifest_sha256':sha(OUT/'manifest.json'),'evidence_bytes':sum(p.stat().st_size for p in OUT.rglob('*') if p.is_file()),
                  'retained_kit_allocated_bytes':package['allocated_bytes'],'cleanup_allocated_bytes':cleanup['allocated_bytes']}))
