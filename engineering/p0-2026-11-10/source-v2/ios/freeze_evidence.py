#!/usr/bin/env python3
"""Freeze bounded offline evidence, without modifying or disposing source media."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

HERE=Path(__file__).resolve().parent
ROOT=Path('/Users/xiaotwu/.muses/tmp/p0-20261110-01')
SCRATCH=ROOT/'source/v2-transport'
OUT=HERE/'evidence'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
assert sha(ROOT/'budget.json')=='7b27e21065887ba0a9072552afa31f64c307f1df6ff8eb4c3ebac25799fe3cbc'
assert not OUT.exists(),'preserve the frozen evidence; do not overwrite it'
OUT.mkdir()
groups={
 'policy-initial':'ios-controller-20261110-223013',
 'policy-ownership':'ios-controller-20261110-223259',
 'policy-final':'ios-controller-20261110-223423',
 'real-audio-abi':'real-audio-abi-20261110-223118',
}
inventory=[]
for label,name in groups.items():
 source=SCRATCH/name;destination=OUT/label;destination.mkdir()
 for file in source.iterdir():
  if file.is_file() and file.suffix in ('.json','.jsonl','.log'):
   assert file.stat().st_size<128*1024
   shutil.copy2(file,destination/file.name)
 opened=subprocess.run(['lsof','+D',str(source)],capture_output=True,text=True)
 assert opened.returncode==1 and not opened.stdout, 'retain active test scratch'
 files=[p for p in source.rglob('*') if p.is_file()]
 inventory.append({'path':str(source),'owner':'p0_audio','status':'completed helper scratch; eligible for coordinator recoverable cleanup after evidence collection',
                   'logical_bytes':sum(p.stat().st_size for p in files),'allocated_bytes':sum(p.stat().st_blocks*512 for p in files),
                   'open_files_observed':0,'files':{str(p.relative_to(source)):sha(p) for p in files}})
receipts=['6f173257f94d43919e0efd10ae222359','97a4c89d16e04b0185dcc574faaca7f3','3bfcb1a513cb4fadac91a7c028c1602b','2e4a34d791184672b76e0104ca39cd0c']
(OUT/'guard-receipts').mkdir()
for receipt in receipts:shutil.copy2(ROOT/'coordination/receipts'/(receipt+'.json'),OUT/'guard-receipts'/(receipt+'.json'))
final=json.loads((OUT/'policy-final/manifest.json').read_text())
assert final['source_sha256'][str(HERE/'iOSMain.m')]==sha(HERE/'iOSMain.m')
sources=[p for p in HERE.iterdir() if p.is_file()]+[HERE.parent/'ios-review.md']
evidence=[p for p in OUT.rglob('*') if p.is_file()]
manifest={'source_sha256':{str(p.relative_to(HERE.parent)):sha(p) for p in sources},
          'evidence':{str(p.relative_to(OUT)):{'sha256':sha(p),'bytes':p.stat().st_size} for p in evidence},
          'scratch_cleanup_inventory':inventory,'actual_free_bytes':shutil.disk_usage(ROOT).free,
          'physical_bytes_recovered':0,'cleanup_performed':False,'phone_operations':False,'external_network_requests':False,
          'source_media_modified':False,'human_audibility_tested':False,
          'scope':'iOS controller syntax/policy and muted macOS real-file audio ABI only; source-v2 phone gate not completed'}
(OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({'manifest_sha256':sha(OUT/'manifest.json'),'evidence_bytes':sum(p.stat().st_size for p in OUT.rglob('*') if p.is_file()),
                  'obsolete_scratch_logical_bytes':sum(x['logical_bytes'] for x in inventory),'obsolete_scratch_allocated_bytes':sum(x['allocated_bytes'] for x in inventory)}))
