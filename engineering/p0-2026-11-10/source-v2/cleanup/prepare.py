#!/usr/bin/env python3
"""Read-only inventory + plan generation. Does not execute any cleanup."""
from pathlib import Path
import concurrent.futures,datetime,hashlib,json,os,runpy,shutil

HERE=Path(__file__).resolve().parent
ENGINEERING=HERE.parents[1]
ROOT=Path('/Users/xiaotwu/.muses/tmp/p0-20261110-01')
SOURCE=ROOT/'source'
maintenance=HERE/'retire_stage3.py'
api=runpy.run_path(str(maintenance));scan,handles,processes,digest=(api[k] for k in ['scan','handles','processes','digest'])
assert digest(ENGINEERING/'retire_scratch.py')=='2b8f6f7a675908bbd7e002199fcb8cefb69acfe6446289fc52c85fba87bb8bd8'
references=[HERE.parent/'runtime/manifest.json',HERE.parent/'control/manifest.json',HERE.parent/'ios/evidence/manifest.json',HERE.parent/'transport/evidence/manifest.json',HERE.parent/'transport/evidence/long/manifest.json']
spec=[('v2-integration/runtime','p0_interop','completed offline QuickJS-NG candidate comparison',references[0]),
      ('v2-integration/control','p0_interop','completed control/module/generated-host offline checks',references[1])]
ios=json.loads(references[2].read_text())
for item in ios['scratch_cleanup_inventory']:
    path=Path(item['path']);assert path.parent==SOURCE/'v2-transport'
    for relative,sha in item['files'].items():assert digest(path/relative)==sha,'iOS helper differs from frozen owner manifest'
    spec.append((str(path.relative_to(SOURCE)),item['owner'],'completed iOS syntax/policy or real-file muted ABI helper',references[2]))
tests=['20261110-134551','20261110-135102','20261110-135409','avio-20261110-135540','decoder-probe-20261110-140339','decoder-probe-20261110-140447','long-20261110-141148']
spec += [('v2-transport/'+name,'p0_audio','completed local transport/decoder tests; small failed/successful receipts retained',references[4] if name.startswith('long-') else references[3]) for name in tests]
spec += [('v2-transport/Trash/unused-private-headers','p0_audio','previously retired unused dependency headers; keep existing recovery plan/journal unchanged',references[3])]
assert len(spec)==14
retained=HERE/'retained-test-evidence';retained.mkdir(exist_ok=True)
retained_files=[]
for name in tests:
    folder=SOURCE/'v2-transport'/name;target=retained/name;target.mkdir(exist_ok=True)
    for file in sorted(folder.iterdir()):
        if file.is_file() and file.suffix in ['.json','.jsonl','.log','.txt']:
            assert file.stat().st_size<=1024*1024,'unexpected unbounded evidence'
            out=target/file.name
            if out.exists():assert out.read_bytes()==file.read_bytes()
            else:out.write_bytes(file.read_bytes())
            retained_files.append({'path':str(out),'sha256':digest(out),'bytes':out.stat().st_size,'origin':str(file)})
rows=[];moves=[];all_inodes={};logical_total=allocated_total=0
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    results=list(pool.map(lambda x:handles(SOURCE/x[0]),spec))
for (relative,owner,reason,reference),open_files in zip(spec,results):
    path=SOURCE/relative;summary,entries=scan(path)
    assert not any(Path(e['relative']).suffix.lower() in ['.m4a','.webm','.wav','.mp3','.aac','.opus','.mp4'] for e in entries),'unexpected media in exact candidate'
    logical_total+=summary['logical_file_bytes'];allocated_total+=summary['allocated_bytes']
    for e in entries:all_inodes[(e['device'],e['inode'])]=e['allocated_bytes']
    rows.append({'path':str(path),'owner':owner,'uid':os.getuid(),'reason':reason,'retained_manifest':str(reference),'retained_manifest_sha256':digest(reference),'inventory':summary,'lsof':open_files,'files':entries})
    moves.append({'source':str(path),'destination_name':relative.replace('/','--'),'owner':owner,'uid':os.getuid(),'reason':reason,'evidence_manifest':str(reference),'evidence_manifest_sha256':digest(reference),'required_inventory':summary})
active=processes([Path(x['source']) for x in moves]);assert not active,'candidate process active'
trash=Path('/Users/xiaotwu/.Trash/Muses-P0-20261110-01/stage3')
assert not trash.exists(),'Stage3 destination already exists; do not overwrite another maintenance attempt'
inventory={'created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'owner_uid':os.getuid(),'paths':rows,'retained_small_evidence':retained_files,'logical_file_bytes':logical_total,'allocated_path_sum_bytes':allocated_total,'allocated_unique_inode_bytes':sum(all_inodes.values()),'hardlink_allocation_difference_bytes':allocated_total-sum(all_inodes.values()),'actual_free_bytes':shutil.disk_usage(ROOT).free,'active_processes':active,'no_mutation_of_candidates':True}
inventory_path=HERE/'stage3-inventory.json';inventory_path.write_text(json.dumps(inventory,indent=2)+'\n')
plan={'stage':'completed-source-v2-runtime-control-and-transport-helpers','created_utc':inventory['created_utc'],'owned_root':str(ROOT),'trash_root':str(trash),'source_inventory_sha256':digest(inventory_path),'script_sha256':digest(maintenance),'parent_retire_script_sha256':digest(ENGINEERING/'retire_scratch.py'),'moves':moves,'required_manifests':[{'path':str(p),'sha256':digest(p)} for p in references]+[{'path':str(inventory_path),'sha256':digest(inventory_path)}]+[{'path':x['path'],'sha256':x['sha256']} for x in retained_files],'preflight':{'uid':os.getuid(),'active_probe_processes':active,'lsof_all_paths_zero':True,'actual_free_bytes':inventory['actual_free_bytes'],'logical_file_bytes':logical_total,'allocated_path_sum_bytes':allocated_total,'allocated_unique_inode_bytes':sum(all_inodes.values())},'retain':['source/v2-parser (further source validation)','source/v2-transport/decoder-inputs (desktop decode dependencies)','source/v2-transport/macosx and iphoneos dependency objects','source/v2-transport/long-fixtures (outside this exact stage3 move set)','source/v2-integration/build and iphoneos (current candidate)','all v2-integration/media live source files and other media directories','original source/audio unfinished phone artifacts','all prior cleanup plans/journals, recovery journal, and bounded evidence'],'deletion':'recoverable same-volume rename only; no purge; not executed by preparation','stage3_has_been_executed':False}
plan_path=HERE/'cleanup-stage3-plan.json';plan_path.write_text(json.dumps(plan,indent=2)+'\n')
hashes={'plan_sha256':digest(plan_path),'script_sha256':digest(maintenance),'inventory_sha256':digest(inventory_path),'preparation_script_sha256':digest(Path(__file__)),'parent_retire_script_sha256':digest(ENGINEERING/'retire_scratch.py')}
(HERE/'frozen-hashes.json').write_text(json.dumps(hashes,indent=2)+'\n')
print(json.dumps({'frozen':hashes,'paths':len(moves),'logical_file_bytes':logical_total,'allocated_unique_inode_bytes':sum(all_inodes.values()),'active_processes':active,'trash_created':False,'cleanup_executed':False},indent=2))
